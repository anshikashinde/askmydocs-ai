from __future__ import annotations


class ApplicationError(Exception):
    """Raised for expected application-level failures."""


class DomainError(ApplicationError):
    """Raised for domain-level validation or business-rule violations."""

