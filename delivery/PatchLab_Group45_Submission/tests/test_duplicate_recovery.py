import json
from patchlab.demo import make_fixture
from patchlab.experiment import Task, execute
from patchlab.workbench import PytestRunner


def setup_case(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    make_fixture(repo)
    task = Task(repo, "HEAD", "Fix reversed intervals", ["interval.py"],
                ["test_interval.py::test_empty"], ["test_interval.py"])
    def check(self, root, selectors):
        good = "max(0," in (root / "interval.py").read_text()
        return {"exit_code": 0 if good else 1, "timed_out": False,
                "output": "passed" if good else "AssertionError: wrong interval"}
    monkeypatch.setattr(PytestRunner, "run", check)
    return task


def proposal(after):
    return {"kind": "propose", "diagnosis": "Preserve positive duration and clamp negatives",
            "edits": [{"path": "interval.py", "before": "    return end - start", "after": after}]}


def test_three_duplicates_stop_without_spending_candidate_budget(tmp_path, monkeypatch):
    task = setup_case(tmp_path, monkeypatch)
    class Model:
        model = "scripted"
        def __init__(self): self.contexts = []
        def decide(self, context):
            self.contexts.append(context)
            return proposal("    return 0"), {"total_tokens": 10}
    model = Model();out = tmp_path / "out"
    result = execute(task, out, model, PytestRunner(None, 30), mode="memory")
    assert result["status"] == "stagnated"
    assert result["attempts"] == result["verified_candidates"] == 1
    assert result["duplicate_proposals"] == 3
    assert result["model_calls"] == 4 and result["tokens_reported"] == 40
    assert len(list(out.glob("candidate-*.patch"))) == 1
    assert len(json.loads((out / "repair-memory.json").read_text())) == 1
    assert model.contexts[-1]["duplicate_recovery"]["original_failure"][0]["evidence"]


def test_novel_patch_after_duplicate_can_use_remaining_budget(tmp_path, monkeypatch):
    task = setup_case(tmp_path, monkeypatch)
    class Model:
        model = "scripted"
        def __init__(self): self.n = 0
        def decide(self, context):
            self.n += 1
            if self.n == 3:
                assert context["duplicate_recovery"]
                assert "NEW evidence" in context["next_action_constraint"]
                return {"kind": "read", "path": "interval.py", "start": 1, "end": 2}, None
            return proposal("    return max(0, end - start)" if self.n == 4 else "    return 0"), None
    out = tmp_path / "out"
    result = execute(task, out, Model(), PytestRunner(None, 30), mode="memory", attempts=2)
    assert result["status"] == "verified"
    assert result["attempts"] == 2 and result["duplicate_proposals"] == 1
    assert (out / "candidate-2.patch").exists()
