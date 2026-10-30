"""Fill the request→event link for approvals written before the column existed.

Since ADR-044 an approved request applies its change through the regular
correction/annulment path and stores ``Solicitud del colaborador: <motivo>`` (plus
``· Nota del supervisor: <nota>`` when there is one) as the event reason. Since
ADR-046 the event also carries ``attendance_request_id``, but the approvals made
before that column existed stayed unlinked. This revision recovers the link
without guessing by timestamp:

* the event must belong to the same attendance, have been written by the same
  supervisor (``decided_by``), be of the type the request's ``mark``/``action``
  produces, come from ``manual``, and carry exactly the reason the approval wrote;
* the pairing has to be one-to-one. When a request matches more than one event or
  an event matches more than one request, nothing is linked — an ambiguous link is
  worse than no link.

Rows that already hold a link are never touched, so running it twice is a no-op.
The downgrade is intentionally a no-op: a backfilled link cannot be told apart
from one written live by ADR-046, and ``20261031_0063`` already refuses to drop
the column while links exist.

Revision ID: 20261031_0064
Revises: 20261031_0063
"""

from alembic import op
import sqlalchemy as sa

revision = "20261031_0064"
down_revision = "20261031_0063"
branch_labels = None
depends_on = None

BACKFILL_SQL = """
WITH candidates AS (
    SELECT r.id AS request_id,
           e.id AS event_id,
           COUNT(*) OVER (PARTITION BY r.id) AS request_matches,
           COUNT(*) OVER (PARTITION BY e.id) AS event_matches
    FROM staff_attendance_requests AS r
    JOIN staff_attendance_events AS e
      ON e.attendance_id = r.attendance_id
     AND e.actor_id = r.decided_by
     AND e.source = 'manual'
     AND e.attendance_request_id IS NULL
     AND e.event_type = CASE
             WHEN r.action = 'correct' THEN r.mark || '_correction'
             WHEN r.mark = 'check_in' THEN 'attendance_voided'
             ELSE 'check_out_voided'
         END
     AND (
         e.reason = 'Solicitud del colaborador: ' || r.justification
         OR e.reason LIKE 'Solicitud del colaborador: ' || r.justification
            || ' · Nota del supervisor: %'
     )
    WHERE r.status = 'approved'
      AND r.decided_by IS NOT NULL
)
UPDATE staff_attendance_events
SET attendance_request_id = (
        SELECT candidates.request_id
        FROM candidates
        WHERE candidates.event_id = staff_attendance_events.id
          AND candidates.request_matches = 1
          AND candidates.event_matches = 1
    )
WHERE id IN (
    SELECT candidates.event_id
    FROM candidates
    WHERE candidates.request_matches = 1
      AND candidates.event_matches = 1
)
"""


def upgrade() -> None:
    op.execute(sa.text(BACKFILL_SQL))


def downgrade() -> None:
    # Nothing to undo: the link is the same one ADR-046 writes at approval time.
    pass
