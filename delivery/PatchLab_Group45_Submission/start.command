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
  printf '%s\n' 'Python 3.12 or newer was not found. Install it and retry.'
  read -r -p 'Press Enter to close...' _
  exit 1
fi
"$python_bin" bootstrap.py "$@"
status=$?
if [ "$status" -ne 0 ]; then
  read -r -p "Startup did not complete. Press Enter to close..." _
fi
exit "$status"
