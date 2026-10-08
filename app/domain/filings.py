from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import ClassVar, TypeAlias


@dataclass(frozen=True)
class FilingReference:
    company_name: str
    ticker: str
    cik: str
    filing_type: str
    filing_date: str
    report_date: str | None
    accession_number: str
    primary_document: str
    source_url: str
    primary_document_description: str | None = None
    acceptance_datetime: str | None = None
    is_xbrl: bool | None = None
    is_inline_xbrl: bool | None = None
    size: int | None = None
    file_number: str | None = None


@dataclass(frozen=True)
class RawFiling:
    content: bytes
    source_url: str
    filename: str
    filing_reference: FilingReference
    retrieved_at: datetime
    content_type: str | None = None


class SourceFormat(StrEnum):
    HTML = "html"
    XHTML = "xhtml"
    INLINE_XBRL = "inline_xbrl"
    UNSUPPORTED = "unsupported"
    MALFORMED = "malformed"


@dataclass(frozen=True)
class Provenance:
    filing_id: str
    document_id: str
    element_id: str | None
    source_url: str
    document_order: int
    start_offset: int | None
    end_offset: int | None
    html_anchor: str | None
    page_number: int | None
    source_element_type: str


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: str = "warning"
    element_id: str | None = None


@dataclass(frozen=True)
class StructureContext:
    part: str | None = None
    item: str | None = None
    section: str | None = None
    subsection: str | None = None


@dataclass(frozen=True)
class DocumentElementBase:
    element_type: ClassVar[str] = "other_structured_element"


@dataclass(frozen=True)
class Heading(DocumentElementBase):
    element_type: ClassVar[str] = "heading"

    text: str
    level: int | None
    element_id: str | None
    document_order: int
    provenance: Provenance
    structure_context: StructureContext | None = None


@dataclass(frozen=True)
class Paragraph(DocumentElementBase):
    element_type: ClassVar[str] = "paragraph"

    text: str
    element_id: str | None
    document_order: int
    provenance: Provenance
    structure_context: StructureContext | None = None


@dataclass(frozen=True)
class TableCell(DocumentElementBase):
    element_type: ClassVar[str] = "table_cell"

    text: str
    row_index: int
    column_index: int
    colspan: int
    rowspan: int
    header_role: str | None
    element_id: str | None
    provenance: Provenance


@dataclass(frozen=True)
class TableRow(DocumentElementBase):
    element_type: ClassVar[str] = "table_row"

    cells: tuple[TableCell, ...]
    row_index: int
    element_id: str | None
    provenance: Provenance


@dataclass(frozen=True)
class Table(DocumentElementBase):
    element_type: ClassVar[str] = "table"

    caption: str | None
    headers: tuple[str, ...]
    rows: tuple[TableRow, ...]
    element_id: str | None
    document_order: int
    provenance: Provenance
    structure_context: StructureContext | None = None


@dataclass(frozen=True)
class ListItem(DocumentElementBase):
    element_type: ClassVar[str] = "list_item"

    text: str
    position: int
    element_id: str | None
    provenance: Provenance


@dataclass(frozen=True)
class ListElement(DocumentElementBase):
    element_type: ClassVar[str] = "list"

    ordered: bool
    items: tuple[ListItem, ...]
    element_id: str | None
    document_order: int
    provenance: Provenance
    structure_context: StructureContext | None = None
    parent_item_id: str | None = None


@dataclass(frozen=True)
class Footnote(DocumentElementBase):
    element_type: ClassVar[str] = "footnote"

    text: str
    reference_id: str | None
    element_id: str | None
    document_order: int
    provenance: Provenance
    structure_context: StructureContext | None = None


@dataclass(frozen=True)
class Link(DocumentElementBase):
    element_type: ClassVar[str] = "link"

    text: str
    href: str | None
    element_id: str | None
    document_order: int
    provenance: Provenance
    structure_context: StructureContext | None = None


@dataclass(frozen=True)
class PageBreak(DocumentElementBase):
    element_type: ClassVar[str] = "page_break"

    page_number: int | None
    element_id: str | None
    document_order: int
    provenance: Provenance
    structure_context: StructureContext | None = None


@dataclass(frozen=True)
class OtherStructuredElement(DocumentElementBase):
    element_type: ClassVar[str] = "other_structured_element"

    tag: str
    text: str
    element_id: str | None
    document_order: int
    provenance: Provenance
    structure_context: StructureContext | None = None


DocumentElement: TypeAlias = (
    Heading | Paragraph | Table | ListElement | Footnote | Link | PageBreak | OtherStructuredElement
)


@dataclass(frozen=True)
class XBRLDimension:
    dimension: str
    value: str
    member_type: str


@dataclass(frozen=True)
class XBRLContext:
    context_id: str
    entity_identifier: str | None
    period_instant: str | None
    period_start: str | None
    period_end: str | None
    dimensions: tuple[XBRLDimension, ...]
    provenance: Provenance


@dataclass(frozen=True)
class XBRLUnit:
    unit_id: str
    measures: tuple[str, ...]
    provenance: Provenance


@dataclass(frozen=True)
class XBRLContinuation:
    continuation_id: str | None
    continued_at: str | None
    text: str
    source_element_id: str | None
    provenance: Provenance


@dataclass(frozen=True)
class XBRLFact:
    fact_id: str | None
    name: str | None
    value: str
    resolved_value: str
    normalized_value: str | None
    fact_type: str
    context_ref: str | None
    unit_ref: str | None
    decimals: str | None
    scale: str | None
    sign: str | None
    format: str | None
    is_hidden: bool
    continued_at: str | None
    continuation_ids: tuple[str, ...]
    attributes: tuple[tuple[str, str], ...]
    source_element_id: str | None
    provenance: Provenance


@dataclass(frozen=True)
class StructuredFiling:
    raw_filing: RawFiling
    source_format: SourceFormat
    document_metadata: tuple[tuple[str, str], ...]
    elements: tuple[DocumentElement, ...]
    xbrl_facts: tuple[XBRLFact, ...]
    xbrl_contexts: tuple[XBRLContext, ...]
    xbrl_units: tuple[XBRLUnit, ...]
    continuations: tuple[XBRLContinuation, ...]
    validation_issues: tuple[ValidationIssue, ...]
