"""Persist verified edits and explicitly apply them with preimage checks and backups."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_application(output: Path, repository: Path, frozen: Path,
                     changes: dict[str, str], patch: str) -> None:
    files = {name: {"before": (frozen / name).read_text(encoding="utf-8"), "after": text}
             for name, text in changes.items()}
    recipe = {"repository": str(repository.resolve()), "patch_sha256": digest(patch.encode()),
              "files": files}
    (output / "application.json").write_text(json.dumps(recipe, ensure_ascii=True, indent=2) + "\n",
                                             encoding="utf-8")


def application_info(output: Path) -> dict | None:
    path = output / "application.json"
    if not path.exists():
        return None
    recipe = json.loads(path.read_text(encoding="utf-8"))
    return {"repository": recipe["repository"], "patch_sha256": recipe["patch_sha256"],
            "files": sorted(recipe["files"])}


def _source(root: Path, name: str) -> Path:
    parts = PurePosixPath(name).parts
    if (not re.fullmatch(r"[A-Za-z0-9_./-]+", name) or not parts or
        any(p in {".", ".."} or p.startswith(".") for p in parts) or
        not name.endswith(".py") or
        any(p.lower() in {"test", "tests", "testing", "fixtures"} for p in parts[:-1]) or
        parts[-1].lower() in {"conftest.py", "tests.py"} or
        parts[-1].lower().startswith("test_") or parts[-1].lower().endswith("_test.py")):
        raise ValueError("Only eligible existing Python source files can be applied.")
    path = root / name
    if not path.is_relative_to(root):
        raise ValueError("Patch path escapes the project.")
    for parent in [path, *path.parents]:
        if parent.is_symlink() or parent.is_junction():
            raise ValueError("Patch application does not follow links or junctions.")
        if parent == root:
            break
    if not path.is_file():
        raise ValueError(f"Source file is missing: {name}")
    return path


def _replace(path: Path, data: bytes, mode: int) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".patchlab-", dir=path.parent)
    temp = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temp.chmod(mode)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def apply_verified(output: Path, patch_sha256: str) -> dict:
    """Caller serializes repository access. No client-supplied path or patch is executed."""
    recipe = json.loads((output / "application.json").read_text(encoding="utf-8"))
    if recipe["patch_sha256"] != patch_sha256 or digest((output / "final.patch").read_bytes()) != patch_sha256:
        raise ValueError("The reviewed patch no longer matches this run. Reload before applying.")
    status = json.loads((output / "result.json").read_text(encoding="utf-8"))["status"]
    if status not in {"verified", "reproducer_passed_no_regression"}:
        raise ValueError("Only a patch that passed its required local checks can be applied.")
    receipt = output / "application-result.json"
    if receipt.exists():
        return json.loads(receipt.read_text(encoding="utf-8"))
    root = Path(recipe["repository"])
    if root.resolve() != root or not root.is_dir():
        raise ValueError("The original project location has changed.")
    if not 1 <= len(recipe["files"]) <= 8:
        raise ValueError("Invalid application file count.")
    planned = []
    for name, edit in recipe["files"].items():
        path = _source(root, name)
        before = path.read_bytes()
        expected = edit["before"].encode("utf-8")
        after = edit["after"].encode("utf-8")
        if max(len(before), len(expected), len(after)) > 256_000:
            raise ValueError("Source file exceeds the application limit.")
        if before != expected:
            if b"\r\n" in before and b"\r" not in before.replace(b"\r\n", b"") and before.replace(b"\r\n", b"\n") == expected:
                after = after.replace(b"\n", b"\r\n")
            else:
                raise ValueError(f"Source changed since the repair: {name}. Start a new task on current source.")
        compile(after.decode("utf-8"), name, "exec")
        planned.append((name, path, before, after, stat.S_IMODE(path.stat().st_mode)))
    backup = output / "apply-backup"
    backup.mkdir(exist_ok=False)
    for name, _, before, _, _ in planned:
        dest = backup / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(before)
    applied = []
    try:
        for name, path, before, after, mode in planned:
            if _source(root, name).read_bytes() != before:
                raise ValueError(f"Source changed during application: {name}")
            _replace(path, after, mode)
            applied.append((path, before, mode))
        result = {"repository": str(root), "files": [x[0] for x in planned],
                  "patch_sha256": patch_sha256, "backup": str(backup), "status": "applied"}
        receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        rollback_errors = []
        for path, before, mode in reversed(applied):
            try:
                _replace(path, before, mode)
            except OSError as error:
                rollback_errors.append(str(error))
        if rollback_errors:
            raise OSError(f"Application failed; restore from {backup}. Rollback errors: {rollback_errors}") from exc
        raise OSError(f"Application failed; written files restored. Backups remain at {backup}: {exc}") from exc
    return result
