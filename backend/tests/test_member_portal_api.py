from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.main import app, get_session
from app.modules.identity.service import ensure_default_access_control, register_user
from app.modules.memberships.models import Member, Membership, Plan
from app.modules.portal.models import MemberLoginCode
from app.modules.portal.service import (
    CODE_LIFETIME,
    CODE_MAX_ATTEMPTS,
    CODE_MAX_REQUESTS,
    InvalidMemberCode,
    request_login_code,
    verify_login_code,
)


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


def _seed_member(session: Session) -> UUID:
    now = datetime.now(timezone.utc)
    plan = Plan(code="MONTHLY", name="Mensual", duration_days=30, price_cents=50000)
    member = Member(first_name="Ana", last_name="Lopez", email="ana@example.com", status="active")
    session.add_all([member, plan])
    session.flush()
    session.add(
        Membership(
            member_id=member.id,
            plan_id=plan.id,
            status="active",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=29),
        )
    )
    session.commit()
    return member.id


def _wrong_code(code: str) -> str:
    return "999999" if code != "999999" else "000000"


def test_member_otp_login_profile_and_session_isolation(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-portal-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")
    monkeypatch.setenv("GYM_NAME", "Centro Fit")

    engine = _build_engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="owner@example.com",
            password="owner-strong-password",
            role_codes=("owner",),
        )
        _seed_member(session)

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            unknown = client.post(
                "/member/auth/request-code",
                json={"email": "nobody@example.com"},
            )
            assert unknown.status_code == 202
            assert unknown.json()["preview_code"] is None

            requested = client.post(
                "/member/auth/request-code",
                json={"email": "ANA@example.com"},
            )
            assert requested.status_code == 202
            code = requested.json()["preview_code"]
            assert code is not None and len(code) == 6 and code.isdigit()
            assert requested.json()["expires_in"] == CODE_LIFETIME.seconds

            rejected = client.post(
                "/member/auth/verify",
                json={"email": "ana@example.com", "code": _wrong_code(code)},
            )
            assert rejected.status_code == 401

            verified = client.post(
                "/member/auth/verify",
                json={"email": "ana@example.com", "code": code},
            )
            assert verified.status_code == 200
            member_token = verified.json()["access_token"]
            member_headers = {"Authorization": f"Bearer {member_token}"}
            assert verified.json()["member"]["first_name"] == "Ana"

            profile = client.get("/member/me", headers=member_headers)
            assert profile.status_code == 200
            body = profile.json()
            assert body["email"] == "ana@example.com"
            assert body["membership"]["plan_name"] == "Mensual"
            assert body["membership"]["days_remaining"] >= 28
            assert body["access_enabled"] is True
            assert body["balance_cents"] == 0

            assert client.get("/admin/dashboard", headers=member_headers).status_code == 401

            owner_login = client.post(
                "/auth/login",
                json={"email": "owner@example.com", "password": "owner-strong-password"},
            )
            assert owner_login.status_code == 200
            staff_headers = {"Authorization": f"Bearer {owner_login.json()['access_token']}"}
            assert client.get("/member/me", headers=staff_headers).status_code == 401

            assert client.post("/member/auth/logout", headers=member_headers).status_code == 204
            assert client.get("/member/me", headers=member_headers).status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_member_code_expires_and_locks_after_attempts(session: Session, monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-portal-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")
    member_id = _seed_member(session)
    now = datetime.now(timezone.utc)

    expired = request_login_code(session, email="ana@example.com", now=now)
    assert expired.preview_code is not None
    with pytest.raises(InvalidMemberCode):
        verify_login_code(
            session,
            email="ana@example.com",
            code=expired.preview_code,
            now=now + CODE_LIFETIME + timedelta(seconds=1),
        )

    later = now + CODE_LIFETIME + timedelta(minutes=2)
    fresh = request_login_code(session, email="ana@example.com", now=later)
    assert fresh.preview_code is not None
    for _ in range(CODE_MAX_ATTEMPTS):
        with pytest.raises(InvalidMemberCode):
            verify_login_code(
                session,
                email="ana@example.com",
                code=_wrong_code(fresh.preview_code),
                now=later,
            )
    with pytest.raises(InvalidMemberCode):
        verify_login_code(session, email="ana@example.com", code=fresh.preview_code, now=later)

    latest = session.exec(
        select(MemberLoginCode)
        .where(MemberLoginCode.member_id == member_id)
        .order_by(MemberLoginCode.created_at.desc())
    ).first()
    assert latest is not None
    assert latest.attempts == CODE_MAX_ATTEMPTS
    assert latest.consumed_at is None


def test_member_code_requests_are_rate_limited(session: Session, monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-portal-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")
    _seed_member(session)
    now = datetime.now(timezone.utc)

    for _ in range(CODE_MAX_REQUESTS):
        assert request_login_code(session, email="ana@example.com", now=now).preview_code is not None
    blocked = request_login_code(session, email="ana@example.com", now=now)
    assert blocked.preview_code is None


def test_member_code_is_not_sent_to_inactive_or_unknown_emails(
    session: Session, monkeypatch
) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-member-portal-secret")
    monkeypatch.setenv("PREVIEW_MODE", "true")
    session.add(Member(first_name="Beto", last_name="Ruiz", email="beto@example.com", status="inactive"))
    session.commit()

    assert request_login_code(session, email="beto@example.com").preview_code is None
    assert request_login_code(session, email="nobody@example.com").preview_code is None
    assert session.exec(select(MemberLoginCode)).first() is None
