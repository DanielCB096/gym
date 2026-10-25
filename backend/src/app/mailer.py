"""Small SMTP transport shared by the club's transactional emails.

The SMTP account is configured through environment variables and preview mode
simulates the delivery instead of contacting a real server, so a demo never
sends private financial documents. Callers translate ``MailNotConfigured`` and
``MailDeliveryFailed`` into their own module errors.
"""

from dataclasses import dataclass
from email.message import EmailMessage
import os
import smtplib
import ssl
from typing import Sequence

DEFAULT_NOT_CONFIGURED_MESSAGE = (
    "El envío de correo no está configurado (SMTP_HOST)."
)
DEFAULT_FAILURE_LABEL = "No se pudo enviar el correo"


class MailerError(Exception):
    """Base class for email transport failures."""


class MailNotConfigured(MailerError):
    pass


class MailDeliveryFailed(MailerError):
    pass


@dataclass(frozen=True)
class EmailAttachment:
    content: bytes
    filename: str
    maintype: str
    subtype: str


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def preview_mode() -> bool:
    return _env_bool("PREVIEW_MODE", False)


def send_email(
    *,
    recipient: str,
    subject: str,
    body: str,
    attachments: Sequence[EmailAttachment] = (),
    not_configured_message: str = DEFAULT_NOT_CONFIGURED_MESSAGE,
    failure_label: str = DEFAULT_FAILURE_LABEL,
) -> str:
    """Send an email and return ``sent`` or ``simulated``.

    Preview mode never contacts a real SMTP server, even when ``SMTP_HOST`` is
    configured: it returns ``simulated`` so the caller can audit the attempt
    without sending private data during a demo.
    """

    if preview_mode():
        return "simulated"

    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        raise MailNotConfigured(not_configured_message)

    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        timeout = float(os.getenv("SMTP_TIMEOUT", "20"))
    except ValueError as error:
        raise MailNotConfigured(
            "SMTP_PORT o SMTP_TIMEOUT no tienen un número válido."
        ) from error
    use_ssl = _env_bool("SMTP_USE_SSL", False)
    use_tls = _env_bool("SMTP_USE_TLS", True)
    username = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", "").strip() or username or "no-reply@localhost"

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    for attachment in attachments:
        message.add_attachment(
            attachment.content,
            maintype=attachment.maintype,
            subtype=attachment.subtype,
            filename=attachment.filename,
        )

    context = ssl.create_default_context()
    try:
        if use_ssl:
            connection = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
        else:
            connection = smtplib.SMTP(host, port, timeout=timeout)
        with connection as server:
            if use_tls and not use_ssl:
                server.starttls(context=context)
            if username and password:
                server.login(username, password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException, ValueError) as error:
        detail = str(error).strip() or error.__class__.__name__
        raise MailDeliveryFailed(f"{failure_label}: {detail}") from error
    return "sent"


__all__ = [
    "EmailAttachment",
    "MailDeliveryFailed",
    "MailNotConfigured",
    "MailerError",
    "preview_mode",
    "send_email",
]
