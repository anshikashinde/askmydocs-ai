from __future__ import annotations

import re
from dataclasses import replace

from app.domain.filings import DocumentElement, Heading, StructureContext

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
                part = part_match.group(1).title()
                item = None
                section = _clean_heading(part_match.group(2))
                subsection = None
            elif item_match:
                item = item_match.group(1).title()
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


def _clean_heading(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None
