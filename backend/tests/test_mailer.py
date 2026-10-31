import pytest

from app import mailer


def test_preview_does_not_contact_smtp(monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")

    def unexpected_connection(*_args, **_kwargs):
        raise AssertionError("preview mode must not open an SMTP connection")

    monkeypatch.setattr(mailer.smtplib, "SMTP", unexpected_connection)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", unexpected_connection)

    assert mailer.send_email(
        recipient="member@example.test",
        subject="Aviso",
        body="Mensaje de prueba",
    ) == "simulated"


def test_missing_smtp_host_is_reported(monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "false")
    monkeypatch.delenv("SMTP_HOST", raising=False)

    with pytest.raises(mailer.MailNotConfigured, match="SMTP_HOST"):
        mailer.send_email(
            recipient="member@example.test",
            subject="Aviso",
            body="Mensaje de prueba",
        )


def test_send_email_uses_starttls_auth_and_preserves_message(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "false")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_TIMEOUT", "8.5")
    monkeypatch.setenv("SMTP_USE_SSL", "false")
    monkeypatch.setenv("SMTP_USE_TLS", "true")
    monkeypatch.setenv("SMTP_USER", "mailer@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "test-password")
    monkeypatch.setenv("SMTP_FROM", "Gym <avisos@example.test>")
    tls_context = object()
    monkeypatch.setattr(mailer.ssl, "create_default_context", lambda: tls_context)

    class FakeSMTP:
        instances = []

        def __init__(self, host, port, *, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout
            self.tls_context = None
            self.credentials = None
            self.message = None
            self.instances.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self, *, context):
            self.tls_context = context

        def login(self, username, password):
            self.credentials = (username, password)

        def send_message(self, message):
            self.message = message

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    result = mailer.send_email(
        recipient="member@example.test",
        subject="Tu comprobante",
        body="El comprobante está adjunto.",
        message_id="receipt-123@example.test",
        attachments=(
            mailer.EmailAttachment(
                content=b"%PDF-test",
                filename="comprobante.pdf",
                maintype="application",
                subtype="pdf",
            ),
        ),
    )

    connection = FakeSMTP.instances[-1]
    assert result == "sent"
    assert connection.host == "smtp.example.test"
    assert connection.port == 2525
    assert connection.timeout == 8.5
    assert connection.tls_context is tls_context
    assert connection.credentials == ("mailer@example.test", "test-password")
    assert connection.message is not None
    assert connection.message["From"] == "Gym <avisos@example.test>"
    assert connection.message["To"] == "member@example.test"
    assert connection.message["Subject"] == "Tu comprobante"
    assert connection.message["Message-ID"] == "<receipt-123@example.test>"
    attachment = connection.message.get_payload()[1]
    assert attachment.get_filename() == "comprobante.pdf"
    assert attachment.get_payload(decode=True) == b"%PDF-test"


def test_send_email_uses_implicit_ssl_without_starttls(monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "false")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USE_SSL", "true")
    monkeypatch.setenv("SMTP_USE_TLS", "true")
    tls_context = object()
    monkeypatch.setattr(mailer.ssl, "create_default_context", lambda: tls_context)

    class FakeSMTPSSL:
        instances = []

        def __init__(self, host, port, *, timeout, context):
            self.connection = (host, port, timeout, context)
            self.message = None
            self.instances.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def send_message(self, message):
            self.message = message

    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTPSSL)
    monkeypatch.setattr(
        mailer.smtplib,
        "SMTP",
        lambda *_args, **_kwargs: pytest.fail("implicit SSL must use SMTP_SSL"),
    )

    result = mailer.send_email(
        recipient="member@example.test",
        subject="Aviso",
        body="Mensaje",
    )

    assert result == "sent"
    assert FakeSMTPSSL.instances[0].connection == (
        "smtp.example.test",
        465,
        20.0,
        tls_context,
    )
    assert FakeSMTPSSL.instances[0].message["To"] == "member@example.test"


def test_smtp_failure_is_reported_as_mail_delivery_failed(monkeypatch) -> None:
    monkeypatch.setenv("PREVIEW_MODE", "false")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_USE_TLS", "false")

    class FailingSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def send_message(self, _message):
            raise mailer.smtplib.SMTPServerDisconnected("connection lost")

    monkeypatch.setattr(mailer.smtplib, "SMTP", FailingSMTP)

    with pytest.raises(mailer.MailDeliveryFailed, match="connection lost"):
        mailer.send_email(
            recipient="member@example.test",
            subject="Aviso",
            body="Mensaje",
            failure_label="No se pudo entregar el correo",
        )
