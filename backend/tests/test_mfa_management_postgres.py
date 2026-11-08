"""PostgreSQL-only checks for self-service MFA (ADR-089 and ADR-090).

Skipped unless ``TEST_POSTGRES_URL`` points at a disposable PostgreSQL database
that has been migrated with ``alembic upgrade head``. This file deliberately does
not call ``create_all``: the point is to exercise the schema the migration leaves
behind, which SQLite cannot show. ``LargeBinary`` becomes ``bytea`` and every
``DateTime(timezone=True)`` becomes ``timestamptz``, so the encrypted secret, the
pending-secret deadline, the failure window and the session revocation all read
back timezone-aware and byte-exact instead of going through SQLite's affinities.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlmodel import Session, select

from app.modules.identity import service as identity_service
from app.modules.identity.models import AppUser, AuthEvent, UserSession
from app.modules.identity.service import (
    InvalidMfaChallenge,
    InvalidSession,
    MfaManagementLocked,
    MfaPasswordRejected,
    authenticate_session,
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

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="TEST_POSTGRES_URL no definido; usa una base desechable",
)

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
PASSWORD = "owner-correct-horse-battery"
PENDING_COLUMNS = ("mfa_pending_secret_encrypted", "mfa_pending_created_at")


def _require_migrated_schema(engine) -> None:
    """Refuse to run against a database that Alembic did not build."""
    ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    head = ScriptDirectory.from_config(Config(str(ini))).get_current_head()
    message = (
        "TEST_POSTGRES_URL debe apuntar a una base desechable migrada con "
        f"'alembic upgrade head' (se esperaba la revisión {head})."
    )
    if not inspect(engine).has_table("alembic_version"):
        pytest.fail(message)
    with engine.connect() as connection:
        applied = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
    if applied != head:
        pytest.fail(f"{message} La base está en {applied}.")


@pytest.fixture(scope="module")
def engine():
    pg_engine = create_engine(POSTGRES_URL)
    _require_migrated_schema(pg_engine)
    yield pg_engine
    pg_engine.dispose()


@pytest.fixture
def pg_session(engine):
    with Session(engine, expire_on_commit=False) as db_session:
        yield db_session


@pytest.fixture
def account(pg_session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", "test-mfa-encryption-key")
    ensure_default_access_control(pg_session)
    suffix = uuid.uuid4().hex[:10]
    return register_user(
        pg_session,
        email=f"mfa-pg-{suffix}@ritmo.test",
        password=PASSWORD,
        role_codes=("owner",),
        now=NOW,
    )


def _enable_mfa(session: Session, user, *, now: datetime = NOW) -> str:
    enrollment = begin_mfa_enrollment(
        session, user_id=user.id, password=PASSWORD, now=now
    )
    confirm_mfa_enrollment(
        session,
        user_id=user.id,
        code=identity_service._totp(enrollment.secret),
        now=now,
    )
    session.commit()
    return enrollment.secret


def _open_session(session: Session, user, secret: str, *, now: datetime):
    login = authenticate_user(session, email=user.email, password=PASSWORD, now=now)
    assert login.mfa_required is True
    assert login.mfa_challenge_id is not None
    verified = verify_mfa_challenge(
        session,
        challenge_id=login.mfa_challenge_id,
        code=identity_service._totp(secret),
        now=now,
    )
    assert verified.access_token is not None
    principal = authenticate_session(session, verified.access_token, now=now)
    return verified.access_token, principal


def _revocation_events(session: Session, user_id) -> list[AuthEvent]:
    return list(
        session.exec(
            select(AuthEvent)
            .where(AuthEvent.user_id == user_id, AuthEvent.event_type == "session_revoked")
            .order_by(AuthEvent.occurred_at)
        ).all()
    )


def test_migration_0091_leaves_the_pending_columns_as_bytea_and_timestamptz(engine) -> None:
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name = 'app_users' AND column_name = ANY(%s)",
            (list(PENDING_COLUMNS),),
        ).all()
    assert {row[0] for row in rows} == set(PENDING_COLUMNS)
    by_name = {row[0]: (row[1], row[2]) for row in rows}
    assert by_name["mfa_pending_secret_encrypted"] == ("bytea", "YES")
    assert by_name["mfa_pending_created_at"] == ("timestamp with time zone", "YES")


def test_the_encrypted_secret_survives_bytea_and_stays_bound_to_its_user(
    engine, pg_session, account
) -> None:
    secret = _enable_mfa(pg_session, account)

    # A different session reads what PostgreSQL actually stored, not the ORM cache.
    with Session(engine) as fresh:
        stored = fresh.get(AppUser, account.id)
        assert stored is not None
        ciphertext = stored.mfa_secret_encrypted
        assert isinstance(ciphertext, bytes)
        assert ciphertext[0] == 1
        assert len(ciphertext) >= 30
        assert stored.mfa_pending_secret_encrypted is None
        assert stored.mfa_pending_created_at is None
        assert stored.mfa_enabled_at is not None
        assert stored.mfa_enabled_at.utcoffset() == timedelta(0)
        assert identity_service._decrypt_mfa_secret(ciphertext, stored.id) == secret
        assert identity_service._verify_totp(secret, identity_service._totp(secret))
        with pytest.raises(InvalidMfaChallenge):
            identity_service._decrypt_mfa_secret(ciphertext, uuid.uuid4())


def test_the_pending_secret_expires_at_fifteen_minutes_with_timestamptz(
    engine, pg_session, account
) -> None:
    enrollment = begin_mfa_enrollment(
        pg_session, user_id=account.id, password=PASSWORD, now=NOW
    )
    pg_session.commit()

    with Session(engine) as fresh:
        stored = fresh.get(AppUser, account.id)
        assert stored is not None
        assert stored.mfa_pending_created_at is not None
        assert stored.mfa_pending_created_at.utcoffset() == timedelta(0)
        assert stored.mfa_pending_created_at == NOW
        assert get_mfa_status(fresh, user_id=account.id, now=NOW + timedelta(minutes=14)).pending
        assert not get_mfa_status(
            fresh, user_id=account.id, now=NOW + timedelta(minutes=15)
        ).pending

        with pytest.raises(InvalidMfaChallenge, match="expiró"):
            confirm_mfa_enrollment(
                fresh,
                user_id=account.id,
                code=identity_service._totp(enrollment.secret),
                now=NOW + timedelta(minutes=15),
            )
        fresh.commit()
        rejected = fresh.get(AppUser, account.id)
        assert rejected is not None
        assert rejected.mfa_enabled is False
        assert rejected.mfa_secret_encrypted is None
        assert rejected.mfa_pending_secret_encrypted is not None

    # One second before the deadline the very same code is still accepted.
    confirmed = confirm_mfa_enrollment(
        pg_session,
        user_id=account.id,
        code=identity_service._totp(enrollment.secret),
        now=NOW + timedelta(minutes=15) - timedelta(seconds=1),
    )
    pg_session.commit()
    assert confirmed.rotated is False
    assert len(confirmed.backup_codes) == 10
    with Session(engine) as fresh:
        stored = fresh.get(AppUser, account.id)
        assert stored is not None
        assert stored.mfa_enabled is True
        assert stored.mfa_pending_secret_encrypted is None
        assert stored.mfa_pending_created_at is None


def test_the_failure_window_is_counted_over_timestamptz_and_releases_after_ten_minutes(
    pg_session, account
) -> None:
    for _ in range(4):
        with pytest.raises(MfaPasswordRejected):
            begin_mfa_enrollment(
                pg_session, user_id=account.id, password="wrong-password", now=NOW
            )

    fifth = NOW + timedelta(minutes=1)
    with pytest.raises(MfaManagementLocked):
        begin_mfa_enrollment(
            pg_session, user_id=account.id, password="wrong-password", now=fifth
        )
    # The lock also rejects the right password while the window is open.
    with pytest.raises(MfaManagementLocked):
        begin_mfa_enrollment(
            pg_session, user_id=account.id, password=PASSWORD, now=fifth
        )

    released = NOW + timedelta(minutes=10, seconds=1)
    enrollment = begin_mfa_enrollment(
        pg_session, user_id=account.id, password=PASSWORD, now=released
    )
    assert enrollment.otp_uri.startswith("otpauth://totp/")
    failures = pg_session.exec(
        select(AuthEvent).where(
            AuthEvent.user_id == account.id,
            AuthEvent.event_type == "mfa_management",
            AuthEvent.result == "failure",
        )
    ).all()
    assert len(failures) == 5
    assert all(event.occurred_at.utcoffset() == timedelta(0) for event in failures)


def test_a_success_event_restarts_the_failure_count(pg_session, account) -> None:
    for _ in range(4):
        with pytest.raises(MfaPasswordRejected):
            begin_mfa_enrollment(
                pg_session, user_id=account.id, password="wrong-password", now=NOW
            )

    enabled_at = NOW + timedelta(minutes=1)
    _enable_mfa(pg_session, account, now=enabled_at)

    # Without the reset these four would add to the previous four and lock at once.
    after = enabled_at + timedelta(minutes=1)
    for _ in range(4):
        with pytest.raises(MfaPasswordRejected):
            disable_mfa(
                pg_session,
                user_id=account.id,
                password="wrong-password",
                code="000000",
                now=after,
            )
    with pytest.raises(MfaManagementLocked):
        disable_mfa(
            pg_session,
            user_id=account.id,
            password="wrong-password",
            code="000000",
            now=after,
        )
    assert get_mfa_status(pg_session, user_id=account.id, now=after).enabled is True


def test_rotation_and_disable_revoke_the_other_sessions_in_postgresql(
    engine, pg_session, account
) -> None:
    secret = _enable_mfa(pg_session, account)
    acting_token, acting = _open_session(pg_session, account, secret, now=NOW)
    intruder_token, intruder = _open_session(pg_session, account, secret, now=NOW)
    other_token, other = _open_session(pg_session, account, secret, now=NOW)

    rotated_at = NOW + timedelta(minutes=1)
    rotation = begin_mfa_rotation(
        pg_session,
        user_id=account.id,
        password=PASSWORD,
        code=identity_service._totp(secret),
        now=rotated_at,
    )
    confirmation = confirm_mfa_rotation(
        pg_session,
        user_id=account.id,
        code=identity_service._totp(rotation.secret),
        current_session_id=acting.session_id,
        now=rotated_at,
    )
    pg_session.commit()
    assert confirmation.rotated is True
    assert len(confirmation.backup_codes) == 10

    with Session(engine) as fresh:
        for session_id in (intruder.session_id, other.session_id):
            revoked = fresh.get(UserSession, session_id)
            assert revoked is not None
            assert revoked.revoked_at == rotated_at
            assert revoked.revoked_at.utcoffset() == timedelta(0)
        kept = fresh.get(UserSession, acting.session_id)
        assert kept is not None
        assert kept.revoked_at is None
        with pytest.raises(InvalidSession):
            authenticate_session(fresh, intruder_token, now=rotated_at)
        with pytest.raises(InvalidSession):
            authenticate_session(fresh, other_token, now=rotated_at)
        assert authenticate_session(fresh, acting_token, now=rotated_at).user_id == account.id
        events = _revocation_events(fresh, account.id)
        assert [event.reason_code for event in events] == ["mfa_rotated", "mfa_rotated"]

    # A session opened after the rotation is the one the disable revokes.
    late_token, late = _open_session(pg_session, account, rotation.secret, now=rotated_at)
    disabled_at = NOW + timedelta(minutes=2)
    disable_mfa(
        pg_session,
        user_id=account.id,
        password=PASSWORD,
        code=identity_service._totp(rotation.secret),
        current_session_id=acting.session_id,
        now=disabled_at,
    )
    pg_session.commit()

    with Session(engine) as fresh:
        revoked_late = fresh.get(UserSession, late.session_id)
        assert revoked_late is not None
        assert revoked_late.revoked_at == disabled_at
        kept = fresh.get(UserSession, acting.session_id)
        assert kept is not None
        assert kept.revoked_at is None
        with pytest.raises(InvalidSession):
            authenticate_session(fresh, late_token, now=disabled_at)
        assert authenticate_session(fresh, acting_token, now=disabled_at).user_id == account.id
        events = _revocation_events(fresh, account.id)
        assert [event.reason_code for event in events] == [
            "mfa_rotated",
            "mfa_rotated",
            "mfa_disabled",
        ]
        stored = fresh.get(AppUser, account.id)
        assert stored is not None
        assert stored.mfa_enabled is False
        assert stored.mfa_secret_encrypted is None
        assert stored.mfa_pending_secret_encrypted is None
        assert stored.mfa_enabled_at is None