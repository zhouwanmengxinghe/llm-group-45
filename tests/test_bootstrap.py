import os
from pathlib import Path

import bootstrap


def test_first_setup_and_saved_key(tmp_path, monkeypatch):
    config = tmp_path / "model.toml"
    secret = tmp_path / "key"
    monkeypatch.setattr(bootstrap, "CONFIG", config)
    monkeypatch.setattr(bootstrap, "SECRET", secret)
    monkeypatch.delenv("PATCHLAB_API_KEY", raising=False)
    answers = iter(["2", "https://example.test/v1/chat/completions", "test-model", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(bootstrap.getpass, "getpass", lambda _: "a-secret")
    monkeypatch.setattr(bootstrap, "protect", lambda key: "encrypted-value")
    bootstrap.configure()
    assert "test-model" in config.read_text(encoding="utf-8")
    assert "a-secret" not in config.read_text(encoding="utf-8")
    assert secret.read_text(encoding="utf-8") == "encrypted-value"
    assert os.environ["PATCHLAB_API_KEY"] == "a-secret"


def test_default_deepseek_needs_only_key(tmp_path, monkeypatch):
    config = tmp_path / "model.toml"
    monkeypatch.setattr(bootstrap, "CONFIG", config)
    monkeypatch.setattr(bootstrap, "SECRET", tmp_path / "key")
    monkeypatch.delenv("PATCHLAB_API_KEY", raising=False)
    answers = iter(["", "n"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(bootstrap.getpass, "getpass", lambda _: "test-key")
    bootstrap.configure()
    import tomllib
    settings = tomllib.loads(config.read_text(encoding="utf-8"))["model"]
    assert settings["url"] == "https://api.deepseek.com/chat/completions"
    assert settings["name"] == "deepseek-flash"
    assert settings["thinking"] == "disabled"
    assert os.environ["PATCHLAB_API_KEY"] == "test-key"


def test_existing_config_and_environment_are_preserved(tmp_path, monkeypatch):
    config = tmp_path / "model.toml"
    content = '[model]\nurl="https://example.test/chat"\nname="custom"\n'
    config.write_text(content, encoding="utf-8")
    monkeypatch.setattr(bootstrap, "CONFIG", config)
    monkeypatch.setattr(bootstrap, "SECRET", tmp_path / "missing")
    monkeypatch.setenv("PATCHLAB_API_KEY", "already-set")
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(AssertionError("unexpected prompt")))
    bootstrap.configure()
    assert config.read_text(encoding="utf-8") == content
    assert os.environ["PATCHLAB_API_KEY"] == "already-set"


def test_launcher_starts_web_with_config_and_proxy(tmp_path, monkeypatch):
    config = tmp_path / "model.toml"
    config.write_text('[model]\nurl="https://example.test/chat"\nname="m"\n', encoding="utf-8")
    monkeypatch.setattr(bootstrap, "CONFIG", config)
    monkeypatch.setattr(bootstrap, "ensure_environment", lambda: None)
    monkeypatch.setattr(bootstrap, "configure", lambda: None)
    monkeypatch.setattr(bootstrap.shutil, "which", lambda _: "git")
    monkeypatch.setattr(bootstrap.sys, "argv", ["bootstrap.py", "--no-browser", "--port", "9876"])
    seen = {}
    def start(command, **kwargs):
        seen.update(command=command, env=kwargs["env"])
        return 0
    monkeypatch.setattr(bootstrap.subprocess, "call", start)
    assert bootstrap.main() == 0
    assert seen["command"][1:4] == ["-m", "patchlab", "web"]
    assert str(config) in seen["command"] and "9876" in seen["command"]
    assert seen["env"]["HTTPS_PROXY"] == "http://127.0.0.1:7890"
    assert seen["env"]["NO_PROXY"] == "localhost,127.0.0.1,::1"
