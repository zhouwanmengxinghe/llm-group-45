import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location(
    "legacy_fixture", Path(__file__).resolve().parents[1] /
    "benchmarks/requests-network/legacy_pytest.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def test_legacy_expression_uses_caller_locals_and_checks_exception():
    value = "evidence"
    def operation(text):
        raise ValueError(text)
    captured = fixture.legacy_raises(ValueError, "operation(value)")
    assert str(captured.value) == value


def test_legacy_expression_fails_when_exception_is_absent():
    with pytest.raises(pytest.fail.Exception):
        fixture.legacy_raises(ValueError, "1 + 1")


def test_legacy_expression_does_not_suppress_wrong_exception():
    with pytest.raises(KeyError):
        fixture.legacy_raises(ValueError, "{}['missing']")


def test_modern_context_manager_is_preserved():
    with fixture.legacy_raises(ValueError, match="expected"):
        raise ValueError("expected")
