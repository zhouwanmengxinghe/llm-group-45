"""One task, one frozen checkout, and independently verified proposals."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import time
from typing import Callable, Protocol

from .workbench import PytestRunner, Workbench, snapshot
from .resilience import retry
from .memory import compact_evidence


class Decider(Protocol):
    model: str

    def decide(self, context: dict) -> tuple[dict, dict | None]: ...


@dataclass
class Task:
    repository: Path
    revision: str
    issue: str
    editable: list[str]
    target: list[str]
    suite: list[str]
    external_evaluation: str | None = None


def execute(
    task: Task, output: Path, model: Decider, runner: PytestRunner, *,
    mode: str = "feedback", calls: int = 16, attempts: int = 5,
    approve: Callable[[str, str], bool] | None = None,
    event_sink: Callable[[dict], None] | None = None,
    session_context: str = "",
) -> dict:
    output = output.resolve()
    if output.is_relative_to(task.repository.resolve()):
        raise ValueError("Output must be outside the target repository.")
    output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    result = {
        "status": "execution_error", "mode": mode, "model": model.model,
        "attempts": 0, "verified_candidates": 0, "model_calls": 0,
        "inspection_calls": 0, "tokens_reported": 0, "calls_with_usage": 0,
        "call_limit": calls, "attempt_limit": 1 if mode == "single" else attempts,
        "completion_limit": getattr(model, "completion_limit", None),
        "test_timeout": runner.timeout, "approval_enabled": approve is not None,
        "target": task.target, "suite": task.suite, "container_image": runner.image,
        "external_evaluation": task.external_evaluation,
    }
    with (output / "events.jsonl").open("w", encoding="utf-8") as events:
        def record(event: str, **details):
            entry = {"event": event, "at_seconds": round(time.monotonic() - start, 3), **details}
            events.write(json.dumps(entry, ensure_ascii=True) + "\n")
            events.flush()
            if event_sink is not None:
                event_sink(entry)

        try:
            if hasattr(model, "on_retry"):
                model.on_retry = lambda info: record("model_retry", **info)
            with TemporaryDirectory(prefix="patchlab-") as temp:
                area = Path(temp)
                frozen = area / "frozen"
                result["revision"] = snapshot(task.repository, task.revision, frozen)
                bench = Workbench(frozen, task.editable)
                record("started", revision=result["revision"], mode=mode, model=model.model)
                for selector in task.target + task.suite:
                    name = selector.split("::", 1)[0]
                    path = (frozen / name).resolve()
                    if not name or not path.is_relative_to(frozen.resolve()) or not path.exists():
                        raise ValueError(f"Invalid pytest selector: {selector}")
                check = area / "initial"
                shutil.copytree(frozen, check)
                if task.external_evaluation:
                    if task.target:
                        raise ValueError("externally evaluated tasks must not expose scoring tests as targets")
                    initial = runner.run(check, task.suite)
                    record("initial_public_suite", **initial)
                    result["initial_public_suite"] = initial
                    if initial["timed_out"] or initial["exit_code"] not in {0, 1}:
                        result["status"] = "initial_test_error"
                        return result
                else:
                    initial = runner.run(check, task.target)
                    record("initial_target", **initial)
                    result["initial_target"] = initial
                    if initial["timed_out"] or initial["exit_code"] != 1:
                        result["status"] = "bug_not_reproduced" if initial["exit_code"] == 0 else "initial_test_error"
                        return result

                observations: list[dict] = []
                history: list[dict] = []
                evidence_summary = ""
                limit = result["attempt_limit"]
                seen: set[str] = set()
                for _ in range(calls):
                    evidence_summary, observations, history = compact_evidence(
                        model, evidence_summary, observations, history if mode == "memory" else history[-1:], record)
                    context = {
                        "issue": task.issue[:8000], "editable": task.editable,
                        "session_context": session_context,
                        "initial_failure": initial["output"][-4500:],
                        "verification_policy": (
                            "Official SWE-bench tests are withheld. Produce a candidate that preserves the "
                            "public regression suite; external evaluation will determine resolution."
                            if task.external_evaluation else
                            "The supplied reproducer and regression suite determine local verification."
                        ),
                        "recent_inspection": list(observations),
                        "evidence_summary": evidence_summary,
                        "repair_feedback": history[-5:] if mode == "memory" else history[-1:],
                        "proposals_remaining": limit - result["attempts"],
                    }
                    result["model_calls"] += 1
                    action, usage = model.decide(context)
                    tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
                    if type(tokens) is int and tokens >= 0:
                        result["tokens_reported"] += tokens
                        result["calls_with_usage"] += 1
                    kind = action.get("kind")
                    record("decision", action=action, usage=usage)
                    if kind == "stop":
                        result["status"] = "model_stopped"
                        result["reason"] = str(action.get("reason", ""))[:2000]
                        return result
                    if kind != "propose":
                        if kind in ("files", "search", "read"):
                            result["inspection_calls"] += 1
                        try:
                            evidence = retry(lambda: bench.inspect(action),
                                             on_retry=lambda info: record("tool_retry", tool=kind, **info))
                        except (ValueError, OSError) as exc:
                            evidence = {"error": str(exc)}
                        observations.append({"request": action, "response": evidence})
                        record("inspection", **evidence)
                        continue

                    result["attempts"] += 1
                    number = result["attempts"]
                    candidate = area / f"candidate-{number}"
                    diagnosis = str(action.get("diagnosis", ""))[:2000]
                    feedback = {"attempt": number}
                    if mode == "memory":
                        feedback["diagnosis"] = diagnosis
                    try:
                        patch, changes = bench.prepare(action.get("edits"))
                        digest = sha256(patch.encode()).hexdigest()
                        (output / f"candidate-{number}.patch").write_bytes(patch.encode())
                        if mode == "memory":
                            feedback["edits"] = [
                                {"path": e["path"], "before": e["before"][:160], "after": e["after"][:160]}
                                for e in action["edits"]
                            ]
                        if mode == "memory" and digest in seen:
                            feedback["failure"] = "This exact patch has already been proposed."
                        elif approve is not None and not approve(diagnosis, patch):
                            feedback["failure"] = "Reviewer rejected the candidate."
                        else:
                            bench.stage(candidate, changes)
                            result["verified_candidates"] += 1
                            if task.external_evaluation:
                                focused = None
                                regression = runner.run(candidate, task.suite)
                                record("candidate_public_suite", attempt=number, **regression)
                            else:
                                focused = runner.run(candidate, task.target)
                                record("candidate_target", attempt=number, **focused)
                                regression = None
                                if not focused["timed_out"] and focused["exit_code"] == 0:
                                    regression = runner.run(candidate, task.suite)
                                    record("candidate_regression", attempt=number, **regression)
                            if regression and not regression["timed_out"] and regression["exit_code"] == 0:
                                (output / "final.patch").write_bytes(patch.encode())
                                if task.external_evaluation:
                                    result.update(
                                        status="candidate_ready", diagnosis=diagnosis,
                                        public_suite_result=regression,
                                    )
                                else:
                                    result.update(status="verified", diagnosis=diagnosis,
                                                  target_result=focused, regression_result=regression)
                                return result
                            failed = regression or focused
                            feedback.update(
                                stage=("public_suite" if task.external_evaluation else
                                       "regression" if regression else "target"),
                                failure="timeout" if failed["timed_out"] else f"pytest exit {failed['exit_code']}",
                                evidence=failed["output"][-2200:],
                            )
                        seen.add(digest)
                    except (ValueError, SyntaxError) as exc:
                        feedback["failure"] = str(exc)
                    record("candidate_rejected", **feedback)
                    history.append(feedback)
                    if number == limit:
                        result["status"] = "proposal_limit"
                        return result
                result["status"] = "decision_limit"
        except Exception as exc:
            result["reason"] = str(exc)[:2000]
            record("error", error_type=type(exc).__name__, message=result["reason"])
        finally:
            result["elapsed_seconds"] = round(time.monotonic() - start, 3)
            record("finished", status=result["status"])
            (output / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n",
                                                encoding="utf-8")
    return result
