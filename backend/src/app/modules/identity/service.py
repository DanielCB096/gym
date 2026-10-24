from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets
from uuid import UUID

from pwdlib import PasswordHash
from sqlalchemy import and_, func, or_
from sqlmodel import Session, select

from app.modules.identity.models import (
    AppUser,
    AuthEvent,
    Employee,
    Permission,
    Role,
    RolePermission,
    UserRoleAssignment,
    UserSession,
    utc_now,
)


PASSWORD_MIN_LENGTH = 12
SESSION_LIFETIME = timedelta(hours=8)
PASSWORD_HASHER = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))

DEFAULT_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "owner": (
        "dashboard.read", "members.read", "members.manage", "access.read", "access.manual_override",
        "staff.read", "staff.manage", "roles.manage", "sessions.manage", "attendance.read", "attendance.manage",
        "attendance.self", "classes.read", "classes.manage", "routines.read", "routines.manage",
        "inventory.read", "inventory.manage",
        "sales.read", "sales.manage", "sales.credit",
        "billing.read", "billing.request", "billing.manage",
        "maintenance.read", "maintenance.report", "maintenance.manage", "payroll.read", "payroll.manage", "finance.read", "settings.manage",
    ),
    "manager": (
        "dashboard.read", "members.read", "members.manage", "access.read", "access.manual_override",
        "staff.read", "staff.manage", "attendance.read", "attendance.manage", "attendance.self", "classes.read",
        "classes.manage", "routines.read", "routines.manage", "inventory.read", "inventory.manage", "sales.read", "sales.manage", "sales.credit",
        "billing.read", "billing.request", "billing.manage",
        "maintenance.read", "maintenance.report", "maintenance.manage", "payroll.read", "finance.read",
    ),
    "reception": (
        "dashboard.read", "members.read", "members.manage", "access.read", "access.manual_override",
        "attendance.read", "attendance.manage", "attendance.self", "inventory.read", "sales.read", "sales.manage",
        "billing.read", "billing.request",
        "maintenance.read", "maintenance.report",
    ),
    "trainer": (
        "dashboard.read", "classes.read", "classes.manage", "routines.read", "routines.manage",
        "attendance.read", "attendance.self", "members.read", "maintenance.read", "maintenance.report",
    ),
    "maintenance": (
        "dashboard.read", "maintenance.read", "maintenance.report", "maintenance.manage", "inventory.read", "attendance.self",
    ),
    "accountant": (
        "dashboard.read", "finance.read", "sales.read", "payroll.read", "attendance.self",
        "billing.read", "billing.request", "billing.manage",
    ),
}

DEFAULT_PERMISSIONS: dict[str, str] = {
    "dashboard.read": "Consultar panel operativo",
    "members.read": "Consultar socios",
    "members.manage": "Crear y actualizar socios",
    "access.read": "Consultar bitácora de accesos",
    "access.manual_override": "Autorizar accesos manuales",
    "staff.read": "Consultar personal",
    "staff.manage": "Administrar expedientes de personal",
    "roles.manage": "Administrar roles y permisos",
    "sessions.manage": "Administrar sesiones activas",
    "attendance.read": "Consultar asistencias",
    "attendance.manage": "Registrar y corregir asistencias",
    "attendance.self": "Marcar la propia asistencia",
    "classes.read": "Consultar clases",
    "classes.manage": "Administrar clases y reservas",
    "routines.read": "Consultar rutinas y progreso",
    "routines.manage": "Administrar rutinas, asignaciones y progreso",
    "inventory.read": "Consultar inventario",
    "inventory.manage": "Administrar inventario",
    "sales.read": "Consultar ventas y cortes de caja",
    "sales.manage": "Registrar ventas y operar la caja",
    "sales.credit": "Administrar límites de crédito de socios",
    "billing.read": "Consultar facturas y datos fiscales",
    "billing.request": "Solicitar facturas y capturar datos fiscales",
    "billing.manage": "Timbrar y cancelar facturas",
    "maintenance.read": "Consultar mantenimiento",
    "maintenance.report": "Reportar fallas y poner equipos fuera de servicio",
    "maintenance.manage": "Administrar mantenimiento",
    "payroll.read": "Consultar nómina",
    "payroll.manage": "Administrar nómina",
    "finance.read": "Consultar reportes financieros",
    "settings.manage": "Administrar configuración del gimnasio",
}

DEFAULT_ROLES: dict[str, tuple[str, str]] = {
    "owner": ("Dueño", "Administración completa del gimnasio."),
    "manager": ("Gerente", "Operación diaria y supervisión de la sucursal."),
    "reception": ("Recepción", "Atención a socios y operación de acceso."),
    "trainer": ("Entrenador", "Clases, agenda y seguimiento de socios."),
    "maintenance": ("Mantenimiento", "Equipos e instalaciones asignados."),
    "accountant": ("Contador", "Consulta financiera y de nómina."),
}


class IdentityError(Exception):
    pass


class AuthenticationFailed(IdentityError):
    pass


class InvalidSession(IdentityError):
    pass


class PermissionDenied(IdentityError):
    pass


class EmailAlreadyRegistered(IdentityError):
    pass


class EmployeeUnavailable(IdentityError):
    pass


class RoleUnavailable(IdentityError):
    pass


class UserUnavailable(IdentityError):
    pass


class LastOwnerRequired(IdentityError):
    pass


class SessionNotFound(IdentityError):
    pass


class RoleNotFound(IdentityError):
    pass


class PermissionNotFound(IdentityError):
    pass


class ImmutableRole(IdentityError):
    pass


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: UUID
    session_id: UUID
    email: str
    employee_id: UUID | None
    roles: tuple[str, ...]
    permissions: frozenset[str]


@dataclass(frozen=True)
class LoginResult:
    access_token: str
    token_type: str
    expires_at: datetime
    user: AuthenticatedUser


@dataclass(frozen=True)
class UserOverview:
    id: UUID
    email: str
    status: str
    employee_id: UUID | None
    employee_name: str | None
    roles: tuple[str, ...]
    last_login_at: datetime | None


@dataclass(frozen=True)
class SessionOverview:
    id: UUID
    user_id: UUID
    email: str
    employee_name: str | None
    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime | None
    is_current: bool


def ensure_default_access_control(session: Session) -> None:
    """Seed the default roles, permissions and their initial grants.

    Default permissions are granted to a role when the role is created in
    this call, or when the permission itself is created here (a brand-new
    permission cannot have been deliberately removed by an administrator, so it
    is safe to seed it into the existing roles). Once a role and a permission
    already exist their link belongs to the administrators (and, in production,
    to the migrations), so removing a default grant is not silently undone on
    the next startup. New permissions for existing roles are added by migrations
    that look roles and permissions up by code.
    """
    roles_by_code = {role.code: role for role in session.exec(select(Role)).all()}
    created_role_codes: set[str] = set()
    for code, (name, description) in DEFAULT_ROLES.items():
        if code not in roles_by_code:
            role = Role(code=code, name=name, description=description, is_system=True)
            session.add(role)
            roles_by_code[code] = role
            created_role_codes.add(code)

    permissions_by_code = {permission.code: permission for permission in session.exec(select(Permission)).all()}
    created_permission_codes: set[str] = set()
    for code, description in DEFAULT_PERMISSIONS.items():
        if code not in permissions_by_code:
            permission = Permission(code=code, description=description)
            session.add(permission)
            permissions_by_code[code] = permission
            created_permission_codes.add(code)
    session.flush()

    existing_pairs = set(
        session.exec(select(RolePermission.role_id, RolePermission.permission_id)).all()
    )
    for role_code, permission_codes in DEFAULT_ROLE_PERMISSIONS.items():
        role_is_new = role_code in created_role_codes
        role = roles_by_code[role_code]
        for permission_code in permission_codes:
            if not role_is_new and permission_code not in created_permission_codes:
                continue
            permission = permissions_by_code[permission_code]
            pair = (role.id, permission.id)
            if pair not in existing_pairs:
                session.add(RolePermission(role_id=role.id, permission_id=permission.id))
                existing_pairs.add(pair)
    session.commit()


def register_user(
    session: Session,
    *,
    email: str,
    password: str,
    employee_id: UUID | None = None,
    role_codes: tuple[str, ...] = (),
    assigned_by: UUID | None = None,
    now: datetime | None = None,
) -> AppUser:
    normalized_email = _normalize_email(email)
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters")
    if session.exec(select(AppUser).where(AppUser.email == normalized_email)).first() is not None:
        raise EmailAlreadyRegistered("Email is already registered")
    if employee_id is not None:
        employee = session.get(Employee, employee_id)
        if employee is None or employee.status != "active":
            raise EmployeeUnavailable("Employee is missing or inactive")
    roles = _load_roles(session, role_codes)
    created_at = now or utc_now()
    _require_aware(created_at)

    user = AppUser(
        employee_id=employee_id,
        email=normalized_email,
        password_hash=PASSWORD_HASHER.hash(password),
        status="active",
    )
    session.add(user)
    session.flush()
    for role in roles:
        session.add(UserRoleAssignment(user_id=user.id, role_id=role.id, assigned_by=assigned_by, assigned_at=created_at))
    session.add(
        AuthEvent(
            user_id=user.id,
            actor_id=assigned_by,
            event_type="account_created",
            result="success",
            reason_code="initial_roles_assigned",
            occurred_at=created_at,
        )
    )
    session.commit()
    session.refresh(user)
    return user


def bootstrap_initial_owner(
    session: Session,
    *,
    email: str,
    password: str,
) -> AppUser:
    ensure_default_access_control(session)
    if session.exec(select(AppUser.id)).first() is not None:
        raise IdentityError("Initial owner bootstrap is available only before the first user exists")
    return register_user(email=email, password=password, role_codes=("owner",), session=session)


def assign_role(
    session: Session,
    *,
    user_id: UUID,
    role_code: str,
    assigned_by: UUID,
    now: datetime | None = None,
) -> UserRoleAssignment:
    occurred_at = now or utc_now()
    _require_aware(occurred_at)
    user = session.get(AppUser, user_id)
    if user is None or user.status != "active":
        raise UserUnavailable("User is missing or inactive")
    role = session.exec(select(Role).where(Role.code == role_code)).first()
    if role is None:
        raise RoleUnavailable("Role is not available")

    assignments = session.exec(
        select(UserRoleAssignment).where(
            UserRoleAssignment.user_id == user_id,
            UserRoleAssignment.role_id == role.id,
            UserRoleAssignment.revoked_at.is_(None),
        )
    ).all()
    for assignment in assignments:
        if assignment.expires_at is None or _as_utc(assignment.expires_at) > occurred_at:
            return assignment
        assignment.revoked_at = occurred_at

    assignment = UserRoleAssignment(
        user_id=user_id,
        role_id=role.id,
        assigned_by=assigned_by,
        assigned_at=occurred_at,
    )
    session.add(assignment)
    session.add(
        AuthEvent(
            user_id=user_id,
            actor_id=assigned_by,
            event_type="role_assigned",
            result="success",
            reason_code=role_code,
            occurred_at=occurred_at,
        )
    )
    session.commit()
    session.refresh(assignment)
    return assignment


def _remaining_active_owners(session: Session, *, excluding_user_id: UUID, now: datetime) -> int:
    """Count active owner assignments other than the given user's."""
    owner_role = session.exec(select(Role).where(Role.code == "owner")).first()
    if owner_role is None:
        return 0
    return session.exec(
        select(func.count(UserRoleAssignment.id))
        .join(AppUser, AppUser.id == UserRoleAssignment.user_id)
        .where(
            UserRoleAssignment.role_id == owner_role.id,
            UserRoleAssignment.user_id != excluding_user_id,
            UserRoleAssignment.revoked_at.is_(None),
            AppUser.status == "active",
            or_(UserRoleAssignment.expires_at.is_(None), UserRoleAssignment.expires_at > now),
        )
    ).one()


def revoke_role(
    session: Session,
    *,
    user_id: UUID,
    role_code: str,
    revoked_by: UUID,
    now: datetime | None = None,
) -> None:
    occurred_at = now or utc_now()
    _require_aware(occurred_at)
    role = session.exec(select(Role).where(Role.code == role_code)).first()
    if role is None:
        raise RoleUnavailable("Role is not available")
    if role_code == "owner" and _remaining_active_owners(session, excluding_user_id=user_id, now=occurred_at) == 0:
        raise LastOwnerRequired("The last active owner role cannot be revoked")
    assignment = session.exec(
        select(UserRoleAssignment).where(
            UserRoleAssignment.user_id == user_id,
            UserRoleAssignment.role_id == role.id,
            UserRoleAssignment.revoked_at.is_(None),
        )
    ).first()
    if assignment is None:
        return
    assignment.revoked_at = occurred_at
    session.add(
        AuthEvent(
            user_id=user_id,
            actor_id=revoked_by,
            event_type="role_revoked",
            result="success",
            reason_code=role_code,
            occurred_at=occurred_at,
        )
    )
    session.commit()


def _role_by_code(session: Session, role_code: str) -> Role:
    role = session.exec(select(Role).where(Role.code == role_code)).first()
    if role is None:
        raise RoleNotFound("Role not found")
    return role


def _permission_by_code(session: Session, permission_code: str) -> Permission:
    permission = session.exec(select(Permission).where(Permission.code == permission_code)).first()
    if permission is None:
        raise PermissionNotFound("Permission not found")
    return permission


def _role_permission_reason(role_code: str, permission_code: str) -> str:
    return f"{role_code}:{permission_code}"[:80]


def grant_role_permission(
    session: Session,
    *,
    role_code: str,
    permission_code: str,
    actor_id: UUID,
    now: datetime | None = None,
) -> None:
    """Grant a permission to a role.

    The owner role is immutable: it always keeps full control, so editing it is
    rejected instead of risking a lockout. Granting an already present pair is a
    no-op.
    """
    occurred_at = now or utc_now()
    _require_aware(occurred_at)
    role = _role_by_code(session, role_code)
    permission = _permission_by_code(session, permission_code)
    if role.code == "owner":
        raise ImmutableRole("The owner role permissions cannot be changed")
    if session.get(RolePermission, (role.id, permission.id)) is not None:
        return
    session.add(RolePermission(role_id=role.id, permission_id=permission.id, granted_at=occurred_at))
    session.add(
        AuthEvent(
            user_id=None,
            actor_id=actor_id,
            event_type="role_permission_granted",
            result="success",
            reason_code=_role_permission_reason(role_code, permission_code),
            occurred_at=occurred_at,
        )
    )
    session.commit()


def revoke_role_permission(
    session: Session,
    *,
    role_code: str,
    permission_code: str,
    actor_id: UUID,
    now: datetime | None = None,
) -> None:
    """Revoke a permission from a role. The owner role is immutable."""
    occurred_at = now or utc_now()
    _require_aware(occurred_at)
    role = _role_by_code(session, role_code)
    permission = _permission_by_code(session, permission_code)
    if role.code == "owner":
        raise ImmutableRole("The owner role permissions cannot be changed")
    existing = session.get(RolePermission, (role.id, permission.id))
    if existing is None:
        return
    session.delete(existing)
    session.add(
        AuthEvent(
            user_id=None,
            actor_id=actor_id,
            event_type="role_permission_revoked",
            result="success",
            reason_code=_role_permission_reason(role_code, permission_code),
            occurred_at=occurred_at,
        )
    )
    session.commit()


def set_user_status(
    session: Session,
    *,
    user_id: UUID,
    status: str,
    actor_id: UUID,
    now: datetime | None = None,
) -> AppUser:
    """Enable or disable a login account.

    Disabling the last active owner account is rejected so the club stays
    administrable. Disabling also revokes every open session so the change
    takes effect immediately instead of when the tokens expire; re-enabling
    does not resurrect those sessions.
    """
    if status not in ("active", "disabled"):
        raise ValueError("Unsupported user status")
    occurred_at = now or utc_now()
    _require_aware(occurred_at)
    user = session.get(AppUser, user_id)
    if user is None:
        raise UserUnavailable("User is missing")
    if user.status == status:
        return user
    if status == "disabled":
        has_owner_role = session.exec(
            select(UserRoleAssignment.id)
            .join(Role, Role.id == UserRoleAssignment.role_id)
            .where(
                UserRoleAssignment.user_id == user_id,
                Role.code == "owner",
                UserRoleAssignment.revoked_at.is_(None),
            )
        ).first()
        if has_owner_role is not None and _remaining_active_owners(session, excluding_user_id=user_id, now=occurred_at) == 0:
            raise LastOwnerRequired("The last active owner account cannot be disabled")
        open_sessions = session.exec(
            select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        ).all()
        for user_session in open_sessions:
            user_session.revoked_at = occurred_at
        event_type = "account_disabled"
    else:
        event_type = "account_enabled"
    user.status = status
    session.add(
        AuthEvent(
            user_id=user_id,
            actor_id=actor_id,
            event_type=event_type,
            result="success",
            reason_code=status,
            occurred_at=occurred_at,
        )
    )
    session.commit()
    session.refresh(user)
    return user


def authenticate_user(
    session: Session,
    *,
    email: str,
    password: str,
    now: datetime | None = None,
) -> LoginResult:
    normalized_email = _normalize_email(email)
    occurred_at = now or utc_now()
    _require_aware(occurred_at)
    user = session.exec(select(AppUser).where(AppUser.email == normalized_email)).first()
    valid_password = PASSWORD_HASHER.verify(password, user.password_hash) if user is not None else False
    if user is None:
        PASSWORD_HASHER.verify(password, DUMMY_PASSWORD_HASH)

    if user is None or user.status != "active" or not valid_password:
        session.add(
            AuthEvent(
                user_id=user.id if user is not None else None,
                event_type="login",
                result="failure",
                reason_code="invalid_credentials",
                occurred_at=occurred_at,
            )
        )
        session.commit()
        raise AuthenticationFailed("Invalid email or password")

    raw_token = secrets.token_urlsafe(32)
    expires_at = occurred_at + SESSION_LIFETIME
    user_session = UserSession(
        user_id=user.id,
        token_sha256=_token_hash(raw_token),
        created_at=occurred_at,
        expires_at=expires_at,
        last_seen_at=occurred_at,
    )
    user.last_login_at = occurred_at
    session.add(user_session)
    session.add(AuthEvent(user_id=user.id, event_type="login", result="success", occurred_at=occurred_at))
    session.commit()
    principal = _build_principal(session, user, user_session, occurred_at)
    return LoginResult(raw_token, "Bearer", expires_at, principal)


def authenticate_session(
    session: Session,
    access_token: str,
    *,
    now: datetime | None = None,
) -> AuthenticatedUser:
    occurred_at = now or utc_now()
    _require_aware(occurred_at)
    user_session = session.exec(
        select(UserSession).where(UserSession.token_sha256 == _token_hash(access_token))
    ).first()
    if (
        user_session is None
        or user_session.revoked_at is not None
        or _as_utc(user_session.expires_at) <= occurred_at
    ):
        raise InvalidSession("Session is invalid or expired")
    user = session.get(AppUser, user_session.user_id)
    if user is None or user.status != "active":
        raise InvalidSession("Session is invalid or expired")
    return _build_principal(session, user, user_session, occurred_at)


def revoke_session(
    session: Session,
    principal: AuthenticatedUser,
    *,
    now: datetime | None = None,
) -> None:
    occurred_at = now or utc_now()
    _require_aware(occurred_at)
    user_session = session.get(UserSession, principal.session_id)
    if user_session is None or user_session.user_id != principal.user_id:
        raise InvalidSession("Session is invalid or expired")
    if user_session.revoked_at is None:
        user_session.revoked_at = occurred_at
        session.add(AuthEvent(user_id=principal.user_id, event_type="logout", result="success", occurred_at=occurred_at))
        session.commit()


def revoke_session_by_id(
    session: Session,
    session_id: UUID,
    *,
    actor_id: UUID,
    now: datetime | None = None,
) -> None:
    """Revoke any session by id, recording the acting administrator."""
    occurred_at = now or utc_now()
    _require_aware(occurred_at)
    user_session = session.get(UserSession, session_id)
    if user_session is None:
        raise SessionNotFound("Session not found")
    if user_session.revoked_at is None:
        user_session.revoked_at = occurred_at
        session.add(
            AuthEvent(
                user_id=user_session.user_id,
                actor_id=actor_id,
                event_type="session_revoked",
                result="success",
                reason_code="admin_revoked",
                occurred_at=occurred_at,
            )
        )
        session.commit()


def require_permission(principal: AuthenticatedUser, permission_code: str) -> AuthenticatedUser:
    if permission_code not in principal.permissions:
        raise PermissionDenied(f"Permission required: {permission_code}")
    return principal


def list_roles_and_permissions(session: Session) -> list[dict[str, object]]:
    roles = session.exec(select(Role).order_by(Role.name)).all()
    result: list[dict[str, object]] = []
    for role in roles:
        permissions = session.exec(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
            .order_by(Permission.code)
        ).all()
        result.append({"code": role.code, "name": role.name, "description": role.description, "permissions": permissions})
    return result


def list_users(session: Session) -> list[UserOverview]:
    """Return login users with their active role codes and employee name."""
    users = session.exec(select(AppUser).order_by(AppUser.email)).all()
    assignment_rows = session.exec(
        select(UserRoleAssignment.user_id, Role.code)
        .join(Role, Role.id == UserRoleAssignment.role_id)
        .where(UserRoleAssignment.revoked_at.is_(None))
        .order_by(Role.code)
    ).all()
    roles_by_user: dict[UUID, list[str]] = {}
    for user_id, role_code in assignment_rows:
        roles_by_user.setdefault(user_id, []).append(role_code)

    employee_ids = [user.employee_id for user in users if user.employee_id is not None]
    employee_names = _employee_name_map(session, employee_ids)

    return [
        UserOverview(
            id=user.id,
            email=user.email,
            status=user.status,
            employee_id=user.employee_id,
            employee_name=employee_names.get(user.employee_id) if user.employee_id is not None else None,
            roles=tuple(roles_by_user.get(user.id, [])),
            last_login_at=_as_utc(user.last_login_at) if user.last_login_at is not None else None,
        )
        for user in users
    ]


def list_active_sessions(
    session: Session,
    *,
    current_session_id: UUID | None = None,
    now: datetime | None = None,
) -> list[SessionOverview]:
    """Return sessions that are neither revoked nor expired, newest first."""
    occurred_at = now or utc_now()
    _require_aware(occurred_at)
    rows = session.exec(
        select(UserSession, AppUser)
        .join(AppUser, AppUser.id == UserSession.user_id)
        .where(UserSession.revoked_at.is_(None))
        .order_by(UserSession.created_at.desc())
    ).all()
    active_rows = [(user_session, user) for user_session, user in rows if _as_utc(user_session.expires_at) > occurred_at]
    employee_ids = [user.employee_id for _, user in active_rows if user.employee_id is not None]
    employee_names = _employee_name_map(session, employee_ids)
    return [
        SessionOverview(
            id=user_session.id,
            user_id=user.id,
            email=user.email,
            employee_name=employee_names.get(user.employee_id) if user.employee_id is not None else None,
            created_at=_as_utc(user_session.created_at),
            expires_at=_as_utc(user_session.expires_at),
            last_seen_at=_as_utc(user_session.last_seen_at) if user_session.last_seen_at is not None else None,
            is_current=current_session_id is not None and user_session.id == current_session_id,
        )
        for user_session, user in active_rows
    ]


def _employee_name_map(session: Session, employee_ids: list[UUID]) -> dict[UUID, str]:
    if not employee_ids:
        return {}
    return {
        employee.id: f"{employee.first_name} {employee.last_name}".strip()
        for employee in session.exec(select(Employee).where(Employee.id.in_(employee_ids))).all()
    }


def _build_principal(
    session: Session,
    user: AppUser,
    user_session: UserSession,
    now: datetime,
) -> AuthenticatedUser:
    active_assignments = and_(
        UserRoleAssignment.user_id == user.id,
        UserRoleAssignment.revoked_at.is_(None),
        UserRoleAssignment.assigned_at <= now,
        or_(UserRoleAssignment.expires_at.is_(None), UserRoleAssignment.expires_at > now),
    )
    role_codes = tuple(
        session.exec(
            select(Role.code)
            .join(UserRoleAssignment, UserRoleAssignment.role_id == Role.id)
            .where(active_assignments)
            .order_by(Role.code)
        ).all()
    )
    permission_codes = session.exec(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRoleAssignment, UserRoleAssignment.role_id == RolePermission.role_id)
        .where(active_assignments)
        .distinct()
        .order_by(Permission.code)
    ).all()
    return AuthenticatedUser(
        user_id=user.id,
        session_id=user_session.id,
        email=user.email,
        employee_id=user.employee_id,
        roles=role_codes,
        permissions=frozenset(permission_codes),
    )


def _load_roles(session: Session, role_codes: tuple[str, ...]) -> list[Role]:
    if not role_codes:
        return []
    roles = session.exec(select(Role).where(Role.code.in_(set(role_codes)))).all()
    roles_by_code = {role.code: role for role in roles}
    missing_roles = set(role_codes) - roles_by_code.keys()
    if missing_roles:
        raise RoleUnavailable(f"Unknown role codes: {', '.join(sorted(missing_roles))}")
    return [roles_by_code[code] for code in dict.fromkeys(role_codes)]


def _normalize_email(email: str) -> str:
    normalized = email.strip().casefold()
    if not normalized or "@" not in normalized:
        raise ValueError("A valid email address is required")
    return normalized


def _token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Authentication timestamps must be timezone-aware")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)