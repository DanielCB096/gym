"""Errors of the finance module and their HTTP meaning.

The API layer maps each class to a status code. Messages are written for the
operator (Spanish) and never expose internal identifiers that are not already
visible in the panel.
"""


class FinanceError(Exception):
    """Base class for every reconciliation failure."""


class BankAccountNotFound(FinanceError):
    pass


class BankMovementNotFound(FinanceError):
    pass


class DuplicateBankAccount(FinanceError):
    """Another account already uses that display name."""


class InvalidBankData(FinanceError):
    """The account or movement data does not satisfy the expected format."""


class InvalidImportBatch(FinanceError):
    """A statement row is invalid; the batch is rejected as a whole."""


class BankMovementStateError(FinanceError):
    """The movement is not in a state that allows the requested action."""


class MatchCandidateNotFound(FinanceError):
    """The selected internal payment, sale or return does not exist."""


class CandidateUnavailable(FinanceError):
    """The internal movement was already reconciled against another line."""


class InvalidMatch(FinanceError):
    """The candidate cannot be linked to this bank movement."""


__all__ = [
    "BankAccountNotFound",
    "BankMovementNotFound",
    "BankMovementStateError",
    "CandidateUnavailable",
    "DuplicateBankAccount",
    "FinanceError",
    "InvalidBankData",
    "InvalidImportBatch",
    "InvalidMatch",
    "MatchCandidateNotFound",
]
