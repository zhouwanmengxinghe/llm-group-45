import json
from pathlib import Path
import subprocess

import pytest

from patchlab.demo import Demonstrator, make_fixture
from patchlab.experiment import Task, execute
from patchlab.workbench import PytestRunner, Workbench, snapshot


def test_oversized_read_returns_bounded_evidence_instead_of_retry_loop(tmp_path):
    (tmp_path / "sample.py").write_text("".join(f"value_{i} = {i}\n" for i in range(200)))
    bench = Workbench(tmp_path, ["sample.py"])
    response = bench.inspect({"kind": "read", "path": "sample.py", "start": 80, "end": 160})
    assert len(response["text"].splitlines()) == 80
    assert response["end"] == 159 and response["next_start"] == 160
    assert response["range_capped"] is True


def test_src_layout_executes_snapshot_source(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "snapshot_only_module.py").write_text("value = 3\n")
    (tmp_path / "test_value.py").write_text("import snapshot_only_module\ndef test_value():\n    assert snapshot_only_module.value == 4\n")
    runner = PytestRunner(None, 30)
    assert runner.run(tmp_path, ["test_value.py"])["exit_code"] == 1
    (tmp_path / "src" / "snapshot_only_module.py").write_text("value = 4\n")
    assert runner.run(tmp_path, ["test_value.py"])["exit_code"] == 0


def run(tmp_path, mode="feedback", approval=None):
    repo = tmp_path / "repo"
    make_fixture(repo)
    task = Task(repo, "HEAD", "Reversed interval duration must be zero.", ["interval.py"],
                ["test_interval.py::test_empty"], ["test_interval.py"])
    out = tmp_path / "out"
    result = execute(task, out, Demonstrator(), PytestRunner(None, 30),
                     mode=mode, approve=approval)
    trace = [json.loads(row) for row in (out / "events.jsonl").read_text().splitlines()]
    return repo, out, result, trace


@pytest.mark.parametrize("mode", ["feedback", "memory"])
def test_recovers_from_a_regression(tmp_path, mode):
    repo, out, result, trace = run(tmp_path, mode)
    assert result["status"] == "verified", result
    assert result["attempts"] == 2
    assert result["provider_requests"] == result["model_calls"]
    assert result["provider_usage_complete"] is False
    assert [r["exit_code"] for r in trace if r["event"] == "candidate_regression"] == [1, 0]
    assert (out / "result.json").is_file()
    subprocess.run(["git", "-C", str(repo), "apply", "--check", str(out / "final.patch")], check=True)
    assert b"max(" not in (repo / "interval.py").read_bytes()


def test_single_attempt_cannot_retry(tmp_path):
    _, out, result, trace = run(tmp_path, "single")
    assert result["status"] == "proposal_limit"
    assert result["attempts"] == 1
    assert not (out / "final.patch").exists()
    assert any(r["event"] == "candidate_regression" and r["exit_code"] == 1 for r in trace)


def test_budget_guidance_and_repeated_inspection_cache(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    make_fixture(repo)
    task = Task(repo, "HEAD", "Fix interval duration.", ["interval.py"],
                ["test_interval.py::test_empty"], ["test_interval.py"])
    inspected = []
    original = Workbench.inspect
    def inspect(bench, action):
        inspected.append(action)
        return original(bench, action)
    monkeypatch.setattr(Workbench, "inspect", inspect)
    monkeypatch.setattr(PytestRunner, "run", lambda *args: {
        "exit_code": 1, "timed_out": False, "output": "expected failure"})
    class Model:
        model = "budget-aware-fixture"
        def __init__(self): self.contexts = []
        def decide(self, context):
            self.contexts.append(context)
            if context["next_action_constraint"]:
                return {"kind": "stop", "reason": "need more evidence"}, None
            return {"kind": "read", "path": "interval.py", "start": 1, "end": 2}, None
    model = Model()
    out = tmp_path / "budget-run"
    result = execute(task, out, model, PytestRunner(None, 30), calls=8)
    assert result["status"] == "model_stopped" and result["model_calls"] == 5
    assert [c["decisions_remaining"] for c in model.contexts] == [8, 7, 6, 5, 4]
    assert len(inspected) == 1
    trace = [json.loads(row) for row in (out / "events.jsonl").read_text().splitlines()]
    assert sum(e["event"] == "inspection_cache_hit" for e in trace) == 3


def test_external_evaluation_produces_unverified_candidate(tmp_path):
    repo = tmp_path / "repo"
    make_fixture(repo)
    task = Task(
        repo, "HEAD", "Reversed intervals should have zero duration.",
        ["interval.py"], [], ["test_interval.py::test_positive"], "swebench",
    )
    result = execute(
        task, tmp_path / "external-run", Demonstrator(), PytestRunner(None, 30),
        mode="feedback",
    )
    assert result["status"] == "candidate_ready"
    assert result["external_evaluation"] == "swebench"
    assert "target_result" not in result
    assert (tmp_path / "external-run" / "final.patch").is_file()


def test_rejected_candidate_does_not_run(tmp_path):
    reviewed = []

    def reject(diagnosis, diff):
        reviewed.append(diff)
        return False

    _, out, result, trace = run(tmp_path, approval=reject)
    assert reviewed and "return 0" in reviewed[0]
    assert result["verified_candidates"] == 0
    assert not (out / "final.patch").exists()
    assert not any(r["event"] == "candidate_target" for r in trace)


def test_test_files_and_outside_paths_cannot_be_edited(tmp_path):
    (tmp_path / "test_code.py").write_text("assert False\n")
    (tmp_path / "code.py").write_text("value = 1\n")
    with pytest.raises(ValueError):
        Workbench(tmp_path, ["test_code.py"])
    bench = Workbench(tmp_path, ["code.py"])
    for path in ("test_code.py", "../code.py", str(Path(tmp_path) / "code.py")):
        with pytest.raises(ValueError):
            bench.prepare([{"path": path, "before": "1", "after": "2"}])


def test_container_python_is_bounded():
    runner = PytestRunner("image:local", 30, "/opt/conda/envs/testbed/bin/python")
    assert runner.python_executable.endswith("/python")
    with pytest.raises(ValueError, match="safe absolute path"):
        PytestRunner("image:local", 30, "python -c")
    with pytest.raises(ValueError, match="only valid"):
        PytestRunner(None, 30, "/usr/bin/python")
    runner = PytestRunner(
        "image:local", 30, "/opt/conda/envs/testbed/bin/python",
        ["bin/test", "-C", "--no-colors"], ["-k", "test_public"],
    )
    assert runner.test_program == ["bin/test", "-C", "--no-colors"]
    assert runner.test_suffix == ["-k", "test_public"]
    with pytest.raises(ValueError, match="without shell syntax"):
        PytestRunner("image:local", 30, test_program=["bin/test", ";", "id"])


def test_custom_test_program_accepts_bounded_module_labels(tmp_path):
    runner = PytestRunner("image:local", 30, test_program=["tests/runtests.py"])
    runner.validate_selectors(tmp_path, ["middleware.test_security"])
    for selector in ("--help", "package..test_module", "../outside.py"):
        with pytest.raises(ValueError, match="invalid"):
            runner.validate_selectors(tmp_path, [selector])


def stage_git_symlink(repo, name, target):
    blob = subprocess.check_output(
        ["git", "-C", str(repo), "hash-object", "-w", "--stdin"], input=target.encode()
    ).decode().strip()
    subprocess.run(
        ["git", "-C", str(repo), "update-index", "--add", "--cacheinfo", f"120000,{blob},{name}"],
        check=True,
    )


def test_snapshot_preserves_safe_repository_symlink(tmp_path):
    repo = tmp_path / "repo"
    make_fixture(repo)
    try:
        (tmp_path / "permission-probe").symlink_to("repo/interval.py")
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows has not granted symlink creation permission")
        raise
    stage_git_symlink(repo, "interval_alias.py", "interval.py")
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "Add safe symlink"],
        check=True, stdout=subprocess.DEVNULL,
    )

    frozen = tmp_path / "frozen"
    snapshot(repo, "HEAD", frozen)
    assert (frozen / "interval_alias.py").is_symlink()
    assert (frozen / "interval_alias.py").read_bytes() == (frozen / "interval.py").read_bytes()


def test_snapshot_rejects_symlink_outside_repository(tmp_path):
    repo = tmp_path / "repo"
    make_fixture(repo)
    stage_git_symlink(repo, "escape.py", "../outside.py")
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "Add unsafe symlink"],
        check=True, stdout=subprocess.DEVNULL,
    )

    with pytest.raises(ValueError, match="stay inside"):
        snapshot(repo, "HEAD", tmp_path / "frozen")
