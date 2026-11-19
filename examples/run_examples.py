"""Run three reproducible examples with real tools and labelled model provenance.

From the project root: python examples/run_examples.py --output runs/examples
Add --live to use the configured provider for the first two cases (paid API).
The failure case always uses a deliberately repeating scripted model.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from patchlab.decision import ChatDecider
from patchlab.demo import make_fixture
from patchlab.experiment import Task, execute
from patchlab.workbench import PytestRunner


class ExampleModel:
    model = "scripted-example-not-an-LLM"

    def __init__(self, changed=False, repeat=False):
        self.changed = changed
        self.repeat = repeat
        self.inspected = False

    def decide(self, context):
        if not self.inspected:
            self.inspected = True
            return {"kind": "read", "path": "interval.py", "start": 1, "end": 10}, None
        before = "    return max(0, end - start)" if self.changed else "    return end - start"
        after = ("    return max(0, end - start) / 60" if self.changed
                 else "    return 0" if self.repeat else "    return max(0, end - start)")
        return {"kind": "propose", "diagnosis": (
            "The new contract returns minutes instead of seconds." if self.changed else
            "Clamp reversed intervals while preserving positive durations."),
            "edits": [{"path": "interval.py", "before": before, "after": after}]}, None


def commit(repo, message):
    for args in [["add", "--", "interval.py", "test_interval.py"],
                 ["-c", "user.name=PatchLab example", "-c", "user.email=example@example.invalid",
                  "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", message]]:
        subprocess.run(["git", "-C", str(repo), "-c", "core.autocrlf=false", *args], check=True)


def run(output, live):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    runner = PytestRunner(None, 30)
    if live:
        import bootstrap
        bootstrap.configure()
        factory = lambda: ChatDecider(1200, bootstrap.CONFIG)
    else:
        factory = lambda: ExampleModel()
    repo = output / "working-project"
    make_fixture(repo)
    issue = "Reversed intervals must return zero; positive intervals must retain their duration in seconds."
    task = Task(repo, "HEAD", issue, ["interval.py"],
                ["test_interval.py::test_empty"], ["test_interval.py"])
    results = {}
    results["normal"] = execute(task, output / "normal", factory(), runner, mode="memory", calls=10)
    patch = output / "normal" / "final.patch"
    if not patch.exists() or results["normal"]["status"] != "verified":
        raise RuntimeError("Normal example did not verify; inspect the retained trace before continuing.")
    # The operator explicitly applies the accepted patch to this disposable fixture.
    subprocess.run(["git", "-C", str(repo), "-c", "core.autocrlf=false", "apply", str(patch)], check=True)
    (repo / "test_interval.py").write_bytes((
        "from interval import duration\n\n"
        "def test_empty():\n    assert duration(6, 3) == 0\n\n"
        "def test_positive():\n    assert duration(0, 120) == 2\n\n"
        "def test_fraction():\n    assert duration(0, 30) == 0.5\n").encode("utf-8"))
    commit(repo, "Accept first repair and change the test contract to minutes")
    changed = "Changed request: duration inputs remain seconds, but return minutes, including fractional minutes. Reversed intervals still return zero."
    task = Task(repo, "HEAD", changed, ["interval.py"],
                ["test_interval.py::test_positive"], ["test_interval.py"])
    model = factory() if live else ExampleModel(changed=True)
    results["changed_request"] = execute(task, output / "changed-request", model, runner,
        mode="memory", calls=10, session_context="The previous seconds-based repair was accepted and explicitly applied by the operator. The return-unit requirement has now changed.")
    failure_repo = output / "failure-project"
    make_fixture(failure_repo)
    task = Task(failure_repo, "HEAD", issue, ["interval.py"],
                ["test_interval.py::test_empty"], ["test_interval.py"])
    results["failure"] = execute(task, output / "failure", ExampleModel(repeat=True), runner,
                                 mode="memory", calls=10)
    record = {"normal_input": issue, "changed_input": changed,
              "first_two_model_source": "live-provider" if live else "scripted-offline",
              "failure_model_source": "scripted-offline", "test_execution": "real-host-pytest",
              "changed_request_setup": "Operator applied first patch to disposable fixture, then updated the public contract and committed it.",
              "results": results}
    (output / "examples-summary.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    expected = (results["normal"]["status"] == "verified" and
                results["changed_request"]["status"] == "verified" and
                results["failure"]["status"] == "stagnated" and
                results["failure"]["duplicate_proposals"] == 3)
    print(json.dumps({name: {k: row.get(k) for k in ["status", "attempts", "duplicate_proposals", "model_calls"]}
                      for name, row in results.items()}, indent=2))
    return 0 if expected else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="A new output directory; existing data is never overwritten.")
    parser.add_argument("--live", action="store_true", help="Use a paid model for normal and changed-request examples.")
    args = parser.parse_args()
    raise SystemExit(run(args.output, args.live))
