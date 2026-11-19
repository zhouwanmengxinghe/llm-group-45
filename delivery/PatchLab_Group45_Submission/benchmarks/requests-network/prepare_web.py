"""Create a private trust root solely inside a disposable fixture container."""
from pathlib import Path
import subprocess
import requests.certs

root = Path(__file__).resolve().parent
subprocess.run([
    "openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes", "-days", "3650",
    "-keyout", str(root / "key.pem"), "-out", str(root / "cert.pem"), "-subj", "/CN=localhost",
    "-addext", "subjectAltName=DNS:localhost,DNS:www.w3.org,DNS:www.google.com,DNS:www.sphinx-doc.org,IP:127.0.0.1",
    "-addext", "basicConstraints=critical,CA:TRUE",
], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
(root / "bundle.pem").write_bytes(Path(requests.certs.where()).read_bytes() + b"\n" + (root / "cert.pem").read_bytes())
