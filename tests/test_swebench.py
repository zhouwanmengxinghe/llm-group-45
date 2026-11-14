import json
from pathlib import Path
import subprocess

import pytest

from patchlab.swebench import (
    export_predictions, freeze_selection, write_evaluation_plan, write_patchlab_manifest,
)


TASK = "demo__project-123"
TASK_REPO_REVISION = ""


def make_task_repo(root: Path) -> str:
    task = root / "tasks" / TASK
    task.mkdir(parents=True)
    (task / "task.yaml").write_text(
        "base_commit: 0123456789abcdef0123456789abcdef01234567\n"
        "datasets:\n"
        "- SWE-bench/SWE-bench_Verified\n"
        "difficulty: <15 min fix\n"
        "image: swebench/demo:latest\n"
        f"instance_id: {TASK}\n"
        "repo: demo/project\n"
        "split: test\n"
        "version: '1.0'\n",
        encoding="utf-8",
    )
    (task / "problem_statement.md").write_text("Public issue text.\n", encoding="utf-8")
    for name in ("gold.patch", "test.patch", "tests.json", "hints.md", "eval.sh"):
        (task / name).write_text("SECRET-HIDDEN-EVALUATION-DATA\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()


def write_selection(path: Path, revision: str):
    path.write_text(json.dumps({
        "dataset": "SWE-bench/SWE-bench_Verified",
        "split": "test",
        "dataset_revision": "a" * 40,
        "task_repo_revision": revision,
        "instances": [TASK],
    }), encoding="utf-8")


def test_freeze_excludes_hidden_evaluation_data(tmp_path):
    task_repo = tmp_path / "tasks"
    revision = make_task_repo(task_repo)
    selection = tmp_path / "selection.json"
    write_selection(selection, revision)
    lock_path = tmp_path / "lock.json"

    lock = freeze_selection(task_repo, selection, lock_path)

    assert lock["instances"][0]["problem_statement"] == "Public issue text."
    assert lock["task_repo_revision"] == revision
    assert "SECRET-HIDDEN-EVALUATION-DATA" not in lock_path.read_text(encoding="utf-8")
    assert set(lock["generation_excludes"]) == {
        "eval.sh", "gold.patch", "hints.md", "test.patch", "tests.json"
    }


def test_freeze_rejects_unpinned_task_repo(tmp_path):
    task_repo = tmp_path / "tasks"
    make_task_repo(task_repo)
    selection = tmp_path / "selection.json"
    write_selection(selection, "b" * 40)
    with pytest.raises(ValueError, match="expected"):
        freeze_selection(task_repo, selection, tmp_path / "lock.json")


def test_export_and_evaluation_plan(tmp_path):
    task_repo = tmp_path / "tasks"
    revision = make_task_repo(task_repo)
    selection = tmp_path / "selection.json"
    write_selection(selection, revision)
    lock_path = tmp_path / "lock.json"
    freeze_selection(task_repo, selection, lock_path)

    batch = tmp_path / "batch"
    run = batch / TASK / "single" / "run-01"
    run.mkdir(parents=True)
    result = run / "result.json"
    result.write_text(json.dumps({"status": "verified"}), encoding="utf-8")
    (run / "final.patch").write_text("--- a/a.py\n+++ b/a.py\n", encoding="utf-8")
    (batch / "batch.json").write_text(json.dumps({"runs": [{
        "task_id": TASK, "mode": "single", "repeat": 1,
        "status": "verified", "result": f"{TASK}/single/run-01/result.json",
    }]}), encoding="utf-8")

    predictions_path = tmp_path / "predictions.jsonl"
    predictions = export_predictions(
        lock_path, batch, predictions_path, mode="single", repeat=1,
        model_name="patchlab-test",
    )
    assert predictions[0]["instance_id"] == TASK
    assert predictions[0]["model_patch"].startswith("--- a/a.py")

    plan_path = tmp_path / "eval-plan.json"
    plan = write_evaluation_plan(
        lock_path, predictions_path, task_repo, plan_path,
        run_id="pilot-01", workers=1,
    )
    assert plan["execute"] is False
    assert plan["command"][:3] == ["swebench", "eval", "verified"]
    assert plan["command"][-2:] == ["-i", TASK]


def test_manifest_uses_issue_but_withholds_scoring_tests(tmp_path):
    task_repo = tmp_path / "tasks"
    revision = make_task_repo(task_repo)
    selection = tmp_path / "selection.json"
    write_selection(selection, revision)
    lock_path = tmp_path / "lock.json"
    freeze_selection(task_repo, selection, lock_path)
    workspaces = tmp_path / "workspaces.json"
    workspaces.write_text(json.dumps({"instances": [{
        "instance_id": TASK,
        "repository": "/safe/repository",
        "editable": ["package/code.py"],
        "suite": ["tests/test_public.py"],
        "container_python": "/opt/conda/envs/testbed/bin/python",
        "test_program": ["bin/test", "-C", "--no-colors"],
        "test_suffix": ["-k", "test_public"],
    }]}), encoding="utf-8")

    manifest = write_patchlab_manifest(
        lock_path, workspaces, tmp_path / "manifest.json"
    )
    task = manifest["tasks"][0]
    assert task["issue"] == "Public issue text."
    assert task["target"] == []
    assert task["evaluation"] == "swebench"
    assert task["runner"]["image"] == "swebench/demo:latest"
    assert task["runner"]["test_program"] == ["bin/test", "-C", "--no-colors"]
    assert task["runner"]["test_suffix"] == ["-k", "test_public"]
