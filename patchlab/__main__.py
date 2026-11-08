"""Command line for repair runs and comparison of recorded results."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from statistics import median
import sys

from .decision import ChatDecider
from .demo import run_demo
from .experiment import Task, execute
from .workbench import PytestRunner


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
    args = parser.parse_args()
    try:
        if args.command == "web":
            from .web import serve
            serve(args.model_config, args.port, not args.no_browser)
            return 0
        if args.command == "summarize":
            print(json.dumps(summarize(args.results), indent=2))
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
