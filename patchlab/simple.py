"""Accessible repair workflow with a generated, independently run reproducer."""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import time
from typing import Callable

from .workbench import Workbench, PytestRunner
from .resilience import retry
from .memory import compact_evidence


EXCLUDE = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "runs", "dist", "build"}


def copy_project(source: Path, dest: Path) -> None:
    """Capture current files without Git history, environment files, or links."""
    total = 0
    dest.mkdir()
    for current, directories, files in os.walk(source, followlinks=False):
        base = Path(current)
        directories[:] = [d for d in directories if d not in EXCLUDE and not d.startswith(".") and not (base / d).is_symlink()]
        for name in files:
            if name.startswith("."):
                continue
            path = base / name
            if path.is_symlink() or not path.is_file():
                continue
            total += path.stat().st_size
            if total > 30_000_000:
                raise ValueError("项目快照超过 30 MB，请选择较小的项目或清理生成文件。")
            target = dest / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def editable_files(root: Path) -> list[str]:
    allowed = []
    for p in root.rglob("*.py"):
        name = p.relative_to(root).as_posix()
        parts = PurePosixPath(name.lower()).parts
        if (re.fullmatch(r"[A-Za-z0-9_./-]+", name)
            and not any(x.startswith(".") or x in {"test", "tests", "testing", "fixtures"} for x in parts[:-1])
            and parts[-1] not in {"conftest.py", "tests.py"}
            and not parts[-1].startswith("test_") and not parts[-1].endswith("_test.py")):
            allowed.append(name)
    return sorted(allowed)


def valid_reproducer(code: object) -> str:
    if not isinstance(code, str) or not 1 <= len(code) <= 6000 or "\x00" in code:
        raise ValueError("复现测试必须是长度不超过 6000 字符的 Python 代码。")
    tree = ast.parse(code)
    functions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")]
    if not functions or not any(isinstance(n, ast.Assert) for f in functions for n in ast.walk(f)):
        raise ValueError("复现测试需要包含 test_ 函数和表达预期行为的 assert。")
    return code.rstrip() + "\n"


def execute_simple(repo: Path, issue: str, steps: str, output: Path, model, runner: PytestRunner,
                   *, session_context: str = "", event_sink: Callable[[dict], None] | None = None,
                   calls: int = 20) -> dict:
    output = output.resolve()
    if output.is_relative_to(repo.resolve()):
        raise ValueError("结果目录不能位于目标项目内。")
    output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    result = {"status": "execution_error", "mode": "simple", "model": model.model,
              "attempts": 0, "model_calls": 0, "verified_candidates": 0}
    with (output / "events.jsonl").open("w", encoding="utf-8") as log:
        def record(event, **details):
            entry = {"event": event, "at_seconds": round(time.monotonic() - start, 3), **details}
            log.write(json.dumps(entry, ensure_ascii=True) + "\n")
            log.flush()
            if event_sink:
                event_sink(entry)
        try:
            if hasattr(model, "on_retry"):
                model.on_retry = lambda info: record("model_retry", **info)
            with tempfile.TemporaryDirectory(prefix="patchlab-simple-") as tmp:
                area = Path(tmp)
                frozen = area / "source"
                copy_project(repo.resolve(), frozen)
                allowed = editable_files(frozen)
                bench = Workbench(frozen, allowed)
                record("started", mode="simple", editable_count=len(allowed))
                observations = []
                feedback = []
                evidence_summary = ""
                repro = None
                for _ in range(calls):
                    evidence_summary, observations, feedback = compact_evidence(
                        model, evidence_summary, observations, feedback, record)
                    context = {"workflow": "simple", "issue": issue[:8000], "user_steps": steps[:4000],
                               "session_context": session_context, "editable": allowed[:300],
                               "recent_inspection": list(observations), "repair_feedback": list(feedback),
                               "evidence_summary": evidence_summary,
                               "reproducer_confirmed": repro is not None, "reproducer": repro}
                    result["model_calls"] += 1
                    action, usage = model.decide(context)
                    record("decision", action=action, usage=usage)
                    kind = action.get("kind")
                    if kind == "stop":
                        result.update(status="needs_information", reason=str(action.get("reason", "需要更多复现步骤"))[:2000])
                        break
                    if kind in ("files", "search", "read"):
                        try:
                            evidence = retry(lambda: bench.inspect(action),
                                             on_retry=lambda info: record("tool_retry", tool=kind, **info))
                        except (ValueError, OSError) as exc:
                            evidence = {"error": str(exc)}
                        observations.append({"request": action, "response": evidence})
                        record("inspection", **evidence)
                        continue
                    if kind == "reproduce":
                        try:
                            test = valid_reproducer(action.get("code"))
                            check = area / f"repro-{result['model_calls']}"
                            shutil.copytree(frozen, check)
                            filename = "test_patchlab_generated_reproducer.py"
                            if (frozen / filename).exists():
                                raise ValueError("项目包含保留的复现文件名。")
                            (check / filename).write_text(test, encoding="utf-8", newline="\n")
                            observed = runner.run(check, [filename])
                            record("reproducer_test", **observed)
                            if observed["exit_code"] == 1 and not observed["timed_out"] and "AssertionError" in observed["output"]:
                                repro = test
                                (output / "reproducer.py").write_text(test, encoding="utf-8")
                                feedback.append({"stage": "reproduction", "result": "failing assertion confirmed", "output": observed["output"][-2000:]})
                            else:
                                feedback.append({"stage": "reproduction", "result": "not confirmed; need a failing assertion", "output": observed["output"][-2000:]})
                        except (ValueError, SyntaxError) as exc:
                            feedback.append({"stage": "reproduction", "error": str(exc)})
                        continue
                    if kind == "propose":
                        if repro is None:
                            feedback.append({"stage": "proposal", "error": "First confirm a failing reproduction test."})
                            continue
                        result["attempts"] += 1
                        number = result["attempts"]
                        try:
                            patch, changes = bench.prepare(action.get("edits"))
                            (output / f"candidate-{number}.patch").write_bytes(patch.encode())
                            candidate = area / f"candidate-{number}"
                            bench.stage(candidate, changes)
                            filename = "test_patchlab_generated_reproducer.py"
                            (candidate / filename).write_text(repro, encoding="utf-8", newline="\n")
                            result["verified_candidates"] += 1
                            focused = runner.run(candidate, [filename])
                            record("candidate_target", attempt=number, **focused)
                            regression = None
                            existing_tests = [p.relative_to(candidate).as_posix() for p in candidate.rglob("*.py")
                                              if (p.name.startswith("test_") or p.name.endswith("_test.py"))
                                              and p.name != filename and not any(part in EXCLUDE for part in p.relative_to(candidate).parts)]
                            if focused["exit_code"] == 0 and not focused["timed_out"] and existing_tests:
                                regression = runner.run(candidate, sorted(existing_tests))
                                record("candidate_regression", attempt=number, **regression)
                            if focused["exit_code"] == 0 and not focused["timed_out"] and (regression is None or (regression["exit_code"] == 0 and not regression["timed_out"])):
                                (output / "final.patch").write_bytes(patch.encode())
                                result.update(status="verified" if regression else "reproducer_passed_no_regression",
                                              diagnosis=str(action.get("diagnosis", ""))[:2000],
                                              regression_tests=len(existing_tests))
                                break
                            failed = regression or focused
                            feedback.append({"stage": "regression" if regression else "target", "output": failed["output"][-2000:]})
                            record("candidate_rejected", attempt=number, failure="测试未通过")
                        except (ValueError, SyntaxError, UnicodeError) as exc:
                            feedback.append({"stage": "proposal", "error": str(exc)})
                            record("candidate_rejected", attempt=number, failure=str(exc))
                        if number >= 5:
                            result["status"] = "proposal_limit"
                            break
                        continue
                    feedback.append({"error": "Unknown action; use files, search, read, reproduce, propose, or stop."})
                else:
                    result.update(status="needs_information", reason="未能在调用预算内完成复现或修复，请提供更多复现步骤。")
        except Exception as exc:
            result["reason"] = str(exc)[:2000]
            record("error", error_type=type(exc).__name__, message=result["reason"])
        finally:
            result["elapsed_seconds"] = round(time.monotonic() - start, 3)
            record("finished", status=result["status"])
            (output / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return result
