from __future__ import annotations


class ApplicationError(Exception):
    """Raised for expected application-level failures."""


class DomainError(ApplicationError):
    """Raised for domain-level validation or business-rule violations."""


class ResourceNotFoundError(ApplicationError):
    """Raised when a requested company or filing cannot be found."""


class UpstreamServiceError(ApplicationError):
    """Raised when an external service fails or returns invalid data."""

