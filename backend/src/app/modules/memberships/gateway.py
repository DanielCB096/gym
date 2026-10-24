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


@dataclass(frozen=True)
class VerifiedWebhook:
    provider: str
    provider_event_id: str
    event_type: str
    payload_sha256: str
    payment_attempt_id: UUID
    outcome: ChargeOutcome


class PaymentGateway(Protocol):
    def charge(self, attempt: PaymentAttempt, payment_method: PaymentMethod) -> ChargeOutcome:
        ...


class GatewayOutcomeUnknown(Exception):
    def __init__(self, failure_code: str = "outcome_unknown") -> None:
        super().__init__(failure_code)
        self.failure_code = failure_code