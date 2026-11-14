import json
from pathlib import Path

import pytest

from patchlab.batch import load_manifest, report_batch, run_batch, validate_tasks
from patchlab.demo import Demonstrator, make_fixture
from patchlab.workbench import PytestRunner


def write_manifest(path: Path, repository: Path):
    path.write_text(json.dumps({"tasks": [{
        "id": "interval-case",
        "repository": str(repository),
        "revision": "HEAD",
        "issue": "Reversed intervals should have zero duration.",
        "editable": ["interval.py"],
        "target": ["test_interval.py::test_empty"],
        "suite": ["test_interval.py"],
    }]}), encoding="utf-8")


def test_manifest_validation_and_batch_run(tmp_path):
    repo = tmp_path / "repo"
    make_fixture(repo)
    manifest = tmp_path / "tasks.json"
    write_manifest(manifest, repo)
    tasks = load_manifest(manifest)
    runner = PytestRunner(None, 30)

    checked = validate_tasks(tasks, runner)
    assert checked[0]["status"] == "valid"

    batch_dir = tmp_path / "batch"
    summary = run_batch(
        tasks, batch_dir, Demonstrator, runner,
        modes=["feedback"], repeats=1,
    )
    assert summary["verified"] == 1
    assert summary["runs"][0]["status"] == "verified"
    assert not Path(summary["runs"][0]["result"]).is_absolute()
    assert (batch_dir / "batch.json").exists()
    assert (batch_dir / "runs.csv").exists()
    assert (batch_dir / "summary.json").exists()

    moved = tmp_path / "moved-batch"
    batch_dir.rename(moved)
    report = report_batch(moved)
    assert report["modes"][0]["verified_rate"] == 1.0
    assert report["modes"][0]["recovered_after_failed_candidate"] == 1


def test_manifest_rejects_duplicate_ids(tmp_path):
    repo = tmp_path / "repo"
    make_fixture(repo)
    row = {
        "id": "same", "repository": str(repo), "issue": "bug", "editable": ["interval.py"],
        "target": ["test_interval.py::test_empty"], "suite": ["test_interval.py"],
    }
    manifest = tmp_path / "tasks.json"
    manifest.write_text(json.dumps({"tasks": [row, row]}), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_manifest(manifest)


def test_batch_rejects_output_inside_target_repository(tmp_path):
    repo = tmp_path / "repo"
    make_fixture(repo)
    manifest = tmp_path / "tasks.json"
    write_manifest(manifest, repo)
    output = repo / "runs" / "batch"
    with pytest.raises(ValueError, match="outside every target repository"):
        run_batch(
            load_manifest(manifest), output, Demonstrator, PytestRunner(None, 30),
            modes=["feedback"], repeats=1,
        )
    assert not output.exists()


def test_swebench_manifest_withholds_scoring_target(tmp_path):
    repo = tmp_path / "repo"
    make_fixture(repo)
    manifest = tmp_path / "tasks.json"
    manifest.write_text(json.dumps({"tasks": [{
        "id": "demo__project-123",
        "repository": str(repo),
        "revision": "HEAD",
        "issue": "Reversed intervals should have zero duration.",
        "editable": ["interval.py"],
        "target": [],
        "suite": ["test_interval.py::test_positive"],
        "evaluation": "swebench",
    }]}), encoding="utf-8")
    tasks = load_manifest(manifest)
    assert tasks[0].task.external_evaluation == "swebench"
    assert validate_tasks(tasks, PytestRunner(None, 30))[0]["status"] == "valid"

    bad = json.loads(manifest.read_text(encoding="utf-8"))
    bad["tasks"][0]["target"] = ["test_interval.py::test_empty"]
    manifest.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="must remain withheld"):
        load_manifest(manifest)


def test_manifest_accepts_per_task_runner(tmp_path):
    repo = tmp_path / "repo"
    make_fixture(repo)
    manifest = tmp_path / "tasks.json"
    write_manifest(manifest, repo)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["tasks"][0]["runner"] = {
        "image": "project:test",
        "container_python": "/opt/env/bin/python",
        "test_program": ["bin/test", "-C"],
        "test_suffix": ["-k", "test_public"],
    }
    manifest.write_text(json.dumps(data), encoding="utf-8")
    item = load_manifest(manifest)[0]
    assert item.image == "project:test"
    assert item.container_python == "/opt/env/bin/python"
    assert item.test_program == ["bin/test", "-C"]
    assert item.test_suffix == ["-k", "test_public"]
