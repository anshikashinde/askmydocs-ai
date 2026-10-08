from __future__ import annotations

import base64

import httpx
from fastapi.testclient import TestClient

from app.infrastructure.sec.client import SECClient
from app.main import app


def test_structured_filing_endpoint_returns_structure_and_raw_source(monkeypatch) -> None:
    raw_content = (
        b"<html><body><h1>Part I</h1><h2>Item 1. Business</h2><p>  A company. </p></body></html>"
    )
    requests: list[httpx.Request] = []
    responses = {
        "/files/company_tickers.json": {
            "0": {"cik_str": 1, "ticker": "EXM", "title": "Example Corp"}
        },
        "/submissions/CIK0000000001.json": {
            "cik": 1,
            "name": "Example Corp",
            "filings": {
                "recent": {
                    "accessionNumber": ["0000000001-25-000001"],
                    "filingDate": ["2025-02-01"],
                    "reportDate": ["2024-12-31"],
                    "form": ["10-K"],
                    "primaryDocument": ["example.htm"],
                }
            },
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path in responses:
            return httpx.Response(200, json=responses[request.url.path])
        if request.url.path.endswith("/example.htm"):
            return httpx.Response(200, content=raw_content, headers={"content-type": "text/html"})
        return httpx.Response(404)

    transport = httpx.Client(transport=httpx.MockTransport(handler))
    sec_client = SECClient("AskMyDocsAI/test test@example.com", client=transport)
    monkeypatch.setattr("app.main.SECClient", lambda **_kwargs: sec_client)

    with TestClient(app) as test_client:
        response = test_client.get("/filings/exm/structured?filing_type=10-K")

    assert response.status_code == 200
    payload = response.json()
    structured = payload["structured_filing"]
    assert structured["source_format"] == "html"
    assert [
        element["text"]
        for element in structured["elements"]
        if element["element_type"] == "heading"
    ] == [
        "Part I",
        "Item 1. Business",
    ]
    assert payload["raw_filing"]["filename"] == "example.htm"
    assert base64.b64decode(payload["raw_filing"]["content_base64"]) == raw_content
    assert payload["raw_filing"]["retrieved_at"].endswith("+00:00")
    assert len(requests) == 3
    transport.close()
