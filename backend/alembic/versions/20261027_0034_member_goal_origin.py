"""Track who created a member goal: staff panel or the member app.

Existing goals keep ``staff`` through the server default, so applying the
migration does not rewrite history. The check constraint mirrors the one on
workout logs and body measurements.

Revision ID: 20261027_0034
Revises: 20261027_0033
"""

from alembic import op
import sqlalchemy as sa

revision = "20261027_0034"
down_revision = "20261027_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "member_goals",
        sa.Column(
            "origin",
            sa.String(length=8),
            nullable=False,
            server_default=sa.text("'staff'"),
        ),
    )
    op.create_check_constraint(
        "ck_member_goals_origin",
        "member_goals",
        "origin IN ('staff', 'app')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_member_goals_origin", "member_goals", type_="check")
    op.drop_column("member_goals", "origin")
