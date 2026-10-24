from collections import deque
from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlmodel import Session, select

from app.modules.memberships.gateway import ChargeOutcome, ChargeStatus, VerifiedWebhook
from app.modules.memberships.models import (
    Member,
    Membership,
    Payment,
    PaymentAttempt,
    PaymentAttemptEvent,
    PaymentMethod,
    ProviderWebhookEvent,
)
from app.modules.memberships.service import (
    ConsentRequired,
    IdempotencyConflict,
    process_verified_webhook,
    retry_failed_charge,
    start_first_charge,
)


class FakePaymentGateway:
    def __init__(self, outcomes: list[ChargeOutcome]) -> None:
        self.outcomes = deque(outcomes)
        self.calls: list[tuple[UUID, str]] = []

    def charge(self, attempt: PaymentAttempt, payment_method: PaymentMethod) -> ChargeOutcome:
        self.calls.append((attempt.id, attempt.idempotency_key))
        return self.outcomes.popleft()


def test_failed_first_charge_retries_and_activates_membership(
    session: Session,
    seeded_ids: tuple[UUID, UUID, UUID],
) -> None:
    member_id, plan_id, payment_method_id = seeded_ids
    gateway = FakePaymentGateway(
        [
            ChargeOutcome(ChargeStatus.FAILED, provider_reference="charge_1", failure_code="declined"),
            ChargeOutcome(
                ChargeStatus.SUCCEEDED,
                provider_reference="charge_2",
                occurred_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
            ),
        ]
    )

    first = start_first_charge(
        session,
        gateway,
        member_id=member_id,
        plan_id=plan_id,
        payment_method_id=payment_method_id,
        idempotency_key="signup-ana-1",
    )
    assert first.status == "failed"
    assert first.payment_id is None
    assert session.get(Member, member_id).status == "pending"

    retried = retry_failed_charge(
        session,
        gateway,
        failed_attempt_id=first.payment_attempt_id,
        idempotency_key="signup-ana-1-retry-1",
    )
    assert retried.status == "succeeded"
    assert retried.payment_id is not None

    membership = session.get(Membership, retried.membership_id)
    attempts = session.exec(select(PaymentAttempt).order_by(PaymentAttempt.attempt_number)).all()
    payments = session.exec(select(Payment)).all()
    events = session.exec(select(PaymentAttemptEvent)).all()

    assert membership.status == "active"
    assert len(attempts) == 2
    assert [attempt.status for attempt in attempts] == ["failed", "succeeded"]
    assert len(payments) == 1
    assert len(events) == 6
    assert len(gateway.calls) == 2


def test_duplicate_webhook_does_not_create_a_second_payment(
    session: Session,
    seeded_ids: tuple[UUID, UUID, UUID],
) -> None:
    member_id, plan_id, payment_method_id = seeded_ids
    gateway = FakePaymentGateway([ChargeOutcome(ChargeStatus.PROCESSING, provider_reference="charge_1")])
    started = start_first_charge(
        session,
        gateway,
        member_id=member_id,
        plan_id=plan_id,
        payment_method_id=payment_method_id,
        idempotency_key="signup-ana-webhook",
    )
    webhook = VerifiedWebhook(
        provider="test-gateway",
        provider_event_id="evt_1",
        event_type="charge.succeeded",
        payload_sha256="a" * 64,
        payment_attempt_id=started.payment_attempt_id,
        outcome=ChargeOutcome(ChargeStatus.SUCCEEDED, provider_reference="charge_1"),
    )

    first_delivery = process_verified_webhook(session, webhook)
    duplicate_delivery = process_verified_webhook(session, webhook)

    assert first_delivery.status == "succeeded"
    assert first_delivery.idempotent_replay is False
    assert duplicate_delivery.idempotent_replay is True
    assert session.get(Membership, started.membership_id).status == "active"
    assert len(session.exec(select(Payment)).all()) == 1
    assert len(session.exec(select(ProviderWebhookEvent)).all()) == 1


def test_same_first_charge_key_replays_without_calling_gateway_again(
    session: Session,
    seeded_ids: tuple[UUID, UUID, UUID],
) -> None:
    member_id, plan_id, payment_method_id = seeded_ids
    gateway = FakePaymentGateway([ChargeOutcome(ChargeStatus.SUCCEEDED, provider_reference="charge_1")])
    request = {
        "member_id": member_id,
        "plan_id": plan_id,
        "payment_method_id": payment_method_id,
        "idempotency_key": "signup-ana-idempotent",
    }

    first = start_first_charge(session, gateway, **request)
    replay = start_first_charge(session, gateway, **request)

    assert replay.payment_attempt_id == first.payment_attempt_id
    assert replay.idempotent_replay is True
    assert len(gateway.calls) == 1
    assert len(session.exec(select(Membership)).all()) == 1
    assert len(session.exec(select(Payment)).all()) == 1


def test_idempotency_key_cannot_be_reused_for_another_request(
    session: Session,
    seeded_ids: tuple[UUID, UUID, UUID],
) -> None:
    member_id, plan_id, payment_method_id = seeded_ids
    gateway = FakePaymentGateway([ChargeOutcome(ChargeStatus.FAILED)])
    start_first_charge(
        session,
        gateway,
        member_id=member_id,
        plan_id=plan_id,
        payment_method_id=payment_method_id,
        idempotency_key="signup-ana-conflict",
    )

    with pytest.raises(IdempotencyConflict):
        start_first_charge(
            session,
            gateway,
            member_id=member_id,
            plan_id=plan_id,
            payment_method_id=payment_method_id,
            idempotency_key="signup-ana-conflict",
            starts_at=datetime(2026, 10, 16, tzinfo=timezone.utc),
        )
def test_first_charge_requires_active_privacy_consent(session: Session) -> None:
    from app.modules.memberships.models import Member, PaymentMethod, Plan

    member = Member(first_name="Luis", last_name="Diaz", email="luis@example.test")
    plan = Plan(code="BASIC", name="Básico", duration_days=30, price_cents=25000)
    session.add_all([member, plan])
    session.flush()
    method = PaymentMethod(
        member_id=member.id,
        provider="test-gateway",
        provider_method_id="pm_luis_1",
        encrypted_provider_token=b"encrypted-token",
    )
    session.add(method)
    session.commit()

    with pytest.raises(ConsentRequired):
        start_first_charge(
            session,
            FakePaymentGateway([]),
            member_id=member.id,
            plan_id=plan.id,
            payment_method_id=method.id,
            idempotency_key="signup-luis-no-consent",
        )
def test_unknown_charge_result_replay_does_not_call_gateway_again(
    session: Session,
    seeded_ids: tuple[UUID, UUID, UUID],
) -> None:
    member_id, plan_id, payment_method_id = seeded_ids
    gateway = FakePaymentGateway([ChargeOutcome(ChargeStatus.UNKNOWN, failure_code="timeout")])
    request = {
        "member_id": member_id,
        "plan_id": plan_id,
        "payment_method_id": payment_method_id,
        "idempotency_key": "signup-ana-unknown",
    }

    first = start_first_charge(session, gateway, **request)
    replay = start_first_charge(session, gateway, **request)

    assert first.status == "unknown"
    assert replay.status == "unknown"
    assert replay.idempotent_replay is True
    assert len(gateway.calls) == 1
    assert len(session.exec(select(Payment)).all()) == 0