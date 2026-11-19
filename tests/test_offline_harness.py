import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "benchmarks/requests-network"
spec = importlib.util.spec_from_file_location("offline_setup", ROOT / "offline_setup.py")
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


def test_offline_setup_preserves_tests_and_patch_content():
    source = ("python -m pip install -e .[test] --verbose\n"
              "git apply - <<'PATCH'\n+python -m pip install example\nPATCH\n"
              "pytest -rA tests/test_example.py\n")
    expected = source.replace("python -m pip install -e",
        "python -m pip install --no-index --no-deps --no-build-isolation -e")
    assert harness.offline_setup(source) == expected


def test_offline_build_wheels_match_verified_lock():
    rows = json.loads((ROOT / "build-wheels/SHA256.json").read_text(encoding="utf-8"))
    assert len(rows) == 5
    for row in rows:
        assert row["source"].startswith("https://pypi.org/pypi/")
        assert hashlib.sha256((ROOT / "build-wheels" / row["file"]).read_bytes()).hexdigest() == row["sha256"]
