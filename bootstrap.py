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
import tomllib
import venv

ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
CONFIG = ROOT / "configs" / "my-model.toml"
SECRET = ROOT / "configs" / ".model-key"
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


def configure() -> None:
    if not CONFIG.exists():
        print("\n首次使用：请选择模型服务。")
        print("1. DeepSeek 官方 V4.1 Flash（默认，只需 API 密钥）")
        print("2. 其他兼容 Chat Completions 的模型（自填地址和模型名）")
        print("3. 暂不配置，先打开工作台")
        choice = input("请选择 [1/2/3，默认 1]: ").strip()
        if choice in ("", "1"):
            url, name = DEEPSEEK_URL, DEEPSEEK_MODEL
        elif choice == "2":
            url = input("完整 Chat completions URL: ").strip()
            name = input("模型名称: ").strip()
            if not url or not name:
                raise ValueError("接口地址和模型名称不能为空，配置未保存。")
        elif choice == "3":
            return
        else:
            raise ValueError("请选择 1、2 或 3。")
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
        raise ValueError("模型配置中的 api_key_env 无效。")
    if os.environ.get(key_name):
        return
    if sys.platform == "win32" and key_name == "PATCHLAB_API_KEY" and SECRET.exists():
        try:
            os.environ[key_name] = unprotect(SECRET.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError) as exc:
            raise ValueError("无法解密保存的密钥。请删除 configs/.model-key 后重新启动并输入密钥。") from exc
        if os.environ[key_name]:
            return
    print(f"请输入 {key_name}（输入时不会显示；留空可先打开页面）。")
    key = getpass.getpass("API 密钥: ")
    if not key:
        return
    os.environ[key_name] = key
    if sys.platform == "win32" and key_name == "PATCHLAB_API_KEY":
        answer = input("是否在当前 Windows 用户下加密保存密钥，方便下次启动？[Y/n] ").strip().lower()
        if answer in ("", "y", "yes"):
            SECRET.write_text(protect(key), encoding="utf-8")
    elif sys.platform == "darwin":
        print("密钥只用于本次运行；下次启动可重新输入或设置环境变量。")


def ensure_environment() -> None:
    if not PYTHON.exists():
        print("正在创建项目独立的 Python 环境……", flush=True)
        venv.EnvBuilder(with_pip=True).create(ROOT / ".venv")
    pip_check = subprocess.run([str(PYTHON), "-m", "pip", "--version"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if pip_check.returncode:
        print("正在修复项目环境中的 pip……", flush=True)
        subprocess.run([str(PYTHON), "-m", "ensurepip", "--upgrade"], cwd=ROOT, check=True)
    probe = subprocess.run([str(PYTHON), "-c", "import pytest; assert pytest.__version__ == '9.1.1'"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if probe.returncode:
        print("正在安装项目测试依赖；首次运行需要连接网络……", flush=True)
        subprocess.run([str(PYTHON), "-m", "pip", "install", "-r", str(ROOT / "requirements-dev.txt")],
                       cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the PatchLab workspace")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if sys.platform not in ("win32", "darwin"):
        raise RuntimeError("该启动器目前支持 Windows 和 macOS。")
    if sys.version_info < (3, 12):
        raise RuntimeError("请安装 Python 3.12 或更高版本，并确保 python 命令可用。")
    if shutil.which("git") is None:
        raise RuntimeError("未找到 Git。请安装 Git 并将其加入 PATH。")
    os.chdir(ROOT)
    ensure_environment()
    configure()
    command = [str(PYTHON), "-m", "patchlab", "web", "--port", str(args.port)]
    if CONFIG.exists():
        command.extend(["--model-config", str(CONFIG)])
    if args.no_browser:
        command.append("--no-browser")
    print("\n正在打开 PatchLab；关闭此窗口将停止服务。", flush=True)
    return subprocess.call(command, cwd=ROOT, env=os.environ.copy())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"\n启动失败：{exc}", file=sys.stderr)
        print("请检查 Python、Git、模型配置和网络连接后重试。", file=sys.stderr)
        raise SystemExit(1)
