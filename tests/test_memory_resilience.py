import errno
import json
from urllib.error import HTTPError

import pytest

from patchlab.memory import compact_evidence
from patchlab.resilience import retry
from patchlab.web import Workspace


def test_retry_transient_with_exponential_delay_and_no_retry_for_client_error():
    calls, delays, events = [], [], []
    def operation():
        calls.append(1)
        if len(calls) < 3:
            raise HTTPError("https://example.test", 503, "unavailable", {}, None)
        return "ok"
    assert retry(operation, sleep=delays.append, jitter=lambda: 0, on_retry=events.append) == "ok"
    assert delays == [0.5, 1.0]
    assert len(events) == 2
    with pytest.raises(HTTPError):
        retry(lambda: (_ for _ in ()).throw(HTTPError("https://example.test", 401, "no", {}, None)),
              sleep=lambda _: pytest.fail("must not retry 401"))


def test_retry_transient_tool_error_and_limit():
    attempts = []
    def action():
        attempts.append(1)
        raise OSError(errno.EAGAIN, "temporarily unavailable")
    with pytest.raises(OSError):
        retry(action, sleep=lambda _: None, jitter=lambda: 0)
    assert len(attempts) == 3


def test_conversation_summary_checkpoint_and_originals_survive_restart(tmp_path):
    ws = Workspace(None, tmp_path)
    sid = "d" * 32
    for i in range(14):
        ws.emit(sid, "message", role="user" if i % 2 == 0 else "assistant", content=f"message {i}")
    class Model:
        model = "fake"
        def __init__(self): self.inputs = []
        def summarize(self, source):
            self.inputs.append(json.loads(source))
            return "摘要：用户的目标和已解决的问题"
    model = Model()
    summary, recent = ws.context(sid, model)
    assert summary.startswith("摘要") and len(recent) == 6
    assert [x["content"] for x in model.inputs[0]["messages"]] == [f"message {i}" for i in range(8)]
    assert len([x for x in ws.records(sid) if x["type"] == "message"]) == 14
    ws2 = Workspace(None, tmp_path)
    assert ws2.context(sid, model) == (summary, recent)
    assert len(model.inputs) == 1


def test_failed_summarization_keeps_original_context(tmp_path):
    ws = Workspace(None, tmp_path)
    sid = "e" * 32
    for i in range(13):
        ws.emit(sid, "message", role="user", content=f"message {i}")
    class Failing:
        def summarize(self, source): raise RuntimeError("unavailable")
    with pytest.raises(RuntimeError):
        ws.context(sid, Failing())
    assert len(ws.records(sid)) == 13
    assert not any(x["type"] == "context_summary" for x in ws.records(sid))


def test_agent_evidence_compaction_keeps_recent_and_records_summary():
    class Model:
        def summarize(self, source):
            parsed = json.loads(source)
            assert parsed["observations"][0]["response"] == "old"
            return "Checked the old file."
    records = []
    observations = [{"response": "old"}, {"response": "middle"}, {"response": "new"}]
    summary, remaining, feedback = compact_evidence(Model(), "", observations, [],
        lambda event, **details: records.append((event, details)), threshold=1)
    assert summary == "Checked the old file." and remaining == observations[-2:]
    assert records[0][0] == "context_compacted"
