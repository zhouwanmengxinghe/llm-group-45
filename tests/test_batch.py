import json
from pathlib import Path

import pytest

from patchlab.batch import load_manifest, run_batch, validate_tasks
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

    summary = run_batch(
        tasks, tmp_path / "batch", Demonstrator, runner,
        modes=["feedback"], repeats=1,
    )
    assert summary["verified"] == 1
    assert summary["runs"][0]["status"] == "verified"
    assert (tmp_path / "batch" / "batch.json").exists()


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
