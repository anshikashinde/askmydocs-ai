from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.application.filing_normalization import normalize_structured_filing
from app.domain.filings import FilingReference, Heading, PageBreak, RawFiling, SourceFormat, Table
from app.infrastructure.parsing.sec_html import SECHTMLParser


def test_apple_2025_filing_structure_survives_phase_1a() -> None:
    response_path = os.getenv("ASKMYDOCS_APPLE_10K_RESPONSE")
    if response_path is None:
        pytest.skip(
            "Set ASKMYDOCS_APPLE_10K_RESPONSE to the SEC response JSON for the Apple 2025 10-K"
        )

    response = json.loads(Path(response_path).read_text())
    reference = FilingReference(**response["filing"])
    raw_filing = RawFiling(
        content=base64.b64decode(response["raw_content_base64"]),
        source_url=reference.source_url,
        filename=reference.primary_document,
        filing_reference=reference,
        retrieved_at=datetime.now(UTC),
        content_type=response.get("content_type"),
    )

    structured = normalize_structured_filing(SECHTMLParser().parse(raw_filing))
    headings = [element for element in structured.elements if isinstance(element, Heading)]

    assert structured.source_format is SourceFormat.INLINE_XBRL
    assert raw_filing.content == structured.raw_filing.content
    assert any(heading.text.startswith("PART I") for heading in headings)
    assert any(heading.text.startswith("Item 1A.") for heading in headings)
    assert any(isinstance(element, Table) for element in structured.elements)
    assert any(isinstance(element, PageBreak) for element in structured.elements)
    assert structured.xbrl_facts
    assert structured.xbrl_contexts
    assert structured.xbrl_units
    assert structured.continuations
    assert any(fact.continuation_ids for fact in structured.xbrl_facts)
    assert normalize_structured_filing(structured) == structured
