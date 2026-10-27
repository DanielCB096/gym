"""Bank reconciliation: import statement lines, suggest internal matches and
record the operator's decision.

The service never creates a money movement and never edits a payment or a sale.
It only links a bank line to the internal row that already recorded the money,
using amount, currency and date proximity as suggestions and a human decision as
the source of truth.
"""

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import re
import unicodedata
from uuid import UUID

from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.modules.finance.errors import (
    BankAccountNotFound,
    BankMovementNotFound,
    BankMovementStateError,
    CandidateUnavailable,
    DuplicateBankAccount,
    InvalidBankData,
    InvalidImportBatch,
    InvalidMatch,
    MatchCandidateNotFound,
)
from app.modules.billing.models import Invoice, InvoicePayment
from app.modules.finance.models import (
    BANK_MOVEMENT_SOURCES,
    BANK_MOVEMENT_STATUSES,
    BankAccount,
    BankMovement,
    BankMovementEvent,
    utc_now,
)
from app.modules.identity.models import AppUser
from app.modules.inventory.models import MemberAccountPayment, Sale, SaleReturn
from app.modules.memberships.models import Member, Membership, Payment, Plan
from app.timezone import club_date, club_timezone, local_midnight

BANK_METHODS = ("card", "transfer", "spei")
ACCOUNT_METHODS = ("card", "transfer")
# Only complements paid by an electronic tender can be traced to a bank line.
# Cash ("01"), account ("99") and other SAT forms never hit the statement.
PPD_BANK_FORMS = ("03", "04", "28")
SUGGESTION_WINDOW_DAYS = 7
MANUAL_SEARCH_WINDOW_DAYS = 60
NEAR_AMOUNT_RATE = 0.02
NEAR_AMOUNT_MIN_CENTS = 100
MAX_IMPORT_ROWS = 500
MAX_AMOUNT_CENTS = 1_000_000_000_000
CANDIDATE_LIMIT = 20
SUGGESTION_PREVIEW = 3

SOURCE_LABELS = {
    "membership_payment": "Pago de membresía",
    "sale": "Venta",
    "member_account_payment": "Abono a cuenta",
    "sale_return": "Devolución",
    "invoice_payment": "Complemento PPD",
}

PPD_FORM_LABELS = {
    "03": "Transferencia",
    "04": "Tarjeta de crédito",
    "28": "Tarjeta de débito",
}

METHOD_LABELS = {
    "card": "Tarjeta",
    "transfer": "Transferencia",
    "spei": "SPEI",
}

STATUS_LABELS = {
    "pending": "pendiente",
    "reconciled": "conciliado",
    "difference": "con diferencia",
    "reviewing": "en revisión",
}


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _signed_money(cents: int) -> str:
    sign = "−" if cents < 0 else "+"
    return f"{sign}${abs(cents) / 100:,.2f}"


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFD", value)
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", without_accents)
    return " ".join(cleaned.split()).upper()


def _member_name(member: Member | None) -> str:
    if member is None:
        return "Público general"
    return f"{member.first_name} {member.last_name}".strip()


def _reference_score(
    movement: BankMovement,
    *,
    folio: str | None = None,
    names: tuple[str | None, ...] = (),
    extra: str | None = None,
) -> int:
    text = _normalize(f"{movement.reference} {movement.description or ''}")
    if not text:
        return 0
    tokens = set(text.split())
    compact = text.replace(" ", "")
    score = 0
    folio_text = _normalize(folio)
    if folio_text and folio_text.replace(" ", "") in compact:
        score += 3
    for name in names:
        for token in _normalize(name).split():
            if len(token) >= 3 and token in tokens:
                score += 1
                break
    for token in _normalize(extra).split():
        if len(token) >= 4 and token in tokens:
            score += 1
            break
    return score


def _candidate_entry(
    movement: BankMovement,
    *,
    source: str,
    source_id: UUID,
    label: str,
    detail: str,
    reference: str,
    occurred_on: date,
    amount_cents: int,
    reference_score: int,
) -> dict[str, object]:
    return {
        "source": source,
        "source_id": str(source_id),
        "label": label,
        "detail": detail,
        "reference": reference,
        "occurred_on": occurred_on.isoformat(),
        "amount_cents": amount_cents,
        "difference_cents": movement.amount_cents - amount_cents,
        "amount_match": movement.amount_cents == amount_cents,
        "reference_score": reference_score,
        "date_distance_days": abs((occurred_on - movement.occurred_on).days),
    }


def _ppd_payment_candidate(
    movement: BankMovement, payment: InvoicePayment, invoice: Invoice
) -> dict[str, object]:
    folio = f"{payment.series}-{payment.folio:06d}"
    invoice_folio = f"{invoice.series}-{invoice.folio:06d}"
    form_label = PPD_FORM_LABELS.get(payment.payment_form, payment.payment_form)
    return _candidate_entry(
        movement,
        source="invoice_payment",
        source_id=payment.id,
        label=f"Complemento PPD {folio}",
        detail=f"Factura {invoice_folio} · {invoice.receptor_name} · {form_label}",
        reference=folio,
        occurred_on=payment.paid_on,
        amount_cents=payment.amount_cents,
        reference_score=_reference_score(
            movement,
            folio=folio,
            names=(invoice.receptor_name,),
            extra=invoice_folio,
        ),
    )


def _sort_key(candidate: dict[str, object], *, searching: bool) -> tuple:
    exact = 0 if candidate["amount_match"] else 1
    score = -int(candidate["reference_score"])
    amount_distance = abs(int(candidate["difference_cents"]))
    distance = int(candidate["date_distance_days"])
    recency = -date.fromisoformat(str(candidate["occurred_on"])).toordinal()
    if searching:
        return (score, exact, amount_distance, distance, recency)
    return (exact, score, amount_distance, distance, recency)


def _matched_keys(session: Session) -> set[tuple[str, str]]:
    rows = session.exec(
        select(BankMovement.matched_source, BankMovement.matched_id).where(
            BankMovement.matched_id.is_not(None)
        )
    ).all()
    return {(str(source), str(identifier)) for source, identifier in rows}


def _is_matched(matched: set[tuple[str, str]], source: str, identifier: UUID) -> bool:
    return (source, str(identifier)) in matched


def _date_window(movement: BankMovement, days: int) -> tuple[datetime, datetime]:
    timezone_zone = club_timezone()
    start = local_midnight(movement.occurred_on - timedelta(days=days), timezone_zone)
    end = local_midnight(movement.occurred_on + timedelta(days=days + 1), timezone_zone)
    return start, end


def _candidate_rows(
    session: Session,
    movement: BankMovement,
    *,
    search: str | None = None,
    limit: int = CANDIDATE_LIMIT,
) -> list[dict[str, object]]:
    term = _normalize(search)
    searching = bool(term)
    days = MANUAL_SEARCH_WINDOW_DAYS if searching else SUGGESTION_WINDOW_DAYS
    start_at, end_at = _date_window(movement, days)
    direction = 1 if movement.amount_cents > 0 else -1
    target = abs(movement.amount_cents)
    tolerance = max(NEAR_AMOUNT_MIN_CENTS, target * NEAR_AMOUNT_RATE)
    low = target - tolerance
    high = target + tolerance
    matched = _matched_keys(session)
    candidates: list[dict[str, object]] = []

    def matches_search(*fields: str | None) -> bool:
        if not searching:
            return True
        haystack = " ".join(_normalize(field) for field in fields if field)
        return term in haystack

    if direction > 0:
        payment_statement = (
            select(Payment, Member, Plan)
            .join(Member, Payment.member_id == Member.id)
            .join(Membership, Payment.membership_id == Membership.id)
            .join(Plan, Membership.plan_id == Plan.id)
            .where(
                Payment.currency == movement.currency,
                Payment.method.in_(BANK_METHODS),
                Payment.paid_at >= start_at,
                Payment.paid_at < end_at,
            )
        )
        if not searching:
            payment_statement = payment_statement.where(
                Payment.amount_cents >= low, Payment.amount_cents <= high
            )
        else:
            payment_statement = payment_statement.where(
                or_(
                    func.lower(Member.first_name).contains(term.lower()),
                    func.lower(Member.last_name).contains(term.lower()),
                    func.lower(Plan.name).contains(term.lower()),
                )
            )
        for payment, member, plan in session.exec(
            payment_statement.order_by(Payment.paid_at.desc()).limit(200)
        ).all():
            if _is_matched(matched, "membership_payment", payment.id):
                continue
            member_label = _member_name(member)
            if searching and not matches_search(
                member_label, plan.name, str(payment.id), METHOD_LABELS.get(payment.method, payment.method)
            ):
                continue
            candidates.append(
                _candidate_entry(
                    movement,
                    source="membership_payment",
                    source_id=payment.id,
                    label=f"Pago de membresía · {member_label}",
                    detail=f"{plan.name} · {METHOD_LABELS.get(payment.method, payment.method)}",
                    reference=f"Pago {str(payment.id)[:8].upper()}",
                    occurred_on=club_date(payment.paid_at),
                    amount_cents=payment.amount_cents,
                    reference_score=_reference_score(
                        movement,
                        names=(member.first_name, member.last_name),
                        extra=plan.name,
                    ),
                )
            )

        sale_statement = (
            select(Sale, Member)
            .outerjoin(Member, Sale.member_id == Member.id)
            .where(
                movement.currency == "MXN",
                Sale.payment_method.in_(ACCOUNT_METHODS),
                Sale.sold_at >= start_at,
                Sale.sold_at < end_at,
            )
        )
        if not searching:
            sale_statement = sale_statement.where(
                Sale.total_cents >= low, Sale.total_cents <= high
            )
        if searching:
            sale_statement = sale_statement.where(
                or_(
                    func.lower(Sale.folio).contains(term.lower()),
                    func.lower(Member.first_name).contains(term.lower()),
                    func.lower(Member.last_name).contains(term.lower()),
                )
            )
        for sale, member in session.exec(
            sale_statement.order_by(Sale.sold_at.desc()).limit(200)
        ).all():
            if _is_matched(matched, "sale", sale.id):
                continue
            member_label = _member_name(member)
            if searching and not matches_search(
                sale.folio, member_label, METHOD_LABELS.get(sale.payment_method, sale.payment_method)
            ):
                continue
            candidates.append(
                _candidate_entry(
                    movement,
                    source="sale",
                    source_id=sale.id,
                    label=f"Venta {sale.folio}",
                    detail=f"{member_label} · {METHOD_LABELS.get(sale.payment_method, sale.payment_method)}",
                    reference=sale.folio,
                    occurred_on=club_date(sale.sold_at),
                    amount_cents=sale.total_cents,
                    reference_score=_reference_score(
                        movement,
                        folio=sale.folio,
                        names=(member.first_name if member else None, member.last_name if member else None),
                    ),
                )
            )

        account_statement = (
            select(MemberAccountPayment, Member)
            .join(Member, MemberAccountPayment.member_id == Member.id)
            .where(
                movement.currency == "MXN",
                MemberAccountPayment.method.in_(ACCOUNT_METHODS),
                MemberAccountPayment.paid_at >= start_at,
                MemberAccountPayment.paid_at < end_at,
            )
        )
        if not searching:
            account_statement = account_statement.where(
                MemberAccountPayment.amount_cents >= low,
                MemberAccountPayment.amount_cents <= high,
            )
        else:
            account_statement = account_statement.where(
                or_(
                    func.lower(Member.first_name).contains(term.lower()),
                    func.lower(Member.last_name).contains(term.lower()),
                )
            )
        for payment, member in session.exec(
            account_statement.order_by(MemberAccountPayment.paid_at.desc()).limit(200)
        ).all():
            if _is_matched(matched, "member_account_payment", payment.id):
                continue
            member_label = _member_name(member)
            if searching and not matches_search(member_label, str(payment.id)):
                continue
            candidates.append(
                _candidate_entry(
                    movement,
                    source="member_account_payment",
                    source_id=payment.id,
                    label=f"Abono a cuenta · {member_label}",
                    detail="Pago a cuenta del socio",
                    reference=f"Abono {str(payment.id)[:8].upper()}",
                    occurred_on=club_date(payment.paid_at),
                    amount_cents=payment.amount_cents,
                    reference_score=_reference_score(
                        movement, names=(member.first_name, member.last_name)
                    ),
                )
            )

        ppd_statement = (
            select(InvoicePayment, Invoice)
            .join(Invoice, Invoice.id == InvoicePayment.invoice_id)
            .where(
                Invoice.status == "stamped",
                InvoicePayment.status == "stamped",
                InvoicePayment.payment_form.in_(PPD_BANK_FORMS),
                InvoicePayment.currency == movement.currency,
                InvoicePayment.paid_on >= club_date(start_at),
                InvoicePayment.paid_on < club_date(end_at),
            )
        )
        if not searching:
            ppd_statement = ppd_statement.where(
                InvoicePayment.amount_cents >= low,
                InvoicePayment.amount_cents <= high,
            )
        for payment, invoice in session.exec(
            ppd_statement.order_by(InvoicePayment.paid_on.desc()).limit(200)
        ).all():
            if _is_matched(matched, "invoice_payment", payment.id):
                continue
            folio = f"{payment.series}-{payment.folio:06d}"
            invoice_folio = f"{invoice.series}-{invoice.folio:06d}"
            if searching and not matches_search(
                folio, invoice_folio, invoice.receptor_name, invoice.receptor_rfc, payment.uuid
            ):
                continue
            candidates.append(_ppd_payment_candidate(movement, payment, invoice))
    else:
        return_statement = (
            select(SaleReturn, Sale, Member)
            .join(Sale, SaleReturn.sale_id == Sale.id)
            .outerjoin(Member, SaleReturn.member_id == Member.id)
            .where(
                movement.currency == "MXN",
                SaleReturn.refund_method.in_(ACCOUNT_METHODS),
                SaleReturn.returned_at >= start_at,
                SaleReturn.returned_at < end_at,
            )
        )
        if not searching:
            return_statement = return_statement.where(
                SaleReturn.total_refund_cents >= low,
                SaleReturn.total_refund_cents <= high,
            )
        if searching:
            return_statement = return_statement.where(
                or_(
                    func.lower(SaleReturn.folio).contains(term.lower()),
                    func.lower(Sale.folio).contains(term.lower()),
                    func.lower(Member.first_name).contains(term.lower()),
                    func.lower(Member.last_name).contains(term.lower()),
                )
            )
        for sale_return, sale, member in session.exec(
            return_statement.order_by(SaleReturn.returned_at.desc()).limit(200)
        ).all():
            if _is_matched(matched, "sale_return", sale_return.id):
                continue
            member_label = _member_name(member)
            if searching and not matches_search(
                sale_return.folio, sale.folio, member_label
            ):
                continue
            candidates.append(
                _candidate_entry(
                    movement,
                    source="sale_return",
                    source_id=sale_return.id,
                    label=f"Devolución {sale_return.folio}",
                    detail=f"Venta {sale.folio} · {sale_return.reason}",
                    reference=sale_return.folio,
                    occurred_on=club_date(sale_return.returned_at),
                    amount_cents=-sale_return.total_refund_cents,
                    reference_score=_reference_score(
                        movement,
                        folio=sale_return.folio,
                        names=(member.first_name if member else None, member.last_name if member else None),
                        extra=sale.folio,
                    ),
                )
            )

    candidates.sort(key=lambda item: _sort_key(item, searching=searching))
    return candidates[:limit]


def _load_candidate(
    session: Session, movement: BankMovement, source: str, source_id: UUID
) -> dict[str, object] | None:
    if source == "membership_payment":
        row = session.exec(
            select(Payment, Member, Plan)
            .join(Member, Payment.member_id == Member.id)
            .join(Membership, Payment.membership_id == Membership.id)
            .join(Plan, Membership.plan_id == Plan.id)
            .where(Payment.id == source_id)
        ).first()
        if row is None:
            return None
        payment, member, plan = row
        if payment.method not in BANK_METHODS or payment.currency != movement.currency:
            raise InvalidMatch("La operación no es un cobro electrónico compatible con la cuenta.")
        if movement.amount_cents < 0:
            raise InvalidMatch("Un pago de membresía no puede conciliar un retiro.")
        member_label = _member_name(member)
        return _candidate_entry(
            movement,
            source="membership_payment",
            source_id=payment.id,
            label=f"Pago de membresía · {member_label}",
            detail=f"{plan.name} · {METHOD_LABELS.get(payment.method, payment.method)}",
            reference=f"Pago {str(payment.id)[:8].upper()}",
            occurred_on=club_date(payment.paid_at),
            amount_cents=payment.amount_cents,
            reference_score=_reference_score(
                movement, names=(member.first_name, member.last_name), extra=plan.name
            ),
        )

    if source == "sale":
        row = session.exec(
            select(Sale, Member)
            .outerjoin(Member, Sale.member_id == Member.id)
            .where(Sale.id == source_id)
        ).first()
        if row is None:
            return None
        sale, member = row
        if sale.payment_method not in ACCOUNT_METHODS or movement.currency != "MXN":
            raise InvalidMatch("La venta no es un cobro electrónico compatible con la cuenta.")
        if movement.amount_cents < 0:
            raise InvalidMatch("Una venta no puede conciliar un retiro.")
        member_label = _member_name(member)
        return _candidate_entry(
            movement,
            source="sale",
            source_id=sale.id,
            label=f"Venta {sale.folio}",
            detail=f"{member_label} · {METHOD_LABELS.get(sale.payment_method, sale.payment_method)}",
            reference=sale.folio,
            occurred_on=club_date(sale.sold_at),
            amount_cents=sale.total_cents,
            reference_score=_reference_score(
                movement,
                folio=sale.folio,
                names=(member.first_name if member else None, member.last_name if member else None),
            ),
        )

    if source == "member_account_payment":
        row = session.exec(
            select(MemberAccountPayment, Member)
            .join(Member, MemberAccountPayment.member_id == Member.id)
            .where(MemberAccountPayment.id == source_id)
        ).first()
        if row is None:
            return None
        payment, member = row
        if payment.method not in ACCOUNT_METHODS or movement.currency != "MXN":
            raise InvalidMatch("El abono no es un cobro electrónico compatible con la cuenta.")
        if movement.amount_cents < 0:
            raise InvalidMatch("Un abono a cuenta no puede conciliar un retiro.")
        member_label = _member_name(member)
        return _candidate_entry(
            movement,
            source="member_account_payment",
            source_id=payment.id,
            label=f"Abono a cuenta · {member_label}",
            detail="Pago a cuenta del socio",
            reference=f"Abono {str(payment.id)[:8].upper()}",
            occurred_on=club_date(payment.paid_at),
            amount_cents=payment.amount_cents,
            reference_score=_reference_score(
                movement, names=(member.first_name, member.last_name)
            ),
        )

    if source == "invoice_payment":
        row = session.exec(
            select(InvoicePayment, Invoice)
            .join(Invoice, Invoice.id == InvoicePayment.invoice_id)
            .where(InvoicePayment.id == source_id)
        ).first()
        if row is None:
            return None
        payment, invoice = row
        if (
            payment.status != "stamped"
            or invoice.status != "stamped"
            or payment.payment_form not in PPD_BANK_FORMS
            or payment.currency != movement.currency
        ):
            raise InvalidMatch(
                "El complemento PPD no es un cobro electrónico compatible con la cuenta."
            )
        if movement.amount_cents < 0:
            raise InvalidMatch("Un complemento PPD no puede conciliar un retiro.")
        return _ppd_payment_candidate(movement, payment, invoice)

    if source == "sale_return":
        row = session.exec(
            select(SaleReturn, Sale, Member)
            .join(Sale, SaleReturn.sale_id == Sale.id)
            .outerjoin(Member, SaleReturn.member_id == Member.id)
            .where(SaleReturn.id == source_id)
        ).first()
        if row is None:
            return None
        sale_return, sale, member = row
        if sale_return.refund_method not in ACCOUNT_METHODS or movement.currency != "MXN":
            raise InvalidMatch("La devolución no es un reembolso electrónico compatible con la cuenta.")
        if movement.amount_cents > 0:
            raise InvalidMatch("Una devolución no puede conciliar un depósito.")
        member_label = _member_name(member)
        return _candidate_entry(
            movement,
            source="sale_return",
            source_id=sale_return.id,
            label=f"Devolución {sale_return.folio}",
            detail=f"Venta {sale.folio} · {sale_return.reason}",
            reference=sale_return.folio,
            occurred_on=club_date(sale_return.returned_at),
            amount_cents=-sale_return.total_refund_cents,
            reference_score=_reference_score(
                movement,
                folio=sale_return.folio,
                names=(member.first_name if member else None, member.last_name if member else None),
                extra=sale.folio,
            ),
        )

    return None


def _account_view(session: Session, account: BankAccount) -> dict[str, object]:
    rows = session.exec(
        select(
            BankMovement.status,
            func.count(),
            func.sum(BankMovement.amount_cents),
            func.min(BankMovement.occurred_on),
            func.max(BankMovement.occurred_on),
        )
        .where(BankMovement.bank_account_id == account.id)
        .group_by(BankMovement.status)
    ).all()
    counts = {status: 0 for status in BANK_MOVEMENT_STATUSES}
    balance_cents = 0
    movement_count = 0
    last_movement_on: date | None = None
    for status, count, amount, _oldest, newest in rows:
        normalized = str(status)
        if normalized in counts:
            counts[normalized] = int(count)
        movement_count += int(count)
        balance_cents += int(amount or 0)
        day = _as_date(newest)
        if day is not None and (last_movement_on is None or day > last_movement_on):
            last_movement_on = day
    return {
        "id": str(account.id),
        "name": account.name,
        "bank_name": account.bank_name,
        "account_last4": account.account_last4,
        "currency": account.currency,
        "status": account.status,
        "created_at": account.created_at,
        "updated_at": account.updated_at,
        "movement_count": movement_count,
        "pending_count": counts["pending"],
        "reconciled_count": counts["reconciled"],
        "difference_count": counts["difference"],
        "reviewing_count": counts["reviewing"],
        "balance_cents": balance_cents,
        "last_movement_on": last_movement_on.isoformat() if last_movement_on else None,
    }


def _as_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def create_bank_account(
    session: Session,
    *,
    name: str,
    bank_name: str,
    account_last4: str,
    currency: str = "MXN",
    actor_id: UUID | None = None,
) -> dict[str, object]:
    display_name = " ".join(name.split())
    bank = " ".join(bank_name.split())
    last4 = account_last4.strip()
    code = currency.strip().upper()
    if len(display_name) < 2 or len(display_name) > 120:
        raise InvalidBankData("El nombre de la cuenta debe tener entre 2 y 120 caracteres.")
    if len(bank) < 2 or len(bank) > 80:
        raise InvalidBankData("El banco debe tener entre 2 y 80 caracteres.")
    if not re.fullmatch(r"\d{4}", last4):
        raise InvalidBankData("Los últimos cuatro dígitos deben ser exactamente cuatro números.")
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise InvalidBankData("La moneda debe ser un código de tres letras, por ejemplo MXN.")
    existing = session.exec(
        select(BankAccount).where(func.lower(BankAccount.name) == display_name.lower())
    ).first()
    if existing is not None:
        raise DuplicateBankAccount("Ya existe una cuenta con ese nombre.")
    account = BankAccount(
        name=display_name,
        bank_name=bank,
        account_last4=last4,
        currency=code,
        created_by=actor_id,
    )
    session.add(account)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise DuplicateBankAccount("Ya existe una cuenta con ese nombre.") from error
    session.refresh(account)
    return _account_view(session, account)


def list_bank_accounts(session: Session) -> dict[str, object]:
    active_first = case((BankAccount.status == "active", 0), else_=1)
    accounts = session.exec(
        select(BankAccount).order_by(active_first, func.lower(BankAccount.name))
    ).all()
    items = [_account_view(session, account) for account in accounts]
    return {"items": items, "total": len(items)}


def update_bank_account_status(
    session: Session, account_id: UUID, *, status: str
) -> dict[str, object]:
    if status not in ("active", "inactive"):
        raise InvalidBankData("El estado de la cuenta no es válido.")
    account = session.get(BankAccount, account_id)
    if account is None:
        raise BankAccountNotFound("La cuenta bancaria no existe.")
    account.status = status
    account.updated_at = utc_now()
    session.add(account)
    session.commit()
    session.refresh(account)
    return _account_view(session, account)


def _import_hash(
    account_id: UUID, occurred_on: date, amount_cents: int, reference: str, description: str
) -> str:
    payload = "|".join(
        (
            str(account_id),
            occurred_on.isoformat(),
            str(amount_cents),
            reference.casefold(),
            description.casefold(),
        )
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def import_bank_movements(
    session: Session,
    account_id: UUID,
    rows: list[dict[str, object]],
    *,
    actor_id: UUID | None = None,
) -> dict[str, object]:
    account = session.get(BankAccount, account_id)
    if account is None:
        raise BankAccountNotFound("La cuenta bancaria no existe.")
    if account.status != "active":
        raise BankMovementStateError(
            "La cuenta está inactiva; reactívala antes de importar movimientos."
        )
    if not rows:
        raise InvalidImportBatch("Agrega al menos una línea del estado de cuenta.")
    if len(rows) > MAX_IMPORT_ROWS:
        raise InvalidImportBatch(f"Puedes importar hasta {MAX_IMPORT_ROWS} movimientos por lote.")

    normalized: list[tuple[date, int, str, str, str]] = []
    seen: set[str] = set()
    duplicates = 0
    for index, row in enumerate(rows, start=1):
        occurred_on = row.get("occurred_on")
        amount_cents = row.get("amount_cents")
        reference = str(row.get("reference") or "").strip()
        description = str(row.get("description") or "").strip()
        if not isinstance(occurred_on, date):
            raise InvalidImportBatch(f"Fila {index}: la fecha no es válida.")
        if not isinstance(amount_cents, int) or isinstance(amount_cents, bool):
            raise InvalidImportBatch(f"Fila {index}: el importe no es válido.")
        if amount_cents == 0:
            raise InvalidImportBatch(f"Fila {index}: el importe no puede ser cero.")
        if abs(amount_cents) > MAX_AMOUNT_CENTS:
            raise InvalidImportBatch(f"Fila {index}: el importe excede el límite permitido.")
        if len(reference) > 120:
            raise InvalidImportBatch(f"Fila {index}: la referencia supera 120 caracteres.")
        if len(description) > 240:
            raise InvalidImportBatch(f"Fila {index}: la descripción supera 240 caracteres.")
        digest = _import_hash(account.id, occurred_on, amount_cents, reference, description)
        if digest in seen:
            duplicates += 1
            continue
        seen.add(digest)
        normalized.append((occurred_on, amount_cents, reference, description, digest))

    existing_hashes = set(
        session.exec(
            select(BankMovement.import_hash).where(
                BankMovement.bank_account_id == account.id,
                BankMovement.import_hash.in_([item[4] for item in normalized]),
            )
        ).all()
    )
    created = 0
    for occurred_on, amount_cents, reference, description, digest in normalized:
        if digest in existing_hashes:
            duplicates += 1
            continue
        movement = BankMovement(
            bank_account_id=account.id,
            occurred_on=occurred_on,
            amount_cents=amount_cents,
            currency=account.currency,
            reference=reference,
            description=description or None,
            import_hash=digest,
            imported_by=actor_id,
        )
        session.add(movement)
        session.flush()
        session.add(
            BankMovementEvent(
                movement_id=movement.id,
                event_type="imported",
                detail=f"Línea importada por {_signed_money(amount_cents)}.",
                actor_id=actor_id,
            )
        )
        created += 1
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise BankMovementStateError(
            "Otra importación simultánea creó las mismas líneas; vuelve a consultar la bandeja."
        ) from error
    return {
        "imported": created,
        "duplicates": duplicates,
        "total_rows": len(rows),
    }


def _movement_summary(session: Session, conditions: tuple) -> dict[str, object]:
    counts = {status: 0 for status in BANK_MOVEMENT_STATUSES}
    for status_value, count in session.exec(
        select(BankMovement.status, func.count()).where(*conditions).group_by(BankMovement.status)
    ).all():
        if status_value in counts:
            counts[str(status_value)] = int(count)

    inflow_cents = session.exec(
        select(func.coalesce(func.sum(BankMovement.amount_cents), 0)).where(
            *conditions, BankMovement.amount_cents > 0
        )
    ).first() or 0
    outflow_cents = session.exec(
        select(func.coalesce(func.sum(BankMovement.amount_cents), 0)).where(
            *conditions, BankMovement.amount_cents < 0
        )
    ).first() or 0
    pending_cents = session.exec(
        select(func.coalesce(func.sum(func.abs(BankMovement.amount_cents)), 0)).where(
            *conditions, BankMovement.status == "pending"
        )
    ).first() or 0
    difference_rows = session.exec(
        select(BankMovement.amount_cents, BankMovement.difference_cents).where(
            *conditions, BankMovement.status == "difference"
        )
    ).all()
    difference_cents = sum(
        abs(int(difference) if difference is not None else int(amount))
        for amount, difference in difference_rows
    )
    oldest_pending = session.exec(
        select(func.min(BankMovement.occurred_on)).where(
            *conditions, BankMovement.status == "pending"
        )
    ).first()
    oldest_day = _as_date(oldest_pending)
    return {
        "count": sum(counts.values()),
        "pending": counts["pending"],
        "reconciled": counts["reconciled"],
        "difference": counts["difference"],
        "reviewing": counts["reviewing"],
        "inflow_cents": int(inflow_cents),
        "outflow_cents": int(outflow_cents),
        "pending_cents": int(pending_cents),
        "difference_cents": difference_cents,
        "oldest_pending_on": oldest_day.isoformat() if oldest_day else None,
    }


def _suggestion_preview(session: Session, movement: BankMovement) -> tuple[int, str | None]:
    if movement.matched_id is not None or movement.status == "reconciled":
        return (0, None)
    candidates = _candidate_rows(session, movement, limit=SUGGESTION_PREVIEW)
    if not candidates:
        return (0, None)
    return (len(candidates), str(candidates[0]["label"]))


def _movement_view(
    session: Session,
    movement: BankMovement,
    account: BankAccount,
    *,
    include_suggestions: bool = True,
) -> dict[str, object]:
    suggestions, suggested_label = (
        _suggestion_preview(session, movement) if include_suggestions else (0, None)
    )
    return {
        "id": str(movement.id),
        "bank_account_id": str(account.id),
        "bank_account_name": account.name,
        "bank_name": account.bank_name,
        "account_last4": account.account_last4,
        "occurred_on": movement.occurred_on.isoformat(),
        "amount_cents": movement.amount_cents,
        "currency": movement.currency,
        "reference": movement.reference,
        "description": movement.description,
        "status": movement.status,
        "matched_source": movement.matched_source,
        "matched_id": str(movement.matched_id) if movement.matched_id else None,
        "matched_label": movement.matched_label,
        "difference_cents": movement.difference_cents,
        "note": movement.note,
        "imported_at": movement.imported_at,
        "reconciled_at": movement.reconciled_at,
        "reviewed_at": movement.reviewed_at,
        "suggestion_count": suggestions,
        "suggested_label": suggested_label,
    }


def list_bank_movements(
    session: Session,
    *,
    bank_account_id: UUID | None = None,
    status_filter: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, object]:
    if status_filter is not None and status_filter not in BANK_MOVEMENT_STATUSES:
        raise InvalidBankData("El estado del movimiento no es válido.")
    if from_date is not None and to_date is not None and from_date > to_date:
        raise InvalidBankData("La fecha inicial no puede ser posterior a la final.")
    if bank_account_id is not None and session.get(BankAccount, bank_account_id) is None:
        raise BankAccountNotFound("La cuenta bancaria no existe.")

    base_conditions: list = []
    if bank_account_id is not None:
        base_conditions.append(BankMovement.bank_account_id == bank_account_id)
    if from_date is not None:
        base_conditions.append(BankMovement.occurred_on >= from_date)
    if to_date is not None:
        base_conditions.append(BankMovement.occurred_on <= to_date)
    term = (search or "").strip().lower()
    if term:
        pattern = f"%{term}%"
        base_conditions.append(
            or_(
                func.lower(BankMovement.reference).like(pattern),
                func.lower(BankMovement.description).like(pattern),
                func.lower(BankMovement.matched_label).like(pattern),
                func.lower(BankMovement.note).like(pattern),
            )
        )

    summary = _movement_summary(session, tuple(base_conditions))
    conditions = list(base_conditions)
    if status_filter is not None:
        conditions.append(BankMovement.status == status_filter)

    total = session.exec(
        select(func.count()).select_from(BankMovement).where(*conditions)
    ).first() or 0
    priority = case(
        (BankMovement.status == "pending", 0),
        (BankMovement.status == "difference", 1),
        (BankMovement.status == "reviewing", 2),
        else_=3,
    )
    rows = session.exec(
        select(BankMovement, BankAccount)
        .join(BankAccount, BankMovement.bank_account_id == BankAccount.id)
        .where(*conditions)
        .order_by(
            priority,
            BankMovement.occurred_on.desc(),
            BankMovement.imported_at.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        _movement_view(session, movement, account) for movement, account in rows
    ]
    return {
        "items": items,
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "pages": max(1, (int(total) + page_size - 1) // page_size),
        "summary": summary,
    }


def _event_views(session: Session, movement_id: UUID) -> list[dict[str, object]]:
    rows = session.exec(
        select(BankMovementEvent, AppUser)
        .outerjoin(AppUser, BankMovementEvent.actor_id == AppUser.id)
        .where(BankMovementEvent.movement_id == movement_id)
        .order_by(BankMovementEvent.occurred_at, BankMovementEvent.id)
    ).all()
    return [
        {
            "id": str(event.id),
            "event_type": event.event_type,
            "detail": event.detail,
            "actor_id": str(event.actor_id) if event.actor_id else None,
            "actor_email": actor.email if actor is not None else None,
            "occurred_at": event.occurred_at,
        }
        for event, actor in rows
    ]


def get_bank_movement(
    session: Session, movement_id: UUID, *, candidate_search: str | None = None
) -> dict[str, object]:
    movement = session.get(BankMovement, movement_id)
    if movement is None:
        raise BankMovementNotFound("El movimiento bancario no existe.")
    account = session.get(BankAccount, movement.bank_account_id)
    if account is None:
        raise BankAccountNotFound("La cuenta bancaria del movimiento no existe.")
    view = _movement_view(session, movement, account, include_suggestions=False)
    candidates = (
        _candidate_rows(session, movement, search=candidate_search)
        if movement.matched_id is None and movement.status != "reconciled"
        else []
    )
    view["suggestion_count"] = len(candidates)
    view["suggested_label"] = str(candidates[0]["label"]) if candidates else None
    view["candidates"] = candidates
    view["events"] = _event_views(session, movement.id)
    return view


def match_bank_movement(
    session: Session,
    movement_id: UUID,
    *,
    source: str,
    source_id: UUID,
    note: str | None = None,
    actor_id: UUID | None = None,
) -> dict[str, object]:
    if source not in BANK_MOVEMENT_SOURCES:
        raise InvalidMatch("El tipo de operación no es válido.")
    movement = session.exec(
        select(BankMovement).where(BankMovement.id == movement_id).with_for_update()
    ).first()
    if movement is None:
        raise BankMovementNotFound("El movimiento bancario no existe.")
    if movement.matched_id is not None or movement.status == "reconciled":
        raise BankMovementStateError("El movimiento ya está vinculado a una operación interna.")
    candidate = _load_candidate(session, movement, source, source_id)
    if candidate is None:
        raise MatchCandidateNotFound("La operación seleccionada ya no existe.")
    existing_match = session.exec(
        select(BankMovement).where(
            BankMovement.matched_source == source,
            BankMovement.matched_id == source_id,
            BankMovement.id != movement.id,
        )
    ).first()
    if existing_match is not None:
        raise CandidateUnavailable("Esa operación interna ya está conciliada con otra línea del banco.")

    reason = (note or "").strip()
    if len(reason) > 300:
        raise InvalidMatch("La nota no puede superar 300 caracteres.")
    difference = int(candidate["difference_cents"])
    status_value = "reconciled" if difference == 0 else "difference"
    if difference != 0 and not reason:
        raise InvalidMatch(
            "El importe no coincide. Escribe el motivo de la diferencia para conciliar."
        )

    previous = movement.status
    now = utc_now()
    movement.matched_source = source
    movement.matched_id = source_id
    movement.matched_label = str(candidate["label"])[:240]
    movement.difference_cents = difference or None
    movement.status = status_value
    movement.note = reason or None
    movement.reconciled_by = actor_id
    movement.reconciled_at = now
    movement.reviewed_by = actor_id
    movement.reviewed_at = now
    session.add(movement)
    detail = (
        f"Vinculado a {candidate['label']} ({_money(int(candidate['amount_cents']))})."
        if difference == 0
        else (
            f"Vinculado a {candidate['label']} con diferencia de "
            f"{_money(abs(difference))}. {reason}"
        )
    )
    session.add(
        BankMovementEvent(
            movement_id=movement.id,
            event_type="matched",
            detail=detail[:400],
            actor_id=actor_id,
        )
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise CandidateUnavailable(
            "Esa operación interna ya está conciliada con otra línea del banco."
        ) from error
    return get_bank_movement(session, movement.id)


def unmatch_bank_movement(
    session: Session,
    movement_id: UUID,
    *,
    reason: str,
    actor_id: UUID | None = None,
) -> dict[str, object]:
    movement = session.exec(
        select(BankMovement).where(BankMovement.id == movement_id).with_for_update()
    ).first()
    if movement is None:
        raise BankMovementNotFound("El movimiento bancario no existe.")
    if movement.matched_id is None:
        raise BankMovementStateError("El movimiento no tiene una coincidencia que desvincular.")
    note = (reason or "").strip()
    if len(note) < 3:
        raise InvalidMatch("Escribe el motivo de la desvinculación.")
    if len(note) > 300:
        raise InvalidMatch("El motivo no puede superar 300 caracteres.")
    previous_label = movement.matched_label or "operación interna"
    previous_status = movement.status
    movement.matched_source = None
    movement.matched_id = None
    movement.matched_label = None
    movement.difference_cents = None
    movement.status = "pending"
    movement.note = None
    movement.reconciled_by = None
    movement.reconciled_at = None
    movement.reviewed_by = actor_id
    movement.reviewed_at = utc_now()
    session.add(movement)
    session.add(
        BankMovementEvent(
            movement_id=movement.id,
            event_type="unmatched",
            detail=(
                f"Se desvinculó {previous_label} (estado anterior: "
                f"{STATUS_LABELS.get(previous_status, previous_status)}). Motivo: {note}"
            )[:400],
            actor_id=actor_id,
        )
    )
    session.commit()
    return get_bank_movement(session, movement.id)


def flag_bank_movement(
    session: Session,
    movement_id: UUID,
    *,
    status: str,
    note: str | None = None,
    actor_id: UUID | None = None,
) -> dict[str, object]:
    if status not in ("pending", "difference", "reviewing"):
        raise InvalidMatch("El estado solicitado no es válido.")
    movement = session.exec(
        select(BankMovement).where(BankMovement.id == movement_id).with_for_update()
    ).first()
    if movement is None:
        raise BankMovementNotFound("El movimiento bancario no existe.")
    if movement.matched_id is not None:
        raise BankMovementStateError(
            "Desvincula la coincidencia antes de marcar el movimiento."
        )
    reason = (note or "").strip()
    if len(reason) > 300:
        raise InvalidMatch("La nota no puede superar 300 caracteres.")
    if status != "pending" and len(reason) < 3:
        raise InvalidMatch("Escribe una nota para marcar la diferencia o la revisión.")
    movement.status = status
    movement.note = reason or None
    if status == "pending":
        movement.reviewed_by = None
        movement.reviewed_at = None
        event_type = "reopened"
        detail = "El movimiento volvió a pendiente." + (f" {reason}" if reason else "")
    else:
        movement.reviewed_by = actor_id
        movement.reviewed_at = utc_now()
        event_type = "flagged"
        label = "diferencia" if status == "difference" else "revisión"
        detail = f"Marcado para {label}: {reason}"
    session.add(movement)
    session.add(
        BankMovementEvent(
            movement_id=movement.id,
            event_type=event_type,
            detail=detail[:400],
            actor_id=actor_id,
        )
    )
    session.commit()
    return get_bank_movement(session, movement.id)


__all__ = [
    "SOURCE_LABELS",
    "create_bank_account",
    "flag_bank_movement",
    "get_bank_movement",
    "import_bank_movements",
    "list_bank_accounts",
    "list_bank_movements",
    "match_bank_movement",
    "unmatch_bank_movement",
    "update_bank_account_status",
]
