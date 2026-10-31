"""Conekta hosted checkout client for one-time membership orders."""

from dataclasses import dataclass
import math
import os
from urllib.parse import urlsplit

import httpx

from app.modules.memberships.gateway import HostedCheckout
from app.modules.memberships.models import PaymentAttempt

API_URL = "https://api.conekta.io/orders"
API_VERSION = "application/vnd.conekta-v2.3.0+json"
DEFAULT_TIMEOUT_SECONDS = 15.0
CHECKOUT_NAME = "Pago de membresía"


class ConektaCheckoutConfigurationError(ValueError):
    pass


class ConektaCheckoutUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ConektaCheckoutSettings:
    api_key: str
    success_url: str
    failure_url: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> "ConektaCheckoutSettings":
        mode = (os.getenv("CONEKTA_MODE") or "sandbox").strip().lower()
        if mode != "sandbox":
            raise ConektaCheckoutConfigurationError(
                "La integración de checkout solo permite sandbox; producción aún no está habilitada."
            )
        api_key = (os.getenv("CONEKTA_SANDBOX_API_KEY") or "").strip()
        if not api_key:
            raise ConektaCheckoutConfigurationError(
                "CONEKTA_SANDBOX_API_KEY es necesaria para crear checkouts de sandbox."
            )
        success_url = _https_url("CONEKTA_SUCCESS_URL")
        failure_url = _https_url("CONEKTA_FAILURE_URL")
        try:
            timeout_seconds = float(os.getenv("CONEKTA_TIMEOUT_SECONDS", "15"))
        except ValueError as error:
            raise ConektaCheckoutConfigurationError(
                "CONEKTA_TIMEOUT_SECONDS debe ser un número mayor a cero."
            ) from error
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0 or timeout_seconds > 60:
            raise ConektaCheckoutConfigurationError(
                "CONEKTA_TIMEOUT_SECONDS debe estar entre 0 y 60 segundos."
            )
        return cls(
            api_key=api_key,
            success_url=success_url,
            failure_url=failure_url,
            timeout_seconds=timeout_seconds,
        )


def _https_url(environment_name: str) -> str:
    value = (os.getenv(environment_name) or "").strip()
    try:
        parsed = urlsplit(value)
    except ValueError as error:
        raise ConektaCheckoutConfigurationError(
            f"{environment_name} debe ser una URL HTTPS válida."
        ) from error
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ConektaCheckoutConfigurationError(
            f"{environment_name} debe ser una URL HTTPS válida."
        )
    return value


class ConektaHostedCheckout:
    provider = "conekta"

    def __init__(
        self,
        settings: ConektaCheckoutSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

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
        customer_info: dict[str, str] = {"name": member_name}
        if member_email:
            customer_info["email"] = member_email
        if member_phone:
            customer_info["phone"] = member_phone

        payload = {
            "checkout": {
                "allowed_payment_methods": ["card"],
                "failure_url": failure_url,
                "name": CHECKOUT_NAME,
                "on_demand_enabled": False,
                "success_url": success_url,
                "type": "HostedPayment",
            },
            "currency": attempt.currency,
            "customer_info": customer_info,
            "line_items": [
                {
                    "description": f"Membresía de gimnasio: {plan_name}",
                    "name": plan_name,
                    "quantity": 1,
                    "unit_price": attempt.amount_cents,
                }
            ],
            "metadata": {
                "membership_id": str(attempt.membership_id),
                "payment_attempt_id": str(attempt.id),
            },
            "pre_authorize": False,
        }
        headers = {
            "Accept": API_VERSION,
            "Accept-Language": "es",
            "Authorization": f"Bearer {self._settings.api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": str(attempt.id),
        }
        try:
            with httpx.Client(
                timeout=self._settings.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.post(API_URL, json=payload, headers=headers)
        except httpx.HTTPError as error:
            raise ConektaCheckoutUnavailable(
                "No se pudo contactar a Conekta; el mismo intento puede reintentarse."
            ) from error

        if not response.is_success:
            raise ConektaCheckoutUnavailable(
                f"Conekta rechazó la creación del checkout (HTTP {response.status_code})."
            )
        try:
            order = response.json()
        except ValueError as error:
            raise ConektaCheckoutUnavailable(
                "Conekta devolvió una respuesta de checkout que no es JSON válido."
            ) from error
        if not isinstance(order, dict):
            raise ConektaCheckoutUnavailable("Conekta devolvió una respuesta de orden inválida.")

        provider_order_id = order.get("id")
        checkout = order.get("checkout")
        amount = order.get("amount")
        currency = order.get("currency")
        checkout_url = checkout.get("url") if isinstance(checkout, dict) else None
        if (
            not isinstance(provider_order_id, str)
            or not provider_order_id
            or len(provider_order_id) > 160
            or type(amount) is not int
            or amount != attempt.amount_cents
            or currency != attempt.currency
            or not isinstance(checkout_url, str)
            or len(checkout_url) > 2048
            or not _is_https_checkout_url(checkout_url)
        ):
            raise ConektaCheckoutUnavailable(
                "La orden devuelta por Conekta no coincide con el intento solicitado."
            )
        return HostedCheckout(
            provider_order_id=provider_order_id,
            checkout_url=checkout_url,
        )


def _is_https_checkout_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
    )
