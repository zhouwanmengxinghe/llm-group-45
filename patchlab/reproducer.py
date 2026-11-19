"""Issue-grounded test contracts fixed before any source patch is proposed."""
from __future__ import annotations

import ast
import re


FILENAME = "test_patchlab_issue_reproducer.py"
FORBIDDEN_IMPORTS = {"os", "sys", "pathlib", "subprocess", "socket", "urllib",
                     "http", "importlib", "inspect", "builtins"}
FORBIDDEN_CALLS = {"open", "exec", "eval", "compile", "__import__", "input"}


def validate(code: object) -> str:
    if not isinstance(code, str) or not 1 <= len(code) <= 6000 or "\x00" in code:
        raise ValueError("Reproducer must be Python text of at most 6000 characters.")
    tree = ast.parse(code)
    tests = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
    if not tests or not any(isinstance(n, ast.Assert) for f in tests for n in ast.walk(f)):
        raise ValueError("Define top-level def test_control() and def test_issue() functions with plain assert statements, not unittest or pytest classes.")
    names = {n.name for n in tests}
    if not {"test_control", "test_issue"}.issubset(names):
        raise ValueError("Provide test_control for a known healthy input and test_issue for the reported defect, using the same public API.")
    for node in ast.walk(tree):
        roots = []
        if isinstance(node, ast.Import):
            roots = [n.name.split(".")[0] for n in node.names]
        elif isinstance(node, ast.ImportFrom):
            roots = [(node.module or "").split(".")[0]]
        if FORBIDDEN_IMPORTS.intersection(roots):
            raise ValueError("Use public project APIs and in-memory inputs; no filesystem, process, or network inspection.")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
                raise ValueError("Dynamic execution and filesystem access are not reproducer tools.")
            if isinstance(node.func, ast.Attribute) and node.func.attr in {
                    "read_text", "read_bytes", "write_text", "write_bytes", "system", "popen"}:
                raise ValueError("Test behavior rather than source text or external commands.")
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Constant):
            raise ValueError("Assertions must check project behavior, not a constant.")
    return code.rstrip() + "\n"


def is_configuration_failure(output: str) -> bool:
    plain = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output)
    warning_error = re.search(r"^E\s+[\w.]*Warning:", plain, re.MULTILINE)
    return bool(warning_error) or any(marker in plain for marker in (
        "ModuleNotFoundError:", "django.core.exceptions.ImproperlyConfigured:",
        "No module named pytest", "CERTIFICATE_VERIFY_FAILED", "Network is unreachable",
    ))


def has_behavioral_failure(output: str) -> bool:
    plain = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output)
    return re.search(r"^E\s+(?:AssertionError\b|assert\b)", plain, re.MULTILINE) is not None


def healthy_control_passed(output: str) -> bool:
    plain = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output)
    node = r"\S+::test_control(?:\[[^\]]*\])?"
    passed = re.search(r"^(?:PASSED\s+" + node + r"\s*|" + node + r"\s+PASSED(?:\s+\[\s*\d+%\])?\s*)$", plain, re.MULTILINE)
    failed = re.search(r"^(?:(?:FAILED|ERROR|SKIPPED|XFAIL|XPASS)\s+" + node + r"(?:\s|$)|" + node + r"\s+(?:FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b)", plain, re.MULTILINE)
    return bool(passed) and not failed
