"""Conekta webhook signature verification."""

import base64
import binascii
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class ConektaWebhookConfigurationError(ValueError):
    pass


class ConektaWebhookSignatureError(ValueError):
    pass


def conekta_webhook_public_key_from_env() -> str:
    mode = (os.getenv("CONEKTA_MODE") or "sandbox").strip().lower()
    if mode != "sandbox":
        raise ConektaWebhookConfigurationError(
            "La recepción de webhooks de Conekta solo está habilitada en sandbox."
        )
    public_key_pem = (os.getenv("CONEKTA_WEBHOOK_PUBLIC_KEY") or "").strip()
    public_key_file = (os.getenv("CONEKTA_WEBHOOK_PUBLIC_KEY_FILE") or "").strip()
    if public_key_pem and public_key_file:
        raise ConektaWebhookConfigurationError(
            "Configura solo una de CONEKTA_WEBHOOK_PUBLIC_KEY o CONEKTA_WEBHOOK_PUBLIC_KEY_FILE."
        )
    if public_key_file:
        try:
            if Path(public_key_file).stat().st_size > 16_384:
                raise ConektaWebhookConfigurationError(
                    "CONEKTA_WEBHOOK_PUBLIC_KEY_FILE excede el tamaño permitido."
                )
            public_key_pem = Path(public_key_file).read_text(encoding="utf-8").strip()
        except ConektaWebhookConfigurationError:
            raise
        except (OSError, UnicodeError) as error:
            raise ConektaWebhookConfigurationError(
                "No se pudo leer CONEKTA_WEBHOOK_PUBLIC_KEY_FILE."
            ) from error
    if not public_key_pem:
        raise ConektaWebhookConfigurationError(
            "Configura CONEKTA_WEBHOOK_PUBLIC_KEY o CONEKTA_WEBHOOK_PUBLIC_KEY_FILE para verificar webhooks."
        )
    return public_key_pem


def verify_conekta_webhook_signature(
    payload: bytes,
    digest_header: str | None,
    public_key_pem: str,
) -> None:
    if not digest_header:
        raise ConektaWebhookSignatureError("Conekta webhook Digest header is missing")

    try:
        signature = base64.b64decode(digest_header, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ConektaWebhookSignatureError(
            "Conekta webhook Digest header is not valid base64"
        ) from error

    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    except (TypeError, ValueError) as error:
        raise ConektaWebhookConfigurationError(
            "CONEKTA_WEBHOOK_PUBLIC_KEY must contain a valid PEM public key"
        ) from error

    if not isinstance(public_key, rsa.RSAPublicKey):
        raise ConektaWebhookConfigurationError(
            "CONEKTA_WEBHOOK_PUBLIC_KEY must be an RSA public key"
        )
    if public_key.key_size < 2048:
        raise ConektaWebhookConfigurationError(
            "CONEKTA_WEBHOOK_PUBLIC_KEY must be at least 2048 bits"
        )

    try:
        public_key.verify(signature, payload, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature as error:
        raise ConektaWebhookSignatureError(
            "Conekta webhook signature does not match the request body"
        ) from error
