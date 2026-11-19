#!/bin/bash
set -euo pipefail
cd /opt/patchlab-network
openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 3650 \
  -keyout key.pem -out cert.pem -subj '/CN=localhost' \
  -addext 'subjectAltName=DNS:localhost,DNS:httpbin.org,DNS:www.google.co.uk,IP:127.0.0.1' \
  -addext 'basicConstraints=critical,CA:TRUE'
chmod 600 key.pem
/opt/miniconda3/envs/testbed/bin/python - <<'PY'
from pathlib import Path
import certifi
bundle = Path(certifi.where())
bundle.write_bytes(bundle.read_bytes() + b'\n' + Path('cert.pem').read_bytes())
PY
/opt/miniconda3/envs/testbed/bin/python -m pip freeze > dependencies.txt
