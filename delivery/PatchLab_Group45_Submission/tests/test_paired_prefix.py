import pytest
from patchlab.paired import PairedDecider, PrefixCache, canonical
from patchlab.diagnostics import excerpt


class Model:
    model = "provider-model"
    completion_limit = 1200
    url = "https://example.test/completions"
    on_retry = None
    def __init__(self): self.requests = self.tokens = 0
    def usage_snapshot(self):
        return {"request_attempts": self.requests, "responses_with_usage": self.requests,
                "tokens_reported": self.tokens, "response_models": ["served-version"]}
    def decide(self, context):
        self.requests += 1
        self.tokens += 10
        return {"kind": "propose" if context["step"] >= 2 else "read"}, {"total_tokens": 10}
    def summarize(self, payload):
        self.requests += 1
        self.tokens += 20
        return "Observed behavior"


def test_common_prefix_saves_actual_requests_without_extra_logical_budget():
    cache = PrefixCache()
    first = PairedDecider(Model(), cache)
    second = PairedDecider(Model(), cache)
    for client, seconds in [(first, "1.23"), (second, "2.34")]:
        for step in [1, 2]:
            client.decide({"patch_attempts": 0, "step": step,
                           "initial_failure": f"1 passed in {seconds}s"})
    assert first.usage_snapshot()["request_attempts"] == 2
    assert second.usage_snapshot()["request_attempts"] == 0
    assert second.usage_snapshot()["logical_tokens_reported"] == 20
    assert second.usage_snapshot()["prefix_cached_decisions"] == 2
    assert second.usage_snapshot()["effective_response_models"] == ["served-version"]
    for _ in range(2):
        second.decide({"patch_attempts": 1, "step": 3})
    assert second.usage_snapshot()["request_attempts"] == 2
    assert second.usage_snapshot()["logical_tokens_reported"] == 40


def test_source_and_assertion_values_are_never_normalized():
    original = {"text": "1 passed in 1.23s", "reproducer": "assert seconds == 1.23",
                "evidence": "E assert 1.23 < 1"}
    assert canonical(original) == original


def test_duration_does_not_shift_truncated_evidence():
    first = "source line\n"*300 + "1 passed in 2.3s"
    second = "source line\n"*300 + "1 passed in 12.34s"
    assert excerpt(first) == excerpt(second)


@pytest.mark.parametrize("summary", [
    "8 passed, 1 skipped, 1 warnings in {} seconds",
    "==== 3 passed, 2 warnings in {}s ====",
    "Ran 12 tests in {}s",
])
def test_legacy_pytest_and_django_durations_share_prefix(summary):
    assert excerpt(summary.format("0.64")) == excerpt(summary.format("12.72"))


def test_assertion_duration_values_are_preserved():
    assert excerpt("E assert actual_seconds == 0.64") == "E assert actual_seconds == 0.64"


def test_summary_cache_and_failed_summary_usage_remain_accounted():
    cache = PrefixCache()
    first, second = PairedDecider(Model(), cache), PairedDecider(Model(), cache)
    assert first.summarize('{"output":"1 passed in 1.23s"}') == second.summarize('{"output":"1 passed in 2.34s"}')
    assert second.usage_snapshot()["request_attempts"] == 0
    assert second.usage_snapshot()["logical_tokens_reported"] == 20
    class Failed(Model):
        def summarize(self, payload):
            super().summarize(payload)
            raise ValueError("truncated")
    failed = PairedDecider(Failed(), PrefixCache())
    with pytest.raises(ValueError): failed.summarize("payload")
    assert failed.usage_snapshot()["logical_tokens_reported"] == 20
