"""Manifest-driven, repeatable repair experiments."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
from typing import Callable

from .experiment import Task, execute
from .workbench import PytestRunner, Workbench, snapshot


TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")


@dataclass(frozen=True)
class BatchTask:
    task_id: str
    task: Task


def _strings(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(x, str) and x for x in value):
        raise ValueError(f"{field} must be a non-empty list of strings")
    return list(value)


def load_manifest(path: Path) -> list[BatchTask]:
    """Load tasks, resolving repository paths relative to the manifest."""
    path = path.resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("manifest.tasks must be a non-empty list")
    tasks: list[BatchTask] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each task must be an object")
        task_id = row.get("id")
        repository = row.get("repository")
        issue = row.get("issue")
        revision = row.get("revision", "HEAD")
        if not isinstance(task_id, str) or not TASK_ID.fullmatch(task_id) or task_id in seen:
            raise ValueError(f"invalid or duplicate task id: {task_id}")
        if not isinstance(repository, str) or not repository:
            raise ValueError(f"task {task_id}: repository must be a path string")
        if not isinstance(revision, str) or not revision or not isinstance(issue, str) or not issue.strip():
            raise ValueError(f"task {task_id}: revision and issue are required")
        repo = (path.parent / repository).resolve()
        if not repo.is_dir():
            raise ValueError(f"task {task_id}: repository does not exist: {repo}")
        tasks.append(BatchTask(task_id, Task(
            repo, revision, issue.strip(), _strings(row.get("editable"), "editable"),
            _strings(row.get("target"), "target"), _strings(row.get("suite"), "suite"),
        )))
        seen.add(task_id)
    return tasks


def validate_tasks(tasks: list[BatchTask], runner: PytestRunner) -> list[dict]:
    """Check revisions, editable paths, selectors, and initial reproduction."""
    results = []
    for item in tasks:
        row = {"task_id": item.task_id, "status": "invalid"}
        try:
            with TemporaryDirectory(prefix="patchlab-validate-") as temp:
                frozen = Path(temp) / "frozen"
                row["revision"] = snapshot(item.task.repository, item.task.revision, frozen)
                Workbench(frozen, item.task.editable)
                for selector in item.task.target + item.task.suite:
                    name = selector.split("::", 1)[0]
                    selected = (frozen / name).resolve()
                    if not name or not selected.is_relative_to(frozen.resolve()) or not selected.exists():
                        raise ValueError(f"invalid pytest selector: {selector}")
                check = Path(temp) / "initial"
                shutil.copytree(frozen, check)
                initial = runner.run(check, item.task.target)
                row["initial_target"] = initial
                if initial["timed_out"] or initial["exit_code"] != 1:
                    raise ValueError("target must reproduce the bug with pytest exit code 1")
                row["status"] = "valid"
        except Exception as exc:
            row["reason"] = f"{type(exc).__name__}: {exc}"
        results.append(row)
    return results


def run_batch(
    tasks: list[BatchTask], output: Path, model_factory: Callable[[], object],
    runner: PytestRunner, *, modes: list[str], repeats: int = 1,
    calls: int = 16, attempts: int = 5,
) -> dict:
    if not modes or any(mode not in {"single", "feedback", "memory"} for mode in modes):
        raise ValueError("modes must contain single, feedback, or memory")
    if not 1 <= repeats <= 20:
        raise ValueError("repeats must be between 1 and 20")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    runs = []
    for item in tasks:
        for mode in modes:
            for repeat in range(1, repeats + 1):
                run_dir = output / item.task_id / mode / f"run-{repeat:02d}"
                result = execute(
                    item.task, run_dir, model_factory(), runner, mode=mode,
                    calls=calls, attempts=attempts,
                )
                runs.append({
                    "task_id": item.task_id, "mode": mode, "repeat": repeat,
                    "status": result["status"], "result": str(run_dir / "result.json"),
                })
    summary = {
        "tasks": len(tasks), "modes": modes, "repeats": repeats, "runs": runs,
        "verified": sum(row["status"] == "verified" for row in runs),
    }
    (output / "batch.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return summary
