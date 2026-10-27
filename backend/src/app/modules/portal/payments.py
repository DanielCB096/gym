"""Member self-service payments and store account (read only).

Membership payments and the store-account ledger are owned by the memberships
and inventory modules. Here we only expose what belongs to the authenticated
member, without cashier, session or credit-limit details used by the staff.
"""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlmodel import Session, func, select

from app.modules.inventory.service import MemberAccountEntry, member_account_statement
from app.modules.memberships.models import Member, Membership, Payment, Plan
from app.modules.portal.service import MemberPortalError

MAX_MEMBER_ACCOUNT_ENTRIES = 100


@dataclass(frozen=True)
class MemberPaymentItem:
    id: UUID
    amount_cents: int
    currency: str
    method: str
    paid_at: datetime
    period_starts_at: datetime | None
    period_ends_at: datetime | None
    plan_name: str | None
    note: str | None


@dataclass(frozen=True)
class MemberPaymentPage:
    items: list[MemberPaymentItem]
    total: int
    page: int
    page_size: int
    pages: int
    total_paid_cents: int


@dataclass(frozen=True)
class MemberAccountView:
    charges_cents: int
    credits_cents: int
    payments_cents: int
    balance_cents: int
    charges_count: int
    payments_count: int
    last_activity_at: datetime | None
    oldest_charge_at: datetime | None
    as_of: date
    entries: list[MemberAccountEntry]
    entries_total: int


def list_member_payments(
    session: Session,
    member_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
) -> MemberPaymentPage:
    _require_member(session, member_id)
    page = max(page, 1)
    page_size = min(max(page_size, 1), 50)

    total = int(
        session.exec(
            select(func.count(Payment.id)).where(Payment.member_id == member_id)
        ).one()
        or 0
    )
    total_paid_cents = int(
        session.exec(
            select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
                Payment.member_id == member_id
            )
        ).one()
        or 0
    )
    rows = session.exec(
        select(Payment, Plan.name)
        .join(Membership, Payment.membership_id == Membership.id)
        .join(Plan, Membership.plan_id == Plan.id)
        .where(Payment.member_id == member_id)
        .order_by(Payment.paid_at.desc(), Payment.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        MemberPaymentItem(
            id=payment.id,
            amount_cents=payment.amount_cents,
            currency=payment.currency,
            method=payment.method,
            paid_at=payment.paid_at,
            period_starts_at=payment.period_starts_at,
            period_ends_at=payment.period_ends_at,
            plan_name=plan_name,
            note=payment.note,
        )
        for payment, plan_name in rows
    ]
    pages = (total + page_size - 1) // page_size if total > 0 else 0
    return MemberPaymentPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        total_paid_cents=total_paid_cents,
    )


def get_member_account(session: Session, member_id: UUID) -> MemberAccountView:
    _require_member(session, member_id)
    statement = member_account_statement(session, member_id)
    summary = statement.summary
    # The ledger arrives newest first; slicing keeps the most recent movements.
    return MemberAccountView(
        charges_cents=summary.charges_cents,
        credits_cents=summary.credits_cents,
        payments_cents=summary.payments_cents,
        balance_cents=summary.balance_cents,
        charges_count=summary.charges_count,
        payments_count=summary.payments_count,
        last_activity_at=summary.last_activity_at,
        oldest_charge_at=summary.oldest_charge_at,
        as_of=statement.as_of,
        entries=statement.entries[:MAX_MEMBER_ACCOUNT_ENTRIES],
        entries_total=len(statement.entries),
    )


def _require_member(session: Session, member_id: UUID) -> Member:
    member = session.get(Member, member_id)
    if member is None:
        raise MemberPortalError("Socio no encontrado")
    return member
