import json
from base64 import b64encode
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlmodel import Session

from app.modules.memberships.conekta_payment_methods import (
    ConektaPaymentMethodConfigurationError,
    ConektaPaymentMethodSettings,
    ConektaPaymentMethodUnavailable,
    ConektaPaymentMethods,
    ConektaRecurringPaymentGateway,
)
from app.modules.memberships.gateway import ChargeStatus
from app.modules.memberships.models import Membership, PaymentAttempt, PaymentMethod, Plan
from app.modules.memberships.payment_method_security import encrypt_payment_reference


def test_sandbox_card_and_renewal_order_use_idempotent_provider_calls() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/customers":
            return httpx.Response(200, json={"id": "cus_test_1", "livemode": False})
        if request.url.path == "/customers/cus_test_1/payment_sources":
            return httpx.Response(
                200,
                json={
                    "id": "src_test_1",
                    "type": "card",
                    "parent_id": "cus_test_1",
                    "payment_source_status": "active",
                    "livemode": False,
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "ord_test_1",
                "amount": 50000,
                "currency": "MXN",
                "livemode": False,
            },
        )

    gateway = ConektaPaymentMethods(
        ConektaPaymentMethodSettings("key_test_private", "key_test_public"),
        transport=httpx.MockTransport(handle),
    )
    saved = gateway.save_card(
        member_name="Ana Demo",
        member_email="ana@example.test",
        member_phone=None,
        card_token="tok_sandbox_1",
        idempotency_key="setup-flow-id",
    )
    order = gateway.create_renewal_order(
        customer_id=saved.customer_id,
        payment_source_id=saved.payment_source_id,
        plan_name="Mensual",
        amount_cents=50000,
        currency="MXN",
        membership_id="membership-id",
        payment_attempt_id="attempt-id",
    )

    assert saved.customer_id == "cus_test_1"
    assert saved.payment_source_id == "src_test_1"
    assert order.provider_order_id == "ord_test_1"
    assert [request.url.path for request in requests] == [
        "/customers",
        "/customers/cus_test_1/payment_sources",
        "/orders",
    ]
    assert requests[0].headers["Idempotency-Key"] == "setup-flow-id:customer"
    assert requests[1].headers["Idempotency-Key"] == "setup-flow-id:source"
    assert requests[2].headers["Idempotency-Key"] == "attempt-id"
    assert requests[1].headers["Authorization"].startswith("Basic ")
    assert "tok_sandbox_1" in requests[1].content.decode("utf-8")
    order_payload = json.loads(requests[2].content)
    assert order_payload["line_items"][0]["unit_price"] == 50000
    assert order_payload["charges"][0]["payment_method"]["payment_source_id"] == "src_test_1"
    assert order_payload["metadata"]["payment_attempt_id"] == "attempt-id"


def test_sandbox_settings_reject_live_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONEKTA_MODE", "sandbox")
    monkeypatch.setenv("CONEKTA_SANDBOX_API_KEY", "key_live_private")
    monkeypatch.setenv("CONEKTA_SANDBOX_PUBLIC_KEY", "key_test_public")
    with pytest.raises(ConektaPaymentMethodConfigurationError, match="key_test_"):
        ConektaPaymentMethodSettings.from_env()


def test_payment_method_gateway_rejects_live_provider_response() -> None:
    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": "cus_live_1", "livemode": True},
        )

    gateway = ConektaPaymentMethods(
        ConektaPaymentMethodSettings("key_test_private", "key_test_public"),
        transport=httpx.MockTransport(handle),
    )
    with pytest.raises(ConektaPaymentMethodUnavailable, match="sandbox"):
        gateway.save_card(
            member_name="Ana Demo",
            member_email=None,
            member_phone=None,
            card_token="tok_sandbox_1",
            idempotency_key="setup-flow-id",
        )


def test_recurring_gateway_reconciles_the_original_idempotent_order(
    session: Session,
    seeded_ids,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    member_id, plan_id, payment_method_id = seeded_ids
    encryption_key = b"payment-method-encryption-key!!!"
    monkeypatch.setenv(
        "MEMBERSHIP_PAYMENT_ENCRYPTION_KEY",
        b64encode(encryption_key).decode("ascii"),
    )
    payment_method = session.get(PaymentMethod, payment_method_id)
    assert payment_method is not None
    payment_method.provider = "conekta"
    payment_method.encrypted_provider_token = encrypt_payment_reference(
        member_id,
        customer_id="cus_sandbox_1",
        payment_source_id="src_sandbox_1",
    )
    session.add(payment_method)
    plan = session.get(Plan, plan_id)
    assert plan is not None
    now = datetime.now(timezone.utc)
    membership = Membership(
        member_id=member_id,
        plan_id=plan_id,
        status="pending_payment",
        starts_at=now,
        ends_at=now + timedelta(days=30),
        auto_renew=True,
    )
    session.add(membership)
    session.flush()
    attempt = PaymentAttempt(
        membership_id=membership.id,
        payment_method_id=payment_method.id,
        method="card",
        provider="conekta",
        idempotency_key="renewal-attempt-reconcile",
        request_fingerprint="c" * 64,
        attempt_number=1,
        amount_cents=plan.price_cents,
        currency=plan.currency,
        status="processing",
        due_at=now,
    )
    session.add(attempt)
    session.commit()

    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "id": "ord_sandbox_renewal_1",
                    "amount": plan.price_cents,
                    "currency": plan.currency,
                    "livemode": False,
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "ord_sandbox_renewal_1",
                "amount": plan.price_cents,
                "currency": plan.currency,
                "payment_status": "paid",
                "charges": {
                    "data": [{"id": "ch_sandbox_renewal_1", "status": "paid"}]
                },
                "livemode": False,
            },
        )

    methods = ConektaPaymentMethods(
        ConektaPaymentMethodSettings("key_test_private", "key_test_public"),
        transport=httpx.MockTransport(handle),
    )
    gateway = ConektaRecurringPaymentGateway(session, methods)
    created = gateway.charge(attempt, payment_method)
    attempt.provider_order_id = created.provider_order_id
    payment_method.status = "inactive"
    monkeypatch.setattr(
        "app.modules.memberships.conekta_payment_methods.decrypt_payment_reference",
        lambda *_: pytest.fail("reconciliation must not decrypt an inactive payment method"),
    )
    reconciled = gateway.charge(attempt, payment_method)

    assert created.status == ChargeStatus.PROCESSING
    assert reconciled.status == ChargeStatus.SUCCEEDED
    assert reconciled.provider_reference == "ch_sandbox_renewal_1"
    assert [request.method for request in requests] == ["POST", "GET"]
    assert requests[0].headers["Idempotency-Key"] == str(attempt.id)
    assert requests[1].url.path == "/orders/ord_sandbox_renewal_1"


def test_reconciliation_waits_if_order_has_a_pending_charge_after_a_decline() -> None:
    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "ord_sandbox_1",
                "amount": 50000,
                "currency": "MXN",
                "payment_status": "unpaid",
                "status": "pending_payment",
                "charges": {
                    "data": [
                        {"id": "ch_declined", "status": "declined"},
                        {"id": "ch_pending", "status": "pending"},
                    ]
                },
                "livemode": False,
            },
        )

    methods = ConektaPaymentMethods(
        ConektaPaymentMethodSettings("key_test_private", "key_test_public"),
        transport=httpx.MockTransport(handle),
    )

    outcome = methods.get_renewal_order_outcome(
        provider_order_id="ord_sandbox_1",
        amount_cents=50000,
        currency="MXN",
    )

    assert outcome.status == ChargeStatus.PROCESSING


def test_reconciliation_rejects_a_paid_order_with_a_different_amount() -> None:
    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "ord_sandbox_1",
                "amount": 1,
                "currency": "MXN",
                "payment_status": "paid",
                "charges": {
                    "data": [{"id": "ch_sandbox_1", "status": "paid"}]
                },
                "livemode": False,
            },
        )

    methods = ConektaPaymentMethods(
        ConektaPaymentMethodSettings("key_test_private", "key_test_public"),
        transport=httpx.MockTransport(handle),
    )
    with pytest.raises(ConektaPaymentMethodUnavailable, match="no coincide"):
        methods.get_renewal_order_outcome(
            provider_order_id="ord_sandbox_1",
            amount_cents=50000,
            currency="MXN",
        )
