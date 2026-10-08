from __future__ import annotations

import re
from dataclasses import replace

from app.domain.filings import (
    DocumentElement,
    Heading,
    ListElement,
    PageBreak,
    StructureContext,
    Table,
)

_PART_HEADING = re.compile(r"^\s*(Part\s+(?:I{1,3}|IV))\b(?:\s*[.\-:]?\s*(.*))?$", re.IGNORECASE)
_ITEM_HEADING = re.compile(r"^\s*(Item\s+\d+[A-Z]?)\s*[.\-:]?\s*(.*)$", re.IGNORECASE)


def extract_sec_structure(elements: tuple[DocumentElement, ...]) -> tuple[DocumentElement, ...]:
    part: str | None = None
    item: str | None = None
    section: str | None = None
    subsection: str | None = None
    structured: list[DocumentElement] = []

    for element in elements:
        if isinstance(element, Heading):
            part_match = _PART_HEADING.match(element.text)
            item_match = _ITEM_HEADING.match(element.text)
            if part_match:
                part_number = part_match.group(1).split()[-1].upper()
                part = f"Part {part_number}"
                item = None
                section = _clean_heading(part_match.group(2))
                subsection = None
            elif item_match:
                item_number = item_match.group(1).split()[-1].upper()
                item = f"Item {item_number}"
                section = _clean_heading(item_match.group(2))
                subsection = None
            elif item is not None:
                if element.level is not None and element.level >= 3:
                    subsection = element.text
                else:
                    section = element.text
                    subsection = None

        context: StructureContext | None = StructureContext(part, item, section, subsection)
        if context is not None and not any(
            (context.part, context.item, context.section, context.subsection)
        ):
            context = None
        structured.append(replace(element, structure_context=context))
    return tuple(structured)


def propagate_page_numbers(elements: tuple[DocumentElement, ...]) -> tuple[DocumentElement, ...]:
    current_page: int | None = None
    result: list[DocumentElement] = []
    for element in elements:
        if isinstance(element, PageBreak):
            if element.page_number is not None:
                current_page = element.page_number + 1
            result.append(element)
            continue

        element_page = element.provenance.page_number
        if element_page is not None:
            current_page = element_page
        elif current_page is not None:
            element = _set_element_page(element, current_page)
        result.append(element)
    return tuple(result)


def _set_element_page(element: DocumentElement, page_number: int) -> DocumentElement:
    provenance = replace(element.provenance, page_number=page_number)
    if isinstance(element, Table):
        rows = tuple(
            replace(
                row,
                provenance=replace(row.provenance, page_number=page_number),
                cells=tuple(
                    replace(cell, provenance=replace(cell.provenance, page_number=page_number))
                    for cell in row.cells
                ),
            )
            for row in element.rows
        )
        return replace(element, provenance=provenance, rows=rows)
    if isinstance(element, ListElement):
        items = tuple(
            replace(item, provenance=replace(item.provenance, page_number=page_number))
            for item in element.items
        )
        return replace(element, provenance=provenance, items=items)
    return replace(element, provenance=provenance)


def _clean_heading(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None
