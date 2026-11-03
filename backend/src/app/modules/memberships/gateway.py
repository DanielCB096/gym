from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.modules.memberships.models import PaymentAttempt, PaymentMethod


class ChargeStatus(StrEnum):
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ChargeOutcome:
    status: ChargeStatus
    provider_reference: str | None = None
    failure_code: str | None = None
    occurred_at: datetime | None = None
    provider_order_id: str | None = None


@dataclass(frozen=True)
class VerifiedWebhook:
    provider: str
    provider_event_id: str
    event_type: str
    payload_sha256: str
    payment_attempt_id: UUID
    outcome: ChargeOutcome


@dataclass(frozen=True)
class HostedCheckout:
    provider_order_id: str
    checkout_url: str


@dataclass(frozen=True)
class SavedPaymentReference:
    customer_id: str
    payment_source_id: str


@dataclass(frozen=True)
class RenewalOrder:
    provider_order_id: str


class PaymentGateway(Protocol):
    def charge(self, attempt: PaymentAttempt, payment_method: PaymentMethod) -> ChargeOutcome:
        ...


class HostedCheckoutGateway(Protocol):
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
        ...


class MemberRenewalGateway(Protocol):
    def save_card(
        self,
        *,
        member_name: str,
        member_email: str | None,
        member_phone: str | None,
        card_token: str,
        idempotency_key: str,
    ) -> SavedPaymentReference:
        ...

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
    ) -> RenewalOrder:
        ...


class GatewayOutcomeUnknown(Exception):
    def __init__(self, failure_code: str = "outcome_unknown") -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code