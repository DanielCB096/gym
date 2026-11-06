from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, select

from app.main import app, get_session
from app.modules.identity import service as identity_service
from app.modules.identity.models import AuthEvent
from app.modules.identity.service import (
    InvalidMfaChallenge,
    MfaManagementLocked,
    MfaNotAvailable,
    MfaPasswordRejected,
    authenticate_user,
    begin_mfa_enrollment,
    begin_mfa_rotation,
    confirm_mfa_enrollment,
    confirm_mfa_rotation,
    disable_mfa,
    ensure_default_access_control,
    get_mfa_status,
    register_user,
    verify_mfa_challenge,
)


NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
PASSWORD = "owner-correct-horse-battery"


@pytest.fixture
def owner(session: Session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", "test-mfa-encryption-key")
    ensure_default_access_control(session)
    return register_user(
        session,
        email="owner-mfa@ritmo.test",
        password=PASSWORD,
        role_codes=("owner",),
        now=NOW,
    )


def _enable_mfa(session: Session, user) -> tuple[str, list[str]]:
    enrollment = begin_mfa_enrollment(
        session,
        user_id=user.id,
        password=PASSWORD,
        now=NOW,
    )
    confirmation = confirm_mfa_enrollment(
        session,
        user_id=user.id,
        code=identity_service._totp(enrollment.secret),
        now=NOW,
    )
    return enrollment.secret, list(confirmation.backup_codes)


def test_enrollment_activates_mfa_and_issues_ten_backup_codes(session: Session, owner) -> None:
    initial = get_mfa_status(session, user_id=owner.id, now=NOW)
    assert initial.available is True
    assert initial.enabled is False
    assert initial.pending is False

    enrollment = begin_mfa_enrollment(
        session,
        user_id=owner.id,
        password=PASSWORD,
        now=NOW,
    )
    assert enrollment.otp_uri.startswith("otpauth://totp/")
    assert get_mfa_status(session, user_id=owner.id, now=NOW).pending is True

    confirmation = confirm_mfa_enrollment(
        session,
        user_id=owner.id,
        code=identity_service._totp(enrollment.secret),
        now=NOW,
    )
    assert confirmation.rotated is False
    assert len(confirmation.backup_codes) == 10

    status = get_mfa_status(session, user_id=owner.id, now=NOW)
    assert status.enabled is True
    assert status.enabled_at is not None
    assert status.backup_codes_remaining == 10
    assert status.pending is False

    login = authenticate_user(session, email=owner.email, password=PASSWORD, now=NOW)
    assert login.mfa_required is True
    assert login.access_token is None


def test_begin_enrollment_rejects_a_wrong_password(session: Session, owner) -> None:
    with pytest.raises(MfaPasswordRejected):
        begin_mfa_enrollment(
            session,
            user_id=owner.id,
            password="not-the-password",
            now=NOW,
        )
    assert get_mfa_status(session, user_id=owner.id, now=NOW).enabled is False


def test_enrollment_is_limited_to_management_roles(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", "test-mfa-encryption-key")
    ensure_default_access_control(session)
    reception = register_user(
        session,
        email="reception-mfa@ritmo.test",
        password="reception-correct-horse-battery",
        role_codes=("reception",),
        now=NOW,
    )

    assert get_mfa_status(session, user_id=reception.id, now=NOW).available is False
    with pytest.raises(MfaNotAvailable):
        begin_mfa_enrollment(
            session,
            user_id=reception.id,
            password="reception-correct-horse-battery",
            now=NOW,
        )


def test_rotation_keeps_the_old_factor_until_it_is_confirmed(session: Session, owner) -> None:
    old_secret, old_codes = _enable_mfa(session, owner)
    old_code = identity_service._totp(old_secret)

    rotation = begin_mfa_rotation(
        session,
        user_id=owner.id,
        password=PASSWORD,
        code=old_code,
        now=NOW,
    )
    assert rotation.secret != old_secret

    # The old authenticator still works while the new secret is pending.
    pending_login = authenticate_user(session, email=owner.email, password=PASSWORD, now=NOW)
    verified = verify_mfa_challenge(
        session,
        challenge_id=pending_login.mfa_challenge_id,
        code=old_code,
        now=NOW,
    )
    assert verified.access_token is not None

    confirmation = confirm_mfa_rotation(
        session,
        user_id=owner.id,
        code=identity_service._totp(rotation.secret),
        now=NOW,
    )
    assert confirmation.rotated is True
    assert len(confirmation.backup_codes) == 10
    assert set(confirmation.backup_codes).isdisjoint(old_codes)

    new_login = authenticate_user(session, email=owner.email, password=PASSWORD, now=NOW)
    with pytest.raises(InvalidMfaChallenge):
        verify_mfa_challenge(
            session,
            challenge_id=new_login.mfa_challenge_id,
            code=old_code,
            now=NOW,
        )

    new_login = authenticate_user(session, email=owner.email, password=PASSWORD, now=NOW)
    verified = verify_mfa_challenge(
        session,
        challenge_id=new_login.mfa_challenge_id,
        code=identity_service._totp(rotation.secret),
        now=NOW,
    )
    assert verified.access_token is not None

    # Old backup codes were deleted with the rotation.
    replay_login = authenticate_user(session, email=owner.email, password=PASSWORD, now=NOW)
    with pytest.raises(InvalidMfaChallenge):
        verify_mfa_challenge(
            session,
            challenge_id=replay_login.mfa_challenge_id,
            code=old_codes[0],
            now=NOW,
        )


def test_expired_rotation_does_not_replace_the_active_secret(session: Session, owner) -> None:
    old_secret, _ = _enable_mfa(session, owner)
    old_code = identity_service._totp(old_secret)
    begin_mfa_rotation(
        session,
        user_id=owner.id,
        password=PASSWORD,
        code=old_code,
        now=NOW,
    )

    with pytest.raises(InvalidMfaChallenge, match="expiró"):
        confirm_mfa_rotation(
            session,
            user_id=owner.id,
            code=identity_service._totp(identity_service._base32_secret()),
            now=NOW + timedelta(minutes=16),
        )

    login = authenticate_user(session, email=owner.email, password=PASSWORD, now=NOW)
    verified = verify_mfa_challenge(
        session,
        challenge_id=login.mfa_challenge_id,
        code=old_code,
        now=NOW,
    )
    assert verified.access_token is not None


def test_disable_requires_password_and_factor_and_clears_the_secret(session: Session, owner) -> None:
    secret, _ = _enable_mfa(session, owner)

    with pytest.raises(MfaPasswordRejected):
        disable_mfa(
            session,
            user_id=owner.id,
            password="not-the-password",
            code=identity_service._totp(secret),
            now=NOW,
        )
    assert get_mfa_status(session, user_id=owner.id, now=NOW).enabled is True

    disable_mfa(
        session,
        user_id=owner.id,
        password=PASSWORD,
        code=identity_service._totp(secret),
        now=NOW,
    )
    status = get_mfa_status(session, user_id=owner.id, now=NOW)
    assert status.enabled is False
    assert status.enabled_at is None
    assert status.backup_codes_remaining == 0

    login = authenticate_user(session, email=owner.email, password=PASSWORD, now=NOW)
    assert login.mfa_required is False
    assert login.access_token is not None


def test_five_invalid_codes_lock_the_management_flow(session: Session, owner) -> None:
    enrollment = begin_mfa_enrollment(
        session,
        user_id=owner.id,
        password=PASSWORD,
        now=NOW,
    )

    for _ in range(4):
        with pytest.raises(InvalidMfaChallenge):
            confirm_mfa_enrollment(
                session,
                user_id=owner.id,
                code="000000",
                now=NOW,
            )

    with pytest.raises(MfaManagementLocked):
        confirm_mfa_enrollment(
            session,
            user_id=owner.id,
            code="000000",
            now=NOW,
        )

    failures = session.exec(
        select(AuthEvent).where(AuthEvent.event_type == "mfa_management")
    ).all()
    assert len(failures) == 5

    # The lock is real: even the correct pending code is rejected.
    with pytest.raises(MfaManagementLocked):
        confirm_mfa_enrollment(
            session,
            user_id=owner.id,
            code=identity_service._totp(enrollment.secret),
            now=NOW,
        )

    # Ten minutes later the window has passed and the pending code is accepted.
    confirmation = confirm_mfa_enrollment(
        session,
        user_id=owner.id,
        code=identity_service._totp(enrollment.secret),
        now=NOW + timedelta(minutes=11),
    )
    assert len(confirmation.backup_codes) == 10
    assert get_mfa_status(session, user_id=owner.id, now=NOW + timedelta(minutes=11)).enabled is True


def test_mfa_management_endpoints_are_wired(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", "test-mfa-encryption-key")
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

    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_default_access_control(session)
        register_user(
            session,
            email="owner-api-mfa@example.com",
            password=PASSWORD,
            role_codes=("owner",),
        )

    def override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    try:
        with TestClient(app) as client:
            login = client.post(
                "/auth/login",
                json={"email": "owner-api-mfa@example.com", "password": PASSWORD},
            )
            assert login.status_code == 200
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            status_response = client.get("/auth/mfa/status", headers=headers)
            assert status_response.status_code == 200
            assert status_response.json()["available"] is True
            assert status_response.json()["enabled"] is False

            rejected = client.post(
                "/auth/mfa/enroll",
                headers=headers,
                json={"password": "wrong-password"},
            )
            assert rejected.status_code == 403

            enrolled = client.post(
                "/auth/mfa/enroll",
                headers=headers,
                json={"password": PASSWORD},
            )
            assert enrolled.status_code == 200
            secret = enrolled.json()["secret"]

            confirmed = client.post(
                "/auth/mfa/enroll/confirm",
                headers=headers,
                json={"code": identity_service._totp(secret)},
            )
            assert confirmed.status_code == 200
            assert len(confirmed.json()["backup_codes"]) == 10

            enabled = client.get("/auth/mfa/status", headers=headers).json()
            assert enabled["enabled"] is True
            assert enabled["backup_codes_remaining"] == 10

            rotated = client.post(
                "/auth/mfa/rotate",
                headers=headers,
                json={"password": PASSWORD, "code": identity_service._totp(secret)},
            )
            assert rotated.status_code == 200
            new_secret = rotated.json()["secret"]

            rotation_confirmed = client.post(
                "/auth/mfa/rotate/confirm",
                headers=headers,
                json={"code": identity_service._totp(new_secret)},
            )
            assert rotation_confirmed.status_code == 200
            assert rotation_confirmed.json()["rotated"] is True

            disabled = client.post(
                "/auth/mfa/disable",
                headers=headers,
                json={"password": PASSWORD, "code": identity_service._totp(new_secret)},
            )
            assert disabled.status_code == 204
            assert client.get("/auth/mfa/status", headers=headers).json()["enabled"] is False
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()
