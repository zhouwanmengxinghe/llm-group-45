"""Preserve pytest 3 expression-style raises used by the 2014 test suite.

The expression executes in its caller's scope and must raise the specified
exception, exactly as with the historical API. No assertions are suppressed.
Only load this plugin for the isolated legacy benchmark, never the Agent UI.
"""
import sys
from types import SimpleNamespace
import pytest

_raises = pytest.raises


def legacy_raises(expected, *args, **kwargs):
    if len(args) == 1 and isinstance(args[0], str):
        caller = sys._getframe(1)
        try:
            with _raises(expected, **kwargs) as captured:
                exec(args[0], caller.f_globals, caller.f_locals)
            return captured
        finally:
            del caller
    return _raises(expected, *args, **kwargs)


def pytest_configure(config):
    pytest.raises = legacy_raises


@pytest.fixture(scope="session")
def httpbin():
    return SimpleNamespace(url="http://localhost")


@pytest.fixture(scope="session")
def httpbin_secure():
    return SimpleNamespace(url="https://localhost")
