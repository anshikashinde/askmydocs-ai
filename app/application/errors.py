from __future__ import annotations


class ApplicationError(Exception):
    """Raised for expected application-level failures."""


class DomainError(ApplicationError):
    """Raised for domain-level validation or business-rule violations."""


class ResourceNotFoundError(ApplicationError):
    """Raised when a requested company or filing cannot be found."""


class UpstreamServiceError(ApplicationError):
    """Raised when an external service fails or returns invalid data."""


class FilingProcessingError(ApplicationError):
    """Base class for deterministic filing-processing failures."""


class DocumentParseError(FilingProcessingError):
    """Raised when a filing cannot be parsed into a structured document."""


class UnsupportedFormatError(DocumentParseError):
    """Raised when the SEC primary document format is unsupported."""


class NormalizationError(FilingProcessingError):
    """Raised when a structured filing cannot be normalized safely."""


class StructureExtractionError(FilingProcessingError):
    """Raised when SEC document structure cannot be represented consistently."""


class XBRLParsingError(FilingProcessingError):
    """Raised when XBRL data cannot be parsed safely."""


class XBRLContinuationError(XBRLParsingError):
    """Raised when a continuation chain cannot be resolved safely."""


class ValidationError(FilingProcessingError):
    """Raised when a structured filing violates required invariants."""
