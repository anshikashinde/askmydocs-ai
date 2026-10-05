from __future__ import annotations

from typing import Any, Protocol

from app.domain.filings import RawFiling


class SECGatewayError(Exception):
    """Raised when the SEC integration cannot provide valid data."""


class SECGateway(Protocol):
    def get_company_tickers(self) -> dict[str, Any]: ...

    def get_submissions(self, cik: str) -> dict[str, Any]: ...

    def download_filing(
        self,
        cik: str,
        accession_number: str,
        primary_document: str,
    ) -> RawFiling: ...