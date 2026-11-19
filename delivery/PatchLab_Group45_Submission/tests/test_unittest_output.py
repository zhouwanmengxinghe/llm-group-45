import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("unittest_output", Path(__file__).resolve().parents[1] / "benchmarks/test-runtime/unittest_output.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize("status", ["ok", "FAIL", "ERROR", "skipped 'optional'"])
def test_multiline_description_preserves_actual_status(status):
    raw = "test_example (suite.Example)\nDescription of behavior. ... " + status + "\n"
    assert module.normalize_unittest_output(raw).splitlines()[-1] == "test_example (suite.Example) ... " + status
