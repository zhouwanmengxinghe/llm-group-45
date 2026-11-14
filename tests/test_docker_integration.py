import os

import pytest

from patchlab.workbench import PytestRunner


IMAGE = os.environ.get("PATCHLAB_DOCKER_IMAGE")
pytestmark = pytest.mark.skipif(not IMAGE, reason="set PATCHLAB_DOCKER_IMAGE to run Docker integration tests")


def test_docker_runner_executes_read_only_candidate(tmp_path):
    (tmp_path / "test_sample.py").write_text("def test_ok():\n    assert 2 + 2 == 4\n", encoding="utf-8")
    result = PytestRunner(IMAGE, 15).run(tmp_path, ["test_sample.py"])
    assert result["exit_code"] == 0
    assert result["timed_out"] is False
    assert "1 passed" in result["output"]


def test_docker_runner_enforces_timeout(tmp_path):
    (tmp_path / "test_slow.py").write_text(
        "import time\n\ndef test_slow():\n    time.sleep(30)\n", encoding="utf-8"
    )
    result = PytestRunner(IMAGE, 1).run(tmp_path, ["test_slow.py"])
    assert result["timed_out"] is True
    assert result["exit_code"] != 0
