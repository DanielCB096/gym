import base64
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from app.modules.memberships.conekta import (
    ConektaWebhookConfigurationError,
    ConektaWebhookSignatureError,
    conekta_webhook_public_key_from_env,
    verify_conekta_webhook_signature,
)


@pytest.fixture
def rsa_keys() -> tuple[RSAPrivateKey, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return private_key, public_key_pem


def _digest(private_key: RSAPrivateKey, payload: bytes) -> str:
    signature = private_key.sign(payload, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode("ascii")


def test_accepts_valid_sha256_rsa_digest(rsa_keys: tuple[RSAPrivateKey, str]) -> None:
    private_key, public_key_pem = rsa_keys
    payload = b'{"type":"charge.paid","id":"evt_123"}'

    verify_conekta_webhook_signature(payload, _digest(private_key, payload), public_key_pem)


def test_rejects_modified_request_body(rsa_keys: tuple[RSAPrivateKey, str]) -> None:
    private_key, public_key_pem = rsa_keys
    payload = b'{"type":"charge.paid","id":"evt_123"}'

    with pytest.raises(ConektaWebhookSignatureError, match="does not match"):
        verify_conekta_webhook_signature(
            payload + b" ",
            _digest(private_key, payload),
            public_key_pem,
        )


@pytest.mark.parametrize("digest", [None, "", "not base64"])
def test_rejects_missing_or_malformed_digest(
    rsa_keys: tuple[RSAPrivateKey, str],
    digest: str | None,
) -> None:
    _, public_key_pem = rsa_keys

    with pytest.raises(ConektaWebhookSignatureError):
        verify_conekta_webhook_signature(b"{}", digest, public_key_pem)


def test_rejects_invalid_public_key(rsa_keys: tuple[RSAPrivateKey, str]) -> None:
    private_key, _ = rsa_keys
    payload = b"{}"

    with pytest.raises(ConektaWebhookConfigurationError, match="valid PEM"):
        verify_conekta_webhook_signature(payload, _digest(private_key, payload), "invalid")


def test_rejects_non_rsa_public_key(rsa_keys: tuple[RSAPrivateKey, str]) -> None:
    private_key, _ = rsa_keys
    ed25519_private_key = Ed25519PrivateKey.generate()
    public_key_pem = ed25519_private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    payload = b"{}"

    with pytest.raises(ConektaWebhookConfigurationError, match="RSA public key"):
        verify_conekta_webhook_signature(payload, _digest(private_key, payload), public_key_pem)


def test_rejects_weak_rsa_public_key(rsa_keys: tuple[RSAPrivateKey, str]) -> None:
    private_key, _ = rsa_keys
    weak_private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    public_key_pem = weak_private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    payload = b"{}"

    with pytest.raises(ConektaWebhookConfigurationError, match="2048 bits"):
        verify_conekta_webhook_signature(payload, _digest(private_key, payload), public_key_pem)


def test_loads_webhook_public_key_from_file(
    monkeypatch,
    tmp_path: Path,
    rsa_keys: tuple[RSAPrivateKey, str],
) -> None:
    _, public_key_pem = rsa_keys
    key_path = tmp_path / "webhook-public.pem"
    key_path.write_text(public_key_pem, encoding="utf-8")
    monkeypatch.setenv("CONEKTA_MODE", "sandbox")
    monkeypatch.delenv("CONEKTA_WEBHOOK_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("CONEKTA_WEBHOOK_PUBLIC_KEY_FILE", str(key_path))

    assert conekta_webhook_public_key_from_env() == public_key_pem.strip()


def test_rejects_both_inline_and_file_webhook_public_keys(
    monkeypatch,
    tmp_path: Path,
    rsa_keys: tuple[RSAPrivateKey, str],
) -> None:
    _, public_key_pem = rsa_keys
    key_path = tmp_path / "webhook-public.pem"
    key_path.write_text(public_key_pem, encoding="utf-8")
    monkeypatch.setenv("CONEKTA_MODE", "sandbox")
    monkeypatch.setenv("CONEKTA_WEBHOOK_PUBLIC_KEY", public_key_pem)
    monkeypatch.setenv("CONEKTA_WEBHOOK_PUBLIC_KEY_FILE", str(key_path))

    with pytest.raises(ConektaWebhookConfigurationError, match="Configura solo una"):
        conekta_webhook_public_key_from_env()


def test_reports_unreadable_webhook_public_key_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CONEKTA_MODE", "sandbox")
    monkeypatch.delenv("CONEKTA_WEBHOOK_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("CONEKTA_WEBHOOK_PUBLIC_KEY_FILE", str(tmp_path / "missing.pem"))

    with pytest.raises(ConektaWebhookConfigurationError, match="No se pudo leer"):
        conekta_webhook_public_key_from_env()
