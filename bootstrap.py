"""First-run setup and local workbench launcher for Windows and macOS."""
from __future__ import annotations

import argparse
import base64
import ctypes
from ctypes import wintypes
import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import venv

ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
CONFIG = ROOT / "configs" / "my-model.toml"
SECRET = ROOT / "configs" / ".model-key"
MAC_SECRET = ROOT / "configs" / ".macos-keys.json"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-flash"


class DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def crypt_bytes(value: bytes, decrypt: bool = False) -> bytes:
    buffer = ctypes.create_string_buffer(value, len(value))
    source = DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = DataBlob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel.LocalFree.restype = wintypes.HLOCAL
    if decrypt:
        ok = crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        ok = crypt.CryptProtectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


def protect(secret: str) -> str:
    return base64.b64encode(crypt_bytes(secret.encode("utf-8"))).decode("ascii")


def unprotect(cipher: str) -> str:
    return crypt_bytes(base64.b64decode(cipher, validate=True), decrypt=True).decode("utf-8")


def read_mac_keys() -> dict[str, str]:
    if not MAC_SECRET.exists():
        return {}
    data = json.loads(MAC_SECRET.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise ValueError("Invalid local key file. Check configs/.macos-keys.json.")
    return data


def save_mac_key(name: str, key: str) -> None:
    keys = read_mac_keys()
    keys[name] = key
    # mkstemp creates a private file (0600 on macOS); replace avoids partial writes.
    fd, temp_name = tempfile.mkstemp(prefix=".macos-key-", dir=MAC_SECRET.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(keys, stream, ensure_ascii=False)
        os.replace(temp_name, MAC_SECRET)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def configure() -> None:
    if not CONFIG.exists():
        print("\nFirst launch: choose a model provider.")
        print("1. DeepSeek Flash (default; official API key required)")
        print("2. Other compatible Chat Completions provider (endpoint and model required)")
        print("3. Skip model setup and open the workspace")
        choice = input("Choose [1/2/3; default 1]: ").strip()
        if choice in ("", "1"):
            url, name = DEEPSEEK_URL, DEEPSEEK_MODEL
        elif choice == "2":
            url = input("Full chat completions URL: ").strip()
            name = input("Model name: ").strip()
            if not url or not name:
                raise ValueError("Endpoint and model are required. Configuration was not saved.")
        elif choice == "3":
            return
        else:
            raise ValueError("Choose 1, 2, or 3.")
        # JSON strings are valid TOML basic strings for these configuration values.
        content = ("[model]\nurl = " + json.dumps(url, ensure_ascii=False)
                   + "\nname = " + json.dumps(name, ensure_ascii=False)
                   + '\napi_key_env = "PATCHLAB_API_KEY"\n')
        if choice in ("", "1"):
            content += 'thinking = "disabled"\n'
        CONFIG.write_text(content, encoding="utf-8")
    with CONFIG.open("rb") as stream:
        model = tomllib.load(stream).get("model", {})
    key_name = model.get("api_key_env", "PATCHLAB_API_KEY")
    if not isinstance(key_name, str) or not key_name:
        raise ValueError("Invalid api_key_env in model configuration.")
    if os.environ.get(key_name):
        return
    if sys.platform == "darwin":
        saved_key = read_mac_keys().get(key_name, "")
        if saved_key:
            os.environ[key_name] = saved_key
            return
    if sys.platform == "win32" and key_name == "PATCHLAB_API_KEY" and SECRET.exists():
        try:
            os.environ[key_name] = unprotect(SECRET.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise ValueError("Cannot decrypt the saved key. Remove configs/.model-key, restart, and enter the key again.") from exc
        if os.environ[key_name]:
            return
    print(f"Enter {key_name} (hidden input; leave blank to open the page without a model).")
    key = getpass.getpass("API key: ")
    if not key:
        return
    os.environ[key_name] = key
    if sys.platform == "win32" and key_name == "PATCHLAB_API_KEY":
        answer = input("Encrypt and save the key for this Windows account? [Y/n] ").strip().lower()
        if answer in ("", "y", "yes"):
            SECRET.write_text(protect(key), encoding="utf-8")
    elif sys.platform == "darwin":
        answer = input("Save the key as plaintext in this local project for the next launch? [y/N] ").strip().lower()
        if answer in ("y", "yes"):
            save_mac_key(key_name, key)
            print("Saved to configs/.macos-keys.json (owner-only permissions; excluded from Git).")
        else:
            print("The key is available for this run only.")


def ensure_environment() -> None:
    if not PYTHON.exists():
        print("Creating the project Python environment...", flush=True)
        venv.EnvBuilder(with_pip=True).create(ROOT / ".venv")
    pip_check = subprocess.run([str(PYTHON), "-m", "pip", "--version"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if pip_check.returncode:
        print("Repairing pip in the project environment...", flush=True)
        subprocess.run([str(PYTHON), "-m", "ensurepip", "--upgrade"], cwd=ROOT, check=True)
    probe = subprocess.run([str(PYTHON), "-c", "import pytest; assert pytest.__version__ == '9.1.1'"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if probe.returncode:
        print("Installing test dependencies; the first launch requires internet access...", flush=True)
        subprocess.run([str(PYTHON), "-m", "pip", "install", "-r", str(ROOT / "requirements-dev.txt")],
                       cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the PatchLab workspace")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if sys.platform not in ("win32", "darwin"):
        raise RuntimeError("This launcher supports Windows and macOS.")
    if sys.version_info < (3, 12):
        raise RuntimeError("Install Python 3.12 or newer and ensure python is on PATH.")
    if shutil.which("git") is None:
        raise RuntimeError("Git was not found. Install Git and add it to PATH.")
    os.chdir(ROOT)
    ensure_environment()
    configure()
    command = [str(PYTHON), "-m", "patchlab", "web", "--port", str(args.port)]
    if CONFIG.exists():
        command.extend(["--model-config", str(CONFIG)])
    if args.no_browser:
        command.append("--no-browser")
    print("\nOpening PatchLab. Closing this window stops the service.", flush=True)
    return subprocess.call(command, cwd=ROOT, env=os.environ.copy())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"\nStartup failed: {exc}", file=sys.stderr)
        print("Check Python, Git, model configuration, and network access, then retry.", file=sys.stderr)
        raise SystemExit(1)
