"""Frozen repository snapshots, bounded inspection, and test execution."""

from __future__ import annotations

import difflib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from threading import Thread
from uuid import uuid4


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, encoding="utf-8", timeout=60
    ).strip()


def snapshot(repo: Path, revision: str, destination: Path) -> str:
    commit = _git(repo, "rev-parse", "--verify", "--end-of-options", revision + "^{commit}")
    with tempfile.TemporaryFile() as archive:
        subprocess.run(
            ["git", "-C", str(repo), "-c", "core.autocrlf=false", "-c", "core.eol=lf",
             "archive", "--format=tar", commit],
            stdout=archive, check=True, timeout=90,
        )
        archive.seek(0)
        with tarfile.open(fileobj=archive) as stream:
            for member in stream:
                if not (member.isfile() or member.isdir()):
                    raise ValueError("The MVP accepts repositories without archived links or special files.")
                if any(p.casefold() == ".git" for p in PurePosixPath(member.name).parts):
                    raise ValueError("Unexpected Git metadata in the snapshot.")
                stream.extract(member, destination, filter="data")
    return commit


class Workbench:
    def __init__(self, root: Path, editable: list[str]):
        self.root = root
        self.sources = frozenset(
            p.relative_to(root).as_posix() for p in root.rglob("*.py") if p.is_file()
        )
        self.editable = frozenset(editable)
        for name in editable:
            parts = PurePosixPath(name.lower()).parts
            if (
                name not in self.sources
                or not re.fullmatch(r"[A-Za-z0-9_./-]+", name)
                or any(p.startswith(".") or p in {"test", "tests", "testing", "fixtures"} for p in parts[:-1])
                or parts[-1] in {"conftest.py", "tests.py"}
                or parts[-1].startswith("test_")
                or parts[-1].endswith("_test.py")
            ):
                raise ValueError(f"Editable path is not an eligible Python source file: {name}")
        if not self.editable:
            raise ValueError("At least one editable Python source file is required.")

    def inspect(self, action: dict) -> dict:
        operation = action.get("kind")
        if operation == "files":
            prefix = action.get("prefix", "")
            if not isinstance(prefix, str):
                raise ValueError("prefix must be a string")
            return {"paths": [p for p in sorted(self.sources) if p.startswith(prefix)][:100]}
        if operation == "search":
            query = action.get("text")
            if not isinstance(query, str) or not 1 <= len(query) <= 160:
                raise ValueError("search needs a literal query of 1–160 characters")
            hits = []
            for name in sorted(self.sources):
                path = self.root / name
                if path.stat().st_size > 256_000:
                    continue
                for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if query in line:
                        hits.append({"path": name, "line": n, "text": line[:240]})
                        if len(hits) == 35:
                            return {"hits": hits}
            return {"hits": hits}
        if operation == "read":
            name, start, end = action.get("path"), action.get("start"), action.get("end")
            if not isinstance(name, str) or name not in self.sources:
                raise ValueError("read requires a listed Python path")
            if type(start) is not int or type(end) is not int or not 1 <= start <= end <= start + 79:
                raise ValueError("read requires a 1-based range of up to 80 lines")
            path = self.root / name
            if path.stat().st_size > 256_000:
                raise ValueError("file exceeds the inspection limit")
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            return {"path": name, "start": start, "text": "\n".join(lines[start - 1 : end])[:8000]}
        raise ValueError("unknown inspection operation")

    def prepare(self, edits: object) -> tuple[str, dict[str, str]]:
        if not isinstance(edits, list) or not 1 <= len(edits) <= 8:
            raise ValueError("a candidate needs one to eight edits")
        changes: dict[str, str] = {}
        originals: dict[str, str] = {}
        for edit in edits:
            if not isinstance(edit, dict):
                raise ValueError("invalid edit")
            name, old, new = (edit.get(k) for k in ("path", "before", "after"))
            if not isinstance(name, str) or name not in self.editable:
                raise ValueError(f"edit is outside the approved source list: {name}")
            if not isinstance(old, str) or not isinstance(new, str) or not old or old == new:
                raise ValueError("an edit needs distinct before/after text")
            if max(len(old), len(new)) > 6000 or any(c in old + new for c in "\r\x00"):
                raise ValueError("edit must be bounded plain text with LF line endings")
            if name not in originals:
                raw = (self.root / name).read_bytes()
                if len(raw) > 256_000 or b"\r" in raw or not raw.endswith(b"\n"):
                    raise ValueError("editable files must be small UTF-8 files with LF and a final newline")
                originals[name] = raw.decode("utf-8")
            current = changes.get(name, originals[name])
            if current.count(old) != 1:
                raise ValueError(f"before text must occur exactly once: {name}")
            changes[name] = current.replace(old, new, 1)
        parts = []
        for name, updated in sorted(changes.items()):
            if updated == originals[name]:
                continue
            if not updated.endswith("\n"):
                raise ValueError("source edits must preserve the final newline")
            compile(updated, name, "exec")
            parts.extend(difflib.unified_diff(
                [line + "\n" for line in originals[name].split("\n")[:-1]],
                [line + "\n" for line in updated.split("\n")[:-1]],
                fromfile=f"a/{name}", tofile=f"b/{name}",
            ))
        if not parts:
            raise ValueError("edits produce an empty patch")
        return "".join(parts), changes

    def stage(self, candidate: Path, changes: dict[str, str]) -> None:
        shutil.copytree(self.root, candidate)
        for name, updated in changes.items():
            (candidate / name).write_bytes(updated.encode("utf-8"))


class PytestRunner:
    def __init__(self, image: str | None, timeout: int):
        self.image = image
        self.timeout = timeout

    def run(self, root: Path, selectors: list[str]) -> dict:
        import sys

        base = ["-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--", *selectors]
        container = "patchlab-" + uuid4().hex
        if self.image:
            command = [
                "docker", "run", "--rm", "--name", container, "--pull", "never",
                "--network", "none", "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--memory", "1g", "--cpus", "1",
                "--pids-limit", "128", "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m",
                "--mount", f"type=bind,source={root},target=/repo,readonly",
                "--workdir", "/repo", "--env", "HOME=/tmp",
                "--entrypoint", "python", self.image, *base,
            ]
            env = os.environ.copy()
        else:
            command = [sys.executable, *base]
            env = {k: v for k, v in os.environ.items() if k.upper() in {
                "PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP", "LANG",
            }}
            env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        start = time.monotonic()
        with subprocess.Popen(
            command, cwd=root, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0,
        ) as process:
            tail = bytearray()

            def drain():
                assert process.stdout is not None
                try:
                    while data := process.stdout.read(4096):
                        tail.extend(data)
                        if len(tail) > 12000:
                            del tail[:-12000]
                except OSError:
                    pass

            reader = Thread(target=drain, daemon=True)
            reader.start()
            timed_out = False
            try:
                process.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                process.wait()
            if self.image and timed_out:
                try:
                    subprocess.run(
                        ["docker", "rm", "-f", container], stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, timeout=10,
                    )
                except subprocess.TimeoutExpired:
                    pass
            reader.join(timeout=2)
            return {
                "exit_code": process.returncode, "timed_out": timed_out,
                "seconds": round(time.monotonic() - start, 3),
                "output": tail.decode("utf-8", errors="replace"),
            }
