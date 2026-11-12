import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.mark.parametrize(
    ("method", "path", "detail"),
    [
        ("GET", "/admin/billing/summary", "La facturación no está disponible"),
        ("GET", "/member/invoices", "La facturación no está disponible"),
        ("GET", "/member/invoices/123/pdf", "La facturación no está disponible"),
        ("GET", "/member/fiscal-profile", "La facturación no está disponible"),
        (
            "GET",
            "/admin/members/123/fiscal-profile",
            "La facturación no está disponible",
        ),
        (
            "POST",
            "/member/membership/checkout",
            "Los pagos en línea no están disponibles",
        ),
        (
            "GET",
            "/member/membership/plans",
            "Los pagos en línea no están disponibles",
        ),
        (
            "POST",
            "/member/membership/auto-renewal",
            "Los pagos en línea no están disponibles",
        ),
        (
            "POST",
            "/member/membership/payment-method/setup/complete",
            "Los pagos en línea no están disponibles",
        ),
        (
            "POST",
            "/webhooks/conekta/membership",
            "Los pagos en línea no están disponibles",
        ),
    ],
)
def test_excluded_first_delivery_routes_are_hidden(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    detail: str,
) -> None:
    monkeypatch.setattr(main, "BILLING_ENABLED", False)
    monkeypatch.setattr(main, "ONLINE_PAYMENTS_ENABLED", False)

    response = TestClient(main.app).request(method, path)

    assert response.status_code == 404
    assert detail in response.json()["detail"]


def test_manual_member_payment_history_is_not_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "ONLINE_PAYMENTS_ENABLED", False)

    response = TestClient(main.app).get("/member/payments")

    assert response.status_code != 404
