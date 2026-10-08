from __future__ import annotations

from typing import Protocol

from app.application.errors import ValidationError
from app.application.filing_normalization import normalize_structured_filing
from app.application.sec_filings import SECFilingService
from app.domain.filings import RawFiling, StructuredFiling


class FilingDocumentParser(Protocol):
    def parse(self, raw_filing: RawFiling) -> StructuredFiling: ...


class FilingDocumentProcessingService:
    def __init__(self, filing_service: SECFilingService, parser: FilingDocumentParser) -> None:
        self._filing_service = filing_service
        self._parser = parser

    def fetch_and_parse(self, ticker: str, filing_type: str) -> StructuredFiling:
        _reference, raw_filing = self._filing_service.fetch_latest_filing(ticker, filing_type)
        structured = self._parser.parse(raw_filing)
        structured = normalize_structured_filing(structured)
        _validate_structured_filing(structured)
        return structured


def _validate_structured_filing(structured: StructuredFiling) -> None:
    raw_filing = structured.raw_filing
    if not isinstance(raw_filing.content, bytes) or not raw_filing.content:
        raise ValidationError("Structured filing must retain non-empty source bytes")
    if raw_filing.source_url != raw_filing.filing_reference.source_url:
        raise ValidationError("Raw filing source URL does not match its filing reference")

    previous_order = 0
    for element in structured.elements:
        if element.document_order <= previous_order:
            raise ValidationError("Structured document elements are not in strict source order")
        if element.provenance.document_order != element.document_order:
            raise ValidationError("Element provenance order does not match document order")
        if element.provenance.source_url != raw_filing.source_url:
            raise ValidationError("Element provenance does not reference the source filing")
        previous_order = element.document_order
