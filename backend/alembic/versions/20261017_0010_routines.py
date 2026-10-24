"""Create the routines and progress tables.

Adds the exercise library (``exercises``), the trainer-owned routine templates
(``routines`` + versioned ``routine_items`` + their ``routine_revisions`` change
log), the assignments to members (``routine_assignments``), the performed
sessions (``workout_logs``) and the append-only body measurements
(``body_measurements``).

Editing a routine publishes a new ``routines.version`` and inserts a fresh set
of ``routine_items`` rows, with the motive recorded in ``routine_revisions``;
older versions are kept so an assignment pins the exact plan the member trained
(``routine_assignments.routine_version``). There is no FK cascade: routines and
assignments are archived/cancelled, never deleted, so history survives.

The ``routines.read`` / ``routines.manage`` permissions are seeded by the
following revision (``20261017_0011``), so this one only handles the schema.

Revision ID: 20261017_0010
Revises: 20261017_0009
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261017_0010"
down_revision = "20261017_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exercises",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("muscle_group", sa.String(length=60), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("equipment_name", sa.String(length=120), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("video_url", sa.String(length=300), nullable=True),
        sa.Column("image_url", sa.String(length=300), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_exercises_name_nonempty"),
        sa.CheckConstraint("length(trim(muscle_group)) > 0", name="ck_exercises_muscle_nonempty"),
        sa.CheckConstraint("length(trim(category)) > 0", name="ck_exercises_category_nonempty"),
        sa.ForeignKeyConstraint(["created_by"], ["app_users.id"], ondelete="RESTRICT"),
    )
    op.create_index("uq_exercises_name_lower", "exercises", [sa.text("lower(name)")], unique=True)
    op.create_index("ix_exercises_muscle_group", "exercises", ["muscle_group"])
    op.create_index("ix_exercises_category", "exercises", ["category"])

    op.create_table(
        "routines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("trainer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("objective", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_routines_name_nonempty"),
        sa.CheckConstraint("status IN ('draft', 'active', 'archived')", name="ck_routines_status"),
        sa.CheckConstraint("version > 0", name="ck_routines_version_positive"),
        sa.ForeignKeyConstraint(["trainer_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["app_users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_routines_status", "routines", ["status"])
    op.create_index("ix_routines_trainer", "routines", ["trainer_id"])

    op.create_table(
        "routine_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("routine_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("exercise_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=False),
        sa.Column("reps", sa.String(length=20), nullable=False),
        sa.Column("rest_seconds", sa.Integer(), nullable=True),
        sa.Column("load_note", sa.String(length=60), nullable=True),
        sa.Column("notes", sa.String(length=200), nullable=True),
        sa.CheckConstraint("version > 0", name="ck_routine_items_version_positive"),
        sa.CheckConstraint("position > 0", name="ck_routine_items_position_positive"),
        sa.CheckConstraint("sets > 0", name="ck_routine_items_sets_positive"),
        sa.CheckConstraint("rest_seconds IS NULL OR rest_seconds >= 0", name="ck_routine_items_rest_nonnegative"),
        sa.ForeignKeyConstraint(["routine_id"], ["routines.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="RESTRICT"),
    )
    op.create_index("uq_routine_items_line", "routine_items", ["routine_id", "version", "position"], unique=True)
    op.create_index("ix_routine_items_version", "routine_items", ["routine_id", "version"])

    op.create_table(
        "routine_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("routine_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_routine_revisions_version_positive"),
        sa.CheckConstraint("item_count > 0", name="ck_routine_revisions_item_count_positive"),
        sa.ForeignKeyConstraint(["routine_id"], ["routines.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["changed_by"], ["app_users.id"], ondelete="RESTRICT"),
    )
    op.create_index("uq_routine_revisions_version", "routine_revisions", ["routine_id", "version"], unique=True)

    op.create_table(
        "routine_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("routine_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("routine_version", sa.Integer(), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trainer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("frequency_per_week", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')", name="ck_routine_assignments_status"
        ),
        sa.CheckConstraint("routine_version > 0", name="ck_routine_assignments_version_positive"),
        sa.CheckConstraint(
            "frequency_per_week IS NULL OR (frequency_per_week >= 1 AND frequency_per_week <= 7)",
            name="ck_routine_assignments_frequency_range",
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date", name="ck_routine_assignments_date_order"
        ),
        sa.ForeignKeyConstraint(["routine_id"], ["routines.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["trainer_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_by"], ["app_users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "uq_routine_assignments_active",
        "routine_assignments",
        ["member_id", "routine_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index("ix_routine_assignments_member_status", "routine_assignments", ["member_id", "status"])
    op.create_index("ix_routine_assignments_routine", "routine_assignments", ["routine_id"])

    op.create_table(
        "workout_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("routine_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("routine_version", sa.Integer(), nullable=False),
        sa.Column("performed_at", sa.Date(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("perceived_effort", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="logged", nullable=False),
        sa.Column("logged_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('logged', 'reviewed')", name="ck_workout_logs_status"),
        sa.CheckConstraint("routine_version > 0", name="ck_workout_logs_version_positive"),
        sa.CheckConstraint(
            "perceived_effort IS NULL OR (perceived_effort >= 1 AND perceived_effort <= 10)",
            name="ck_workout_logs_effort_range",
        ),
        sa.CheckConstraint(
            "duration_minutes IS NULL OR duration_minutes >= 0",
            name="ck_workout_logs_duration_nonnegative",
        ),
        sa.ForeignKeyConstraint(["assignment_id"], ["routine_assignments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["routine_id"], ["routines.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["logged_by"], ["app_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["app_users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_workout_logs_assignment_date", "workout_logs", ["assignment_id", "performed_at"])
    op.create_index("ix_workout_logs_member_date", "workout_logs", ["member_id", "performed_at"])

    op.create_table(
        "body_measurements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("waist_cm", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("chest_cm", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("body_fat_percent", sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column("notes", sa.String(length=300), nullable=True),
        sa.Column("measured_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("weight_kg IS NULL OR weight_kg > 0", name="ck_body_measurements_weight"),
        sa.CheckConstraint("waist_cm IS NULL OR waist_cm > 0", name="ck_body_measurements_waist"),
        sa.CheckConstraint("chest_cm IS NULL OR chest_cm > 0", name="ck_body_measurements_chest"),
        sa.CheckConstraint(
            "body_fat_percent IS NULL OR (body_fat_percent >= 0 AND body_fat_percent <= 100)",
            name="ck_body_measurements_fat_range",
        ),
        sa.ForeignKeyConstraint(["member_id"], ["members.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["measured_by"], ["app_users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_body_measurements_member_date", "body_measurements", ["member_id", "measured_at"])


def downgrade() -> None:
    op.drop_index("ix_body_measurements_member_date", table_name="body_measurements")
    op.drop_table("body_measurements")
    op.drop_index("ix_workout_logs_member_date", table_name="workout_logs")
    op.drop_index("ix_workout_logs_assignment_date", table_name="workout_logs")
    op.drop_table("workout_logs")
    op.drop_index("ix_routine_assignments_routine", table_name="routine_assignments")
    op.drop_index("ix_routine_assignments_member_status", table_name="routine_assignments")
    op.drop_index("uq_routine_assignments_active", table_name="routine_assignments")
    op.drop_table("routine_assignments")
    op.drop_index("uq_routine_revisions_version", table_name="routine_revisions")
    op.drop_table("routine_revisions")
    op.drop_index("ix_routine_items_version", table_name="routine_items")
    op.drop_index("uq_routine_items_line", table_name="routine_items")
    op.drop_table("routine_items")
    op.drop_index("ix_routines_trainer", table_name="routines")
    op.drop_index("ix_routines_status", table_name="routines")
    op.drop_table("routines")
    op.drop_index("ix_exercises_category", table_name="exercises")
    op.drop_index("ix_exercises_muscle_group", table_name="exercises")
    op.drop_index("uq_exercises_name_lower", table_name="exercises")
    op.drop_table("exercises")
