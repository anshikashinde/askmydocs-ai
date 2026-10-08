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


@pytest.mark.parametrize(
    ("ticker", "environment_variable"),
    [
        ("AAPL", "ASKMYDOCS_APPLE_10K_RESPONSE"),
        ("MSFT", "ASKMYDOCS_MICROSOFT_10K_RESPONSE"),
    ],
)
def test_issuer_10k_structure_survives_phase_1a(
    ticker: str,
    environment_variable: str,
) -> None:
    response_path = os.getenv(environment_variable)
    if response_path is None:
        pytest.skip(f"Set {environment_variable} to the SEC response JSON for the {ticker} 10-K")

    response = json.loads(Path(response_path).read_text())
    source = response.get("raw_filing", response)
    reference_data = source.get("filing_reference", source.get("filing"))
    content_base64 = source.get("content_base64", source.get("raw_content_base64"))
    reference = FilingReference(**reference_data)
    raw_filing = RawFiling(
        content=base64.b64decode(content_base64),
        source_url=reference.source_url,
        filename=reference.primary_document,
        filing_reference=reference,
        retrieved_at=datetime.now(UTC),
        content_type=source.get("content_type"),
    )

    structured = normalize_structured_filing(SECHTMLParser().parse(raw_filing))
    headings = [element for element in structured.elements if isinstance(element, Heading)]

    assert reference.ticker == ticker
    assert structured.validation_issues == ()
    assert structured.source_format is SourceFormat.INLINE_XBRL
    assert raw_filing.content == structured.raw_filing.content
    assert any(heading.text.upper().startswith("PART I") for heading in headings)
    assert any(heading.text.lower().startswith("item 1a.") for heading in headings)
    if ticker == "MSFT":
        assert any(heading.text.lower().startswith("item 7.") for heading in headings)
        assert any(heading.text.lower().startswith("item 8.") for heading in headings)
        assert any(
            element.structure_context
            and element.structure_context.part == "Part II"
            and element.structure_context.item == "Item 8"
            and isinstance(element, Table)
            and len(element.rows) >= 40
            for element in structured.elements
        )
    else:
        for part in ("Part I", "Part II", "Part III", "Part IV"):
            assert any(heading.text.upper().startswith(part.upper()) for heading in headings)
    assert any(isinstance(element, Table) for element in structured.elements)
    assert all(element.element_id for element in structured.elements)
    assert all(
        element.provenance.filing_id == reference.accession_number
        and element.provenance.document_id == reference.primary_document
        and element.provenance.source_url == reference.source_url
        and element.provenance.document_order == element.document_order
        for element in structured.elements
    )
    assert any(isinstance(element, PageBreak) for element in structured.elements)
    assert structured.xbrl_facts
    assert structured.xbrl_contexts
    assert structured.xbrl_units
    assert structured.continuations
    assert any(fact.continuation_ids for fact in structured.xbrl_facts)
    assert normalize_structured_filing(structured) == structured
