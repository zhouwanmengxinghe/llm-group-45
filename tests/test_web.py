import threading

from patchlab.web import Workspace


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
