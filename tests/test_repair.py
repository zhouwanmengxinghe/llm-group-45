import json
from pathlib import Path
import subprocess

import pytest

from patchlab.demo import Demonstrator, make_fixture
from patchlab.experiment import Task, execute
from patchlab.workbench import PytestRunner, Workbench


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
        ["bin/test", "-C", "--no-colors"],
    )
    assert runner.test_program == ["bin/test", "-C", "--no-colors"]
    with pytest.raises(ValueError, match="without shell syntax"):
        PytestRunner("image:local", 30, test_program=["bin/test", ";", "id"])
