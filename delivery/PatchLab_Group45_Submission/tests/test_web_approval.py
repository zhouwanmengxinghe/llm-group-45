import hashlib
import json
from pathlib import Path
import threading
import time
import shutil
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

import pytest

from patchlab.demo import make_fixture
from patchlab.patch_application import apply_verified, save_application
from patchlab.web import Workspace, create_server
from patchlab.workbench import snapshot
from patchlab.workbench import PytestRunner
from patchlab.simple import execute_simple


def wait_for(predicate, seconds=12):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.02)
    raise AssertionError("Expected asynchronous state did not arrive")


class RepairModel:
    model = "scripted-review-test"

    def __init__(self, *args):
        pass

    def decide(self, context):
        return {"kind": "propose", "diagnosis": "Preserve positive durations; clamp reversed intervals.",
                "edits": [{"path": "interval.py", "before": "return end - start",
                           "after": "return max(0, end - start)"}]}, None


def start_repair(workspace, repo, sid):
    workspace.start(sid, {"kind": "repair", "message": "Clamp reversed intervals", "repo": str(repo),
                         "repair_type": "professional", "editable": "interval.py", "trusted": True,
                         "target": "test_interval.py::test_empty", "suite": "test_interval.py"})


def test_web_waits_for_approval_then_applies_and_followup_uses_current_files(tmp_path, monkeypatch):
    monkeypatch.setattr("patchlab.web.ChatDecider", RepairModel)
    repo = tmp_path / "project"
    make_fixture(repo)
    original = (repo / "interval.py").read_bytes()
    workspace = Workspace(None, tmp_path / "sessions")
    sid = "a" * 32
    start_repair(workspace, repo, sid)
    pending = wait_for(lambda: workspace.pending_approval(sid))
    try:
        assert (repo / "interval.py").read_bytes() == original
        assert not any(r.get("data", {}).get("event") == "candidate_target" for r in workspace.records(sid))
        with pytest.raises(ValueError, match="no longer pending"):
            workspace.decide_approval("b" * 32, pending["id"], True)
        with pytest.raises(ValueError, match="Another task"):
            start_repair(workspace, repo, "c" * 32)
    finally:
        workspace.decide_approval(sid, pending["id"], True)
    wait_for(lambda: sid not in workspace.active)
    result = next(r for r in workspace.records(sid) if r["type"] == "run_result")
    assert result["result"]["status"] == "verified"
    assert result["result"]["approval_enabled"] is True
    assert (repo / "interval.py").read_bytes() == original
    applied = workspace.apply_patch(sid, result["run_id"], result["application"]["patch_sha256"])
    assert applied["status"] == "applied"
    assert (Path(applied["backup"]) / "interval.py").read_bytes() == original
    assert b"max(0, end - start)" in (repo / "interval.py").read_bytes()
    snapshot(repo, "WORKTREE", tmp_path / "next")
    assert (tmp_path / "next/interval.py").read_bytes() == (repo / "interval.py").read_bytes()
    snapshot(repo, "HEAD", tmp_path / "head")
    assert (tmp_path / "head/interval.py").read_bytes() == original
    # Retrying an old apply action must never overwrite later manual changes.
    (repo / "interval.py").write_text("value = 42\n", encoding="utf-8")
    assert workspace.apply_patch(sid, result["run_id"], result["application"]["patch_sha256"]) == applied
    assert (repo / "interval.py").read_text() == "value = 42\n"


def test_rejection_stale_decision_and_expiry_are_bounded(tmp_path):
    workspace = Workspace(None, tmp_path)
    sid = "d" * 32
    values = []
    thread = threading.Thread(target=lambda: values.append(workspace.approval(sid, "f" * 16, "diagnosis", "diff", timeout=3)))
    thread.start()
    pending = wait_for(lambda: workspace.pending_approval(sid))
    with pytest.raises(ValueError, match="true or false"):
        workspace.decide_approval(sid, pending["id"], "false")
    workspace.decide_approval(sid, pending["id"], False)
    thread.join(3)
    assert values == [False]
    with pytest.raises(ValueError, match="no longer pending"):
        workspace.decide_approval(sid, pending["id"], True)
    with pytest.raises(TimeoutError, match="expired"):
        workspace.approval(sid, "f" * 16, "diagnosis", "diff", timeout=.01)
    assert workspace.pending_approval(sid) is None


def recipe(tmp_path, files=None):
    repo = tmp_path / "source"
    repo.mkdir()
    files = files or {"calc.py": "value = 1\n"}
    for name, text in files.items():
        (repo / name).write_bytes(text.encode())
    output = tmp_path / "run"
    output.mkdir()
    patch = "reviewed patch\n"
    changes = {name: text.replace("1", "2") for name, text in files.items()}
    save_application(output, repo, repo, changes, patch)
    (output / "final.patch").write_bytes(patch.encode())
    (output / "result.json").write_text(json.dumps({"status": "verified"}))
    return repo, output, hashlib.sha256(patch.encode()).hexdigest()


def test_apply_prechecks_all_files_and_preserves_unrelated_work(tmp_path):
    repo, out, sha = recipe(tmp_path, {"a.py": "value = 1\n", "b.py": "value = 1\n"})
    (repo / "b.py").write_bytes(b"manual = 9\n")
    with pytest.raises(ValueError, match="Source changed"):
        apply_verified(out, sha)
    assert (repo / "a.py").read_bytes() == b"value = 1\n"
    assert (repo / "b.py").read_bytes() == b"manual = 9\n"
    assert not (out / "apply-backup").exists()


def test_apply_rolls_back_partial_writes_and_retains_backups(tmp_path, monkeypatch):
    repo, out, sha = recipe(tmp_path, {"a.py": "value = 1\n", "b.py": "value = 1\n"})
    from patchlab import patch_application
    replace = patch_application._replace
    def fail_second(path, data, mode):
        if path.name == "b.py":
            raise OSError("simulated write failure")
        replace(path, data, mode)
    monkeypatch.setattr(patch_application, "_replace", fail_second)
    with pytest.raises(OSError, match="written files restored"):
        apply_verified(out, sha)
    assert (repo / "a.py").read_bytes() == b"value = 1\n"
    assert (out / "apply-backup/a.py").read_bytes() == b"value = 1\n"
    assert not (out / "application-result.json").exists()


def test_apply_preserves_crlf_and_rejects_tampering(tmp_path):
    repo, out, sha = recipe(tmp_path)
    (repo / "calc.py").write_bytes(b"value = 1\r\n")
    with pytest.raises(ValueError, match="no longer matches"):
        apply_verified(out, "wrong hash")
    result = apply_verified(out, sha)
    assert result["status"] == "applied"
    assert (repo / "calc.py").read_bytes() == b"value = 2\r\n"


def test_simple_rejected_candidate_never_runs_candidate_tests(tmp_path):
    repo = tmp_path / "project"
    make_fixture(repo)
    class SimpleModel(RepairModel):
        def decide(self, context):
            if not context["reproducer_confirmed"]:
                return {"kind": "reproduce", "code": "from interval import duration\ndef test_reverse():\n    assert duration(4, 2) == 0\n"}, None
            return super().decide(context)
    reviews = []
    output = tmp_path / "output"
    result = execute_simple(repo, "Clamp reverse intervals", "", output, SimpleModel(),
                            PytestRunner(None, 10), calls=2,
                            approve=lambda diagnosis, patch: reviews.append(patch) or False)
    assert len(reviews) == 1
    assert result["approval_enabled"] is True
    assert result["verified_candidates"] == 0
    assert not (output / "final.patch").exists()
    assert not any(json.loads(line)["event"] == "candidate_target"
                   for line in (output / "events.jsonl").read_text().splitlines())


def test_apply_rejects_unverified_candidate(tmp_path):
    repo, output, sha = recipe(tmp_path)
    (output / "result.json").write_text(json.dumps({"status": "candidate_ready"}))
    with pytest.raises(ValueError, match="passed its required"):
        apply_verified(output, sha)
    assert (repo / "calc.py").read_bytes() == b"value = 1\n"


@pytest.mark.parametrize("name", ["../outside.py", "/outside.py", "tests/test_calc.py"])
def test_apply_rejects_ineligible_paths(tmp_path, name):
    repo, out, sha = recipe(tmp_path)
    p = out / "application.json"
    data = json.loads(p.read_text())
    data["files"] = {name: {"before": "value = 1\n", "after": "value = 2\n"}}
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        apply_verified(out, sha)
    assert (repo / "calc.py").read_text() == "value = 1\n"


def test_web_http_actions_require_token_and_explicit_confirmation(tmp_path):
    workspace = Workspace(None, tmp_path / "sessions")
    server = create_server(workspace, "test-access-token")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    opener = build_opener(ProxyHandler({}))
    def post(route, data, token="test-access-token"):
        request = Request(url + route, json.dumps(data).encode(),
                          {"Content-Type": "application/json", "X-PatchLab-Token": token})
        return opener.open(request, timeout=3)
    try:
        with pytest.raises(HTTPError) as exc:
            post("/api/approval", {}, "incorrect")
        assert exc.value.code == 403
        with pytest.raises(HTTPError) as exc:
            post("/api/apply", {"session": "a" * 32})
        assert exc.value.code == 400
        assert "confirmation" in exc.value.read().decode()
        sid = "e" * 32
        decisions = []
        approval_thread = threading.Thread(target=lambda: decisions.append(
            workspace.approval(sid, "1" * 16, "review", "diff", timeout=3)))
        approval_thread.start()
        pending = wait_for(lambda: workspace.pending_approval(sid))
        with post("/api/approval", {"session": sid, "request_id": pending["id"], "approved": True}) as response:
            assert response.status == 200
        approval_thread.join(3)
        assert decisions == [True]
        repo, output, sha = recipe(tmp_path)
        run_id = "2" * 16
        destination = workspace.path(sid) / "repairs" / run_id
        shutil.copytree(output, destination)
        with post("/api/apply", {"session": sid, "run_id": run_id, "patch_sha256": sha, "confirmed": True}) as response:
            assert json.load(response)["status"] == "applied"
        assert (repo / "calc.py").read_bytes() == b"value = 2\n"
        with opener.open(url, timeout=3) as response:
            html = response.read().decode()
        assert 'id="requireApproval" checked' in html
        assert 'id="revision" value="WORKTREE"' in html
        assert 'id="approvalPanel"' in html
        assert 'Apply patch to project' in html
    finally:
        server.shutdown()
        server.server_close()
