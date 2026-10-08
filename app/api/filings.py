from __future__ import annotations

import base64
from dataclasses import asdict

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.application.errors import DocumentParseError, UnsupportedFormatError
from app.application.sec_filings import SECFilingService
from app.application.structured_filings import FilingDocumentProcessingService

router = APIRouter(prefix="/filings", tags=["filings"])


@router.get("/{ticker}")
def get_filing(
    ticker: str,
    request: Request,
    filing_type: str = Query(..., pattern="^(10-K|10-Q)$"),
) -> JSONResponse:
    reference, raw_filing = SECFilingService(request.app.state.sec_client).fetch_latest_filing(
        ticker,
        filing_type,
    )
    return JSONResponse(
        content={
            "filing": asdict(reference),
            "raw_content_base64": base64.b64encode(raw_filing.content).decode("ascii"),
            "content_type": raw_filing.content_type,
        }
    )


@router.get("/{ticker}/structured")
def get_structured_filing(
    ticker: str,
    request: Request,
    filing_type: str = Query(..., pattern="^(10-K|10-Q)$"),
) -> JSONResponse:
    try:
        structured = FilingDocumentProcessingService(
            SECFilingService(request.app.state.sec_client),
            request.app.state.filing_parser,
        ).fetch_and_parse(ticker, filing_type)
    except UnsupportedFormatError as exc:
        return JSONResponse(status_code=415, content={"detail": str(exc)})
    except DocumentParseError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    structured_payload = asdict(structured)
    structured_payload["elements"] = [
        {**element_data, "element_type": element.element_type}
        for element_data, element in zip(
            structured_payload["elements"],
            structured.elements,
            strict=True,
        )
    ]
    raw_filing = structured_payload.pop("raw_filing")
    raw_content = raw_filing.pop("content")
    raw_filing["retrieved_at"] = structured.raw_filing.retrieved_at.isoformat()
    raw_filing["content_base64"] = base64.b64encode(raw_content).decode("ascii")
    return JSONResponse(
        content={
            "structured_filing": structured_payload,
            "raw_filing": raw_filing,
        }
    )
