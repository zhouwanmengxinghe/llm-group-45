"""Safe preparation and export helpers for SWE-bench experiments.

The bridge intentionally reads only public task metadata and the problem
statement. Gold patches, test patches, test lists, and grader output remain
outside the PatchLab generation context.
"""

from __future__ import annotations

import ast
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess


INSTANCE_ID = re.compile(r"[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-[0-9]+")
REVISION = re.compile(r"[0-9a-f]{40}")
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
FORBIDDEN_TASK_FILES = {"gold.patch", "test.patch", "tests.json", "hints.md", "eval.sh"}
DATASET_ALIASES = {"SWE-bench/SWE-bench_Verified": "verified"}


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _git_head(repository: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        text=True, encoding="utf-8", timeout=30,
    ).strip()


def _yaml_scalars(path: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Parse the small scalar/list subset used by upstream task.yaml files."""
    scalars: dict[str, str] = {}
    lists: dict[str, list[str]] = {}
    current_list: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith("- ") and current_list is not None:
            lists[current_list].append(raw[2:].strip())
            continue
        current_list = None
        if raw[:1].isspace() or ":" not in raw:
            raise ValueError(f"unsupported task metadata syntax: {path}")
        key, value = raw.split(":", 1)
        value = value.strip()
        if not value:
            current_list = key
            lists[key] = []
            continue
        if value[:1] in {"'", '"'}:
            parsed = ast.literal_eval(value)
            if not isinstance(parsed, str):
                raise ValueError(f"task metadata value must be text: {key}")
            value = parsed
        scalars[key] = value
    return scalars, lists


def load_selection(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = ("dataset", "split", "dataset_revision", "task_repo_revision", "instances")
    if not isinstance(data, dict) or any(key not in data for key in required):
        raise ValueError("SWE-bench selection is missing required fields")
    if data["dataset"] not in DATASET_ALIASES or data["split"] != "test":
        raise ValueError("the pilot supports only the SWE-bench Verified test split")
    if not all(isinstance(data[key], str) and data[key] for key in required[:-1]):
        raise ValueError("selection metadata fields must be non-empty strings")
    if not REVISION.fullmatch(data["dataset_revision"]) or not REVISION.fullmatch(data["task_repo_revision"]):
        raise ValueError("dataset and task-repository revisions must be 40-character commits")
    ids = data["instances"]
    if (
        not isinstance(ids, list) or not 1 <= len(ids) <= 30
        or not all(isinstance(item, str) and INSTANCE_ID.fullmatch(item) for item in ids)
        or len(ids) != len(set(ids))
    ):
        raise ValueError("instances must contain 1-30 unique SWE-bench instance IDs")
    return data


def freeze_selection(task_repository: Path, selection_path: Path, output: Path) -> dict:
    """Create a generation-safe lock from a pinned upstream task repository."""
    task_repository = task_repository.resolve()
    selection = load_selection(selection_path)
    actual_revision = _git_head(task_repository)
    if actual_revision != selection["task_repo_revision"]:
        raise ValueError(
            f"task repository is at {actual_revision}, expected {selection['task_repo_revision']}"
        )

    locked = []
    for instance_id in selection["instances"]:
        directory = task_repository / "tasks" / instance_id
        metadata_path = directory / "task.yaml"
        problem_path = directory / "problem_statement.md"
        if not metadata_path.is_file() or not problem_path.is_file():
            raise ValueError(f"missing public metadata for {instance_id}")
        scalars, lists = _yaml_scalars(metadata_path)
        needed = ("instance_id", "repo", "base_commit", "split", "version", "image")
        if any(not scalars.get(key) for key in needed):
            raise ValueError(f"incomplete task metadata for {instance_id}")
        if scalars["instance_id"] != instance_id or scalars["split"] != selection["split"]:
            raise ValueError(f"task identity or split mismatch for {instance_id}")
        if selection["dataset"] not in lists.get("datasets", []):
            raise ValueError(f"{instance_id} is not in {selection['dataset']}")
        if not REVISION.fullmatch(scalars["base_commit"]):
            raise ValueError(f"invalid base commit for {instance_id}")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", scalars["repo"]):
            raise ValueError(f"invalid repository for {instance_id}")
        problem = problem_path.read_text(encoding="utf-8").strip()
        if not 1 <= len(problem) <= 100_000:
            raise ValueError(f"invalid problem statement for {instance_id}")
        locked.append({
            "instance_id": instance_id,
            "repo": scalars["repo"],
            "base_commit": scalars["base_commit"],
            "version": scalars["version"],
            "difficulty": scalars.get("difficulty"),
            "image": scalars["image"],
            "problem_statement": problem,
            "metadata_sha256": _sha256(metadata_path),
            "problem_statement_sha256": _sha256(problem_path),
        })

    lock = {
        "schema": 1,
        "dataset": selection["dataset"],
        "split": selection["split"],
        "dataset_revision": selection["dataset_revision"],
        "task_repo_revision": selection["task_repo_revision"],
        "instances": locked,
        "generation_excludes": sorted(FORBIDDEN_TASK_FILES),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(lock, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return lock


def load_lock(path: Path) -> dict:
    lock = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(lock, dict) or lock.get("schema") != 1:
        raise ValueError("unsupported SWE-bench lock")
    expected = set(FORBIDDEN_TASK_FILES)
    if set(lock.get("generation_excludes", [])) != expected:
        raise ValueError("lock does not declare all hidden evaluation artifacts")
    instances = lock.get("instances")
    if not isinstance(instances, list) or not instances:
        raise ValueError("lock has no instances")
    ids = [row.get("instance_id") for row in instances if isinstance(row, dict)]
    if len(ids) != len(instances) or len(ids) != len(set(ids)):
        raise ValueError("lock contains invalid or duplicate instances")
    return lock


def write_patchlab_manifest(lock_path: Path, workspace_path: Path, output: Path) -> dict:
    """Join safe task metadata with operator-selected source and public tests."""
    lock = load_lock(lock_path)
    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    rows = workspace.get("instances") if isinstance(workspace, dict) else None
    if not isinstance(rows, list):
        raise ValueError("workspace configuration must contain an instances list")
    by_id = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("instance_id"), str):
            raise ValueError("invalid workspace instance")
        instance_id = row["instance_id"]
        if instance_id in by_id:
            raise ValueError(f"duplicate workspace instance: {instance_id}")
        repository, editable, suite = row.get("repository"), row.get("editable"), row.get("suite")
        if not isinstance(repository, str) or not repository:
            raise ValueError(f"{instance_id}: repository is required")
        for name, value in (("editable", editable), ("suite", suite)):
            if not isinstance(value, list) or not value or not all(isinstance(x, str) and x for x in value):
                raise ValueError(f"{instance_id}: {name} must be a non-empty list")
        by_id[instance_id] = row
    expected = [row["instance_id"] for row in lock["instances"]]
    if set(by_id) != set(expected):
        raise ValueError("workspace IDs must exactly match the frozen lock")

    tasks = []
    for instance in lock["instances"]:
        workspace_row = by_id[instance["instance_id"]]
        tasks.append({
            "id": instance["instance_id"],
            "repository": workspace_row["repository"],
            "revision": instance["base_commit"],
            "issue": instance["problem_statement"],
            "editable": workspace_row["editable"],
            "target": [],
            "suite": workspace_row["suite"],
            "evaluation": "swebench",
            "runner": {
                "image": instance["image"],
                "container_python": workspace_row.get("container_python", "python"),
                "test_program": workspace_row.get("test_program"),
                "test_suffix": workspace_row.get("test_suffix"),
            },
        })
    manifest = {
        "name": "SWE-bench Verified pilot (external official evaluation)",
        "dataset_revision": lock["dataset_revision"],
        "task_repo_revision": lock["task_repo_revision"],
        "tasks": tasks,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return manifest


def export_predictions(
    lock_path: Path, batch_output: Path, output: Path, *,
    mode: str, repeat: int, model_name: str,
) -> list[dict]:
    """Convert PatchLab final patches into the official prediction schema."""
    if mode not in {"single", "feedback", "memory"} or repeat < 1 or not model_name:
        raise ValueError("invalid prediction selection")
    lock = load_lock(lock_path)
    batch_output = batch_output.resolve()
    index = json.loads((batch_output / "batch.json").read_text(encoding="utf-8"))
    runs = index.get("runs") if isinstance(index, dict) else None
    if not isinstance(runs, list):
        raise ValueError("batch output has no run index")
    selected = {
        row.get("task_id"): row for row in runs
        if isinstance(row, dict) and row.get("mode") == mode and row.get("repeat") == repeat
    }
    predictions = []
    for instance in lock["instances"]:
        instance_id = instance["instance_id"]
        entry = selected.get(instance_id)
        patch = ""
        if entry is not None and isinstance(entry.get("result"), str):
            result_path = (batch_output / entry["result"]).resolve()
            if not result_path.is_relative_to(batch_output) or not result_path.is_file():
                raise ValueError(f"unsafe or missing result for {instance_id}")
            result = json.loads(result_path.read_text(encoding="utf-8"))
            patch_path = result_path.parent / "final.patch"
            if result.get("status") in {"verified", "candidate_ready"} and patch_path.is_file():
                patch = patch_path.read_text(encoding="utf-8")
        predictions.append({
            "instance_id": instance_id,
            "model_name_or_path": model_name,
            "model_patch": patch,
        })
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=True) + "\n" for row in predictions),
        encoding="utf-8",
    )
    return predictions


def write_evaluation_plan(
    lock_path: Path, predictions: Path, task_repository: Path,
    output: Path, *, run_id: str, workers: int = 1,
) -> dict:
    """Write, but deliberately do not execute, the official harness command."""
    if not RUN_ID.fullmatch(run_id) or not 1 <= workers <= 8:
        raise ValueError("invalid run id or worker count")
    lock = load_lock(lock_path)
    if lock.get("dataset") not in DATASET_ALIASES:
        raise ValueError("unsupported SWE-bench dataset")
    rows = [json.loads(line) for line in predictions.read_text(encoding="utf-8").splitlines() if line]
    expected = [row["instance_id"] for row in lock["instances"]]
    if [row.get("instance_id") for row in rows] != expected:
        raise ValueError("prediction IDs or order do not match the frozen lock")
    command = [
        "swebench", "eval", DATASET_ALIASES[lock["dataset"]],
        "-p", str(predictions.resolve()), "--run-id", run_id,
        "-j", str(workers), "--task-repo", str(task_repository.resolve()),
    ]
    for instance_id in expected:
        command.extend(["-i", instance_id])
    plan = {
        "schema": 1,
        "execute": False,
        "dataset_revision": lock["dataset_revision"],
        "task_repo_revision": lock["task_repo_revision"],
        "command": command,
        "note": "Review resources and configuration before executing this command.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return plan
