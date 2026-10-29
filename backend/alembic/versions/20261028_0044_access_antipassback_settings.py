"""Club-wide antipassback window for the reception kiosk.

A single row (id 1) holds ``antipassback_seconds``: the minimum gap between two
authorized entries of the same member. ``0`` disables the rule, which is the
initial value. The kiosk reads it on every check-in; the panel edits it with
``settings.manage``.

Revision ID: 20261028_0044
Revises: 20261028_0043
"""

from alembic import op
import sqlalchemy as sa

revision = "20261028_0044"
down_revision = "20261028_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "access_settings",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "antipassback_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "antipassback_seconds >= 0 AND antipassback_seconds <= 3600",
            name="ck_access_settings_antipassback_range",
        ),
    )
    op.execute(
        "INSERT INTO access_settings (id, antipassback_seconds) VALUES (1, 0)"
    )


def downgrade() -> None:
    op.drop_table("access_settings")
