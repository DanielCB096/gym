from collections.abc import Iterator
from sqlite3 import Connection
from uuid import UUID

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

from app.modules.identity import models as identity_models
from app.modules.memberships import models


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection: Connection, _: object) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db_session:
        yield db_session
    engine.dispose()


@pytest.fixture
def seeded_ids(session: Session) -> tuple[UUID, UUID, UUID]:
    from app.modules.memberships.models import Member, MemberConsent, PaymentMethod, Plan, utc_now

    member = Member(first_name="Ana", last_name="Lopez", email="ana@example.test")
    plan = Plan(code="MONTHLY", name="Mensual", duration_days=30, price_cents=50000)
    session.add_all([member, plan])
    session.flush()
    session.add(
        MemberConsent(
            member_id=member.id,
            consent_type="privacy_notice",
            document_version="v1",
            accepted_at=utc_now(),
        )
    )
    payment_method = PaymentMethod(
        member_id=member.id,
        provider="test-gateway",
        provider_method_id="pm_ana_1",
        encrypted_provider_token=b"encrypted-token",
        is_default=True,
    )
    session.add(payment_method)
    session.commit()
    return member.id, plan.id, payment_method.id