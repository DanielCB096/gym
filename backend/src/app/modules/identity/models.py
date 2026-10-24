from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Employee(SQLModel, table=True):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive', 'terminated')", name="ck_employees_status"),
        UniqueConstraint("employee_number", name="uq_employees_employee_number"),
        Index(
            "uq_employees_email_lower",
            text("lower(email)"),
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
            sqlite_where=text("email IS NOT NULL"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    employee_number: str = Field(max_length=40)
    first_name: str = Field(max_length=100)
    last_name: str = Field(max_length=100)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=30)
    job_title: str = Field(max_length=100)
    status: str = Field(
        default="active",
        sa_column=Column(String(20), nullable=False, server_default=text("'active'")),
    )
    hired_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )


class AppUser(SQLModel, table=True):
    __tablename__ = "app_users"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'disabled')", name="ck_app_users_status"),
        Index("uq_app_users_email_lower", text("lower(email)"), unique=True),
        UniqueConstraint("employee_id", name="uq_app_users_employee"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    employee_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT")),
    )
    email: str = Field(max_length=254)
    password_hash: str = Field(sa_type=String(255))
    status: str = Field(
        default="active",
        sa_column=Column(String(20), nullable=False, server_default=text("'active'")),
    )
    last_login_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )


class Role(SQLModel, table=True):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("code", name="uq_roles_code"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    code: str = Field(max_length=50)
    name: str = Field(max_length=100)
    description: str = Field(default="", sa_type=Text)
    is_system: bool = Field(default=True)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class Permission(SQLModel, table=True):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("code", name="uq_permissions_code"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    code: str = Field(max_length=100)
    description: str = Field(default="", sa_type=Text)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class RolePermission(SQLModel, table=True):
    __tablename__ = "role_permissions"

    role_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True)
    )
    permission_id: UUID = Field(
        sa_column=Column(
            Uuid(as_uuid=True),
            ForeignKey("permissions.id", ondelete="RESTRICT"),
            primary_key=True,
        )
    )
    granted_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class UserRoleAssignment(SQLModel, table=True):
    __tablename__ = "user_role_assignments"
    __table_args__ = (
        CheckConstraint(
            "expires_at IS NULL OR expires_at > assigned_at",
            name="ck_user_role_assignments_expiry_order",
        ),
        Index(
            "uq_user_role_assignments_active",
            "user_id",
            "role_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
        Index("ix_user_role_assignments_user_expiry", "user_id", "expires_at", "revoked_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT"), nullable=False)
    )
    role_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    )
    assigned_by: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    assigned_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    expires_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    revoked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class UserSession(SQLModel, table=True):
    __tablename__ = "user_sessions"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="ck_user_sessions_expiry_order"),
        UniqueConstraint("token_sha256", name="uq_user_sessions_token_hash"),
        Index("ix_user_sessions_user_expiry", "user_id", "expires_at", "revoked_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT"), nullable=False)
    )
    token_sha256: str = Field(max_length=64)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))
    revoked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    last_seen_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class AuthEvent(SQLModel, table=True):
    __tablename__ = "auth_events"
    __table_args__ = (
        CheckConstraint("result IN ('success', 'failure')", name="ck_auth_events_result"),
        Index("ix_auth_events_user_time", "user_id", "occurred_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    actor_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid(as_uuid=True), ForeignKey("app_users.id", ondelete="RESTRICT")),
    )
    event_type: str = Field(max_length=40)
    result: str = Field(max_length=16)
    reason_code: str | None = Field(default=None, max_length=80)
    occurred_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )