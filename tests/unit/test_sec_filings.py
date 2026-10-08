from __future__ import annotations

import httpx

from app.application.sec_filings import SECFilingService
from app.infrastructure.sec.client import SECClient


def test_fetch_latest_filing_preserves_raw_content_and_parallel_metadata() -> None:
    requests: list[httpx.Request] = []
    raw_content = b"<html>raw\x00filing</html>"
    ticker_payload = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
    submissions_payload = {
        "cik": 320193,
        "name": "Apple Inc.",
        "filings": {
            "recent": {
                "accessionNumber": ["0000320193-25-000079", "0000320193-25-000080"],
                "filingDate": ["2025-01-30", "2025-02-01"],
                "reportDate": ["2024-12-28", "2025-01-31"],
                "acceptanceDateTime": ["2025-01-30T16:30:00.000Z", "2025-02-01T10:00:00.000Z"],
                "form": ["10-K", "8-K"],
                "fileNumber": ["001-36743", "001-36743"],
                "size": [12345, 456],
                "isXBRL": [1, 0],
                "isInlineXBRL": [1, 0],
                "primaryDocument": ["aapl-20241228.htm", "aapl-20250201.htm"],
                "primaryDocDescription": ["10-K", "8-K"],
            }
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("company_tickers.json"):
            return httpx.Response(200, json=ticker_payload)
        if request.url.path.endswith("CIK0000320193.json"):
            return httpx.Response(200, json=submissions_payload)
        if request.url.path.endswith("/320193/000032019325000079/aapl-20241228.htm"):
            return httpx.Response(
                200,
                content=raw_content,
                headers={"content-type": "text/html; charset=utf-8"},
            )
        return httpx.Response(404)

    transport_client = httpx.Client(transport=httpx.MockTransport(handler))
    sec_client = SECClient(
        user_agent="AskMyDocsAI/test contact@example.com",
        timeout_seconds=12,
        client=transport_client,
    )

    reference, raw_filing = SECFilingService(sec_client).fetch_latest_filing("aapl", "10-k")

    assert reference.ticker == "AAPL"
    assert reference.cik == "0000320193"
    assert reference.filing_date == "2025-01-30"
    assert reference.report_date == "2024-12-28"
    assert reference.accession_number == "0000320193-25-000079"
    assert reference.primary_document == "aapl-20241228.htm"
    assert reference.is_xbrl is True
    assert reference.is_inline_xbrl is True
    assert reference.source_url == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20241228.htm"
    )
    assert raw_filing.content == raw_content
    assert raw_filing.content_type == "text/html; charset=utf-8"
    assert len(requests) == 3
    assert all(
        request.headers["user-agent"] == "AskMyDocsAI/test contact@example.com"
        for request in requests
    )
    assert all(request.headers["accept-encoding"] == "gzip, deflate" for request in requests)
    assert "company_tickers.json" in str(requests[0].url)
    assert requests[1].url.path == "/submissions/CIK0000320193.json"
    assert (
        requests[2].url.path == "/Archives/edgar/data/320193/000032019325000079/aapl-20241228.htm"
    )
    sec_client.close()
    transport_client.close()
