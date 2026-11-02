import json

import httpx
import pytest

from app.modules.memberships.conekta_payment_methods import (
    ConektaPaymentMethodConfigurationError,
    ConektaPaymentMethodSettings,
    ConektaPaymentMethodUnavailable,
    ConektaPaymentMethods,
)


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
