"""Generate the VAPID key pair that signs the staff's Web Push.

Run it from the ``backend`` directory with the virtualenv Python:

    .\\.venv\\Scripts\\python.exe generate_vapid_keys.py

Paste both lines into the backend environment (``.env`` or the deployment
panel) and restart the API. Only the private key is configured: the panel
derives the public key from it, so the browser cannot be handed one key while
the server signs with another. The keys do not expire, but rotating them
invalidates every subscription already registered, so the staff must activate
their browsers again.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _encode_base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def main() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_raw = private_key.private_numbers().private_value.to_bytes(32, "big")
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    print("Guarda estas líneas como variables de entorno del backend:")
    print()
    print(f"VAPID_PRIVATE_KEY={_encode_base64url(private_raw)}")
    print("VAPID_SUBJECT=mailto:avisos@centro-fit.local")
    print()
    print("Clave pública que el navegador recibirá (derivada de la privada):")
    print(_encode_base64url(public_raw))


if __name__ == "__main__":
    main()
