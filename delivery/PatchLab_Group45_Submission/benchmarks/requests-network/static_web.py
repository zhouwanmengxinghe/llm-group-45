"""Offline HTML resources for legacy link-checking integration tests.

These are HTTP fixtures, not mocks of Sphinx or its link-checking functions.
Broken anchors, refused ports, redirects in upstream local handlers, and 404s
continue to be processed by the original application code.
"""
import http.server
from pathlib import Path
import ssl
import threading
from urllib.parse import urlsplit


class Pages(http.server.BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.respond(False)

    def do_GET(self):
        self.respond(True)

    def respond(self, body):
        path = urlsplit(self.path).path
        if path.endswith((".png", ".jpg")):
            self.send_error(404)
            return
        html = b'<!doctype html><html><body><h1 id="defaulting">Namespace</h1><p id="install-sphinx">Installation</p></body></html>'
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        if body:
            self.wfile.write(html)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    http_server = http.server.ThreadingHTTPServer(("127.0.0.1", 80), Pages)
    https_server = http.server.ThreadingHTTPServer(("127.0.0.1", 443), Pages)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(root / "cert.pem", root / "key.pem")
    https_server.socket = context.wrap_socket(https_server.socket, server_side=True)
    threading.Thread(target=http_server.serve_forever, daemon=True).start()
    https_server.serve_forever()
