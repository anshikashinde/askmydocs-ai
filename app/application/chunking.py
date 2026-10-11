from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import TypeAlias

from app.application.chunking_config import ChunkingSettings
from app.application.chunking_ports import Tokenizer
from app.application.errors import ChunkingError
from app.domain.chunks import (
    Chunk,
    ChunkMetadata,
    ChunkProvenance,
    ChunkRelationships,
    ChunkSourceReference,
    ChunkType,
    generate_chunk_id,
)
from app.domain.filings import (
    DocumentElement,
    Footnote,
    Heading,
    Link,
    ListElement,
    ListItem,
    OtherStructuredElement,
    PageBreak,
    Paragraph,
    Provenance,
    StructureContext,
    StructuredFiling,
    Table,
    TableCell,
    TableRow,
)


@dataclass(frozen=True)
class ChunkingResult:
    chunks: tuple[Chunk, ...]
    input_element_count: int
    token_counts: tuple[int, ...]


@dataclass(frozen=True)
class _Candidate:
    chunk_type: ChunkType
    content: str
    elements: tuple[DocumentElement, ...]
    context: StructureContext | None
    structured_content: DocumentElement | None = None
    table_id: str | None = None
    parent_table_id: str | None = None
    table_chunk_index: int | None = None
    total_table_chunks: int | None = None
    list_id: str | None = None
    list_chunk_index: int | None = None
    total_list_chunks: int | None = None


@dataclass(frozen=True)
class _TextUnit:
    elements: tuple[DocumentElement, ...]
    context: StructureContext | None
    overlap_barrier_before: bool = False


SourceElement: TypeAlias = tuple[DocumentElement | TableRow | TableCell | ListItem, Provenance]


class StructuredFilingChunker:
    def __init__(self, settings: ChunkingSettings, tokenizer: Tokenizer) -> None:
        self._settings = settings
        self._tokenizer = tokenizer
        self._configuration_key = json.dumps(
            {
                "target_chunk_tokens": settings.target_chunk_tokens,
                "max_chunk_tokens": settings.max_chunk_tokens,
                "min_chunk_tokens": settings.min_chunk_tokens,
                "overlap_tokens": settings.overlap_tokens,
                "chunking_version": settings.chunking_version,
                "tokenizer_encoding": settings.tokenizer_encoding,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def chunk(self, filing: StructuredFiling) -> ChunkingResult:
        self._validate_input(filing)
        candidates = self._build_candidates(filing)
        self._validate_candidate_sources(filing, candidates)

        chunks: list[Chunk] = []
        for position, candidate in enumerate(candidates):
            source_references = self._source_references(candidate.elements)
            provenance = self._make_provenance(source_references)
            metadata = self._make_metadata(filing, candidate, provenance)
            source_ids = provenance.source_element_ids
            chunk_id = generate_chunk_id(
                filing_id=provenance.filing_id,
                document_id=provenance.document_id,
                source_element_ids=source_ids,
                source_position=position,
                chunking_version=self._settings.chunking_version,
                configuration_key=self._configuration_key,
                content=candidate.content,
            )
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    chunk_type=candidate.chunk_type,
                    content=candidate.content,
                    metadata=metadata,
                    provenance=provenance,
                    relationships=ChunkRelationships(),
                    chunking_version=self._settings.chunking_version,
                    structured_content=candidate.structured_content,
                    xbrl_fact_ids=self._related_xbrl_fact_ids(filing, source_references),
                )
            )

        linked_chunks = self._link_chunks(chunks)
        self._validate_chunks(filing, linked_chunks)
        token_counts = tuple(self._token_count(chunk.content) for chunk in linked_chunks)
        return ChunkingResult(linked_chunks, len(filing.elements), token_counts)

    def _validate_input(self, filing: StructuredFiling) -> None:
        reference = filing.raw_filing.filing_reference
        if filing.raw_filing.source_url != reference.source_url:
            raise ChunkingError("Raw filing source URL does not match filing identity")
        previous_order = 0
        for element in filing.elements:
            if element.document_order <= previous_order:
                raise ChunkingError("Structured document elements are not in strict source order")
            provenance = element.provenance
            if provenance.document_order != element.document_order:
                raise ChunkingError("Source element provenance order is inconsistent")
            if provenance.filing_id != reference.accession_number:
                raise ChunkingError("Source element filing identity does not match the filing")
            if provenance.source_url != filing.raw_filing.source_url:
                raise ChunkingError("Source element URL does not match the filing")
            if provenance.document_id and provenance.document_id != reference.primary_document:
                raise ChunkingError("Source element document identity does not match the filing")
            previous_order = element.document_order

    def _validate_candidate_sources(
        self,
        filing: StructuredFiling,
        candidates: tuple[_Candidate, ...],
    ) -> None:
        expected_ids: set[str] = set()
        for element in filing.elements:
            if isinstance(element, PageBreak):
                continue
            for source_element, provenance in self._element_sources(element):
                source_id = source_element.element_id
                if source_id is None:
                    raise ChunkingError(
                        "A chunkable Phase 1A source element is missing its element ID"
                    )
                if provenance.element_id != source_id:
                    raise ChunkingError("Source element ID does not match its provenance ID")
                expected_ids.add(source_id)

        actual_ids = {
            element_id
            for candidate in candidates
            for _element, provenance in self._element_sources_for_candidate(candidate)
            if (element_id := provenance.element_id) is not None
        }
        if expected_ids != actual_ids:
            missing_ids = sorted(expected_ids - actual_ids)
            raise ChunkingError(f"Chunking omitted source element IDs: {missing_ids}")

    def _build_candidates(self, filing: StructuredFiling) -> tuple[_Candidate, ...]:
        candidates: list[_Candidate] = []
        units: list[_TextUnit] = []
        pending_headings: list[Heading] = []
        active_context: StructureContext | None = None
        overlap_barrier = False

        def flush_narrative() -> None:
            nonlocal active_context
            if pending_headings:
                headings = tuple(pending_headings)
                pending_headings.clear()
                units.append(_TextUnit(headings, active_context, overlap_barrier))
            if units:
                candidates.extend(self._pack_narrative(tuple(units)))
                units.clear()
            active_context = None

        for element in filing.elements:
            if isinstance(element, PageBreak):
                overlap_barrier = True
                continue
            if isinstance(element, Heading):
                if (pending_headings or units) and element.structure_context != active_context:
                    flush_narrative()
                pending_headings.append(element)
                active_context = element.structure_context
                continue
            if isinstance(element, Paragraph):
                if (pending_headings or units) and element.structure_context != active_context:
                    flush_narrative()
                current_context = element.structure_context
                heading_elements = tuple(pending_headings)
                pending_headings.clear()
                units.append(
                    _TextUnit(
                        (*heading_elements, element),
                        current_context,
                        overlap_barrier,
                    )
                )
                overlap_barrier = False
                active_context = current_context
                continue

            flush_narrative()
            if isinstance(element, Table):
                candidates.extend(self._table_candidates(element))
            elif isinstance(element, ListElement):
                candidates.extend(self._list_candidates(element))
            else:
                candidates.append(self._other_candidate(element))
            overlap_barrier = False

        flush_narrative()
        return tuple(candidates)

    def _pack_narrative(self, units: tuple[_TextUnit, ...]) -> list[_Candidate]:
        output: list[_Candidate] = []
        current: list[_TextUnit] = []

        def flush() -> None:
            if current:
                elements = tuple(element for unit in current for element in unit.elements)
                content = self._render_elements(elements)
                output.append(
                    _Candidate(
                        ChunkType.NARRATIVE,
                        content,
                        elements,
                        current[0].context,
                    )
                )
                current.clear()

        for unit in units:
            unit_text = self._render_elements(unit.elements)
            if self._token_count(unit_text) > self._settings.max_chunk_tokens:
                flush()
                pieces = list(
                    self._tokenizer.split_text(unit_text, self._settings.max_chunk_tokens)
                )
                if len(pieces) > 1 and self._token_count(pieces[-1]) < (
                    self._settings.min_chunk_tokens
                ):
                    merged_tail = pieces[-2] + pieces[-1]
                    if self._token_count(merged_tail) <= self._settings.max_chunk_tokens:
                        pieces[-2:] = [merged_tail]
                output.extend(
                    _Candidate(ChunkType.NARRATIVE, piece, unit.elements, unit.context)
                    for piece in pieces
                )
                continue
            proposed = [*current, unit]
            proposed_text = self._render_units(proposed)
            if current and self._token_count(proposed_text) > self._settings.target_chunk_tokens:
                previous = tuple(current)
                flush()
                overlap = self._overlap_units(previous, unit)
                if self._token_count(self._render_units([*overlap, unit])) > (
                    self._settings.max_chunk_tokens
                ):
                    overlap = ()
                current.extend(overlap)
            if current and self._token_count(self._render_units([*current, unit])) > (
                self._settings.max_chunk_tokens
            ):
                flush()
            current.append(unit)

        if (
            current
            and self._token_count(self._render_units(current)) < (self._settings.min_chunk_tokens)
            and output
        ):
            previous_candidate = output[-1]
            last_elements = tuple(
                current_element for unit in current for current_element in unit.elements
            )
            merged_elements = (*previous_candidate.elements, *last_elements)
            merged_content = self._render_elements(merged_elements)
            if self._token_count(merged_content) <= self._settings.max_chunk_tokens:
                output[-1] = replace(
                    previous_candidate, content=merged_content, elements=merged_elements
                )
                current.clear()
        flush()
        return output

    def _overlap_units(
        self,
        previous: tuple[_TextUnit, ...],
        next_unit: _TextUnit,
    ) -> tuple[_TextUnit, ...]:
        if self._settings.overlap_tokens == 0 or next_unit.overlap_barrier_before:
            return ()
        next_page = self._page_start(next_unit.elements)
        selected: list[_TextUnit] = []
        count = 0
        for unit in reversed(previous):
            if unit.context != next_unit.context or unit.overlap_barrier_before:
                break
            unit_page = self._page_end(unit.elements)
            if next_page is not None and unit_page is not None and unit_page != next_page:
                break
            unit_count = self._token_count(self._render_elements(unit.elements))
            if count + unit_count > self._settings.overlap_tokens:
                break
            selected.append(unit)
            count += unit_count
        return tuple(reversed(selected))

    def _table_candidates(self, table: Table) -> list[_Candidate]:
        if self._token_count(self._render_table(table)) <= self._settings.max_chunk_tokens:
            table_chunks = [table]
        else:
            header_rows = self._table_header_rows(table)
            data_rows = table.rows[len(header_rows) :]
            row_groups: list[list[TableRow]] = []
            current_rows: list[TableRow] = []
            for row in data_rows:
                proposed = [*current_rows, row]
                proposed_table = replace(table, rows=(*header_rows, *proposed))
                if (
                    current_rows
                    and row.row_index > self._row_span_end(current_rows)
                    and self._token_count(self._render_table(proposed_table))
                    > self._settings.max_chunk_tokens
                ):
                    row_groups.append(current_rows)
                    current_rows = [row]
                else:
                    current_rows = proposed
            if current_rows or not row_groups:
                row_groups.append(current_rows)
            table_chunks = [replace(table, rows=(*header_rows, *group)) for group in row_groups]

        total = len(table_chunks)
        output: list[_Candidate] = []
        for index, table_chunk in enumerate(table_chunks, start=1):
            output.append(
                _Candidate(
                    chunk_type=ChunkType.TABLE,
                    content=self._render_table(table_chunk),
                    elements=(table_chunk,),
                    context=table.structure_context,
                    structured_content=table_chunk,
                    table_id=table.element_id,
                    parent_table_id=(table.element_id if total > 1 else table.parent_table_id),
                    table_chunk_index=index,
                    total_table_chunks=total,
                )
            )
        return output

    def _list_candidates(self, list_element: ListElement) -> list[_Candidate]:
        if self._token_count(self._render_list(list_element)) <= self._settings.max_chunk_tokens:
            item_groups = [list_element.items]
        else:
            item_groups = []
            current_items: list[ListItem] = []
            for item in list_element.items:
                proposed = replace(list_element, items=(*current_items, item))
                if current_items and self._token_count(self._render_list(proposed)) > (
                    self._settings.max_chunk_tokens
                ):
                    item_groups.append(tuple(current_items))
                    current_items = [item]
                else:
                    current_items.append(item)
            if current_items or not item_groups:
                item_groups.append(tuple(current_items))

        total = len(item_groups)
        return [
            _Candidate(
                chunk_type=ChunkType.LIST,
                content=self._render_list(replace(list_element, items=items)),
                elements=(replace(list_element, items=items),),
                context=list_element.structure_context,
                structured_content=replace(list_element, items=items),
                list_id=list_element.element_id,
                list_chunk_index=index,
                total_list_chunks=total,
            )
            for index, items in enumerate(item_groups, start=1)
        ]

    def _other_candidate(self, element: DocumentElement) -> _Candidate:
        if isinstance(element, (Footnote, Link, OtherStructuredElement)):
            content = element.text
            context = element.structure_context
        else:
            content = ""
            context = getattr(element, "structure_context", None)
        return _Candidate(
            ChunkType.OTHER,
            content,
            (element,),
            context,
            structured_content=element,
        )

    def _make_metadata(
        self,
        filing: StructuredFiling,
        candidate: _Candidate,
        provenance: ChunkProvenance,
    ) -> ChunkMetadata:
        reference = filing.raw_filing.filing_reference
        context = candidate.context
        return ChunkMetadata(
            company=reference.company_name,
            ticker=reference.ticker,
            cik=reference.cik,
            accession_number=reference.accession_number,
            form_type=reference.filing_type,
            filing_date=reference.filing_date,
            period_of_report=reference.report_date,
            part=context.part if context else None,
            item=context.item if context else None,
            section=context.section if context else None,
            subsection=context.subsection if context else None,
            document_id=provenance.document_id or reference.primary_document,
            source_element_ids=provenance.source_element_ids,
            source_url=provenance.source_url or filing.raw_filing.source_url,
            html_anchors=provenance.html_anchors,
            page_start=provenance.page_start,
            page_end=provenance.page_end,
            table_id=candidate.table_id,
            parent_table_id=candidate.parent_table_id,
            table_chunk_index=candidate.table_chunk_index,
            total_table_chunks=candidate.total_table_chunks,
            list_id=candidate.list_id,
            list_chunk_index=candidate.list_chunk_index,
            total_list_chunks=candidate.total_list_chunks,
        )

    def _make_provenance(
        self,
        references: tuple[ChunkSourceReference, ...],
    ) -> ChunkProvenance:
        source_ids = tuple(reference.element_id for reference in references)
        pages = [
            reference.page_number for reference in references if reference.page_number is not None
        ]
        starts = [
            reference.start_offset for reference in references if reference.start_offset is not None
        ]
        ends = [
            reference.end_offset for reference in references if reference.end_offset is not None
        ]
        first_reference = references[0] if references else None
        return ChunkProvenance(
            filing_id=self._filing_id(references),
            document_id=self._document_id(references),
            source_element_ids=source_ids,
            source_url=first_reference.source_url if first_reference else None,
            html_anchors=tuple(reference.html_anchor for reference in references),
            start_offset=min(starts) if starts else None,
            end_offset=max(ends) if ends else None,
            page_start=min(pages) if pages else None,
            page_end=max(pages) if pages else None,
            source_references=references,
        )

    @staticmethod
    def _filing_id(references: tuple[ChunkSourceReference, ...]) -> str | None:
        return references[0].filing_id if references else None

    @staticmethod
    def _document_id(references: tuple[ChunkSourceReference, ...]) -> str | None:
        return references[0].document_id if references else None

    def _source_references(
        self,
        elements: tuple[DocumentElement, ...],
    ) -> tuple[ChunkSourceReference, ...]:
        references: list[ChunkSourceReference] = []
        seen_ids: set[str] = set()
        for element in elements:
            for _source_element, provenance in self._element_sources(element):
                if provenance.element_id is not None and provenance.element_id in seen_ids:
                    continue
                if provenance.element_id is not None:
                    seen_ids.add(provenance.element_id)
                references.append(
                    ChunkSourceReference(
                        element_id=provenance.element_id,
                        filing_id=provenance.filing_id,
                        document_id=provenance.document_id,
                        document_order=provenance.document_order,
                        source_element_type=provenance.source_element_type,
                        source_url=provenance.source_url,
                        html_anchor=provenance.html_anchor,
                        start_offset=provenance.start_offset,
                        end_offset=provenance.end_offset,
                        page_number=provenance.page_number,
                    )
                )
        return tuple(references)

    @staticmethod
    def _element_sources(element: DocumentElement) -> tuple[SourceElement, ...]:
        sources: list[SourceElement] = [(element, element.provenance)]
        if isinstance(element, Table):
            for row in element.rows:
                sources.append((row, row.provenance))
                sources.extend((cell, cell.provenance) for cell in row.cells)
        elif isinstance(element, ListElement):
            sources.extend((item, item.provenance) for item in element.items)
        return tuple(sources)

    def _element_sources_for_candidate(
        self,
        candidate: _Candidate,
    ) -> tuple[SourceElement, ...]:
        return tuple(
            source for element in candidate.elements for source in self._element_sources(element)
        )

    def _related_xbrl_fact_ids(
        self,
        filing: StructuredFiling,
        references: tuple[ChunkSourceReference, ...],
    ) -> tuple[str, ...]:
        source_ids = {reference.element_id for reference in references if reference.element_id}
        anchors = {reference.html_anchor for reference in references if reference.html_anchor}
        return tuple(
            fact.fact_id
            for fact in filing.xbrl_facts
            if fact.fact_id
            and (fact.source_element_id in source_ids or fact.provenance.html_anchor in anchors)
        )

    def _validate_chunks(self, filing: StructuredFiling, chunks: tuple[Chunk, ...]) -> None:
        ids = [chunk.chunk_id for chunk in chunks]
        if len(ids) != len(set(ids)):
            raise ChunkingError("Chunk IDs are not unique")
        valid_source_ids = {
            provenance.element_id
            for element in filing.elements
            for _source, provenance in self._element_sources(element)
            if provenance.element_id is not None
        }
        valid_table_ids = {
            element.element_id for element in filing.elements if isinstance(element, Table)
        }
        valid_list_ids = {
            element.element_id for element in filing.elements if isinstance(element, ListElement)
        }
        known_fact_ids = {fact.fact_id for fact in filing.xbrl_facts if fact.fact_id}
        table_groups: dict[str, list[Chunk]] = {}
        list_groups: dict[str, list[Chunk]] = {}
        for index, chunk in enumerate(chunks):
            if not chunk.content and chunk.structured_content is None:
                raise ChunkingError(f"Chunk {chunk.chunk_id} has no content or structure")
            if not chunk.provenance.source_element_ids:
                raise ChunkingError(f"Chunk {chunk.chunk_id} has no source elements")
            if any(
                source_id is None or source_id not in valid_source_ids
                for source_id in (chunk.provenance.source_element_ids)
            ):
                raise ChunkingError(f"Chunk {chunk.chunk_id} references an invalid source element")
            if chunk.provenance.filing_id != filing.raw_filing.filing_reference.accession_number:
                raise ChunkingError(f"Chunk {chunk.chunk_id} has an invalid filing identity")
            if (
                chunk.metadata.accession_number
                != filing.raw_filing.filing_reference.accession_number
            ):
                raise ChunkingError(
                    f"Chunk {chunk.chunk_id} metadata has an invalid filing identity"
                )
            if chunk.provenance.document_id not in (
                None,
                filing.raw_filing.filing_reference.primary_document,
            ):
                raise ChunkingError(f"Chunk {chunk.chunk_id} has an invalid document identity")
            if any(
                reference.filing_id != filing.raw_filing.filing_reference.accession_number
                for reference in chunk.provenance.source_references
            ):
                raise ChunkingError(f"Chunk {chunk.chunk_id} has inconsistent source filing IDs")
            if any(
                reference.document_id
                not in (
                    None,
                    filing.raw_filing.filing_reference.primary_document,
                )
                for reference in chunk.provenance.source_references
            ):
                raise ChunkingError(f"Chunk {chunk.chunk_id} has inconsistent source document IDs")
            if any(
                reference.source_url != filing.raw_filing.source_url
                for reference in chunk.provenance.source_references
            ):
                raise ChunkingError(f"Chunk {chunk.chunk_id} has inconsistent source URLs")
            if chunk.metadata.document_id not in (
                None,
                filing.raw_filing.filing_reference.primary_document,
            ):
                raise ChunkingError(
                    f"Chunk {chunk.chunk_id} metadata has an invalid document identity"
                )
            if any(fact_id not in known_fact_ids for fact_id in chunk.xbrl_fact_ids):
                raise ChunkingError(f"Chunk {chunk.chunk_id} references an unknown XBRL fact")
            expected_previous = chunks[index - 1].chunk_id if index > 0 else None
            expected_next = chunks[index + 1].chunk_id if index + 1 < len(chunks) else None
            if chunk.relationships.previous_chunk_id != expected_previous:
                raise ChunkingError("Chunk previous relationship is inconsistent")
            if chunk.relationships.next_chunk_id != expected_next:
                raise ChunkingError("Chunk next relationship is inconsistent")
            if chunk.relationships.parent_chunk_id is not None and (
                chunk.relationships.parent_chunk_id not in ids
                or chunk.relationships.parent_chunk_id == chunk.chunk_id
            ):
                raise ChunkingError("Chunk parent relationship is invalid")
            if chunk.chunk_type is ChunkType.TABLE and (
                not isinstance(chunk.structured_content, Table) or not chunk.metadata.table_id
            ):
                raise ChunkingError("Table chunk is missing its structured table identity")
            if chunk.chunk_type is ChunkType.TABLE:
                table_id = chunk.metadata.table_id
                table_index = chunk.metadata.table_chunk_index
                table_total = chunk.metadata.total_table_chunks
                if (
                    table_id is None
                    or table_id not in valid_table_ids
                    or table_index is None
                    or table_total is None
                    or table_index < 1
                    or table_index > table_total
                ):
                    raise ChunkingError("Table chunk relationship metadata is invalid")
                if table_total > 1 and chunk.metadata.parent_table_id != table_id:
                    raise ChunkingError("Split table chunk does not reference its parent table")
                if (
                    chunk.metadata.parent_table_id is not None
                    and chunk.metadata.parent_table_id not in valid_table_ids
                ):
                    raise ChunkingError("Table chunk references an unknown parent table")
                table_groups.setdefault(table_id, []).append(chunk)
            if chunk.chunk_type is ChunkType.LIST:
                list_id = chunk.metadata.list_id
                list_index = chunk.metadata.list_chunk_index
                list_total = chunk.metadata.total_list_chunks
                if (
                    list_id is None
                    or list_id not in valid_list_ids
                    or list_index is None
                    or list_total is None
                    or list_index < 1
                    or list_index > list_total
                    or not isinstance(chunk.structured_content, ListElement)
                ):
                    raise ChunkingError("List chunk relationship metadata is invalid")
                list_groups.setdefault(list_id, []).append(chunk)

        for table_id, group in table_groups.items():
            total = group[0].metadata.total_table_chunks
            indexes = sorted(
                index
                for index in (chunk.metadata.table_chunk_index for chunk in group)
                if index is not None
            )
            if total != len(group) or indexes != list(range(1, len(group) + 1)):
                raise ChunkingError(f"Table chunk sequence is incomplete for {table_id}")
            if any(chunk.metadata.total_table_chunks != total for chunk in group):
                raise ChunkingError(f"Table chunk totals disagree for {table_id}")
        for list_id, group in list_groups.items():
            total = group[0].metadata.total_list_chunks
            indexes = sorted(
                index
                for index in (chunk.metadata.list_chunk_index for chunk in group)
                if index is not None
            )
            if total != len(group) or indexes != list(range(1, len(group) + 1)):
                raise ChunkingError(f"List chunk sequence is incomplete for {list_id}")
            if any(chunk.metadata.total_list_chunks != total for chunk in group):
                raise ChunkingError(f"List chunk totals disagree for {list_id}")

    @staticmethod
    def _link_chunks(chunks: list[Chunk]) -> tuple[Chunk, ...]:
        return tuple(
            replace(
                chunk,
                relationships=ChunkRelationships(
                    previous_chunk_id=chunks[index - 1].chunk_id if index > 0 else None,
                    next_chunk_id=(chunks[index + 1].chunk_id if index + 1 < len(chunks) else None),
                ),
            )
            for index, chunk in enumerate(chunks)
        )

    def _render_units(self, units: list[_TextUnit]) -> str:
        return self._render_elements(tuple(element for unit in units for element in unit.elements))

    @staticmethod
    def _render_elements(elements: tuple[DocumentElement, ...]) -> str:
        return "\n\n".join(
            text for element in elements if (text := getattr(element, "text", "")).strip()
        )

    def _render_table(self, table: Table) -> str:
        lines: list[str] = []
        if table.caption:
            lines.append(f"Table: {table.caption}")
        if table.headers:
            lines.append("Headers: " + " | ".join(table.headers))
        if table.rows:
            lines.append("Rows:")
            lines.extend(
                f"{row.row_index}: " + " | ".join(cell.text for cell in row.cells)
                for row in table.rows
            )
        return "\n".join(lines)

    @staticmethod
    def _render_list(list_element: ListElement) -> str:
        marker = "{index}. " if list_element.ordered else "- "
        return "\n".join(
            (marker.format(index=item.position) if list_element.ordered else marker) + item.text
            for item in list_element.items
        )

    @staticmethod
    def _table_header_rows(table: Table) -> tuple[TableRow, ...]:
        rows: list[TableRow] = []
        for row in table.rows:
            if not row.cells or not all(
                cell.header_role in {"header", "col", "colgroup"} for cell in row.cells
            ):
                break
            rows.append(row)
        return tuple(rows)

    @staticmethod
    def _row_span_end(rows: list[TableRow]) -> int:
        return max(row.row_index + cell.rowspan - 1 for row in rows for cell in row.cells)

    def _token_count(self, text: str) -> int:
        return len(self._tokenizer.encode(text))

    @staticmethod
    def _page_start(elements: tuple[DocumentElement, ...]) -> int | None:
        values = [
            provenance.page_number
            for element in elements
            for _source, provenance in StructuredFilingChunker._element_sources(element)
            if provenance.page_number is not None
        ]
        return min(values) if values else None

    @staticmethod
    def _page_end(elements: tuple[DocumentElement, ...]) -> int | None:
        values = [
            provenance.page_number
            for element in elements
            for _source, provenance in StructuredFilingChunker._element_sources(element)
            if provenance.page_number is not None
        ]
        return max(values) if values else None
