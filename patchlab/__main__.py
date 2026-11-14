"""Command line for repair runs and comparison of recorded results."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from statistics import median
import sys

from .decision import ChatDecider
from .batch import load_manifest, report_batch, run_batch, validate_tasks
from .demo import run_demo
from .experiment import Task, execute
from .workbench import PytestRunner
from .swebench import (
    export_predictions, freeze_selection, write_evaluation_plan, write_patchlab_manifest,
)


def approve(diagnosis: str, patch: str) -> bool:
    print(f"\nDiagnosis: {diagnosis}\n\n{patch}", file=sys.stderr)
    return input("Run tests on this candidate? [y/N] ").strip().casefold() in {"y", "yes"}


def summarize(paths: list[Path]) -> list[dict]:
    groups = defaultdict(list)
    for path in paths:
        row = json.loads(path.read_text(encoding="utf-8"))
        groups[(row["model"], row["mode"])].append(row)
    output = []
    for (model, mode), rows in sorted(groups.items()):
        verified = [r for r in rows if r["status"] == "verified"]
        observed = [r["tokens_reported"] for r in rows if r["calls_with_usage"] == r["model_calls"]
                    and r["model_calls"] > 0]
        output.append({
            "model": model, "mode": mode, "runs": len(rows),
            "verified_on_supplied_tests": len(verified),
            "verified_rate_on_supplied_tests": len(verified) / len(rows),
            "recovered_after_failed_candidate": sum(r["verified_candidates"] > 1 for r in verified),
            "statuses": {s: sum(r["status"] == s for r in rows) for s in sorted({r["status"] for r in rows})},
            "median_seconds": median(r["elapsed_seconds"] for r in rows),
            "median_attempts": median(r["attempts"] for r in rows),
            "median_model_calls": median(r["model_calls"] for r in rows),
            "complete_token_records": len(observed),
            "median_total_tokens_when_known": median(observed) if observed else None,
        })
    return output


def positive(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return n


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m patchlab")
    commands = parser.add_subparsers(dest="command", required=True)
    web = commands.add_parser("web", help="Launch the local browser workspace.")
    web.add_argument("--model-config", type=Path)
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--no-browser", action="store_true")
    demo = commands.add_parser("demo", help="Run the offline scripted fixture.")
    run = commands.add_parser("run", help="Ask a configured model to repair a Git revision.")
    for item in (run, demo):
        item.add_argument("--output", required=True, type=Path)
        item.add_argument("--mode", choices=["single", "feedback", "memory"], default="feedback")
        item.add_argument("--timeout", type=positive, default=90, help="Seconds per pytest command.")
        item.add_argument("--approve", action="store_true")
        executor = item.add_mutually_exclusive_group(required=True)
        executor.add_argument("--image", help="Existing Linux Docker image with Python and test dependencies.")
        executor.add_argument("--trusted-local", action="store_true", help="Execute trusted code on the host.")
    run.add_argument("--repo", type=Path, required=True)
    run.add_argument("--revision", default="HEAD")
    run.add_argument("--issue", required=True)
    run.add_argument("--editable", action="append", required=True)
    run.add_argument("--target", action="append", required=True)
    run.add_argument("--suite", action="append", required=True)
    run.add_argument("--calls", type=positive, default=16)
    run.add_argument("--attempts", choices=range(1, 6), type=int, default=5)
    run.add_argument("--completion-tokens", type=positive, default=1200)
    run.add_argument("--model-config", type=Path, help="TOML model configuration file")
    summary = commands.add_parser("summarize", help="Group result.json files by model and condition.")
    summary.add_argument("results", nargs="+", type=Path)
    validate = commands.add_parser("validate-manifest", help="Validate benchmark tasks without a model call.")
    validate.add_argument("--manifest", required=True, type=Path)
    validate.add_argument("--timeout", type=positive, default=90)
    validate_executor = validate.add_mutually_exclusive_group(required=True)
    validate_executor.add_argument("--image")
    validate_executor.add_argument("--trusted-local", action="store_true")
    batch = commands.add_parser("batch", help="Run a frozen manifest across repair conditions.")
    batch.add_argument("--manifest", required=True, type=Path)
    batch.add_argument("--output", required=True, type=Path)
    batch.add_argument("--mode", action="append", choices=["single", "feedback", "memory"])
    batch.add_argument("--repeats", type=positive, default=1)
    batch.add_argument("--timeout", type=positive, default=90)
    batch.add_argument("--calls", type=positive, default=16)
    batch.add_argument("--attempts", choices=range(1, 6), type=int, default=5)
    batch.add_argument("--completion-tokens", type=positive, default=1200)
    batch.add_argument("--model-config", type=Path)
    batch_executor = batch.add_mutually_exclusive_group(required=True)
    batch_executor.add_argument("--image")
    batch_executor.add_argument("--trusted-local", action="store_true")
    batch_report = commands.add_parser("batch-report", help="Rebuild CSV and summary files for a batch.")
    batch_report.add_argument("--output", required=True, type=Path)
    swe_freeze = commands.add_parser(
        "swebench-freeze", help="Create a generation-safe lock from a pinned SWE-bench task repo."
    )
    swe_freeze.add_argument("--task-repo", required=True, type=Path)
    swe_freeze.add_argument("--selection", required=True, type=Path)
    swe_freeze.add_argument("--output", required=True, type=Path)
    swe_export = commands.add_parser(
        "swebench-export", help="Export PatchLab final patches in SWE-bench prediction format."
    )
    swe_export.add_argument("--lock", required=True, type=Path)
    swe_export.add_argument("--batch-output", required=True, type=Path)
    swe_export.add_argument("--output", required=True, type=Path)
    swe_export.add_argument("--mode", required=True, choices=["single", "feedback", "memory"])
    swe_export.add_argument("--repeat", type=positive, default=1)
    swe_export.add_argument("--model-name", required=True)
    swe_manifest = commands.add_parser(
        "swebench-manifest", help="Join a frozen lock with operator-selected public tests."
    )
    swe_manifest.add_argument("--lock", required=True, type=Path)
    swe_manifest.add_argument("--workspaces", required=True, type=Path)
    swe_manifest.add_argument("--output", required=True, type=Path)
    swe_plan = commands.add_parser(
        "swebench-eval-plan", help="Write an official evaluation command without executing it."
    )
    swe_plan.add_argument("--lock", required=True, type=Path)
    swe_plan.add_argument("--predictions", required=True, type=Path)
    swe_plan.add_argument("--task-repo", required=True, type=Path)
    swe_plan.add_argument("--output", required=True, type=Path)
    swe_plan.add_argument("--run-id", required=True)
    swe_plan.add_argument("--workers", type=positive, default=1)
    args = parser.parse_args()
    try:
        if args.command == "web":
            from .web import serve
            serve(args.model_config, args.port, not args.no_browser)
            return 0
        if args.command == "summarize":
            print(json.dumps(summarize(args.results), indent=2))
            return 0
        if args.command == "validate-manifest":
            rows = validate_tasks(load_manifest(args.manifest), PytestRunner(args.image, args.timeout))
            print(json.dumps(rows, indent=2))
            return 0 if all(row["status"] == "valid" for row in rows) else 1
        if args.command == "batch":
            modes = args.mode or ["single", "feedback", "memory"]
            factory = lambda: ChatDecider(args.completion_tokens, args.model_config)
            result = run_batch(
                load_manifest(args.manifest), args.output, factory,
                PytestRunner(args.image, args.timeout), modes=modes, repeats=args.repeats,
                calls=args.calls, attempts=args.attempts,
            )
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "batch-report":
            print(json.dumps(report_batch(args.output), indent=2))
            return 0
        if args.command == "swebench-freeze":
            result = freeze_selection(args.task_repo, args.selection, args.output)
            print(json.dumps({"instances": len(result["instances"]), "output": str(args.output)}, indent=2))
            return 0
        if args.command == "swebench-export":
            result = export_predictions(
                args.lock, args.batch_output, args.output, mode=args.mode,
                repeat=args.repeat, model_name=args.model_name,
            )
            print(json.dumps({"predictions": len(result), "output": str(args.output)}, indent=2))
            return 0
        if args.command == "swebench-manifest":
            result = write_patchlab_manifest(args.lock, args.workspaces, args.output)
            print(json.dumps({"tasks": len(result["tasks"]), "output": str(args.output)}, indent=2))
            return 0
        if args.command == "swebench-eval-plan":
            result = write_evaluation_plan(
                args.lock, args.predictions, args.task_repo, args.output,
                run_id=args.run_id, workers=args.workers,
            )
            print(json.dumps(result, indent=2))
            return 0
        runner = PytestRunner(args.image, args.timeout)
        gate = approve if args.approve else None
        if args.command == "demo":
            result = run_demo(args.output, args.mode, runner, gate)
        else:
            task = Task(args.repo, args.revision, args.issue, args.editable, args.target, args.suite)
            result = execute(task, args.output, ChatDecider(args.completion_tokens, args.model_config), runner,
                             mode=args.mode, calls=args.calls, attempts=args.attempts, approve=gate)
        print(json.dumps({"status": result["status"], "attempts": result["attempts"],
                          "reason": result.get("reason"),
                          "result": str(args.output / "result.json")}, ensure_ascii=True))
        return 0 if result["status"] == "verified" else 1
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"PatchLab: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
