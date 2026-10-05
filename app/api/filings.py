from __future__ import annotations

import base64
from dataclasses import asdict

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.application.sec_filings import SECFilingService

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