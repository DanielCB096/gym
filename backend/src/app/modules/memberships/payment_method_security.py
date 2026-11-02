"""Encryption helpers for reusable payment references."""

import base64
import binascii
import json
import os
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class PaymentMethodEncryptionConfigurationError(ValueError):
    pass


class PaymentMethodEncryptionError(ValueError):
    pass


def _encryption_key_from_env() -> bytes:
    encoded_key = (os.getenv("MEMBERSHIP_PAYMENT_ENCRYPTION_KEY") or "").strip()
    if not encoded_key:
        raise PaymentMethodEncryptionConfigurationError(
            "MEMBERSHIP_PAYMENT_ENCRYPTION_KEY debe configurarse para guardar métodos de pago."
        )
    try:
        key = base64.b64decode(encoded_key, validate=True)
    except (binascii.Error, ValueError) as error:
        raise PaymentMethodEncryptionConfigurationError(
            "MEMBERSHIP_PAYMENT_ENCRYPTION_KEY debe ser una clave AES-256 en Base64."
        ) from error
    if len(key) != 32:
        raise PaymentMethodEncryptionConfigurationError(
            "MEMBERSHIP_PAYMENT_ENCRYPTION_KEY debe decodificar a exactamente 32 bytes."
        )
    return key


def validate_payment_method_encryption_configuration() -> None:
    _encryption_key_from_env()


def encrypt_payment_reference(
    member_id: UUID,
    *,
    customer_id: str,
    payment_source_id: str,
) -> bytes:
    payload = json.dumps(
        {"customer_id": customer_id, "payment_source_id": payment_source_id},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    nonce = os.urandom(12)
    ciphertext = AESGCM(_encryption_key_from_env()).encrypt(
        nonce,
        payload,
        f"gym-payment-method:v1:{member_id}".encode("ascii"),
    )
    return b"\x01" + nonce + ciphertext


def decrypt_payment_reference(
    member_id: UUID,
    encrypted_reference: bytes,
) -> tuple[str, str]:
    if len(encrypted_reference) < 30 or encrypted_reference[0] != 1:
        raise PaymentMethodEncryptionError("El método de pago cifrado tiene un formato desconocido.")
    nonce = encrypted_reference[1:13]
    ciphertext = encrypted_reference[13:]
    try:
        plaintext = AESGCM(_encryption_key_from_env()).decrypt(
            nonce,
            ciphertext,
            f"gym-payment-method:v1:{member_id}".encode("ascii"),
        )
        reference = json.loads(plaintext)
    except (InvalidTag, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PaymentMethodEncryptionError(
            "No se pudo descifrar la referencia del método de pago."
        ) from error
    if (
        not isinstance(reference, dict)
        or not isinstance(reference.get("customer_id"), str)
        or not isinstance(reference.get("payment_source_id"), str)
        or not reference["customer_id"].startswith("cus_")
        or not reference["payment_source_id"].startswith("src_")
    ):
        raise PaymentMethodEncryptionError("La referencia del método de pago no es válida.")
    return reference["customer_id"], reference["payment_source_id"]
