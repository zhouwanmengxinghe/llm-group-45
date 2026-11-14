"""A self-contained, offline experiment with a known regression."""

from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from .experiment import Task, execute
from .workbench import PytestRunner


class Demonstrator:
    model = "scripted-demo"

    def decide(self, context: dict) -> tuple[dict, None]:
        if not context["recent_inspection"]:
            return {"kind": "read", "path": "interval.py", "start": 1, "end": 3}, None
        feedback = context["repair_feedback"]
        if not feedback:
            diagnosis = "Clamping prevents an empty interval from having negative duration."
            replacement = "    return 0"
        elif feedback[-1].get("stage") in {"regression", "public_suite"}:
            diagnosis = "Regression evidence shows positive intervals must retain their duration."
            replacement = "    return max(0, end - start)"
        else:
            return {"kind": "stop", "reason": "unexpected fixture result"}, None
        return {
            "kind": "propose", "diagnosis": diagnosis,
            "edits": [{"path": "interval.py", "before": "    return end - start",
                       "after": replacement}],
        }, None


def make_fixture(repo: Path) -> None:
    repo.mkdir()
    (repo / "interval.py").write_bytes(
        b"def duration(start, end):\n    return end - start\n"
    )
    (repo / "test_interval.py").write_bytes(
        b"from interval import duration\n\n"
        b"def test_empty():\n    assert duration(6, 3) == 0\n\n"
        b"def test_positive():\n    assert duration(2, 7) == 5\n"
    )
    for args in [
        ["init", "--quiet"], ["-c", "core.autocrlf=false", "add", "--", "interval.py", "test_interval.py"],
        ["-c", "user.name=PatchLab fixture", "-c", "user.email=fixture@example.invalid",
         "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Build interval fixture"],
    ]:
        subprocess.run(["git", "-C", str(repo), *args], check=True)


def run_demo(output: Path, mode: str, runner: PytestRunner, approve=None) -> dict:
    with TemporaryDirectory(prefix="patchlab-demo-") as temp:
        repo = Path(temp) / "interval-case"
        make_fixture(repo)
        task = Task(repo, "HEAD", "Reversed intervals should have zero duration.",
                    ["interval.py"], ["test_interval.py::test_empty"], ["test_interval.py"])
        return execute(task, output, Demonstrator(), runner, mode=mode, approve=approve)
