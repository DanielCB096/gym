from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select

from app.modules.identity.models import AuthEvent, Permission, Role, RolePermission, UserRoleAssignment, UserSession
from app.modules.identity.service import (
    AuthenticationFailed,
    ImmutableRole,
    InvalidSession,
    LastOwnerRequired,
    PermissionDenied,
    PermissionNotFound,
    RoleNotFound,
    authenticate_session,
    authenticate_user,
    ensure_default_access_control,
    grant_role_permission,
    register_user,
    require_permission,
    revoke_role,
    revoke_role_permission,
    revoke_session,
)


NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


def test_role_permissions_are_checked_server_side(session: Session) -> None:
    ensure_default_access_control(session)
    user = register_user(
        session,
        email="recepcion@ritmo.test",
        password="correct-horse-battery-staple",
        role_codes=("reception",),
        now=NOW,
    )

    login = authenticate_user(session, email=user.email, password="correct-horse-battery-staple", now=NOW)
    principal = authenticate_session(session, login.access_token, now=NOW + timedelta(minutes=1))

    assert principal.roles == ("reception",)
    assert "access.manual_override" in principal.permissions
    user_session = session.exec(select(UserSession).where(UserSession.user_id == user.id)).one()
    assert user_session.token_sha256 != login.access_token
    assert require_permission(principal, "access.manual_override") is principal
    with pytest.raises(PermissionDenied):
        require_permission(principal, "roles.manage")
    with pytest.raises(PermissionDenied):
        require_permission(principal, "payroll.read")


def test_password_failure_is_generic_and_audited(session: Session) -> None:
    ensure_default_access_control(session)
    register_user(
        session,
        email="manager@ritmo.test",
        password="correct-horse-battery-staple",
        role_codes=("manager",),
        now=NOW,
    )

    with pytest.raises(AuthenticationFailed, match="Invalid email or password"):
        authenticate_user(session, email="manager@ritmo.test", password="incorrect-password", now=NOW)
    with pytest.raises(AuthenticationFailed, match="Invalid email or password"):
        authenticate_user(session, email="missing@ritmo.test", password="incorrect-password", now=NOW)

    events = session.exec(select(AuthEvent).where(AuthEvent.event_type == "login")).all()
    assert len(events) == 2
    assert all(event.result == "failure" for event in events)


def test_session_expiry_and_logout_revoke_access(session: Session) -> None:
    ensure_default_access_control(session)
    user = register_user(
        session,
        email="owner@ritmo.test",
        password="correct-horse-battery-staple",
        role_codes=("owner",),
        now=NOW,
    )
    login = authenticate_user(session, email=user.email, password="correct-horse-battery-staple", now=NOW)
    principal = authenticate_session(session, login.access_token, now=NOW + timedelta(minutes=1))

    revoke_session(session, principal, now=NOW + timedelta(minutes=2))
    with pytest.raises(InvalidSession):
        authenticate_session(session, login.access_token, now=NOW + timedelta(minutes=3))

    user_session = session.get(UserSession, principal.session_id)
    assert user_session.revoked_at.replace(tzinfo=timezone.utc) == NOW + timedelta(minutes=2)


def test_expired_role_assignment_no_longer_grants_permission(session: Session) -> None:
    ensure_default_access_control(session)
    user = register_user(
        session,
        email="temporary@ritmo.test",
        password="correct-horse-battery-staple",
        now=NOW,
    )
    manager_role = session.exec(select(Role).where(Role.code == "manager")).one()
    session.add(
        UserRoleAssignment(
            user_id=user.id,
            role_id=manager_role.id,
            assigned_at=NOW - timedelta(days=2),
            expires_at=NOW - timedelta(days=1),
        )
    )
    session.commit()
    login = authenticate_user(
        session,
        email=user.email,
        password="correct-horse-battery-staple",
        now=NOW,
    )
    principal = authenticate_session(session, login.access_token, now=NOW)
    assert principal.roles == ()
    with pytest.raises(PermissionDenied):
        require_permission(principal, "staff.manage")


def test_last_owner_cannot_be_demoted(session: Session) -> None:
    ensure_default_access_control(session)
    owner = register_user(
        session,
        email="only-owner@ritmo.test",
        password="correct-horse-battery-staple",
        role_codes=("owner",),
        now=NOW,
    )
    authenticate_user(
        session,
        email=owner.email,
        password="correct-horse-battery-staple",
        now=NOW,
    ).user

    with pytest.raises(LastOwnerRequired):
        revoke_role(
            session,
            user_id=owner.id,
            role_code="owner",
            revoked_by=owner.id,
            now=NOW + timedelta(minutes=1),
        )
    assert "owner" in authenticate_session(session, authenticate_user(
        session,
        email=owner.email,
        password="correct-horse-battery-staple",
        now=NOW + timedelta(minutes=2),
    ).access_token, now=NOW + timedelta(minutes=2)).roles


def test_reception_registers_attendance_but_does_not_manage_staff(session: Session) -> None:
    ensure_default_access_control(session)
    register_user(
        session,
        email="reception-matrix@ritmo.test",
        password="correct-horse-battery-staple",
        role_codes=("reception",),
        now=NOW,
    )
    login = authenticate_user(
        session, email="reception-matrix@ritmo.test", password="correct-horse-battery-staple", now=NOW
    )
    principal = authenticate_session(session, login.access_token, now=NOW)

    # Documented matrix: recepción registra asistencia y consulta el schedule.
    assert "attendance.read" in principal.permissions
    assert "attendance.manage" in principal.permissions
    # ...but does not manage personnel records or roles.
    assert "staff.read" not in principal.permissions
    assert "staff.manage" not in principal.permissions
    assert "roles.manage" not in principal.permissions


def test_trainer_only_reads_attendance(session: Session) -> None:
    ensure_default_access_control(session)
    register_user(
        session,
        email="trainer-matrix@ritmo.test",
        password="correct-horse-battery-staple",
        role_codes=("trainer",),
        now=NOW,
    )
    login = authenticate_user(
        session, email="trainer-matrix@ritmo.test", password="correct-horse-battery-staple", now=NOW
    )
    principal = authenticate_session(session, login.access_token, now=NOW)

    assert "attendance.read" in principal.permissions
    assert "attendance.manage" not in principal.permissions
    assert "staff.read" not in principal.permissions


def test_role_permission_grants_change_effective_permissions(session: Session) -> None:
    ensure_default_access_control(session)
    actor = register_user(
        session,
        email="owner-rbac@ritmo.test",
        password="correct-horse-battery-staple",
        role_codes=("owner",),
        now=NOW,
    )
    register_user(
        session,
        email="reception-rbac@ritmo.test",
        password="correct-horse-battery-staple",
        role_codes=("reception",),
        now=NOW,
    )
    login = authenticate_user(
        session, email="reception-rbac@ritmo.test", password="correct-horse-battery-staple", now=NOW
    )
    principal = authenticate_session(session, login.access_token, now=NOW + timedelta(minutes=1))
    assert "payroll.read" not in principal.permissions

    grant_role_permission(
        session,
        role_code="reception",
        permission_code="payroll.read",
        actor_id=actor.id,
        now=NOW + timedelta(minutes=2),
    )
    granted = authenticate_session(session, login.access_token, now=NOW + timedelta(minutes=3))
    assert "payroll.read" in granted.permissions

    # Granting the same pair again is a no-op and is not audited twice.
    grant_role_permission(
        session,
        role_code="reception",
        permission_code="payroll.read",
        actor_id=actor.id,
        now=NOW + timedelta(minutes=4),
    )
    grant_events = session.exec(select(AuthEvent).where(AuthEvent.event_type == "role_permission_granted")).all()
    assert len(grant_events) == 1

    revoke_role_permission(
        session,
        role_code="reception",
        permission_code="payroll.read",
        actor_id=actor.id,
        now=NOW + timedelta(minutes=5),
    )
    revoked = authenticate_session(session, login.access_token, now=NOW + timedelta(minutes=6))
    assert "payroll.read" not in revoked.permissions
    revoke_events = session.exec(select(AuthEvent).where(AuthEvent.event_type == "role_permission_revoked")).all()
    assert len(revoke_events) == 1


def test_owner_role_permissions_are_immutable(session: Session) -> None:
    ensure_default_access_control(session)
    owner = register_user(
        session,
        email="owner-immutable@ritmo.test",
        password="correct-horse-battery-staple",
        role_codes=("owner",),
        now=NOW,
    )

    with pytest.raises(ImmutableRole):
        grant_role_permission(
            session, role_code="owner", permission_code="payroll.read", actor_id=owner.id, now=NOW
        )
    with pytest.raises(ImmutableRole):
        revoke_role_permission(
            session, role_code="owner", permission_code="settings.manage", actor_id=owner.id, now=NOW
        )

    login = authenticate_user(
        session, email=owner.email, password="correct-horse-battery-staple", now=NOW
    )
    principal = authenticate_session(session, login.access_token, now=NOW)
    assert "settings.manage" in principal.permissions


def test_unknown_role_or_permission_is_rejected(session: Session) -> None:
    ensure_default_access_control(session)
    owner = register_user(
        session,
        email="owner-unknown@ritmo.test",
        password="correct-horse-battery-staple",
        role_codes=("owner",),
        now=NOW,
    )

    with pytest.raises(RoleNotFound):
        grant_role_permission(
            session, role_code="ghost", permission_code="payroll.read", actor_id=owner.id, now=NOW
        )
    with pytest.raises(PermissionNotFound):
        grant_role_permission(
            session, role_code="reception", permission_code="ghost.read", actor_id=owner.id, now=NOW
        )
    with pytest.raises(RoleNotFound):
        revoke_role_permission(
            session, role_code="ghost", permission_code="payroll.read", actor_id=owner.id, now=NOW
        )


def test_reseeding_keeps_manual_permission_changes(session: Session) -> None:
    ensure_default_access_control(session)
    owner = register_user(
        session,
        email="owner-reseed@ritmo.test",
        password="correct-horse-battery-staple",
        role_codes=("owner",),
        now=NOW,
    )
    revoke_role_permission(
        session, role_code="reception", permission_code="inventory.read", actor_id=owner.id, now=NOW
    )

    # A later startup (preview seeds on boot) must not restore the removed grant.
    ensure_default_access_control(session)

    reception_role = session.exec(select(Role).where(Role.code == "reception")).one()
    permission_ids = session.exec(
        select(RolePermission.permission_id).where(RolePermission.role_id == reception_role.id)
    ).all()
    inventory_read = session.exec(select(Permission).where(Permission.code == "inventory.read")).one()
    assert inventory_read.id not in permission_ids