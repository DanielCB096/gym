"""Expiration date for kiosk device tokens.

``kiosk_devices.token_expires_at`` bounds the life of the bearer token. New
devices and token rotations get 90 days; the kiosk refuses an expired token with
the same ``401`` as a revoked one. Devices that already existed receive a full
window from the upgrade so a running tablet is not cut off mid-shift; a NULL
value (only possible for rows created outside the service) keeps the old
never-expire behavior.

Revision ID: 20261028_0045
Revises: 20261028_0044
"""

from alembic import op
import sqlalchemy as sa

revision = "20261028_0045"
down_revision = "20261028_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "kiosk_devices",
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE kiosk_devices "
        "SET token_expires_at = now() + INTERVAL '90 days' "
        "WHERE token_expires_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("kiosk_devices", "token_expires_at")
