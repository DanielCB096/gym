import json
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest

from app.modules.memberships.conekta_checkout import (
    ConektaCheckoutConfigurationError,
    ConektaHostedCheckout,
    ConektaCheckoutSettings,
    ConektaCheckoutUnavailable,
)
from app.modules.memberships.models import PaymentAttempt


def _attempt() -> PaymentAttempt:
    return PaymentAttempt(
        id=uuid4(),
        membership_id=uuid4(),
        method="card",
        provider="conekta",
        idempotency_key="member-checkout-1",
        request_fingerprint="a" * 64,
        attempt_number=1,
        amount_cents=50000,
        currency="MXN",
        status="pending",
        due_at=datetime.now(timezone.utc),
    )


def _settings() -> ConektaCheckoutSettings:
    return ConektaCheckoutSettings(
        api_key="sandbox-test-key",
        success_url="https://gym.example.test/payments/return",
        failure_url="https://gym.example.test/payments/failed",
    )


def test_creates_hosted_order_with_internal_amount_and_idempotency() -> None:
    attempt = _attempt()
    captured: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["payload"] = request.read()
        return httpx.Response(
            200,
            json={
                "id": "ord_test_123",
                "amount": 50000,
                "currency": "MXN",
                "checkout": {"url": "https://pay.conektame.io/link/test"},
            },
        )

    gateway = ConektaHostedCheckout(_settings(), transport=httpx.MockTransport(handle))
    result = gateway.create_checkout(
        attempt,
        member_name="Ana López",
        member_email="ana@example.test",
        member_phone=None,
        plan_name="Mensual",
        success_url=_settings().success_url,
        failure_url=_settings().failure_url,
    )

    headers = captured["headers"]
    payload = json.loads(captured["payload"])
    assert headers["Authorization"] == "Bearer sandbox-test-key"
    assert headers["Idempotency-Key"] == str(attempt.id)
    assert payload["line_items"][0]["unit_price"] == attempt.amount_cents
    assert payload["currency"] == attempt.currency
    assert payload["checkout"]["type"] == "HostedPayment"
    assert payload["checkout"]["allowed_payment_methods"] == ["card"]
    assert payload["checkout"]["on_demand_enabled"] is False
    assert payload["metadata"]["payment_attempt_id"] == str(attempt.id)
    assert result.provider_order_id == "ord_test_123"
    assert result.checkout_url == "https://pay.conektame.io/link/test"


@pytest.mark.parametrize(
    "order",
    [
        {
            "id": "ord_test_123",
            "amount": 50001,
            "currency": "MXN",
            "checkout": {"url": "https://pay.conektame.io/link/test"},
        },
        {
            "id": "ord_test_123",
            "amount": 50000,
            "currency": "USD",
            "checkout": {"url": "https://pay.conektame.io/link/test"},
        },
        {
            "id": "ord_test_123",
            "amount": 50000,
            "currency": "MXN",
            "checkout": {"url": "http://pay.conektame.io/link/test"},
        },
    ],
)
def test_rejects_order_response_not_matching_requested_amount_currency_or_secure_url(
    order: dict[str, object],
) -> None:
    gateway = ConektaHostedCheckout(
        _settings(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=order)),
    )

    with pytest.raises(ConektaCheckoutUnavailable, match="no coincide"):
        gateway.create_checkout(
            _attempt(),
            member_name="Ana López",
            member_email="ana@example.test",
            member_phone=None,
            plan_name="Mensual",
            success_url=_settings().success_url,
            failure_url=_settings().failure_url,
        )


def test_does_not_expose_provider_error_response_body() -> None:
    gateway = ConektaHostedCheckout(
        _settings(),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(401, json={"secret": "sensitive-provider-response"})
        ),
    )

    with pytest.raises(ConektaCheckoutUnavailable) as error:
        gateway.create_checkout(
            _attempt(),
            member_name="Ana López",
            member_email="ana@example.test",
            member_phone=None,
            plan_name="Mensual",
            success_url=_settings().success_url,
            failure_url=_settings().failure_url,
        )
    assert "sensitive-provider-response" not in str(error.value)


def test_requires_sandbox_key_and_https_return_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONEKTA_MODE", "production")
    with pytest.raises(ConektaCheckoutConfigurationError, match="solo permite sandbox"):
        ConektaCheckoutSettings.from_env()

    monkeypatch.setenv("CONEKTA_MODE", "sandbox")
    monkeypatch.setenv("CONEKTA_SANDBOX_API_KEY", "test-key")
    monkeypatch.setenv("CONEKTA_SUCCESS_URL", "http://gym.example.test/return")
    monkeypatch.setenv("CONEKTA_FAILURE_URL", "https://gym.example.test/failure")
    with pytest.raises(ConektaCheckoutConfigurationError, match="HTTPS"):
        ConektaCheckoutSettings.from_env()
