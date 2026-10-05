from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FilingReference:
    company_name: str
    ticker: str
    cik: str
    filing_type: str
    filing_date: str
    report_date: str | None
    accession_number: str
    primary_document: str
    source_url: str
    primary_document_description: str | None = None
    acceptance_datetime: str | None = None
    is_xbrl: bool | None = None
    is_inline_xbrl: bool | None = None
    size: int | None = None
    file_number: str | None = None


@dataclass(frozen=True)
class RawFiling:
    content: bytes
    source_url: str
    content_type: str | None = None