"""Manifest-driven, repeatable repair experiments."""

from __future__ import annotations

from dataclasses import dataclass
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re
import shutil
from statistics import median
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


def _optional_strings(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
        raise ValueError(f"{field} must be a list of strings")
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
        evaluation = row.get("evaluation", "supplied_tests")
        if not isinstance(task_id, str) or not TASK_ID.fullmatch(task_id) or task_id in seen:
            raise ValueError(f"invalid or duplicate task id: {task_id}")
        if not isinstance(repository, str) or not repository:
            raise ValueError(f"task {task_id}: repository must be a path string")
        if not isinstance(revision, str) or not revision or not isinstance(issue, str) or not issue.strip():
            raise ValueError(f"task {task_id}: revision and issue are required")
        repo = (path.parent / repository).resolve()
        if not repo.is_dir():
            raise ValueError(f"task {task_id}: repository does not exist: {repo}")
        if evaluation not in {"supplied_tests", "swebench"}:
            raise ValueError(f"task {task_id}: unsupported evaluation policy")
        target = _optional_strings(row.get("target"), "target")
        if evaluation == "supplied_tests" and not target:
            raise ValueError(f"task {task_id}: supplied-tests evaluation needs a target")
        if evaluation == "swebench" and target:
            raise ValueError(f"task {task_id}: SWE-bench scoring tests must remain withheld")
        tasks.append(BatchTask(task_id, Task(
            repo, revision, issue.strip(), _strings(row.get("editable"), "editable"),
            target, _strings(row.get("suite"), "suite"),
            "swebench" if evaluation == "swebench" else None,
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
                if item.task.external_evaluation:
                    initial = runner.run(check, item.task.suite)
                    row["initial_public_suite"] = initial
                    if initial["timed_out"] or initial["exit_code"] not in {0, 1}:
                        raise ValueError("public suite must run with pytest exit code 0 or 1")
                else:
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
    for item in tasks:
        if output.is_relative_to(item.task.repository.resolve()):
            raise ValueError("batch output must be outside every target repository")
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
                    "status": result["status"],
                    "result": (run_dir / "result.json").relative_to(output).as_posix(),
                })
    summary = {
        "tasks": len(tasks), "modes": modes, "repeats": repeats, "runs": runs,
        "verified": sum(row["status"] == "verified" for row in runs),
        "candidate_ready": sum(row["status"] == "candidate_ready" for row in runs),
    }
    (output / "batch.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    report_batch(output)
    return summary


def report_batch(output: Path) -> dict:
    """Create portable run details and mode-level statistics from batch outputs."""
    output = output.resolve()
    index = json.loads((output / "batch.json").read_text(encoding="utf-8"))
    indexed = index.get("runs") if isinstance(index, dict) else None
    if not isinstance(indexed, list):
        raise ValueError("batch.json does not contain a runs list")
    details = []
    for entry in indexed:
        if not isinstance(entry, dict) or not isinstance(entry.get("result"), str):
            raise ValueError("batch.json contains an invalid run entry")
        result_path = (output / entry["result"]).resolve()
        if not result_path.is_relative_to(output) or not result_path.is_file():
            raise ValueError(f"missing or unsafe result path: {entry['result']}")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        details.append({
            "task_id": entry.get("task_id"), "mode": entry.get("mode"),
            "repeat": entry.get("repeat"), "status": result.get("status"),
            "attempts": result.get("attempts"), "model_calls": result.get("model_calls"),
            "inspection_calls": result.get("inspection_calls"),
            "tested_candidates": result.get("verified_candidates"),
            "elapsed_seconds": result.get("elapsed_seconds"),
            "tokens_reported": result.get("tokens_reported"),
            "calls_with_usage": result.get("calls_with_usage"),
            "reason": result.get("reason"), "result": entry["result"],
        })

    fields = [
        "task_id", "mode", "repeat", "status", "attempts", "model_calls",
        "inspection_calls", "tested_candidates", "elapsed_seconds", "tokens_reported",
        "calls_with_usage", "reason", "result",
    ]
    with (output / "runs.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(details)

    grouped = defaultdict(list)
    for row in details:
        grouped[row["mode"]].append(row)
    modes = []
    for mode, rows in sorted(grouped.items()):
        verified = [row for row in rows if row["status"] == "verified"]
        complete_usage = [
            row["tokens_reported"] for row in rows
            if isinstance(row["model_calls"], int) and row["model_calls"] > 0
            and row["calls_with_usage"] == row["model_calls"]
            and isinstance(row["tokens_reported"], int)
        ]
        modes.append({
            "mode": mode, "runs": len(rows), "verified": len(verified),
            "candidate_ready": sum(row["status"] == "candidate_ready" for row in rows),
            "verified_rate": len(verified) / len(rows),
            "recovered_after_failed_candidate": sum(
                isinstance(row["attempts"], int) and row["attempts"] > 1 for row in verified
            ),
            "statuses": dict(sorted(Counter(row["status"] for row in rows).items())),
            "median_elapsed_seconds": median(row["elapsed_seconds"] for row in rows),
            "median_attempts": median(row["attempts"] for row in rows),
            "median_model_calls": median(row["model_calls"] for row in rows),
            "complete_token_records": len(complete_usage),
            "median_total_tokens_when_complete": median(complete_usage) if complete_usage else None,
        })
    report = {"runs": len(details), "tasks": index.get("tasks"), "modes": modes}
    (output / "summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return report
