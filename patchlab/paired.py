"""Optional benchmark control: replay identical pre-patch model inputs.

All arms keep the same logical decision budget. Physical provider usage and
standalone-equivalent replay usage are reported separately. No test verdict is
cached, and feedback after the first source proposal is never replayed.
"""
from __future__ import annotations

import copy
from hashlib import sha256
import json
import re
from .diagnostics import stable_log


LOG_KEYS = {"initial_failure", "reproducer_baseline_failure", "output", "evidence", "failure"}


def canonical(value, key=""):
    if isinstance(value, dict):
        return {k: canonical(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [canonical(v, key) for v in value]
    if isinstance(value, str) and key in LOG_KEYS:
        return stable_log(value)
    return value


class PrefixCache:
    def __init__(self):
        self.entries = {}
        self.owner_claimed = False


class PairedDecider:
    def __init__(self, delegate, cache: PrefixCache):
        self.delegate = delegate
        self.cache = cache
        self.can_write_prefix = not cache.owner_claimed
        cache.owner_claimed = True
        self.model = delegate.model
        self.completion_limit = delegate.completion_limit
        self.closed = False
        self.logical_tokens = self.logical_requests = self.logical_responses = 0
        self.hits = self.decision_hits = 0
        self.effective_models = set()
        self.on_cache_hit = None

    @property
    def on_retry(self):
        return self.delegate.on_retry

    @on_retry.setter
    def on_retry(self, callback):
        self.delegate.on_retry = callback

    def usage_snapshot(self):
        return {**self.delegate.usage_snapshot(), "logical_tokens_reported": self.logical_tokens,
                "logical_request_attempts": self.logical_requests,
                "logical_responses_with_usage": self.logical_responses,
                "effective_response_models": sorted(self.effective_models),
                "prefix_cache_hits": self.hits, "prefix_cached_decisions": self.decision_hits}

    def _invoke(self, purpose, payload):
        identity = [self.model, self.completion_limit, getattr(self.delegate, "url", ""), purpose,
                    canonical(payload)]
        digest = sha256(json.dumps(identity, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
        if not self.closed and digest in self.cache.entries:
            value, delta = self.cache.entries[digest]
            value = copy.deepcopy(value)
            self.hits += 1
            self.decision_hits += purpose == "decision"
            if purpose == "decision" and isinstance(value[1], dict):
                value[1]["patchlab_replayed_prefix"] = True
            if self.on_cache_hit:
                self.on_cache_hit({"purpose": purpose, "context_sha256": digest})
        else:
            before = self.delegate.usage_snapshot()
            try:
                value = self.delegate.decide(payload) if purpose == "decision" else self.delegate.summarize(payload)
            except Exception:
                after = self.delegate.usage_snapshot()
                self.logical_tokens += after["tokens_reported"] - before["tokens_reported"]
                self.logical_requests += after["request_attempts"] - before["request_attempts"]
                self.logical_responses += after["responses_with_usage"] - before["responses_with_usage"]
                raise
            after = self.delegate.usage_snapshot()
            delta = {k: after[k] - before[k] for k in (
                "tokens_reported", "request_attempts", "responses_with_usage")}
            delta["response_models"] = after.get("response_models", [])
            if not self.closed and self.can_write_prefix:
                self.cache.entries[digest] = (copy.deepcopy(value), delta)
        self.logical_tokens += delta["tokens_reported"]
        self.logical_requests += delta["request_attempts"]
        self.logical_responses += delta["responses_with_usage"]
        self.effective_models.update(delta.get("response_models", []))
        return value

    def decide(self, context):
        if context.get("patch_attempts", 0):
            self.closed = True
        value = self._invoke("decision", context)
        if value[0].get("kind") == "propose":
            self.closed = True
        return value

    def summarize(self, text):
        # The compactor passes JSON. Preserve source strings and normalize only
        # explicitly named diagnostic fields, never program text or assertions.
        try:
            normalized = json.dumps(canonical(json.loads(text)), ensure_ascii=True, sort_keys=True)
        except ValueError:
            normalized = text
        return self._invoke("summary", normalized)
