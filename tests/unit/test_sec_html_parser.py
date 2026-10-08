from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.errors import DocumentParseError, UnsupportedFormatError
from app.application.filing_normalization import normalize_structured_filing
from app.domain.filings import (
    FilingReference,
    Footnote,
    Heading,
    Link,
    ListElement,
    PageBreak,
    Paragraph,
    RawFiling,
    SourceFormat,
    Table,
)
from app.infrastructure.parsing.sec_html import SECHTMLParser


def make_raw_filing(content: bytes, content_type: str = "text/html") -> RawFiling:
    reference = FilingReference(
        company_name="Example Corp",
        ticker="EXM",
        cik="0000000001",
        filing_type="10-K",
        filing_date="2025-02-01",
        report_date="2024-12-31",
        accession_number="0000000001-25-000001",
        primary_document="example.htm",
        source_url="https://www.sec.gov/Archives/edgar/data/1/000000000125000001/example.htm",
    )
    return RawFiling(
        content=content,
        source_url=reference.source_url,
        filename=reference.primary_document,
        filing_reference=reference,
        retrieved_at=datetime.now(UTC),
        content_type=content_type,
    )


def test_parses_structured_html_and_retains_raw_source() -> None:
    source = b"""<!doctype html>
    <html lang="en"><head><title>Example 10-K</title>
    <meta name="description" content="annual filing"></head><body>
      <h1 id="company">Example Corp</h1>
    <h2>Part I</h2>
      <h2 id="risk-heading">Item 1A. Risk Factors</h2>
    <h3>Risk Disclosure</h3>
    <p id="risk-text">  Risks   remain <a id="risk-link" href="#footnote-1">1</a>.  </p>
      <table id="financial-table"><caption>Revenue</caption>
        <tr><th scope="col">Year</th><th scope="col" colspan="2">Revenue</th></tr>
        <tr><td rowspan="2">2024</td><td id="revenue">100</td></tr>
        <tr><td>90</td></tr>
      </table>
      <ol id="risk-list"><li id="risk-one">First risk<ul><li>Nested risk</li></ul></li><li>Second risk</li></ol>
      <div id="footnote-1" class="footnote">Footnote text</div>
      <div id="empty-anchor"></div>
      <span id="page-label">Example Corp | 2025 Form 10-K | 58</span>
    <hr style="page-break-after:always" />
    <p id="following-page">Following page.</p>
    <table id="layout-table" role="presentation"><tr><td></td><td></td></tr></table>
    <table id="unknown-table"><tr><td>Unclassified grid</td></tr></table>
      <script>this must not execute</script>
    </body></html>"""
    raw = make_raw_filing(source)

    structured = SECHTMLParser().parse(raw)

    assert structured.raw_filing is raw
    assert structured.source_format is SourceFormat.HTML
    assert ("title", "Example 10-K") in structured.document_metadata
    assert any(
        isinstance(element, Heading) and element.element_id == "risk-heading"
        for element in structured.elements
    )
    generated_heading = next(
        element
        for element in structured.elements
        if isinstance(element, Heading) and element.text == "Part I"
    )
    assert generated_heading.element_id.startswith("elem-")
    assert generated_heading.provenance.html_anchor is None
    assert all(element.element_id for element in structured.elements)
    second_parse = SECHTMLParser().parse(raw)
    assert [element.element_id for element in second_parse.elements] == [
        element.element_id for element in structured.elements
    ]
    paragraph = next(element for element in structured.elements if isinstance(element, Paragraph))
    assert paragraph.text == "  Risks   remain 1.  "
    assert paragraph.structure_context is not None
    assert paragraph.structure_context.part == "Part I"
    assert paragraph.structure_context.item == "Item 1A"
    assert paragraph.structure_context.section == "Risk Factors"
    assert paragraph.structure_context.subsection == "Risk Disclosure"
    assert paragraph.provenance.start_offset is None
    assert paragraph.provenance.source_url == raw.source_url
    assert all(
        element.provenance.source_url == raw.source_url
        and element.provenance.document_order == element.document_order
        for element in structured.elements
    )
    table = next(element for element in structured.elements if isinstance(element, Table))
    assert table.table_type.value == "data"
    assert table.caption == "Revenue"
    assert table.headers == ("Year", "Revenue")
    assert table.rows[0].cells[1].colspan == 2
    assert table.rows[1].cells[0].rowspan == 2
    assert table.rows[2].cells[0].column_index == 1
    lists = [element for element in structured.elements if isinstance(element, ListElement)]
    assert len(lists) == 2
    assert len(lists[0].items) == 2
    assert lists[0].items[0].text == "First risk"
    assert lists[1].parent_item_id == "risk-one"
    assert any(
        element.tag == "anchor" and element.element_id == "empty-anchor"
        for element in structured.elements
        if hasattr(element, "tag")
    )
    assert any(
        isinstance(element, Footnote) and element.element_id == "footnote-1"
        for element in structured.elements
    )
    assert any(
        isinstance(element, Link) and element.href == "#footnote-1"
        for element in structured.elements
    )
    page_break = next(element for element in structured.elements if isinstance(element, PageBreak))
    assert page_break.page_number == 58
    following_page = next(
        element for element in structured.elements if element.element_id == "following-page"
    )
    assert following_page.provenance.page_number == 59
    layout_table = next(
        element
        for element in structured.elements
        if isinstance(element, Table) and element.element_id == "layout-table"
    )
    assert layout_table.table_type.value == "layout"
    assert [len(row.cells) for row in layout_table.rows] == [2]
    assert [cell.text for cell in layout_table.rows[0].cells] == ["", ""]
    unknown_table = next(
        element
        for element in structured.elements
        if isinstance(element, Table) and element.element_id == "unknown-table"
    )
    assert unknown_table.table_type.value == "unknown"
    assert all(
        "this must not execute" not in getattr(element, "text", "")
        for element in structured.elements
    )

    normalized = normalize_structured_filing(structured)
    assert (
        next(element for element in normalized.elements if isinstance(element, Paragraph)).text
        == "Risks remain 1."
    )
    assert normalize_structured_filing(normalized) == normalized
    assert normalized.raw_filing.content == source


def test_nested_tables_remain_separate_and_link_to_parent() -> None:
    raw = make_raw_filing(
        b'<html><body><table id="outer"><tr><td>before<table id="inner" role="presentation">'
        b"<tr><td>nested cell</td></tr></table>after</td></tr></table></body></html>"
    )

    tables = [
        element for element in SECHTMLParser().parse(raw).elements if isinstance(element, Table)
    ]

    assert len(tables) == 2
    outer = next(table for table in tables if table.element_id == "outer")
    inner = next(table for table in tables if table.element_id == "inner")
    assert outer.rows[0].cells[0].text == "beforeafter"
    assert inner.parent_table_id == outer.element_id
    assert inner.rows[0].cells[0].text == "nested cell"


def test_duplicate_source_ids_get_distinct_internal_ids() -> None:
    raw = make_raw_filing(
        b'<html><body><p id="duplicate">First</p><p id="duplicate">Second</p></body></html>'
    )

    paragraphs = [
        element for element in SECHTMLParser().parse(raw).elements if isinstance(element, Paragraph)
    ]

    assert len(paragraphs) == 2
    assert paragraphs[0].element_id != paragraphs[1].element_id
    assert all(paragraph.provenance.html_anchor == "duplicate" for paragraph in paragraphs)
    assert all(paragraph.element_id.startswith("elem-") for paragraph in paragraphs)


def test_extracts_xbrl_facts_contexts_units_and_resolves_continuations() -> None:
    source = b"""<html><body>
      <ix:header><ix:hidden>
        <xbrli:context id="ctx-2024"><xbrli:entity><xbrli:identifier>0000000001</xbrli:identifier></xbrli:entity>
          <xbrli:period><xbrli:instant>2024-12-31</xbrli:instant></xbrli:period>
          <xbrli:scenario><xbrldi:explicitMember dimension="us-gaap:RegionAxis">us-gaap:USMember</xbrldi:explicitMember></xbrli:scenario>
        </xbrli:context>
        <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
        <ix:nonNumeric id="hidden-fact" name="dei:EntityRegistrantName" contextRef="ctx-2024">Example Corp</ix:nonNumeric>
      </ix:hidden></ix:header>
      <ix:nonFraction id="fact-1" name="us-gaap:Revenue" contextRef="ctx-2024" unitRef="usd"
        decimals="-6" scale="6" sign="-" format="ixt:num-dot-decimal">12</ix:nonFraction>
      <ix:nonNumeric id="fact-2" name="dei:EntityRegistrantName" contextRef="ctx-2024" continuedAt="cont-1">Example</ix:nonNumeric>
      <ix:continuation id="cont-1" continuedAt="cont-2"> Corp</ix:continuation>
      <ix:continuation id="cont-2"> Ltd</ix:continuation>
    </body></html>"""

    structured = SECHTMLParser().parse(make_raw_filing(source))

    assert structured.source_format is SourceFormat.INLINE_XBRL
    assert len(structured.xbrl_contexts) == 1
    assert structured.xbrl_contexts[0].period_instant == "2024-12-31"
    assert structured.xbrl_contexts[0].dimensions[0].value == "us-gaap:USMember"
    assert structured.xbrl_units[0].measures == ("iso4217:USD",)
    fact = next(fact for fact in structured.xbrl_facts if fact.fact_id == "fact-1")
    assert fact.value == "12"
    assert fact.decimals == "-6"
    assert fact.scale == "6"
    assert fact.sign == "-"
    assert fact.format == "ixt:num-dot-decimal"
    assert dict(fact.attributes)["name"] == "us-gaap:Revenue"
    assert fact.is_hidden is False
    hidden_fact = next(fact for fact in structured.xbrl_facts if fact.fact_id == "hidden-fact")
    assert hidden_fact.is_hidden is True
    continued_fact = next(fact for fact in structured.xbrl_facts if fact.fact_id == "fact-2")
    assert continued_fact.resolved_value == "Example Corp Ltd"
    assert continued_fact.continuation_ids == ("cont-1", "cont-2")
    normalized = normalize_structured_filing(structured)
    assert (
        next(fact for fact in normalized.xbrl_facts if fact.fact_id == "fact-1").normalized_value
        == "12"
    )
    assert structured.validation_issues == ()


@pytest.mark.parametrize(
    ("continuation_markup", "expected_code"),
    [
        (
            '<ix:continuation id="loop" continuedAt="loop">text</ix:continuation>',
            "circular_continuation",
        ),
        ("", "missing_continuation_target"),
        (
            '<ix:continuation id="loop">text</ix:continuation><ix:continuation id="loop">duplicate</ix:continuation>',
            "duplicate_continuation_id",
        ),
    ],
)
def test_reports_invalid_continuation_chains(
    continuation_markup: str,
    expected_code: str,
) -> None:
    source = (
        '<html><body><ix:nonNumeric id="fact" name="dei:Name" continuedAt="'
        'loop">value</ix:nonNumeric>'
        f"{continuation_markup}</body></html>"
    ).encode()

    structured = SECHTMLParser().parse(make_raw_filing(source))

    assert expected_code in {issue.code for issue in structured.validation_issues}


def test_rejects_unsupported_document_format() -> None:
    with pytest.raises(UnsupportedFormatError):
        SECHTMLParser().parse(make_raw_filing(b"%PDF-1.7", "application/pdf"))


def test_rejects_empty_document_as_malformed() -> None:
    with pytest.raises(DocumentParseError):
        SECHTMLParser().parse(make_raw_filing(b""))


def test_parses_xhtml_large_html_and_recoverable_markup() -> None:
    parser = SECHTMLParser()
    xhtml = make_raw_filing(
        b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p id="x">XHTML</p></body></html>',
        "application/xhtml+xml",
    )
    assert parser.parse(xhtml).source_format is SourceFormat.XHTML

    large = make_raw_filing(
        ("<html><body>" + "<p>Revenue 123.</p>" * 10000 + "</body></html>").encode()
    )
    large_result = parser.parse(large)
    assert sum(isinstance(element, Paragraph) for element in large_result.elements) == 10000

    malformed = make_raw_filing(b"<html><body><h1>Recovered heading<p>Recovered paragraph</body>")
    malformed_result = parser.parse(malformed)
    assert any(isinstance(element, Paragraph) for element in malformed_result.elements)
