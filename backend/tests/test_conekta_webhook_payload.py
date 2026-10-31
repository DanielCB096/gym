import json

import pytest

from app.modules.memberships.conekta_webhooks import (
    ConektaWebhookPayloadError,
    parse_conekta_webhook,
)


def _order_paid_payload() -> bytes:
    return json.dumps(
        {
            "id": "evt_sandbox_1",
            "type": "order.paid",
            "livemode": False,
            "created_at": 1793479500,
            "data": {
                "object": {
                    "id": "ord_sandbox_1",
                    "object": "order",
                    "livemode": False,
                    "amount": 50000,
                    "currency": "MXN",
                    "payment_status": "paid",
                    "charges": {
                        "data": [
                            {"id": "ch_declined", "status": "declined"},
                            {"id": "ch_paid", "status": "paid"},
                        ]
                    },
                }
            },
        },
        separators=(",", ":"),
    ).encode()


def test_parses_paid_order_using_its_successful_charge() -> None:
    event = parse_conekta_webhook(_order_paid_payload())

    assert event.provider_event_id == "evt_sandbox_1"
    assert event.event_type == "order.paid"
    assert event.provider_order_id == "ord_sandbox_1"
    assert event.amount_cents == 50000
    assert event.currency == "MXN"
    assert event.outcome is not None
    assert event.outcome.status.value == "succeeded"
    assert event.outcome.provider_reference == "ch_paid"
    assert event.outcome.occurred_at is not None


def test_rejects_live_order_even_if_other_fields_match() -> None:
    payload = json.loads(_order_paid_payload())
    payload["livemode"] = True

    with pytest.raises(ConektaWebhookPayloadError, match="sandbox"):
        parse_conekta_webhook(json.dumps(payload).encode())


def test_rejects_paid_event_without_paid_status() -> None:
    payload = json.loads(_order_paid_payload())
    payload["data"]["object"]["payment_status"] = "pending_payment"

    with pytest.raises(ConektaWebhookPayloadError, match="estado paid"):
        parse_conekta_webhook(json.dumps(payload).encode())


def test_maps_declined_charge_to_failed_outcome() -> None:
    payload = {
        "id": "evt_declined",
        "type": "charge.created",
        "livemode": False,
        "data": {
            "object": {
                "id": "ch_declined",
                "object": "charge",
                "livemode": False,
                "order_id": "ord_sandbox_1",
                "amount": 50000,
                "currency": "MXN",
                "status": "declined",
            }
        },
    }

    event = parse_conekta_webhook(json.dumps(payload).encode())

    assert event.outcome is not None
    assert event.outcome.status.value == "failed"
    assert event.outcome.failure_code == "conekta_declined"


def test_ignores_non_payment_state_events() -> None:
    payload = {
        "id": "evt_created",
        "type": "charge.created",
        "livemode": False,
        "data": {
            "object": {
                "id": "ch_pending",
                "object": "charge",
                "livemode": False,
                "order_id": "ord_sandbox_1",
                "amount": 50000,
                "currency": "MXN",
                "status": "pending",
            }
        },
    }

    assert parse_conekta_webhook(json.dumps(payload).encode()).outcome is None
