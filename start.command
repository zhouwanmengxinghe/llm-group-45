#!/bin/bash
cd "$(dirname "$0")" || exit 1
python_bin=""
for candidate in python3.14 python3.13 python3.12 python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 12))' >/dev/null 2>&1; then
    python_bin="$candidate"
    break
  fi
done
if [ -z "$python_bin" ]; then
  printf '%s\n' '未找到 Python 3.12 或更高版本，请先安装后重试。'
  read -r -p '按回车关闭窗口...' _
  exit 1
fi
"$python_bin" bootstrap.py "$@"
status=$?
if [ "$status" -ne 0 ]; then
  read -r -p '启动未完成，按回车关闭窗口...' _
fi
exit "$status"
