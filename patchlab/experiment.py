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
from .diagnostics import excerpt
from .repair_memory import RepairMemory
from .patch_application import save_application
from .reproducer import (FILENAME as REPRODUCER_FILE, validate as validate_reproducer,
                         is_configuration_failure, has_behavioral_failure)
from .reproducer import healthy_control_passed


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
    guided: bool = True,
    require_reproducer: bool = False,
) -> dict:
    output = output.resolve()
    if output.is_relative_to(task.repository.resolve()):
        raise ValueError("Output must be outside the target repository.")
    output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    needs_reproducer = bool(task.external_evaluation)
    fallback_candidate = None
    result = {
        "status": "execution_error", "mode": mode, "model": model.model,
        "attempts": 0, "verified_candidates": 0, "model_calls": 0,
        "inspection_calls": 0, "tokens_reported": 0, "calls_with_usage": 0,
        "provider_requests": None, "provider_responses_with_usage": None,
        "provider_tokens_reported": None, "provider_usage_complete": False,
        "provider_requests_by_purpose": {},
        "call_limit": calls, "attempt_limit": 1 if mode == "single" else attempts,
        "completion_limit": getattr(model, "completion_limit", None),
        "test_timeout": runner.timeout, "approval_enabled": approve is not None,
        "target": task.target, "suite": task.suite, "container_image": runner.image,
        "container_python": runner.python_executable,
        "test_program": runner.test_program,
        "test_suffix": runner.test_suffix,
        "external_evaluation": task.external_evaluation,
        "guided": guided,
        "issue_reproducer_enabled": needs_reproducer,
        "issue_reproducer_required": needs_reproducer and require_reproducer,
        "reproducer_attempts": 0, "reproducer_confirmed": False,
    }
    snapshot_usage = getattr(model, "usage_snapshot", None)
    provider_start = snapshot_usage() if callable(snapshot_usage) else None
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
            if hasattr(model, "on_cache_hit"):
                model.on_cache_hit = lambda info: record("paired_prefix_replay", **info)
            with TemporaryDirectory(prefix="patchlab-") as temp:
                area = Path(temp)
                frozen = area / "frozen"
                result["revision"] = snapshot(task.repository, task.revision, frozen)
                bench = Workbench(frozen, task.editable)
                record("started", revision=result["revision"], mode=mode, model=model.model)
                runner.validate_selectors(frozen, task.target + task.suite)
                check = area / "initial"
                shutil.copytree(frozen, check)
                if task.external_evaluation:
                    if task.target:
                        raise ValueError("externally evaluated tasks must not expose scoring tests as targets")
                    initial = runner.run(check, task.suite)
                    record("initial_public_suite", **initial)
                    result["initial_public_suite"] = initial
                    if initial["timed_out"] or initial["exit_code"] != 0:
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
                duplicate_streak = 0
                recovering_duplicate = False
                result["duplicate_proposals"] = 0
                inspected: dict[str, dict] = {}
                last_proposal_step = 0
                failure_memory = RepairMemory()
                reproducer = None
                reproducer_baseline_failure = ""
                semantic_rejection_seen = False
                reproducer_runner = PytestRunner(runner.image, min(60, runner.timeout), runner.python_executable,
                                                 test_suffix=["-W", "default", "-rA", "-vv"])
                if needs_reproducer and (frozen / REPRODUCER_FILE).exists():
                    raise ValueError("Reserved reproducer filename already exists in the repository")
                for step in range(calls):
                    evidence_summary, observations, history = compact_evidence(
                        model, evidence_summary, observations, history[-1:], record)
                    context = {
                        "workflow": "external" if needs_reproducer else "supplied_tests",
                        "patch_attempts": result["attempts"],
                        "issue": task.issue[:8000], "editable": task.editable,
                        "session_context": session_context,
                        "initial_failure": excerpt(initial["output"], 4500),
                        "verification_policy": (
                            "Official SWE-bench tests are withheld. Produce a candidate that preserves the "
                            "public regression suite; external evaluation will determine resolution."
                            if task.external_evaluation else
                            "The supplied reproducer and regression suite determine local verification."
                        ),
                        "recent_inspection": list(observations),
                        "evidence_summary": evidence_summary,
                        "repair_feedback": failure_memory.view() if mode == "memory" and result["attempts"] else history[-1:],
                        "reproducer_confirmed": reproducer is not None,
                        "reproducer": reproducer,
                        "reproducer_budget_remaining": max(0, 2-result["reproducer_attempts"]) if not result["attempts"] else 0,
                        "reproducer_baseline_failure": reproducer_baseline_failure,
                        "decisions_remaining": calls - step,
                        "next_action_constraint": (
                            ("Submit a minimal issue-grounded reproducer now, or stop with missing evidence. "
                             if needs_reproducer and reproducer is None and result["reproducer_attempts"] < 2 else
                             "Propose a concrete minimal patch now, or stop with the missing evidence. ") +
                            "Further repository inspection is not allowed this turn."
                            if guided and (
                                (result["attempts"] == 0 and step >= max(2, calls // 2))
                                or (result["attempts"] > 0 and step - last_proposal_step >= 3)
                                or calls - step <= 2
                            ) else ""
                        ),
                    }
                    if result["attempts"]:
                        context["proposals_remaining"] = limit - result["attempts"]
                    if recovering_duplicate:
                        context["duplicate_recovery"] = {
                            "consecutive_duplicates": duplicate_streak,
                            "stop_after": 3,
                            "original_failure": history[-1:] ,
                        }
                        context["next_action_constraint"] = (
                            "The last patch repeats a rejected candidate and was not tested again. "
                            "Read or search NEW evidence, propose a DIFFERENT patch with a diagnosis "
                            "explaining how it addresses the observed failure, or stop explicitly. "
                            "If requirements conflict, report the conflict instead of resubmitting. "
                            "Duplicate proposals use model-call/token budget, not repair-candidate budget.")
                    if mode == "memory" and result["attempts"] and failure_memory.entries:
                        context["memory_policy"] = (
                            "Use the pinned failure ledger. Preserve the frozen test contract. "
                            "Avoid identical failed candidates, but a failed patch can contain a useful partial fix. "
                            "Every candidate starts from the original base: compose all still-needed earlier edits. "
                            "Explain how the observed failure changes the hypothesis.")
                    with (output / "contexts.jsonl").open("a", encoding="utf-8") as context_log:
                        context_log.write(json.dumps(context, ensure_ascii=True) + "\n")
                    result["model_calls"] += 1
                    action, usage = model.decide(context)
                    tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
                    if type(tokens) is int and tokens >= 0:
                        result["tokens_reported"] += tokens
                        result["calls_with_usage"] += 1
                    kind = action.get("kind")
                    record("decision", action=action, usage=usage)
                    if kind == "reproduce" and needs_reproducer:
                        result["reproducer_attempts"] += 1
                        feedback = {"stage": "reproducer_setup"}
                        try:
                            if reproducer is not None:
                                raise ValueError("The confirmed test contract is frozen and cannot be replaced.")
                            if result["attempts"] or result["reproducer_attempts"] > 2:
                                raise ValueError("Reproducer preparation budget ended. Preserve the contract if any and propose source edits from available evidence.")
                            code = validate_reproducer(action.get("code"))
                            probe = area / f"reproducer-{result['reproducer_attempts']}"
                            shutil.copytree(frozen, probe)
                            (probe / REPRODUCER_FILE).write_text(code, encoding="utf-8", newline="\n")
                            (output / f"reproducer-{result['reproducer_attempts']}.py").write_text(code, encoding="utf-8")
                            baseline = reproducer_runner.run(probe, [REPRODUCER_FILE])
                            record("reproducer_test", **baseline)
                            if (not baseline["timed_out"] and baseline["exit_code"] == 1
                                    and not is_configuration_failure(baseline["output"])
                                    and has_behavioral_failure(baseline["output"])
                                    and healthy_control_passed(baseline["output"])):
                                reproducer = code
                                reproducer_baseline_failure = excerpt(baseline["output"], 1800)
                                history = []
                                failure_memory.entries.clear()
                                result.update(reproducer_confirmed=True,
                                              reproducer_control_passed=True,
                                              reproducer_sha256=sha256(code.encode()).hexdigest())
                                (output / "reproducer.py").write_text(code, encoding="utf-8")
                                record("reproducer_confirmed", sha256=result["reproducer_sha256"])
                                observations.append({"request": {"kind": "reproduce"},
                                                     "response": {"confirmed": True, "failure": excerpt(baseline["output"])}})
                                continue
                            feedback.update(failure="On the unchanged base, test_control must PASS on a known healthy input of the same API, while test_issue must fail a behavioral assertion. Do not invent unrelated return-shape assumptions. Use healthy behavior as the oracle when appropriate. Catch reported exceptions explicitly and initialize required API options.",
                                            evidence=excerpt(baseline["output"]))
                        except (ValueError, SyntaxError) as exc:
                            feedback["failure"] = str(exc)
                        history.append(feedback)
                        failure_memory.reject(action, feedback)
                        record("reproducer_rejected", **feedback)
                        continue
                    if kind == "stop":
                        result["status"] = "model_stopped"
                        result["reason"] = str(action.get("reason", ""))[:2000]
                        return result
                    if kind != "propose":
                        if kind in ("files", "search", "read"):
                            result["inspection_calls"] += 1
                        try:
                            inspection_key = json.dumps(action, sort_keys=True)
                            if guided and inspection_key in inspected:
                                evidence = {**inspected[inspection_key], "already_inspected": True,
                                            "guidance": "This exact inspection was already completed. Use this evidence to propose a patch or inspect a different location."}
                                record("inspection_cache_hit", action=action)
                            else:
                                evidence = retry(lambda: bench.inspect(action),
                                                 on_retry=lambda info: record("tool_retry", tool=kind, **info))
                                if guided and kind in {"read", "search", "files"}:
                                    inspected[inspection_key] = evidence
                                if kind in {"read", "search", "files"} and "error" not in evidence:
                                    recovering_duplicate = False
                        except (ValueError, OSError) as exc:
                            evidence = {"error": str(exc)}
                        observations = [o for o in observations if o.get("request") != action]
                        observations.append({"request": action, "response": evidence})
                        record("inspection", **evidence)
                        continue

                    if needs_reproducer and require_reproducer and reproducer is None:
                        observations.append({"request": {"kind": "propose"}, "response": {
                            "error": "Confirm an issue-grounded failing reproducer before proposing source edits."}})
                        continue
                    if recovering_duplicate and not str(action.get("diagnosis", "")).strip():
                        observations.append({"request": action, "response": {
                            "error": "A revised failure diagnosis is required before a new candidate."}})
                        continue
                    result["attempts"] += 1
                    last_proposal_step = step
                    number = result["attempts"]
                    candidate = area / f"candidate-{number}"
                    diagnosis = str(action.get("diagnosis", ""))[:2000]
                    feedback = {"attempt": number, "diagnosis": diagnosis}
                    try:
                        patch, changes = bench.prepare(action.get("edits"))
                        digest = sha256(patch.encode()).hexdigest()
                        if digest in seen:
                            result["attempts"] -= 1
                            result["duplicate_proposals"] += 1
                            duplicate_streak += 1
                            recovering_duplicate = True
                            record("duplicate_proposal", sha256=digest,
                                   consecutive_duplicates=duplicate_streak,
                                   effective_attempts=result["attempts"])
                            observations.append({"request": {"kind": "propose"}, "response": {
                                "error": "Identical rejected patch; no new candidate or test execution.",
                                "consecutive_duplicates": duplicate_streak}})
                            if duplicate_streak >= 3:
                                result["status"] = "stagnated"
                                result["reason"] = "Three duplicate proposals without a novel candidate."
                                return result
                            continue
                        duplicate_streak = 0
                        recovering_duplicate = False
                        (output / f"candidate-{number}.patch").write_bytes(patch.encode())
                        feedback["edits"] = [
                                {"path": e["path"], "before": e["before"][:160], "after": e["after"][:160]}
                                for e in action["edits"]
                            ]
                        if approve is not None and not approve(diagnosis, patch):
                            feedback["failure"] = "Reviewer rejected the candidate."
                        else:
                            bench.stage(candidate, changes)
                            result["verified_candidates"] += 1
                            if task.external_evaluation:
                                focused = None
                                if reproducer is not None:
                                    (candidate / REPRODUCER_FILE).write_text(reproducer, encoding="utf-8", newline="\n")
                                    focused = reproducer_runner.run(candidate, [REPRODUCER_FILE])
                                    record("candidate_reproducer", attempt=number, **focused)
                                regression = runner.run(candidate, task.suite)
                                record("candidate_public_suite", attempt=number, **regression)
                                if not regression["timed_out"] and regression["exit_code"] == 0 and fallback_candidate is None:
                                    fallback_candidate = {"patch": patch, "diagnosis": diagnosis,
                                                          "public": regression, "focused": focused,
                                                          "attempt": number}
                            else:
                                focused = runner.run(candidate, task.target)
                                record("candidate_target", attempt=number, **focused)
                                regression = None
                                if not focused["timed_out"] and focused["exit_code"] == 0:
                                    regression = runner.run(candidate, task.suite)
                                    record("candidate_regression", attempt=number, **regression)
                            public_ok = regression and not regression["timed_out"] and regression["exit_code"] == 0
                            contract_ok = focused is None or (not focused["timed_out"] and focused["exit_code"] == 0)
                            if public_ok and (not task.external_evaluation or contract_ok or (mode == "single" and not require_reproducer)):
                                if not task.external_evaluation:
                                    save_application(output, task.repository, frozen, changes, patch)
                                (output / "final.patch").write_bytes(patch.encode())
                                if task.external_evaluation:
                                    result.update(
                                        status="candidate_ready", diagnosis=diagnosis,
                                        public_suite_result=regression,
                                        reproducer_result=focused,
                                        candidate_selection="single_public_candidate" if not contract_ok else "passed_local_checks",
                                    )
                                else:
                                    result.update(status="verified", diagnosis=diagnosis,
                                                  target_result=focused, regression_result=regression)
                                result["recovered_after_semantic_failure"] = semantic_rejection_seen
                                return result
                            failed = (regression or focused) if not public_ok else focused
                            feedback.update(
                                stage=("reproducer" if task.external_evaluation and public_ok else
                                       "public_suite" if task.external_evaluation else
                                       "regression" if regression else "target"),
                                failure="timeout" if failed["timed_out"] else f"pytest exit {failed['exit_code']}",
                                evidence=excerpt(failed["output"]),
                                issue_contract_passed=bool(focused and not focused["timed_out"] and focused["exit_code"] == 0),
                            )
                            semantic_rejection_seen = True
                        seen.add(digest)
                    except (ValueError, SyntaxError) as exc:
                        feedback["failure"] = str(exc)
                    record("candidate_rejected", **feedback)
                    history.append(feedback)
                    failure_memory.reject(action, feedback)
                    (output / "repair-memory.json").write_text(
                        json.dumps(failure_memory.entries, indent=2, ensure_ascii=True), encoding="utf-8")
                    if number == limit:
                        result["status"] = "proposal_limit"
                        return result
                result["status"] = "decision_limit"
        except Exception as exc:
            result["reason"] = str(exc)[:2000]
            record("error", error_type=type(exc).__name__, message=result["reason"])
        finally:
            if (task.external_evaluation and not require_reproducer and fallback_candidate is not None
                    and not (output / "final.patch").exists()):
                result["stop_reason"] = result["status"]
                result.update(status="candidate_ready", diagnosis=fallback_candidate["diagnosis"],
                              public_suite_result=fallback_candidate["public"],
                              reproducer_result=fallback_candidate["focused"],
                              candidate_selection="retained_public_candidate",
                              selected_attempt=fallback_candidate["attempt"],
                              recovered_after_semantic_failure=False)
                (output / "final.patch").write_bytes(fallback_candidate["patch"].encode())
                record("public_candidate_retained", attempt=fallback_candidate["attempt"], stop_reason=result["stop_reason"])
            provider_end = snapshot_usage() if callable(snapshot_usage) else None
            if isinstance(provider_start, dict) and isinstance(provider_end, dict):
                result["provider_response_models"] = provider_end.get("response_models", [])
                result["effective_response_models"] = provider_end.get("effective_response_models", result["provider_response_models"])
                if "logical_request_attempts" in provider_end:
                    logical_requests = provider_end["logical_request_attempts"] - provider_start.get("logical_request_attempts", 0)
                    logical_responses = provider_end["logical_responses_with_usage"] - provider_start.get("logical_responses_with_usage", 0)
                    result["standalone_equivalent_usage_complete"] = logical_requests == logical_responses
                for source, target in (
                    ("logical_tokens_reported", "standalone_equivalent_tokens_reported"),
                    ("logical_request_attempts", "standalone_equivalent_provider_requests"),
                    ("prefix_cache_hits", "prefix_cache_hits"),
                    ("prefix_cached_decisions", "prefix_cached_decisions"),
                ):
                    if source in provider_end:
                        result[target] = provider_end[source] - provider_start.get(source, 0)
                result["provider_requests"] = (
                    provider_end.get("request_attempts", 0)
                    - provider_start.get("request_attempts", 0)
                )
                result["provider_responses_with_usage"] = (
                    provider_end.get("responses_with_usage", 0)
                    - provider_start.get("responses_with_usage", 0)
                )
                result["provider_tokens_reported"] = (
                    provider_end.get("tokens_reported", 0)
                    - provider_start.get("tokens_reported", 0)
                )
                start_purposes = provider_start.get("requests_by_purpose", {})
                end_purposes = provider_end.get("requests_by_purpose", {})
                if isinstance(start_purposes, dict) and isinstance(end_purposes, dict):
                    result["provider_requests_by_purpose"] = {
                        purpose: count - start_purposes.get(purpose, 0)
                        for purpose, count in end_purposes.items()
                        if count - start_purposes.get(purpose, 0)
                    }
                result["provider_usage_complete"] = (
                    result["provider_requests"]
                    == result["provider_responses_with_usage"]
                )
            else:
                result["provider_requests"] = result["model_calls"]
                result["provider_responses_with_usage"] = result["calls_with_usage"]
                result["provider_tokens_reported"] = result["tokens_reported"]
                result["provider_requests_by_purpose"] = {
                    "decision": result["model_calls"]
                }
                result["provider_usage_complete"] = (
                    result["model_calls"] == result["calls_with_usage"]
                )
            result["elapsed_seconds"] = round(time.monotonic() - start, 3)
            record("finished", status=result["status"])
            (output / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n",
                                                encoding="utf-8")
    return result
