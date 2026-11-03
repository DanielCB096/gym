from collections import deque
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlmodel import Session, select

from app.modules.memberships.gateway import ChargeOutcome, ChargeStatus
from app.modules.memberships.models import (
    Member,
    MemberConsent,
    Membership,
    MembershipEvent,
    Payment,
    PaymentAttempt,
    PaymentMethod,
    Plan,
)
from app.modules.memberships.service import (
    _apply_outcome,
    get_member_auto_renewal,
    run_auto_renewal_batch,
)


class FakeRenewalGateway:
    def __init__(self, outcomes: list[ChargeOutcome]) -> None:
        self.outcomes = deque(outcomes)
        self.calls: list[tuple[UUID, str]] = []

    def charge(
        self,
        attempt: PaymentAttempt,
        payment_method: PaymentMethod,
    ) -> ChargeOutcome:
        assert payment_method.provider == "conekta"
        self.calls.append((attempt.id, attempt.idempotency_key))
        return self.outcomes.popleft()


def _authorize_renewal(
    session: Session,
    member_id: UUID,
    *,
    now: datetime,
) -> None:
    session.add(
        MemberConsent(
            member_id=member_id,
            consent_type="membership_auto_renewal",
            document_version="auto-renewal-v1",
            evidence_digest="a" * 64,
            accepted_at=now - timedelta(days=30),
        )
    )
    session.commit()


def _set_up_conekta_method(
    session: Session,
    payment_method_id: UUID,
) -> None:
    payment_method = session.get(PaymentMethod, payment_method_id)
    assert payment_method is not None
    payment_method.provider = "conekta"
    payment_method.encrypted_provider_token = b"encrypted-reference"
    payment_method.status = "active"
    payment_method.is_default = True
    session.add(payment_method)
    session.commit()


def test_due_membership_expires_and_starts_one_automatic_renewal(
    session: Session,
    seeded_ids: tuple[UUID, UUID, UUID],
) -> None:
    member_id, plan_id, payment_method_id = seeded_ids
    now = datetime.now(timezone.utc)
    _authorize_renewal(session, member_id, now=now)
    _set_up_conekta_method(session, payment_method_id)
    previous = Membership(
        member_id=member_id,
        plan_id=plan_id,
        status="active",
        starts_at=now - timedelta(days=30),
        ends_at=now - timedelta(seconds=1),
        auto_renew=True,
    )
    session.add(previous)
    session.commit()
    gateway = FakeRenewalGateway(
        [
            ChargeOutcome(
                ChargeStatus.PROCESSING,
                provider_order_id="ord_sandbox_renewal_1",
            )
        ]
    )

    result = run_auto_renewal_batch(session, gateway, now=now)
    replay = run_auto_renewal_batch(
        session,
        gateway,
        now=now + timedelta(minutes=5),
    )

    assert result.expired_memberships == 1
    assert result.charges_started == 1
    assert replay == type(replay)()
    assert len(gateway.calls) == 1
    assert gateway.calls[0][1].startswith("auto-renewal:")
    session.refresh(previous)
    assert previous.status == "expired"
    assert previous.auto_renew is False
    renewed = session.exec(
        select(Membership).where(Membership.id != previous.id)
    ).one()
    attempt = session.exec(select(PaymentAttempt)).one()
    assert renewed.status == "pending_payment"
    assert renewed.auto_renew is True
    assert attempt.status == "processing"
    assert attempt.provider_order_id == "ord_sandbox_renewal_1"
    assert session.exec(select(Payment)).all() == []
    assert session.exec(
        select(MembershipEvent).where(
            MembershipEvent.membership_id == previous.id,
            MembershipEvent.event_type == "expired",
        )
    ).one()


def test_expired_member_without_saved_card_can_still_request_first_capture(
    session: Session,
    seeded_ids: tuple[UUID, UUID, UUID],
    monkeypatch,
) -> None:
    from base64 import b64encode

    from app.modules.memberships.service import create_member_payment_method_setup

    member_id, plan_id, _ = seeded_ids
    now = datetime.now(timezone.utc)
    _authorize_renewal(session, member_id, now=now)
    membership = Membership(
        member_id=member_id,
        plan_id=plan_id,
        status="active",
        starts_at=now - timedelta(days=30),
        ends_at=now - timedelta(seconds=1),
        auto_renew=True,
    )
    session.add(membership)
    session.commit()
    monkeypatch.setenv(
        "MEMBERSHIP_PAYMENT_ENCRYPTION_KEY",
        b64encode(b"payment-method-encryption-key!!!").decode("ascii"),
    )

    result = run_auto_renewal_batch(
        session,
        FakeRenewalGateway([]),
        now=now,
    )
    state = get_member_auto_renewal(session, member_id, now=now)
    setup = create_member_payment_method_setup(session, member_id, now=now)

    assert result.expired_memberships == 1
    assert result.charges_started == 0
    assert state.first_renewal_due is True
    assert state.first_renewal_requires_member_action is True
    assert setup.plan_name == "Mensual"
    assert session.get(Membership, membership.id).status == "expired"


def test_inactive_plan_stops_auto_renewal_without_creating_a_charge(
    session: Session,
    seeded_ids: tuple[UUID, UUID, UUID],
) -> None:
    member_id, plan_id, payment_method_id = seeded_ids
    now = datetime.now(timezone.utc)
    _authorize_renewal(session, member_id, now=now)
    _set_up_conekta_method(session, payment_method_id)
    plan = session.get(Plan, plan_id)
    assert plan is not None
    plan.is_active = False
    session.add(plan)
    membership = Membership(
        member_id=member_id,
        plan_id=plan_id,
        status="active",
        starts_at=now - timedelta(days=30),
        ends_at=now - timedelta(seconds=1),
        auto_renew=True,
    )
    session.add(membership)
    session.commit()

    result = run_auto_renewal_batch(
        session,
        FakeRenewalGateway([]),
        now=now,
    )

    session.refresh(membership)
    assert result.expired_memberships == 1
    assert result.charges_started == 0
    assert membership.status == "expired"
    assert membership.auto_renew is False
    assert session.exec(select(PaymentAttempt)).all() == []
    blocked_event = session.exec(
        select(MembershipEvent).where(
            MembershipEvent.membership_id == membership.id,
            MembershipEvent.event_type == "auto_renewal_blocked",
        )
    ).one()
    assert blocked_event.event_metadata == {"reason": "plan_unavailable"}


def test_automatic_retries_follow_club_calendar_days_one_three_and_five(
    session: Session,
    seeded_ids: tuple[UUID, UUID, UUID],
) -> None:
    member_id, plan_id, payment_method_id = seeded_ids
    now = datetime.now(timezone.utc)
    due_at = now - timedelta(days=6)
    _authorize_renewal(session, member_id, now=now)
    _set_up_conekta_method(session, payment_method_id)
    membership = Membership(
        member_id=member_id,
        plan_id=plan_id,
        status="pending_payment",
        starts_at=due_at,
        ends_at=due_at + timedelta(days=30),
        auto_renew=True,
    )
    session.add(membership)
    session.flush()
    first_attempt = PaymentAttempt(
        membership_id=membership.id,
        payment_method_id=payment_method_id,
        method="card",
        provider="conekta",
        idempotency_key=f"auto-renewal:{membership.id}:attempt:1",
        request_fingerprint="a" * 64,
        attempt_number=1,
        amount_cents=50000,
        currency="MXN",
        status="failed",
        due_at=due_at,
        requested_at=due_at,
    )
    session.add(first_attempt)
    session.commit()
    gateway = FakeRenewalGateway(
        [
            ChargeOutcome(ChargeStatus.FAILED, failure_code="conekta_declined"),
            ChargeOutcome(ChargeStatus.FAILED, failure_code="conekta_declined"),
            ChargeOutcome(ChargeStatus.FAILED, failure_code="conekta_declined"),
        ]
    )

    for delay_days in (1, 3, 5):
        early = run_auto_renewal_batch(
            session,
            gateway,
            now=due_at + timedelta(days=delay_days) - timedelta(seconds=1),
        )
        due = run_auto_renewal_batch(
            session,
            gateway,
            now=due_at + timedelta(days=delay_days),
        )
        assert early.retries_started == 0
        assert due.retries_started == 1

    exhausted = run_auto_renewal_batch(
        session,
        gateway,
        now=due_at + timedelta(days=10),
    )
    attempts = session.exec(
        select(PaymentAttempt)
        .where(PaymentAttempt.membership_id == membership.id)
        .order_by(PaymentAttempt.attempt_number)
    ).all()
    assert exhausted.retries_started == 0
    assert [attempt.attempt_number for attempt in attempts] == [1, 2, 3, 4]
    assert [attempt.status for attempt in attempts] == ["failed"] * 4
    assert len(gateway.calls) == 3


def test_unknown_attempt_is_reconciled_without_creating_another_attempt(
    session: Session,
    seeded_ids: tuple[UUID, UUID, UUID],
) -> None:
    member_id, plan_id, payment_method_id = seeded_ids
    now = datetime.now(timezone.utc)
    due_at = now - timedelta(days=1)
    _authorize_renewal(session, member_id, now=now)
    _set_up_conekta_method(session, payment_method_id)
    membership = Membership(
        member_id=member_id,
        plan_id=plan_id,
        status="pending_payment",
        starts_at=due_at,
        ends_at=due_at + timedelta(days=30),
        auto_renew=True,
    )
    session.add(membership)
    session.flush()
    attempt = PaymentAttempt(
        membership_id=membership.id,
        payment_method_id=payment_method_id,
        method="card",
        provider="conekta",
        provider_order_id="ord_sandbox_unknown",
        idempotency_key=f"auto-renewal:{membership.id}:attempt:1",
        request_fingerprint="b" * 64,
        attempt_number=1,
        amount_cents=50000,
        currency="MXN",
        status="unknown",
        due_at=due_at,
        requested_at=now - timedelta(minutes=20),
    )
    session.add(attempt)
    session.add(
        MembershipEvent(
            membership_id=membership.id,
            event_type="renewal_payment_pending",
            to_status="pending_payment",
            actor_type="system",
            event_metadata={},
            occurred_at=due_at,
        )
    )
    session.commit()
    payment_method = session.get(PaymentMethod, payment_method_id)
    assert payment_method is not None
    payment_method.status = "inactive"
    session.add(payment_method)
    session.commit()
    gateway = FakeRenewalGateway(
        [
            ChargeOutcome(
                ChargeStatus.SUCCEEDED,
                provider_reference="ch_sandbox_paid",
                occurred_at=now,
                provider_order_id="ord_sandbox_unknown",
            )
        ]
    )

    result = run_auto_renewal_batch(session, gateway, now=now)
    replay = run_auto_renewal_batch(
        session,
        gateway,
        now=now + timedelta(minutes=5),
    )

    assert result.attempts_reconciled == 1
    assert replay.attempts_reconciled == 0
    assert len(gateway.calls) == 1
    assert session.get(Membership, membership.id).status == "active"
    assert session.get(PaymentAttempt, attempt.id).status == "succeeded"
    assert len(session.exec(select(PaymentAttempt)).all()) == 1
    assert len(session.exec(select(Payment)).all()) == 1


def test_late_processing_result_does_not_reopen_terminal_failed_attempt(
    session: Session,
    seeded_ids: tuple[UUID, UUID, UUID],
) -> None:
    member_id, plan_id, payment_method_id = seeded_ids
    now = datetime.now(timezone.utc)
    membership = Membership(
        member_id=member_id,
        plan_id=plan_id,
        status="pending_payment",
        starts_at=now,
        ends_at=now + timedelta(days=30),
    )
    session.add(membership)
    session.flush()
    attempt = PaymentAttempt(
        membership_id=membership.id,
        payment_method_id=payment_method_id,
        method="card",
        provider="conekta",
        provider_order_id="ord_sandbox_declined",
        idempotency_key="terminal-failure-test",
        request_fingerprint="c" * 64,
        attempt_number=1,
        amount_cents=50000,
        currency="MXN",
        status="failed",
        failure_code="conekta_declined",
        resolved_at=now,
        due_at=now,
    )
    session.add(attempt)
    session.commit()

    result = _apply_outcome(
        session,
        attempt,
        ChargeOutcome(
            ChargeStatus.PROCESSING,
            provider_order_id="ord_sandbox_declined",
        ),
        source="reconciliation",
        commit=True,
    )

    session.refresh(attempt)
    assert result.status == "failed"
    assert result.idempotent_replay is True
    assert attempt.failure_code == "conekta_declined"
    assert attempt.resolved_at.replace(tzinfo=timezone.utc) == now
