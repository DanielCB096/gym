from collections.abc import Iterator
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app import mailer
from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.inventory import models as inventory_models
from app.modules.inventory import statements
from app.modules.memberships.models import Member


def _build_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _: object) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _seed_users(session: Session) -> None:
    ensure_default_access_control(session)
    for email, password, role in (
        ("manager@example.com", "manager-strong-password", "manager"),
        ("reception@example.com", "reception-strong-password", "reception"),
        ("accountant@example.com", "accountant-strong-password", "accountant"),
        ("trainer@example.com", "trainer-strong-password", "trainer"),
    ):
        register_user(session, email=email, password=password, role_codes=(role,))


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _override(engine):
    def dependency() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    return dependency


def _seed_members(session: Session):
    member = Member(
        first_name="Ana",
        last_name="Lopez",
        email="ana@example.com",
        phone="+52 555 123 4567",
        status="active",
    )
    no_email = Member(first_name="Beto", last_name="Ruiz", status="active")
    session.add_all([member, no_email])
    session.commit()
    return member.id, no_email.id


def _create_product(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/admin/products",
        headers=headers,
        json={
            "sku": "agua-600",
            "name": "Agua 600 ml",
            "category": "Bebidas",
            "price_cents": 1500,
            "initial_stock": 40,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _charge_account(
    client: TestClient, headers: dict[str, str], product_id: str, member_id, quantity: int = 2
):
    response = client.post(
        "/admin/sales",
        headers=headers,
        json={
            "items": [{"product_id": product_id, "quantity": quantity}],
            "payment_method": "account",
            "member_id": str(member_id),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_statement_csv_and_pdf_exports_follow_read_permissions() -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id, _ = _seed_members(session)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            product_id = _create_product(client, manager)
            client.post(
                "/admin/cash-sessions",
                headers=reception,
                json={"opening_cash_cents": 0},
            )
            sale = _charge_account(client, reception, product_id, member_id)
            assert sale["total_cents"] == 3000

            statement = client.get(
                f"/admin/member-accounts/{member_id}", headers=reception
            )
            assert statement.status_code == 200, statement.text
            assert statement.json()["as_of"]

            csv_response = client.get(
                f"/admin/member-accounts/{member_id}/statement.csv", headers=reception
            )
            assert csv_response.status_code == 200, csv_response.text
            assert csv_response.headers["content-type"].startswith("text/csv")
            disposition = csv_response.headers["content-disposition"]
            assert "estado-cuenta-ana-lopez-" in disposition
            assert disposition.endswith('.csv"')
            assert csv_response.content.startswith(b"\xef\xbb\xbf")
            csv_text = csv_response.content.decode("utf-8-sig")
            assert "Ana Lopez" in csv_text
            # A leading plus is a spreadsheet formula trigger; keep it as text.
            assert "Teléfono,'+52 555 123 4567" in csv_text
            assert "V-" in csv_text
            assert "30.00" in csv_text
            assert "0-30 días" in csv_text
            assert "Movimientos (del más antiguo al más reciente)" in csv_text

            pdf_response = client.get(
                f"/admin/member-accounts/{member_id}/statement.pdf", headers=reception
            )
            assert pdf_response.status_code == 200, pdf_response.text
            assert pdf_response.headers["content-type"] == "application/pdf"
            assert pdf_response.content.startswith(b"%PDF-")
            assert "estado-cuenta-ana-lopez-" in pdf_response.headers["content-disposition"]

            # The accountant can audit the account; the trainer cannot read sales.
            assert client.get(
                f"/admin/member-accounts/{member_id}/statement.csv", headers=accountant
            ).status_code == 200
            assert client.get(
                f"/admin/member-accounts/{member_id}/statement.pdf", headers=accountant
            ).status_code == 200
            assert client.get(
                f"/admin/member-accounts/{member_id}/statement.csv", headers=trainer
            ).status_code == 403
            assert client.get(
                f"/admin/member-accounts/{uuid4()}/statement.csv", headers=reception
            ).status_code == 404
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_send_statement_simulates_in_preview_and_records_audit(
    monkeypatch,
) -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id, no_email_id = _seed_members(session)

    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setenv("PREVIEW_MODE", "true")
    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            product_id = _create_product(client, manager)
            client.post(
                "/admin/cash-sessions",
                headers=reception,
                json={"opening_cash_cents": 0},
            )
            _charge_account(client, reception, product_id, member_id)

            sent = client.post(
                f"/admin/member-accounts/{member_id}/statement/send",
                headers=reception,
                json={"format": "pdf"},
            )
            assert sent.status_code == 201, sent.text
            body = sent.json()
            assert body["status"] == "simulated"
            assert body["recipient"] == "ana@example.com"
            assert body["format"] == "pdf"
            assert body["as_of"]
            assert body["error"] is None

            csv_sent = client.post(
                f"/admin/member-accounts/{member_id}/statement/send",
                headers=manager,
                json={"format": "csv"},
            )
            assert csv_sent.status_code == 201, csv_sent.text
            assert csv_sent.json()["status"] == "simulated"
            assert csv_sent.json()["format"] == "csv"

            # A member without email can receive an explicit recipient, but not
            # an implicit one.
            missing = client.post(
                f"/admin/member-accounts/{no_email_id}/statement/send",
                headers=reception,
                json={"format": "pdf"},
            )
            assert missing.status_code == 422
            assert "correo" in missing.json()["detail"]
            override = client.post(
                f"/admin/member-accounts/{no_email_id}/statement/send",
                headers=reception,
                json={"format": "pdf", "recipient": "tutor@example.com"},
            )
            assert override.status_code == 201, override.text
            assert override.json()["recipient"] == "tutor@example.com"

            # Sending is a register operation, not a read-only audit permission.
            assert client.post(
                f"/admin/member-accounts/{member_id}/statement/send",
                headers=accountant,
                json={"format": "pdf"},
            ).status_code == 403
            assert client.post(
                f"/admin/member-accounts/{member_id}/statement/send",
                headers=trainer,
                json={"format": "pdf"},
            ).status_code == 403
            assert client.post(
                f"/admin/member-accounts/{member_id}/statement/send",
                headers=reception,
                json={"format": "xml"},
            ).status_code == 422
            assert client.post(
                f"/admin/member-accounts/{uuid4()}/statement/send",
                headers=reception,
                json={"format": "pdf"},
            ).status_code == 404

        with Session(engine) as session:
            rows = session.exec(
                select(inventory_models.MemberAccountStatementDelivery).order_by(
                    inventory_models.MemberAccountStatementDelivery.created_at
                )
            ).all()
            assert len(rows) == 3
            assert [row.status for row in rows] == ["simulated", "simulated", "simulated"]
            assert rows[0].channel == "email"
            assert rows[0].recipient == "ana@example.com"
            assert rows[2].recipient == "tutor@example.com"
            assert rows[0].actor_id is not None
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_send_statement_uses_smtp_and_records_failures(monkeypatch) -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id, _ = _seed_members(session)

    class FakeSMTP:
        instances: list["FakeSMTP"] = []

        def __init__(self, host: str, port: int, timeout: float) -> None:
            self.host = host
            self.port = port
            self.timeout = timeout
            self.started_tls = False
            self.login_args: tuple[str, str] | None = None
            self.message = None
            FakeSMTP.instances.append(self)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> bool:
            return False

        def starttls(self, context=None) -> None:
            self.started_tls = True

        def login(self, username: str, password: str) -> None:
            self.login_args = (username, password)

        def send_message(self, message) -> None:
            self.message = message

    class FailingSMTP(FakeSMTP):
        def send_message(self, message) -> None:
            raise mailer.smtplib.SMTPException("smtp down")

    monkeypatch.delenv("PREVIEW_MODE", raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_FROM", "club@example.test")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setenv("SMTP_USE_TLS", "true")
    monkeypatch.setenv("SMTP_USE_SSL", "false")
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)

    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            product_id = _create_product(client, manager)
            client.post(
                "/admin/cash-sessions",
                headers=reception,
                json={"opening_cash_cents": 0},
            )
            _charge_account(client, reception, product_id, member_id)

            sent = client.post(
                f"/admin/member-accounts/{member_id}/statement/send",
                headers=reception,
                json={"format": "pdf"},
            )
            assert sent.status_code == 201, sent.text
            assert sent.json()["status"] == "sent"
            assert len(FakeSMTP.instances) == 1
            connection = FakeSMTP.instances[0]
            assert connection.host == "smtp.test"
            assert connection.port == 2525
            assert connection.started_tls is True
            assert connection.login_args == ("smtp-user", "smtp-secret")
            assert connection.message is not None
            assert connection.message["To"] == "ana@example.com"
            attachments = list(connection.message.iter_attachments())
            assert len(attachments) == 1
            assert attachments[0].get_filename().startswith("estado-cuenta-ana-lopez-")
            assert attachments[0].get_content_type() == "application/pdf"

            monkeypatch.setattr(mailer.smtplib, "SMTP", FailingSMTP)
            failed = client.post(
                f"/admin/member-accounts/{member_id}/statement/send",
                headers=reception,
                json={"format": "csv"},
            )
            assert failed.status_code == 502, failed.text
            assert "No se pudo enviar" in failed.json()["detail"]

            with Session(engine) as session:
                rows = session.exec(
                    select(inventory_models.MemberAccountStatementDelivery).order_by(
                        inventory_models.MemberAccountStatementDelivery.created_at
                    )
                ).all()
                assert [row.status for row in rows] == ["sent", "failed"]
                assert rows[1].error and "smtp down" in rows[1].error
                assert rows[1].format == "csv"
                failed_id = rows[1].id

            # Retrying a failed attempt uses the original recipient and format
            # and appends a new row linked to the failure.
            monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
            retried = client.post(
                f"/admin/member-accounts/{member_id}/statement/deliveries/{failed_id}/retry",
                headers=reception,
            )
            assert retried.status_code == 201, retried.text
            assert retried.json()["status"] == "sent"
            assert retried.json()["format"] == "csv"
            assert retried.json()["recipient"] == "ana@example.com"
            assert retried.json()["retry_of_id"] == str(failed_id)

        with Session(engine) as session:
            rows = session.exec(
                select(inventory_models.MemberAccountStatementDelivery).order_by(
                    inventory_models.MemberAccountStatementDelivery.created_at
                )
            ).all()
            assert [row.status for row in rows] == ["sent", "failed", "sent"]
            assert rows[2].retry_of_id == failed_id
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_statement_delivery_history_and_retry(monkeypatch) -> None:
    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_users(session)
        member_id, no_email_id = _seed_members(session)

    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setenv("PREVIEW_MODE", "true")
    app.dependency_overrides[get_session] = _override(engine)
    try:
        with TestClient(app) as client:
            manager = _login(client, "manager@example.com", "manager-strong-password")
            reception = _login(client, "reception@example.com", "reception-strong-password")
            accountant = _login(client, "accountant@example.com", "accountant-strong-password")
            trainer = _login(client, "trainer@example.com", "trainer-strong-password")
            product_id = _create_product(client, manager)
            client.post(
                "/admin/cash-sessions",
                headers=reception,
                json={"opening_cash_cents": 0},
            )
            _charge_account(client, reception, product_id, member_id)

            first = client.post(
                f"/admin/member-accounts/{member_id}/statement/send",
                headers=reception,
                json={"format": "pdf"},
            )
            second = client.post(
                f"/admin/member-accounts/{member_id}/statement/send",
                headers=manager,
                json={"format": "csv"},
            )
            assert first.status_code == 201, first.text
            assert second.status_code == 201, second.text
            first_id = first.json()["id"]
            second_id = second.json()["id"]

            history = client.get(
                f"/admin/member-accounts/{member_id}/statement/deliveries",
                headers=reception,
            )
            assert history.status_code == 200, history.text
            body = history.json()
            assert body["total"] == 2
            assert body["page"] == 1
            assert body["pages"] == 1
            assert len(body["items"]) == 2
            assert body["items"][0]["created_at"] >= body["items"][1]["created_at"]
            by_id = {item["id"]: item for item in body["items"]}
            assert by_id[first_id]["recipient"] == "ana@example.com"
            assert by_id[first_id]["format"] == "pdf"
            assert by_id[first_id]["actor_email"] == "reception@example.com"
            assert by_id[first_id]["retry_of_id"] is None
            assert by_id[second_id]["format"] == "csv"
            assert by_id[second_id]["actor_email"] == "manager@example.com"

            paged = client.get(
                f"/admin/member-accounts/{member_id}/statement/deliveries",
                headers=reception,
                params={"page": 2, "page_size": 1},
            )
            assert paged.status_code == 200, paged.text
            assert paged.json()["total"] == 2
            assert paged.json()["page"] == 2
            assert paged.json()["page_size"] == 1
            assert paged.json()["pages"] == 2
            assert len(paged.json()["items"]) == 1

            # The accountant can audit the history; sending/retrying is a
            # register operation reserved to sales.manage.
            assert client.get(
                f"/admin/member-accounts/{member_id}/statement/deliveries",
                headers=accountant,
            ).status_code == 200
            assert client.get(
                f"/admin/member-accounts/{member_id}/statement/deliveries",
                headers=trainer,
            ).status_code == 403
            assert client.get(
                f"/admin/member-accounts/{uuid4()}/statement/deliveries",
                headers=reception,
            ).status_code == 404

            retried = client.post(
                f"/admin/member-accounts/{member_id}/statement/deliveries/{first_id}/retry",
                headers=reception,
            )
            assert retried.status_code == 201, retried.text
            retried_body = retried.json()
            assert retried_body["status"] == "simulated"
            assert retried_body["format"] == "pdf"
            assert retried_body["recipient"] == "ana@example.com"
            assert retried_body["retry_of_id"] == first_id

            after_retry = client.get(
                f"/admin/member-accounts/{member_id}/statement/deliveries",
                headers=reception,
            )
            assert after_retry.status_code == 200, after_retry.text
            assert after_retry.json()["total"] == 3
            retried_item = next(
                item for item in after_retry.json()["items"] if item["id"] == retried_body["id"]
            )
            assert retried_item["retry_of_id"] == first_id
            assert retried_item["actor_email"] == "reception@example.com"

            assert client.post(
                f"/admin/member-accounts/{member_id}/statement/deliveries/{second_id}/retry",
                headers=accountant,
            ).status_code == 403
            assert client.post(
                f"/admin/member-accounts/{member_id}/statement/deliveries/{second_id}/retry",
                headers=trainer,
            ).status_code == 403
            assert client.post(
                f"/admin/member-accounts/{member_id}/statement/deliveries/{uuid4()}/retry",
                headers=reception,
            ).status_code == 404

            other = client.post(
                f"/admin/member-accounts/{no_email_id}/statement/send",
                headers=reception,
                json={"format": "pdf", "recipient": "tutor@example.com"},
            )
            assert other.status_code == 201, other.text
            assert client.post(
                f"/admin/member-accounts/{member_id}/statement/deliveries/{other.json()['id']}/retry",
                headers=reception,
            ).status_code == 404

            # A real delivery is not retried from the history to avoid duplicate
            # financial emails. Mark the row as sent to exercise that branch in
            # preview mode.
            with Session(engine) as session:
                record = session.get(
                    inventory_models.MemberAccountStatementDelivery,
                    UUID(retried_body["id"]),
                )
                assert record is not None
                record.status = "sent"
                session.add(record)
                session.commit()
            rejected = client.post(
                f"/admin/member-accounts/{member_id}/statement/deliveries/{retried_body['id']}/retry",
                headers=reception,
            )
            assert rejected.status_code == 409, rejected.text
            assert "Solo se pueden reintentar" in rejected.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
