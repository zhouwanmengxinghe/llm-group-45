import json

from patchlab.simple import execute_simple
from patchlab.workbench import PytestRunner


class Model:
    model = "fake"
    def __init__(self): self.calls = 0
    def decide(self, context):
        self.calls += 1
        if self.calls == 1:
            return {"kind": "read", "path": "calc.py", "start": 1, "end": 3}, None
        if self.calls == 2:
            return {"kind": "reproduce", "code": "from calc import duration\ndef test_reverse():\n    assert duration(4, 2) == 0\n"}, None
        assert context["reproducer_confirmed"]
        return {"kind": "propose", "diagnosis": "negative interval", "edits": [
            {"path": "calc.py", "before": "return end - start", "after": "return max(0, end - start)"}]}, None


def test_simple_repairs_uncommitted_project_with_generated_test(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_bytes(b"def duration(start, end):\n    return end - start\n")
    output = tmp_path / "output"
    result = execute_simple(repo, "reverse interval must be zero", "", output, Model(), PytestRunner(None, 30))
    assert result["status"] == "reproducer_passed_no_regression", result
    assert (output / "final.patch").exists()
    assert (output / "reproducer.py").exists()
    assert (repo / "calc.py").read_text() == "def duration(start, end):\n    return end - start\n"
    events = [json.loads(x) for x in (output / "events.jsonl").read_text().splitlines()]
    assert any(x["event"] == "reproducer_test" and x["exit_code"] == 1 for x in events)
    assert any(x["event"] == "candidate_target" and x["exit_code"] == 0 for x in events)


def test_does_not_claim_success_without_reproduction(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_text("value = 1\n")
    class NoRepro:
        model = "fake"
        def decide(self, context):
            return {"kind": "stop", "reason": "请提供操作步骤"}, None
    result = execute_simple(repo, "有问题", "", tmp_path / "out", NoRepro(), PytestRunner(None, 10))
    assert result["status"] == "needs_information"
    assert "步骤" in result["reason"]
    assert not (tmp_path / "out" / "final.patch").exists()


def test_simple_retries_when_existing_regression_test_fails(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_bytes(b"def duration(start, end):\n    return end - start\n")
    (repo / "test_calc.py").write_bytes(
        b"from calc import duration\ndef test_positive():\n    assert duration(1, 3) == 2\n"
    )
    class RetryModel(Model):
        def decide(self, context):
            self.calls += 1
            if self.calls == 1:
                return {"kind": "reproduce", "code": "from calc import duration\ndef test_reverse():\n    assert duration(4, 2) == 0\n"}, None
            replacement = "return 0" if self.calls == 2 else "return max(0, end - start)"
            return {"kind": "propose", "diagnosis": "repair", "edits": [
                {"path": "calc.py", "before": "return end - start", "after": replacement}]}, None
    out = tmp_path / "out"
    result = execute_simple(repo, "reverse interval must be zero", "", out, RetryModel(), PytestRunner(None, 30))
    assert result["status"] == "verified", result
    assert result["attempts"] == 2
    events = [json.loads(x) for x in (out / "events.jsonl").read_text().splitlines()]
    assert [e["exit_code"] for e in events if e["event"] == "candidate_regression"] == [1, 0]
