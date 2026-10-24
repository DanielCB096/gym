"""Errors of the billing module and their HTTP meaning.

The API layer maps each class to a status code. Messages are written for the
operator (Spanish) and never include PAC credentials or the raw XML.
"""


class BillingError(Exception):
    """Base class for every billing failure."""


class FiscalDataInvalid(BillingError):
    """The receptor data does not satisfy CFDI 4.0."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class InvoiceNotFound(BillingError):
    pass


class BillingMemberNotFound(BillingError):
    pass


class OriginNotFound(BillingError):
    pass


class OriginNotInvoiceable(BillingError):
    """The sale or payment exists but cannot be invoiced as it is."""

    def __init__(self, message: str, *, origin_type: str, origin_id: str) -> None:
        super().__init__(message)
        self.origin_type = origin_type
        self.origin_id = origin_id


class OriginAlreadyInvoiced(BillingError):
    def __init__(self, invoice_id: str) -> None:
        super().__init__("Esta operación ya tiene una factura vigente.")
        self.invoice_id = invoice_id


class InvoiceIdempotencyConflict(BillingError):
    """The idempotency key was reused with a different request."""


class InvoiceStateError(BillingError):
    """The invoice is not in a state that allows the requested action."""


class InvoiceNumberingError(BillingError):
    pass


class PacUnavailable(BillingError):
    """No PAC is configured (or the real integration is not implemented yet)."""


class PacRejected(BillingError):
    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class CancellationNotAllowed(BillingError):
    pass


__all__ = [
    "BillingError",
    "BillingMemberNotFound",
    "CancellationNotAllowed",
    "FiscalDataInvalid",
    "InvoiceIdempotencyConflict",
    "InvoiceNotFound",
    "InvoiceNumberingError",
    "InvoiceStateError",
    "OriginAlreadyInvoiced",
    "OriginNotFound",
    "OriginNotInvoiceable",
    "PacRejected",
    "PacUnavailable",
]
