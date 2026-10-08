from __future__ import annotations

import re
import threading
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx

from app.application.sec_gateway import SECGatewayError
from app.domain.filings import FilingReference, RawFiling

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"


class SECClientError(SECGatewayError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SECClient:
    def __init__(
        self,
        user_agent: str,
        timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._user_agent = user_agent.strip()
        self._timeout_seconds = timeout_seconds
        self._client = client or httpx.Client()
        self._owns_client = client is None
        self._company_tickers: dict[str, Any] | None = None
        self._request_lock = threading.Lock()
        self._last_request_at = 0.0

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_company_tickers(self) -> dict[str, Any]:
        if self._company_tickers is None:
            payload = self._get_json(COMPANY_TICKERS_URL)
            if not isinstance(payload, dict):
                raise SECClientError("SEC ticker data was not a JSON object")
            self._company_tickers = payload
        return self._company_tickers

    def get_submissions(self, cik: str) -> dict[str, Any]:
        if not re.fullmatch(r"\d{10}", cik):
            raise SECClientError("CIK must contain exactly 10 digits")
        payload = self._get_json(SUBMISSIONS_URL.format(cik=cik))
        if not isinstance(payload, dict):
            raise SECClientError("SEC submissions data was not a JSON object")
        return payload

    def build_archive_url(
        self,
        cik: str,
        accession_number: str,
        primary_document: str,
    ) -> str:
        if not re.fullmatch(r"\d{10}", cik):
            raise SECClientError("CIK must contain exactly 10 digits")
        accession = accession_number.replace("-", "")
        if not re.fullmatch(r"\d+", accession):
            raise SECClientError("Accession number contains invalid characters")
        if not primary_document or "/" in primary_document or "\\" in primary_document:
            raise SECClientError("Primary document contains invalid characters")

        cik_without_zeroes = str(int(cik))
        return ARCHIVE_URL.format(
            cik=cik_without_zeroes,
            accession=accession,
            document=quote(primary_document, safe=""),
        )

    def download_filing(self, filing_reference: FilingReference) -> RawFiling:
        source_url = self.build_archive_url(
            filing_reference.cik,
            filing_reference.accession_number,
            filing_reference.primary_document,
        )
        if source_url != filing_reference.source_url:
            raise SECClientError("Filing reference source URL does not match SEC archive metadata")
        response = self._get(source_url)
        return RawFiling(
            content=response.content,
            source_url=source_url,
            filename=filing_reference.primary_document,
            filing_reference=filing_reference,
            retrieved_at=datetime.now(UTC),
            content_type=response.headers.get("content-type"),
        )

    def _get_json(self, url: str) -> Any:
        response = self._get(url)
        try:
            return response.json()
        except ValueError as exc:
            raise SECClientError("SEC returned invalid JSON") from exc

    def _get(self, url: str) -> httpx.Response:
        if not self._user_agent:
            raise SECClientError("SEC_USER_AGENT must be configured")
        self._wait_for_rate_limit()
        try:
            response = self._client.get(
                url,
                headers={
                    "User-Agent": self._user_agent,
                    "Accept-Encoding": "gzip, deflate",
                },
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            raise SECClientError(
                f"SEC returned HTTP {exc.response.status_code}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.TimeoutException as exc:
            raise SECClientError("SEC request timed out") from exc
        except httpx.RequestError as exc:
            raise SECClientError("SEC request failed") from exc

    def _wait_for_rate_limit(self) -> None:
        with self._request_lock:
            delay = 0.11 - (time.monotonic() - self._last_request_at)
            if delay > 0:
                time.sleep(delay)
            self._last_request_at = time.monotonic()
