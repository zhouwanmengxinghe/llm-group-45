import threading

from patchlab.web import Workspace


def test_chat_uses_session_context_and_records_answer(tmp_path, monkeypatch):
    received = []
    completed = threading.Event()

    class FakeModel:
        def __init__(self, *args): pass
        def chat(self, messages):
            received.extend(messages)
            return "Test response"

    monkeypatch.setattr("patchlab.web.ChatDecider", FakeModel)
    workspace = Workspace(None, tmp_path)
    original = workspace.emit

    def emit(sid, kind, **kwargs):
        original(sid, kind, **kwargs)
        if kwargs.get("content") == "Test response":
            completed.set()

    monkeypatch.setattr(workspace, "emit", emit)
    sid = "b" * 32
    workspace.emit(sid, "message", role="user", content="Earlier context")
    workspace.start(sid, {"kind": "chat", "message": "Continue"})
    assert completed.wait(3)
    assert [m["content"] for m in received[1:]] == ["Earlier context", "Continue"]
    assert workspace.records(sid)[-1]["content"] == "Test response"
