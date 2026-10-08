from __future__ import annotations

import re
from dataclasses import replace

from app.application.errors import NormalizationError
from app.domain.filings import (
    DocumentElement,
    Footnote,
    Heading,
    Link,
    ListElement,
    OtherStructuredElement,
    Paragraph,
    StructuredFiling,
    Table,
    XBRLFact,
)

_WHITESPACE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    """Collapse layout whitespace without rewriting lexical content."""
    return _WHITESPACE.sub(" ", value).strip()


def normalize_structured_filing(filing: StructuredFiling) -> StructuredFiling:
    try:
        return replace(
            filing,
            elements=tuple(_normalize_element(element) for element in filing.elements),
            xbrl_facts=tuple(_normalize_fact(fact) for fact in filing.xbrl_facts),
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise NormalizationError("Structured filing could not be normalized") from exc


def _normalize_element(element: DocumentElement) -> DocumentElement:
    if isinstance(element, (Heading, Paragraph, Footnote, Link, OtherStructuredElement)):
        return replace(element, text=normalize_text(element.text))
    if isinstance(element, Table):
        rows = tuple(
            replace(
                row,
                cells=tuple(replace(cell, text=normalize_text(cell.text)) for cell in row.cells),
            )
            for row in element.rows
        )
        return replace(
            element,
            caption=normalize_text(element.caption) if element.caption is not None else None,
            headers=tuple(normalize_text(header) for header in element.headers),
            rows=rows,
        )
    if isinstance(element, ListElement):
        return replace(
            element,
            items=tuple(replace(item, text=normalize_text(item.text)) for item in element.items),
        )
    return element


def _normalize_fact(fact: XBRLFact) -> XBRLFact:
    return replace(fact, normalized_value=normalize_text(fact.resolved_value))
