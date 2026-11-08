import threading

from patchlab.web import Workspace, compressed_context


def test_context_compression_keeps_recent_and_original_records(tmp_path):
    workspace = Workspace(None, tmp_path)
    sid = "a" * 32
    for i in range(12):
        workspace.emit(sid, "message", role="user" if i % 2 == 0 else "assistant", content=f"message {i}")
    records = workspace.records(sid)
    summary, recent = compressed_context(records)
    assert "message 0" in summary
    assert recent[-1]["content"] == "message 11"
    assert len(recent) == 6
    assert len(workspace.records(sid)) == 12


def test_chat_uses_session_context_and_records_answer(tmp_path, monkeypatch):
    received = []
    completed = threading.Event()

    class FakeModel:
        def __init__(self, *args): pass
        def chat(self, messages):
            received.extend(messages)
            return "测试回复"

    monkeypatch.setattr("patchlab.web.ChatDecider", FakeModel)
    workspace = Workspace(None, tmp_path)
    original = workspace.emit

    def emit(sid, kind, **kwargs):
        original(sid, kind, **kwargs)
        if kwargs.get("content") == "测试回复":
            completed.set()

    monkeypatch.setattr(workspace, "emit", emit)
    sid = "b" * 32
    workspace.emit(sid, "message", role="user", content="之前的上下文")
    workspace.start(sid, {"kind": "chat", "message": "继续"})
    assert completed.wait(3)
    assert [m["content"] for m in received[1:]] == ["之前的上下文", "继续"]
    assert workspace.records(sid)[-1]["content"] == "测试回复"
