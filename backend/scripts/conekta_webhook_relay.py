"""Expose only the Conekta membership webhook through a temporary local tunnel."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

WEBHOOK_PATH = "/webhooks/conekta/membership"
MAX_BODY_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 16_384
DEFAULT_TARGET = "http://api:8000/webhooks/conekta/membership"
TARGET = os.getenv("WEBHOOK_RELAY_TARGET", DEFAULT_TARGET)
PORT = int(os.getenv("WEBHOOK_RELAY_PORT", "8765"))

target_url = urlsplit(TARGET)
if (
    target_url.scheme != "http"
    or not target_url.hostname
    or target_url.path != WEBHOOK_PATH
    or target_url.query
    or target_url.fragment
    or target_url.username
    or target_url.password
):
    raise RuntimeError("WEBHOOK_RELAY_TARGET must be the internal Conekta membership webhook URL")
if not 1 <= PORT <= 65535:
    raise RuntimeError("WEBHOOK_RELAY_PORT must be between 1 and 65535")


class ConektaWebhookRelay(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != WEBHOOK_PATH:
            self._respond(404, b'{"detail":"Not found"}')
            return
        self.connection.settimeout(10)
        if self.headers.get("Transfer-Encoding"):
            self._respond(411, b'{"detail":"Content-Length required"}')
            return
        try:
            content_length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._respond(411, b'{"detail":"Content-Length required"}')
            return
        if content_length < 0:
            self._respond(400, b'{"detail":"Invalid Content-Length"}')
            return
        if content_length > MAX_BODY_BYTES:
            self._respond(413, b'{"detail":"Payload too large"}')
            return

        payload = self.rfile.read(content_length)
        if len(payload) != content_length:
            self._respond(400, b'{"detail":"Incomplete request body"}')
            return
        headers = {
            "Content-Type": self.headers.get("Content-Type", "application/json"),
        }
        digest = self.headers.get("Digest")
        if digest is not None:
            headers["Digest"] = digest
        forwarded_request = Request(TARGET, data=payload, headers=headers, method="POST")
        try:
            with urlopen(forwarded_request, timeout=15) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                _log_upstream_error(response.status, body)
                self._respond(response.status, body)
        except HTTPError as error:
            body = error.read(MAX_RESPONSE_BYTES + 1)
            _log_upstream_error(error.code, body)
            self._respond(error.code, body)
        except (TimeoutError, URLError):
            self._respond(502, b'{"detail":"Local webhook service unavailable"}')

    def do_GET(self) -> None:
        self._respond(404, b'{"detail":"Not found"}')

    def _respond(self, status_code: int, body: bytes) -> None:
        if len(body) > MAX_RESPONSE_BYTES:
            status_code = 502
            body = b'{"detail":"Local webhook response too large"}'
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *args: object) -> None:
        return


def _log_upstream_error(status_code: int, body: bytes) -> None:
    if status_code < 400:
        return
    try:
        response = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        response = None
    detail = response.get("detail") if isinstance(response, dict) else None
    if isinstance(detail, str):
        print(
            f"Webhook upstream returned HTTP {status_code}: {detail[:300]}",
            file=sys.stderr,
            flush=True,
        )
    else:
        print(
            f"Webhook upstream returned HTTP {status_code}",
            file=sys.stderr,
            flush=True,
        )


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), ConektaWebhookRelay)
    server.daemon_threads = True
    print(f"Webhook-only relay listening on port {PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
