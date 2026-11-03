"""Conekta sandbox operations for saving and charging a member card."""

import base64
from dataclasses import dataclass
import math
import os
import re
from urllib.parse import urlsplit

import httpx

from app.modules.memberships.gateway import ChargeOutcome, ChargeStatus
from app.modules.memberships.models import Membership, PaymentAttempt, PaymentMethod, Plan
from sqlmodel import Session

from app.modules.memberships.payment_method_security import decrypt_payment_reference

API_URL = "https://api.conekta.io"
API_VERSION = "application/vnd.conekta-v2.3.0+json"
DEFAULT_TIMEOUT_SECONDS = 15.0
_PROVIDER_ID = re.compile(r"^(cus|src|ord|ch)_[A-Za-z0-9_-]{1,156}$")


class ConektaPaymentMethodConfigurationError(ValueError):
    pass


class ConektaPaymentMethodUnavailable(RuntimeError):
    def __init__(self, message: str, *, outcome_unknown: bool = True) -> None:
        super().__init__(message)
        self.outcome_unknown = outcome_unknown


@dataclass(frozen=True)
class ConektaPaymentMethodSettings:
    api_key: str
    public_key: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> "ConektaPaymentMethodSettings":
        mode = (os.getenv("CONEKTA_MODE") or "sandbox").strip().lower()
        if mode != "sandbox":
            raise ConektaPaymentMethodConfigurationError(
                "La captura y el cobro de renovación solo están habilitados en sandbox."
            )
        api_key = (os.getenv("CONEKTA_SANDBOX_API_KEY") or "").strip()
        public_key = (os.getenv("CONEKTA_SANDBOX_PUBLIC_KEY") or "").strip()
        if not api_key.startswith("key_test_") or not public_key.startswith("key_test_"):
            raise ConektaPaymentMethodConfigurationError(
                "Configura únicamente llaves key_test_ de Conekta; las llaves productivas están deshabilitadas."
            )
        try:
            timeout_seconds = float(os.getenv("CONEKTA_TIMEOUT_SECONDS", "15"))
        except ValueError as error:
            raise ConektaPaymentMethodConfigurationError(
                "CONEKTA_TIMEOUT_SECONDS debe ser un número mayor a cero."
            ) from error
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0 or timeout_seconds > 60:
            raise ConektaPaymentMethodConfigurationError(
                "CONEKTA_TIMEOUT_SECONDS debe estar entre 0 y 60 segundos."
            )
        return cls(api_key, public_key, timeout_seconds)


@dataclass(frozen=True)
class ConektaSavedCard:
    customer_id: str
    payment_source_id: str


@dataclass(frozen=True)
class ConektaRenewalOrder:
    provider_order_id: str


class ConektaPaymentMethods:
    def __init__(
        self,
        settings: ConektaPaymentMethodSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    def save_card(
        self,
        *,
        member_name: str,
        member_email: str | None,
        member_phone: str | None,
        card_token: str,
        idempotency_key: str,
    ) -> ConektaSavedCard:
        customer: dict[str, str] = {"name": member_name}
        if member_email:
            customer["email"] = member_email
        if member_phone:
            customer["phone"] = member_phone
        customer_result = self._post(
            "/customers",
            customer,
            f"{idempotency_key}:customer",
        )
        customer_id = customer_result.get("id")
        if (
            ("livemode" in customer_result and customer_result.get("livemode") is not False)
            or not _valid_provider_id(customer_id, "cus")
        ):
            raise ConektaPaymentMethodUnavailable(
                "Conekta no devolvió un cliente válido de sandbox."
            )

        source_result = self._post(
            f"/customers/{customer_id}/payment_sources",
            {"type": "card", "token_id": card_token},
            f"{idempotency_key}:source",
        )
        payment_source_id = source_result.get("id")
        if (
            ("livemode" in source_result and source_result.get("livemode") is not False)
            or not _valid_provider_id(payment_source_id, "src")
            or source_result.get("type") != "card"
            or source_result.get("parent_id") != customer_id
            or source_result.get("payment_source_status") != "active"
        ):
            raise ConektaPaymentMethodUnavailable(
                "Conekta no devolvió un método de pago activo asociado al cliente."
            )
        return ConektaSavedCard(customer_id, payment_source_id)

    def create_renewal_order(
        self,
        *,
        customer_id: str,
        payment_source_id: str,
        plan_name: str,
        amount_cents: int,
        currency: str,
        membership_id: str,
        payment_attempt_id: str,
    ) -> ConektaRenewalOrder:
        result = self._post(
            "/orders",
            {
                "currency": currency,
                "customer_info": {"customer_id": customer_id},
                "line_items": [
                    {
                        "name": f"Renovación de membresía: {plan_name}",
                        "unit_price": amount_cents,
                        "quantity": 1,
                    }
                ],
                "charges": [
                    {
                        "payment_method": {
                            "type": "card",
                            "payment_source_id": payment_source_id,
                        }
                    }
                ],
                "metadata": {
                    "membership_id": membership_id,
                    "payment_attempt_id": payment_attempt_id,
                },
            },
            payment_attempt_id,
        )
        provider_order_id = result.get("id")
        if (
            ("livemode" in result and result.get("livemode") is not False)
            or not _valid_provider_id(provider_order_id, "ord")
            or type(result.get("amount")) is not int
            or result["amount"] != amount_cents
            or result.get("currency") != currency
        ):
            raise ConektaPaymentMethodUnavailable(
                "La orden de renovación devuelta por Conekta no coincide con el importe solicitado."
            )
        return ConektaRenewalOrder(provider_order_id)

    def get_renewal_order_outcome(
        self,
        *,
        provider_order_id: str,
        amount_cents: int,
        currency: str,
    ) -> ChargeOutcome:
        if not _valid_provider_id(provider_order_id, "ord"):
            raise ConektaPaymentMethodUnavailable(
                "La referencia de orden de Conekta no es válida."
            )
        result = self._request("GET", f"/orders/{provider_order_id}")
        if (
            ("livemode" in result and result.get("livemode") is not False)
            or result.get("id") != provider_order_id
            or type(result.get("amount")) is not int
            or result["amount"] != amount_cents
            or result.get("currency") != currency
        ):
            raise ConektaPaymentMethodUnavailable(
                "La orden consultada en Conekta no coincide con el intento."
            )

        charges = result.get("charges")
        charge_data = charges.get("data") if isinstance(charges, dict) else None
        charge_items = (
            [charge for charge in charge_data if isinstance(charge, dict)]
            if isinstance(charge_data, list)
            else []
        )
        paid_charge_ids = [
            charge.get("id")
            for charge in charge_items
            if charge.get("status") == "paid"
            and _valid_provider_id(charge.get("id"), "ch")
        ]
        order_status = result.get("status")
        payment_status = result.get("payment_status") or order_status
        if payment_status == "paid":
            if len(paid_charge_ids) != 1:
                raise ConektaPaymentMethodUnavailable(
                    "La orden pagada no contiene exactamente un cargo verificable."
                )
            return ChargeOutcome(
                status=ChargeStatus.SUCCEEDED,
                provider_reference=paid_charge_ids[0],
                provider_order_id=provider_order_id,
            )

        declined_charge_ids = [
            charge.get("id")
            for charge in charge_items
            if charge.get("status") == "declined"
            and _valid_provider_id(charge.get("id"), "ch")
        ]
        all_charges_declined = bool(charge_items) and (
            len(declined_charge_ids) == len(charge_items)
        )
        if (
            payment_status == "declined"
            or order_status in {"declined", "expired", "canceled", "cancelled"}
            or all_charges_declined
        ):
            return ChargeOutcome(
                status=ChargeStatus.FAILED,
                provider_reference=declined_charge_ids[0] if declined_charge_ids else None,
                failure_code="conekta_declined",
                provider_order_id=provider_order_id,
            )
        return ChargeOutcome(
            status=ChargeStatus.PROCESSING,
            provider_order_id=provider_order_id,
        )

    def _post(
        self,
        path: str,
        payload: dict[str, object],
        idempotency_key: str,
    ) -> dict[str, object]:
        return self._request(
            "POST",
            path,
            payload=payload,
            idempotency_key=idempotency_key,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        basic_token = base64.b64encode(f"{self._settings.api_key}:".encode("utf-8")).decode("ascii")
        headers = {
            "Accept": API_VERSION,
            "Accept-Language": "es",
            "Authorization": f"Basic {basic_token}",
            "Content-Type": "application/json",
        }
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        try:
            with httpx.Client(
                timeout=self._settings.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.request(
                    method,
                    f"{API_URL}{path}",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError as error:
            raise ConektaPaymentMethodUnavailable(
                "No se pudo confirmar la operación con Conekta; el mismo flujo debe reintentarse."
            ) from error
        if not response.is_success:
            raise ConektaPaymentMethodUnavailable(
                f"Conekta rechazó la operación de renovación (HTTP {response.status_code}).",
                outcome_unknown=(
                    method != "POST"
                    or response.status_code in {408, 409, 429}
                    or response.status_code >= 500
                ),
            )
        try:
            result = response.json()
        except ValueError as error:
            raise ConektaPaymentMethodUnavailable(
                "Conekta devolvió una respuesta que no es JSON válido."
            ) from error
        if not isinstance(result, dict):
            raise ConektaPaymentMethodUnavailable("Conekta devolvió una respuesta inválida.")
        return result


class ConektaRecurringPaymentGateway:
    def __init__(self, session: Session, methods: ConektaPaymentMethods) -> None:
        self._session = session
        self._methods = methods

    def charge(self, attempt: PaymentAttempt, payment_method: PaymentMethod) -> ChargeOutcome:
        if payment_method.provider != "conekta":
            raise ConektaPaymentMethodUnavailable(
                "El método de pago no pertenece a Conekta.",
                outcome_unknown=False,
            )
        if attempt.provider_order_id is not None:
            try:
                return self._methods.get_renewal_order_outcome(
                    provider_order_id=attempt.provider_order_id,
                    amount_cents=attempt.amount_cents,
                    currency=attempt.currency,
                )
            except ConektaPaymentMethodUnavailable:
                return ChargeOutcome(
                    status=ChargeStatus.UNKNOWN,
                    failure_code="conekta_reconciliation_unavailable",
                    provider_order_id=attempt.provider_order_id,
                )

        customer_id, payment_source_id = decrypt_payment_reference(
            payment_method.member_id,
            payment_method.encrypted_provider_token,
        )
        membership = self._session.get(Membership, attempt.membership_id)
        plan = self._session.get(Plan, membership.plan_id) if membership is not None else None
        if membership is None or plan is None:
            raise ConektaPaymentMethodUnavailable(
                "No se encontró el plan asociado al intento.",
                outcome_unknown=False,
            )
        try:
            order = self._methods.create_renewal_order(
                customer_id=customer_id,
                payment_source_id=payment_source_id,
                plan_name=plan.name,
                amount_cents=attempt.amount_cents,
                currency=attempt.currency,
                membership_id=str(membership.id),
                payment_attempt_id=str(attempt.id),
            )
        except ConektaPaymentMethodUnavailable as error:
            return ChargeOutcome(
                status=(
                    ChargeStatus.UNKNOWN
                    if error.outcome_unknown
                    else ChargeStatus.FAILED
                ),
                failure_code=(
                    "conekta_outcome_unknown"
                    if error.outcome_unknown
                    else "conekta_rejected"
                ),
            )
        return ChargeOutcome(
            status=ChargeStatus.PROCESSING,
            provider_order_id=order.provider_order_id,
        )


def _valid_provider_id(value: object, prefix: str) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(f"{prefix}_")
        and _PROVIDER_ID.fullmatch(value) is not None
    )


def member_payment_method_url_from_env() -> str:
    value = (os.getenv("MEMBER_PAYMENT_METHOD_URL") or "").strip()
    try:
        parsed = urlsplit(value)
    except ValueError as error:
        raise ConektaPaymentMethodConfigurationError(
            "MEMBER_PAYMENT_METHOD_URL debe ser una URL válida."
        ) from error
    local_http = (
        parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1"}
        and (os.getenv("CONEKTA_MODE") or "sandbox").strip().lower() == "sandbox"
    )
    if (
        not parsed.hostname
        or (parsed.scheme != "https" and not local_http)
        or parsed.username
        or parsed.password
        or parsed.path.rstrip("/") != "/member/payment-method"
        or parsed.query
        or parsed.fragment
    ):
        raise ConektaPaymentMethodConfigurationError(
            "MEMBER_PAYMENT_METHOD_URL debe ser HTTPS y apuntar a /member/payment-method."
        )
    return value.rstrip("/")
