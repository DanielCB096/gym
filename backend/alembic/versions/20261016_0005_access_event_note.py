"""Add the note column to access_events.

Manual overrides record the operator's free-text reason; reader decisions leave
it empty. The note is separate from ``reason`` so reason codes stay stable.

Revision ID: 20261016_0005
Revises: 20261016_0004
"""

from alembic import op
import sqlalchemy as sa

revision = "20261016_0005"
down_revision = "20261016_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("access_events", sa.Column("note", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("access_events", "note")
