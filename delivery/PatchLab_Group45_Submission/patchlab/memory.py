"""Compact older agent evidence while retaining recent observations verbatim."""
from __future__ import annotations

import json


def compact_evidence(model, summary: str, observations: list, feedback: list, record,
                     threshold: int = 12000):
    data = {"summary": summary, "observations": observations, "feedback": feedback}
    if len(json.dumps(data, ensure_ascii=False)) <= threshold:
        return summary, observations, feedback
    old_observations, recent_observations = observations[:-2], observations[-2:]
    old_feedback, recent_feedback = feedback[:-2], feedback[-2:]
    if not old_observations and not old_feedback:
        return summary, observations, feedback
    payload = json.dumps({"previous_summary": summary, "observations": old_observations,
                          "feedback": old_feedback}, ensure_ascii=False)
    try:
        new_summary = model.summarize(payload)
    except ValueError as exc:
        record("context_compaction_failed", scope="agent", reason=str(exc))
        fallback = "Exact excerpts from older evidence (truncated):\n" + payload[:6000]
        record("context_compaction_fallback", summary=fallback)
        return fallback, recent_observations, recent_feedback
    if not isinstance(new_summary, str) or not new_summary.strip() or len(new_summary) > 8000:
        record("context_compaction_failed", scope="agent", reason="invalid summary")
        fallback = "Exact excerpts from older evidence (truncated):\n" + payload[:6000]
        record("context_compaction_fallback", summary=fallback)
        return fallback, recent_observations, recent_feedback
    record("context_compacted", scope="agent", summary=new_summary,
           observations=len(old_observations), feedback=len(old_feedback))
    return new_summary, recent_observations, recent_feedback
