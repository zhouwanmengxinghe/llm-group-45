"""HTTPBin fixture for unchanged legacy Requests tests; no public egress."""
from pathlib import Path
import threading

from httpbin import app
from werkzeug.serving import make_server


def main():
    root = Path(__file__).resolve().parent
    http = make_server("127.0.0.1", 80, app, threaded=True)
    https = make_server("127.0.0.1", 443, app, threaded=True,
                        ssl_context=(str(root / "cert.pem"), str(root / "key.pem")))
    threading.Thread(target=http.serve_forever, daemon=True).start()
    https.serve_forever()


if __name__ == "__main__":
    main()
