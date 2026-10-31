from uuid import UUID

import pytest
from sqlmodel import Session, select

from app.modules.memberships.gateway import HostedCheckout
from app.modules.memberships.models import Member, Membership, Payment, PaymentAttempt, Plan
from app.modules.memberships.service import (
    IdempotencyConflict,
    start_hosted_membership_checkout,
)


class FakeHostedCheckoutGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, int]] = []
        self.fail_next = False

    def create_checkout(
        self,
        attempt: PaymentAttempt,
        *,
        member_name: str,
        member_email: str | None,
        member_phone: str | None,
        plan_name: str,
        success_url: str,
        failure_url: str,
    ) -> HostedCheckout:
        self.calls.append((attempt.id, attempt.amount_cents))
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("Conekta is unavailable")
        return HostedCheckout(
            provider_order_id=f"ord_{attempt.id.hex}",
            checkout_url=f"https://pay.conektame.io/link/{attempt.id.hex}",
        )


def _start_checkout(
    session: Session,
    gateway: FakeHostedCheckoutGateway,
    member_id: UUID,
    plan_id: UUID,
    idempotency_key: str,
):
    return start_hosted_membership_checkout(
        session,
        gateway,
        member_id=member_id,
        plan_id=plan_id,
        idempotency_key=idempotency_key,
        success_url="https://gym.example.test/payments/return",
        failure_url="https://gym.example.test/payments/failed",
    )


def test_checkout_is_pending_until_verified_payment_and_replay_is_idempotent(
    session: Session,
    seeded_ids: tuple[UUID, UUID, UUID],
) -> None:
    member_id, plan_id, _ = seeded_ids
    gateway = FakeHostedCheckoutGateway()

    first = _start_checkout(session, gateway, member_id, plan_id, "online-signup-ana")
    replay = _start_checkout(session, gateway, member_id, plan_id, "online-signup-ana")

    membership = session.get(Membership, first.membership_id)
    attempt = session.get(PaymentAttempt, first.payment_attempt_id)
    assert first.status == "pending"
    assert first.checkout_url == replay.checkout_url
    assert replay.idempotent_replay is True
    assert membership.status == "pending_payment"
    assert membership.auto_renew is False
    assert attempt.provider == "conekta"
    assert attempt.provider_order_id is not None
    assert attempt.checkout_url == first.checkout_url
    assert session.exec(select(Payment)).all() == []
    assert gateway.calls == [(attempt.id, attempt.amount_cents)]


def test_failed_provider_request_can_retry_same_attempt_without_new_membership(
    session: Session,
    seeded_ids: tuple[UUID, UUID, UUID],
) -> None:
    member_id, plan_id, _ = seeded_ids
    gateway = FakeHostedCheckoutGateway()
    gateway.fail_next = True

    with pytest.raises(RuntimeError, match="unavailable"):
        _start_checkout(session, gateway, member_id, plan_id, "online-signup-retry")
    first_attempt = session.exec(select(PaymentAttempt)).one()
    first_membership = session.exec(select(Membership)).one()

    retried = _start_checkout(session, gateway, member_id, plan_id, "online-signup-retry")

    assert retried.payment_attempt_id == first_attempt.id
    assert retried.membership_id == first_membership.id
    assert retried.checkout_url is not None
    assert len(session.exec(select(PaymentAttempt)).all()) == 1
    assert len(session.exec(select(Membership)).all()) == 1
    assert len(gateway.calls) == 2


def test_idempotency_key_cannot_be_reused_for_another_plan(
    session: Session,
    seeded_ids: tuple[UUID, UUID, UUID],
) -> None:
    member_id, plan_id, _ = seeded_ids
    other_plan = Plan(
        code="ANNUAL",
        name="Anual",
        duration_days=365,
        price_cents=500000,
        currency="MXN",
    )
    session.add(other_plan)
    session.commit()
    gateway = FakeHostedCheckoutGateway()

    _start_checkout(session, gateway, member_id, plan_id, "online-signup-conflict")

    with pytest.raises(IdempotencyConflict):
        _start_checkout(session, gateway, member_id, other_plan.id, "online-signup-conflict")

    assert len(gateway.calls) == 1
