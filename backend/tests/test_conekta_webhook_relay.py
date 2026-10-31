import importlib.util
from pathlib import Path
from http.server import ThreadingHTTPServer
import socket
from threading import Thread
from typing import Any

import httpx
import pytest


def _relay_module() -> Any:
    script_path = Path(__file__).parents[1] / "scripts" / "conekta_webhook_relay.py"
    spec = importlib.util.spec_from_file_location("conekta_webhook_relay", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load Conekta webhook relay")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def relay_server(monkeypatch: pytest.MonkeyPatch):
    module = _relay_module()
    forwarded: list[tuple[str, bytes, str | None]] = []

    class FakeResponse:
        status = 200

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self, _size: int) -> bytes:
            return b'{"status":"processed"}'

    def fake_urlopen(request, *, timeout: float):
        assert timeout == 15
        forwarded.append(
            (request.full_url, request.data, request.headers.get("Digest"))
        )
        return FakeResponse()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.ConektaWebhookRelay)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", forwarded
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_relay_forwards_only_original_signed_webhook(relay_server) -> None:
    base_url, forwarded = relay_server
    body = b'{"id":"evt_1"}'
    digest = "signed-body-digest"

    response = httpx.post(
        f"{base_url}/webhooks/conekta/membership",
        content=body,
        headers={"Digest": digest},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "processed"}
    assert forwarded == [
        ("http://api:8000/webhooks/conekta/membership", body, digest)
    ]


def test_relay_does_not_forward_other_paths_or_methods(relay_server) -> None:
    base_url, forwarded = relay_server

    post_response = httpx.post(f"{base_url}/docs", content=b"not a webhook")
    get_response = httpx.get(f"{base_url}/webhooks/conekta/membership")

    assert post_response.status_code == 404
    assert get_response.status_code == 404
    assert forwarded == []


def test_relay_rejects_oversized_body(relay_server) -> None:
    base_url, forwarded = relay_server
    address = httpx.URL(base_url)
    with socket.create_connection((address.host, address.port), timeout=5) as client:
        client.sendall(
            (
                "POST /webhooks/conekta/membership HTTP/1.1\r\n"
                f"Host: {address.host}:{address.port}\r\n"
                f"Content-Length: {1_048_576 + 1}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
        )
        response = client.recv(1024)

    assert response.startswith(b"HTTP/1.0 413 ")
    assert forwarded == []
