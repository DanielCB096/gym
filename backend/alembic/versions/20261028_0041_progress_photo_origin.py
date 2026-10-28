"""Record who uploaded a progress photo.

Members can now upload their own progress photos from the app, and
``uploaded_by`` points at staff accounts, so it cannot tell an app upload from
a desk one. ``origin`` carries that fact and defaults to ``staff`` so every
photo already stored keeps its current meaning.

Revision ID: 20261028_0041
Revises: 20261028_0040
"""

from alembic import op
import sqlalchemy as sa

revision = "20261028_0041"
down_revision = "20261028_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "progress_photos",
        sa.Column(
            "origin",
            sa.String(length=8),
            nullable=False,
            server_default=sa.text("'staff'"),
        ),
    )
    op.create_check_constraint(
        "ck_progress_photos_origin",
        "progress_photos",
        "origin IN ('staff', 'app')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_progress_photos_origin", "progress_photos", type_="check")
    op.drop_column("progress_photos", "origin")
