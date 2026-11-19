import json
from pathlib import Path
import pytest

from patchlab.demo import make_fixture
from patchlab.experiment import Task, execute
from patchlab.reproducer import validate, is_configuration_failure, healthy_control_passed
from patchlab.workbench import PytestRunner


@pytest.mark.parametrize("mode", ["single", "memory"])
def test_semantic_failure_is_retried_only_with_iteration_and_contract_stays_frozen(tmp_path, mode):
    repo = tmp_path / "repo"
    make_fixture(repo)
    contract = "from interval import duration\ndef test_control():\n    assert duration(2, 7) == 5\ndef test_issue():\n    assert duration(4, 2) == 0\n"
    class Model:
        model = "contract-fixture"
        def __init__(self): self.calls = 0
        def decide(self, context):
            self.calls += 1
            if self.calls == 1:
                return {"kind": "reproduce", "code": contract}, None
            if self.calls == 3:
                return {"kind": "reproduce", "code": contract.replace("== 0", "== 2")}, None
            if self.calls == 4:
                assert context["reproducer"] == contract
                assert any(x["stage"] == "reproducer" for x in context["repair_feedback"])
                assert any("frozen" in x["failure"] for x in context["repair_feedback"])
            after = "    return abs(end - start)" if self.calls == 2 else "    return max(0, end - start)"
            return {"kind": "propose", "diagnosis": "interval behavior", "edits": [
                {"path": "interval.py", "before": "    return end - start", "after": after}]}, None
    task = Task(repo, "HEAD", "Reverse intervals should have zero duration.", ["interval.py"],
                [], ["test_interval.py::test_positive"], "swebench")
    out = tmp_path / "run"
    result = execute(task, out, Model(), PytestRunner(None, 30), mode=mode)
    if mode == "single":
        assert result["status"] == "candidate_ready"
        assert result["attempts"] == 1 and (out / "final.patch").exists()
        assert result["reproducer_result"]["exit_code"] == 1
        assert result["candidate_selection"] == "single_public_candidate"
    else:
        assert result["status"] == "candidate_ready", result
        assert result["recovered_after_semantic_failure"] is True
        assert result["attempts"] == 2
    assert (out / "reproducer.py").read_text() == contract
    events = [json.loads(x) for x in (out / "events.jsonl").read_text().splitlines()]
    assert any(x["event"] == "candidate_reproducer" and x["exit_code"] == 1 for x in events)


@pytest.mark.parametrize("code", [
    "def test_fake():\n    assert False\n",
    "from pathlib import Path\ndef test_source():\n    assert Path('/testbed/code.py').read_text()\n",
    "def test_dynamic():\n    assert eval('True')\n",
])
def test_contract_rejects_constant_and_source_inspection_or_dynamic_execution(code):
    with pytest.raises(ValueError):
        validate(code)


def test_unhandled_warning_cannot_be_mistaken_for_bug_reproduction():
    assert is_configuration_failure("E           astropy.utils.exceptions.AstropyUserWarning: missing option")
    assert not is_configuration_failure("E   AssertionError: expected value\nUserWarning in warning summary")


def test_healthy_control_must_pass_without_a_failed_parameter():
    assert healthy_control_passed("PASSED test_repro.py::test_control\nFAILED test_repro.py::test_issue")
    assert not healthy_control_passed("PASSED test_repro.py::test_control[1]\nFAILED test_repro.py::test_control[2]")


def test_legacy_verbose_pytest_control_status_is_recognized():
    assert healthy_control_passed("test_repro.py::test_control PASSED [ 50%]\ntest_repro.py::test_issue FAILED [100%]")
    assert not healthy_control_passed("test_repro.py::test_control[1] PASSED [ 25%]\ntest_repro.py::test_control[2] SKIPPED [ 50%]")
    assert not healthy_control_passed("test_repro.py::test_control FAILED [ 50%]\ntest_repro.py::test_issue PASSED [100%]")
