from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.application.errors import ResourceNotFoundError, UpstreamServiceError
from app.application.sec_gateway import SECGateway, SECGatewayError
from app.domain.filings import FilingReference, RawFiling

SUPPORTED_FILING_TYPES = {"10-K", "10-Q"}


class SECFilingService:
    def __init__(self, client: SECGateway) -> None:
        self._client = client

    def fetch_latest_filing(
        self, ticker: str, filing_type: str
    ) -> tuple[FilingReference, RawFiling]:
        normalized_ticker = ticker.strip().upper()
        normalized_form = filing_type.strip().upper()
        if normalized_form not in SUPPORTED_FILING_TYPES:
            raise ValueError("filing_type must be 10-K or 10-Q")
        if not normalized_ticker:
            raise ValueError("ticker must not be empty")

        try:
            ticker_record = self._find_ticker(normalized_ticker)
            cik = _format_cik(ticker_record.get("cik_str"))
            submissions = self._client.get_submissions(cik)
            company_name = submissions.get("name")
            submission_cik = _format_cik(submissions.get("cik"))
            if not isinstance(company_name, str) or not company_name.strip():
                raise SECGatewayError("SEC submissions response is missing company name")
            if submission_cik != cik:
                raise SECGatewayError("SEC submissions CIK does not match ticker lookup")
            filing = self._find_recent_filing(submissions, normalized_form)
            source_url = self._client.build_archive_url(
                cik,
                filing["accessionNumber"],
                filing["primaryDocument"],
            )
            reference = FilingReference(
                company_name=company_name.strip(),
                ticker=normalized_ticker,
                cik=cik,
                filing_type=normalized_form,
                filing_date=filing["filingDate"],
                report_date=_optional_str(filing.get("reportDate")),
                accession_number=filing["accessionNumber"],
                primary_document=filing["primaryDocument"],
                source_url=source_url,
                primary_document_description=_optional_str(filing.get("primaryDocDescription")),
                acceptance_datetime=_optional_str(filing.get("acceptanceDateTime")),
                is_xbrl=_optional_bool(filing.get("isXBRL")),
                is_inline_xbrl=_optional_bool(filing.get("isInlineXBRL")),
                size=_optional_int(filing.get("size")),
                file_number=_optional_str(filing.get("fileNumber")),
            )
            raw_filing = self._client.download_filing(reference)
        except ResourceNotFoundError:
            raise
        except SECGatewayError as exc:
            raise UpstreamServiceError(str(exc)) from exc

        return reference, raw_filing

    def _find_ticker(self, ticker: str) -> Mapping[str, Any]:
        records = self._client.get_company_tickers()
        # The SEC states that ticker/CIK association files are periodically updated and does not guarantee their accuracy or scope.
        for record in records.values():
            if isinstance(record, Mapping) and str(record.get("ticker", "")).upper() == ticker:
                return record
        raise ResourceNotFoundError(f"Ticker '{ticker}' was not found")

    @staticmethod
    def _find_recent_filing(submissions: Mapping[str, Any], filing_type: str) -> dict[str, Any]:
        filings = submissions.get("filings")
        recent = filings.get("recent") if isinstance(filings, Mapping) else None
        if not isinstance(recent, Mapping):
            raise SECGatewayError("SEC submissions response is missing recent filings")

        accessions = recent.get("accessionNumber")
        if not isinstance(accessions, list):
            raise SECGatewayError("SEC recent filings are missing accession numbers")
        for field, values in recent.items():
            if isinstance(values, list) and len(values) != len(accessions):
                raise SECGatewayError(
                    f"SEC recent filing array '{field}' has an inconsistent length"
                )

        forms = recent.get("form")
        filing_dates = recent.get("filingDate")
        primary_documents = recent.get("primaryDocument")
        if not isinstance(forms, list):
            raise SECGatewayError("SEC recent filings are missing form values")
        if not isinstance(filing_dates, list):
            raise SECGatewayError("SEC recent filings are missing filing dates")
        if not isinstance(primary_documents, list):
            raise SECGatewayError("SEC recent filings are missing primary documents")

        for index, form in enumerate(forms):
            if form != filing_type:
                continue
            accession = accessions[index]
            filing_date = filing_dates[index]
            primary_document = primary_documents[index]
            if not all(
                isinstance(value, str) and value
                for value in (accession, filing_date, primary_document)
            ):
                raise SECGatewayError("SEC recent filing is missing required metadata")
            return {
                field: values[index] for field, values in recent.items() if isinstance(values, list)
            }
        raise ResourceNotFoundError(f"No recent {filing_type} filing was found")


def _format_cik(value: Any) -> str:
    try:
        cik_number = int(value)
    except (TypeError, ValueError) as exc:
        raise SECGatewayError("SEC response contains an invalid CIK") from exc
    if cik_number <= 0:
        raise SECGatewayError("SEC response contains an invalid CIK")
    return f"{cik_number:010d}"


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
