import json

import pytest

from patchlab.decision import ChatDecider


def test_config_and_provider_request(tmp_path, monkeypatch):
    config = tmp_path / "model.toml"
    config.write_text('[model]\nurl="https://example.test/v1/chat/completions"\n'
                      'name="model-one"\napi_key_env="TEST_MODEL_KEY"\n', encoding="utf-8")
    for name in ("PATCHLAB_API_URL", "PATCHLAB_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TEST_MODEL_KEY", "secret")
    client = ChatDecider(512, config)
    captured = {}

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            return json.dumps({"choices": [{"message": {"content": '{"kind":"files","prefix":""}'},
                                              "finish_reason": "stop"}],
                               "usage": {"total_tokens": 17}}).encode()

    class Opener:
        def open(self, request, timeout):
            captured["url"] = request.full_url
            captured["auth"] = request.get_header("Authorization")
            captured["payload"] = json.loads(request.data)
            return Response()

    client.opener = Opener()
    action, usage = client.decide({"issue": "example"})
    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["auth"] == "Bearer secret"
    assert captured["payload"]["model"] == "model-one"
    assert action["kind"] == "files" and usage["total_tokens"] == 17
    monkeypatch.setenv("PATCHLAB_MODEL", "model-two")
    assert ChatDecider(512, config).model == "model-two"


def test_missing_remote_key_is_reported(tmp_path, monkeypatch):
    config = tmp_path / "model.toml"
    config.write_text('[model]\nurl="https://example.test/completions"\nname="m"\n'
                      'api_key_env="MISSING_TEST_KEY"\n', encoding="utf-8")
    for name in ("PATCHLAB_API_URL", "PATCHLAB_MODEL", "MISSING_TEST_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="MISSING_TEST_KEY"):
        ChatDecider(100, config)
