"""Create a synthetic member checkout for a disposable Conekta sandbox test DB."""

import argparse
import os
import sys
from uuid import UUID, uuid4

from sqlmodel import Session, create_engine, select

from app.modules.memberships.conekta_checkout import (
    ConektaCheckoutConfigurationError,
    ConektaCheckoutSettings,
    ConektaHostedCheckout,
    ConektaCheckoutUnavailable,
)
from app.modules.memberships.models import (
    Member,
    MemberConsent,
    Membership,
    Payment,
    PaymentAttempt,
    Plan,
    utc_now,
)
from app.modules.memberships.service import BillingError, start_hosted_membership_checkout


def _positive_amount(value: str) -> int:
    try:
        amount = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("amount must be an integer number of cents") from error
    if amount <= 0:
        raise argparse.ArgumentTypeError("amount must be greater than zero")
    return amount


def _engine():
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    return create_engine(database_url)


def _create_checkout(session: Session, *, amount_cents: int) -> UUID:
    now = utc_now()
    token = uuid4().hex
    member = Member(
        first_name="Sandbox",
        last_name="Conekta",
        email=f"conekta-sandbox-{token}@example.com",
        status="pending",
    )
    plan = Plan(
        code=f"CONK-{token[:20].upper()}",
        name="Plan de prueba Conekta",
        duration_days=30,
        price_cents=amount_cents,
        currency="MXN",
    )
    session.add_all([member, plan])
    session.flush()
    session.add(
        MemberConsent(
            member_id=member.id,
            consent_type="privacy_notice",
            document_version="sandbox-only-synthetic-test",
            accepted_at=now,
        )
    )
    settings = ConektaCheckoutSettings.from_env()
    session.commit()

    attempt_key = str(uuid4())
    try:
        result = start_hosted_membership_checkout(
            session,
            ConektaHostedCheckout(settings),
            member_id=member.id,
            plan_id=plan.id,
            idempotency_key=attempt_key,
            success_url=settings.success_url,
            failure_url=settings.failure_url,
        )
    except ConektaCheckoutUnavailable:
        attempt = session.exec(
            select(PaymentAttempt).where(PaymentAttempt.idempotency_key == attempt_key)
        ).first()
        if attempt is not None:
            print(
                f"Retry checkout creation with --resume-attempt {attempt.id}",
                file=sys.stderr,
            )
        raise
    return result.payment_attempt_id


def _resume_checkout(session: Session, attempt_id: UUID) -> UUID:
    attempt = session.get(PaymentAttempt, attempt_id)
    if (
        attempt is None
        or attempt.provider != "conekta"
        or attempt.provider_order_id is not None
        or attempt.status != "pending"
    ):
        raise ValueError("Attempt must be a pending Conekta checkout without a provider order")
    membership = session.get(Membership, attempt.membership_id)
    if membership is None:
        raise ValueError("Attempt membership no longer exists")
    settings = ConektaCheckoutSettings.from_env()
    start_hosted_membership_checkout(
        session,
        ConektaHostedCheckout(settings),
        member_id=membership.member_id,
        plan_id=membership.plan_id,
        idempotency_key=attempt.idempotency_key,
        success_url=settings.success_url,
        failure_url=settings.failure_url,
    )
    return attempt.id


def _show_status(session: Session, attempt_id: UUID) -> None:
    attempt = session.get(PaymentAttempt, attempt_id)
    if attempt is None:
        raise ValueError("Payment attempt was not found")
    membership = session.get(Membership, attempt.membership_id)
    payment = session.exec(
        select(Payment).where(Payment.payment_attempt_id == attempt.id)
    ).first()
    print(f"payment_attempt_id={attempt.id}")
    print(f"payment_attempt_status={attempt.status}")
    print(f"membership_status={membership.status if membership else 'missing'}")
    print(f"confirmed_payment={'yes' if payment else 'no'}")
    print(f"provider_reference={attempt.provider_reference or 'not available'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--resume-attempt", type=UUID)
    operation.add_argument("--status", type=UUID)
    parser.add_argument("--amount-cents", type=_positive_amount, default=1000)
    args = parser.parse_args()

    engine = _engine()
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        with Session(engine) as session:
            if args.status:
                _show_status(session, args.status)
                return 0
            if args.resume_attempt:
                attempt_id = _resume_checkout(session, args.resume_attempt)
            else:
                attempt_id = _create_checkout(session, amount_cents=args.amount_cents)
            attempt = session.get(PaymentAttempt, attempt_id)
            if attempt is None or attempt.checkout_url is None:
                raise RuntimeError("Conekta checkout URL was not saved")
            print(f"payment_attempt_id={attempt.id}")
            print(f"checkout_url={attempt.checkout_url}")
            print("This creates a sandbox order only; it does not charge a real card.")
            return 0
    except (BillingError, ConektaCheckoutConfigurationError, ConektaCheckoutUnavailable, ValueError, RuntimeError) as error:
        print(f"Sandbox checkout setup failed: {error}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
