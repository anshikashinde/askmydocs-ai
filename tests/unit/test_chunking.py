from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.application.chunk_indexing import FilingIndexPreparationService
from app.application.chunking import StructuredFilingChunker
from app.application.errors import ChunkingError, EmbeddingError
from app.config import ChunkingSettings
from app.domain.filings import (
    FilingReference,
    Heading,
    ListElement,
    ListItem,
    Paragraph,
    Provenance,
    RawFiling,
    SourceFormat,
    StructureContext,
    StructuredFiling,
    Table,
    TableCell,
    TableRow,
    TableType,
    XBRLFact,
)
from app.infrastructure.bm25 import BM25TextRepresentationBuilder
from app.infrastructure.chunk_index import InMemoryChunkIndexRepository
from app.infrastructure.file_chunk_index import FileSystemChunkIndexRepository
from app.infrastructure.tokenization import TiktokenTokenizer


def make_filing(
    elements: tuple,
    facts: tuple[XBRLFact, ...] = (),
) -> StructuredFiling:
    reference = FilingReference(
        company_name="Example Corp",
        ticker="EXM",
        cik="0000000001",
        filing_type="10-K",
        filing_date="2025-02-01",
        report_date="2024-12-31",
        accession_number="0000000001-25-000001",
        primary_document="example.htm",
        source_url="https://www.sec.gov/example.htm",
    )
    raw = RawFiling(
        content=b"source",
        source_url=reference.source_url,
        filename=reference.primary_document,
        filing_reference=reference,
        retrieved_at=datetime(2025, 2, 1, tzinfo=UTC),
    )
    return StructuredFiling(
        raw_filing=raw,
        source_format=SourceFormat.HTML,
        document_metadata=(),
        elements=elements,
        xbrl_facts=facts,
        xbrl_contexts=(),
        xbrl_units=(),
        continuations=(),
        validation_issues=(),
    )


def provenance(
    element_id: str,
    order: int,
    element_type: str,
    page_number: int | None = None,
) -> Provenance:
    return Provenance(
        filing_id="0000000001-25-000001",
        document_id="example.htm",
        element_id=element_id,
        source_url="https://www.sec.gov/example.htm",
        document_order=order,
        start_offset=None,
        end_offset=None,
        html_anchor=element_id,
        page_number=page_number,
        source_element_type=element_type,
    )


def chunker(
    *,
    target: int = 100,
    maximum: int = 120,
    minimum: int = 0,
    overlap: int = 0,
) -> StructuredFilingChunker:
    settings = ChunkingSettings(
        target_chunk_tokens=target,
        max_chunk_tokens=maximum,
        min_chunk_tokens=minimum,
        overlap_tokens=overlap,
    )
    return StructuredFilingChunker(settings, TiktokenTokenizer(settings.tokenizer_encoding))


def test_chunking_is_deterministic_and_propagates_structure() -> None:
    context = StructureContext("Part II", "Item 7", "Management Discussion", "Revenue")
    elements = (
        Heading(
            "Revenue",
            3,
            "heading-revenue",
            1,
            provenance("heading-revenue", 1, "heading", 5),
            context,
        ),
        Paragraph(
            "Revenue increased during the year.",
            "paragraph-1",
            2,
            provenance("paragraph-1", 2, "paragraph", 5),
            context,
        ),
        Paragraph(
            "Net sales reached 100 billion dollars.",
            "paragraph-2",
            3,
            provenance("paragraph-2", 3, "paragraph", 6),
            context,
        ),
    )
    filing = make_filing(elements)

    first = chunker().chunk(filing).chunks
    second = chunker().chunk(filing).chunks

    assert first == second
    assert len(first) == 1
    assert first[0].chunk_type.value == "narrative"
    assert "Revenue" in first[0].content
    assert "Net sales reached" in first[0].content
    assert first[0].metadata.part == "Part II"
    assert first[0].metadata.item == "Item 7"
    assert first[0].metadata.section == "Management Discussion"
    assert first[0].metadata.subsection == "Revenue"
    assert first[0].provenance.source_element_ids == (
        "heading-revenue",
        "paragraph-1",
        "paragraph-2",
    )
    assert first[0].provenance.page_start == 5
    assert first[0].provenance.page_end == 6
    assert first[0].relationships.previous_chunk_id is None
    assert first[0].relationships.next_chunk_id is None


def test_table_chunks_keep_structure_headers_rows_and_xbrl_links() -> None:
    table_provenance = provenance("table-1", 1, "table", 12)
    header_provenance = provenance("row-header", 1, "table_row", 12)
    header = TableRow(
        cells=(
            TableCell(
                "Year", 0, 0, 1, 1, "col", "cell-year", provenance("cell-year", 1, "table_cell", 12)
            ),
            TableCell(
                "Revenue",
                0,
                1,
                2,
                1,
                "col",
                "cell-revenue",
                provenance("cell-revenue", 1, "table_cell", 12),
            ),
        ),
        row_index=0,
        element_id="row-header",
        provenance=header_provenance,
    )
    rows = [header]
    for row_index in range(1, 13):
        row_provenance = provenance(f"row-{row_index}", 1, "table_row", 12)
        cells = (
            TableCell(
                f"Year {2025 - row_index}",
                row_index,
                0,
                1,
                2 if row_index == 1 else 1,
                "row",
                f"cell-year-{row_index}",
                provenance(f"cell-year-{row_index}", 1, "table_cell", 12),
            ),
            TableCell(
                f"{100 - row_index} million dollars",
                row_index,
                1,
                1,
                1,
                None,
                f"cell-value-{row_index}",
                provenance(f"cell-value-{row_index}", 1, "table_cell", 12),
            ),
        )
        rows.append(TableRow(cells, row_index, f"row-{row_index}", row_provenance))
    table = Table(
        caption="Revenue by year",
        headers=("Year", "Revenue"),
        rows=tuple(rows),
        table_type=TableType.DATA,
        element_id="table-1",
        document_order=1,
        provenance=table_provenance,
        structure_context=StructureContext("Part II", "Item 8", "Statements", None),
    )
    fact_provenance = provenance("fact-revenue", 1, "xbrl_fact", 12)
    fact = XBRLFact(
        fact_id="fact-revenue",
        name="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        value="99",
        resolved_value="99",
        normalized_value="99",
        fact_type="nonfraction",
        context_ref="context-1",
        unit_ref="usd",
        decimals="-6",
        scale="6",
        sign=None,
        format=None,
        is_hidden=False,
        continued_at=None,
        continuation_ids=(),
        attributes=(),
        source_element_id="cell-value-1",
        provenance=fact_provenance,
    )

    result = chunker(target=12, maximum=20).chunk(make_filing((table,), (fact,)))
    table_chunks = result.chunks

    assert len(table_chunks) > 1
    assert all(item.chunk_type.value == "table" for item in table_chunks)
    assert all(isinstance(item.structured_content, Table) for item in table_chunks)
    assert all(item.metadata.table_id == "table-1" for item in table_chunks)
    assert all(item.metadata.parent_table_id == "table-1" for item in table_chunks)
    assert [item.metadata.table_chunk_index for item in table_chunks] == list(
        range(1, len(table_chunks) + 1)
    )
    assert all(item.metadata.total_table_chunks == len(table_chunks) for item in table_chunks)
    assert all(item.structured_content.rows[0].element_id == "row-header" for item in table_chunks)
    assert table_chunks[0].structured_content.rows[0].cells[1].colspan == 2
    assert all(
        item.provenance.page_start == 12 and item.provenance.page_end == 12 for item in table_chunks
    )
    assert any("cell-value-1" in item.provenance.source_element_ids for item in table_chunks)
    assert any("fact-revenue" in item.xbrl_fact_ids for item in table_chunks)
    assert any(
        {row.row_index for row in item.structured_content.rows}.issuperset({1, 2})
        for item in table_chunks
    )
    assert {
        cell.text
        for item in table_chunks
        for row in item.structured_content.rows
        for cell in row.cells
    } >= {
        "Year 2013",
        "88 million dollars",
    }


def test_lists_remain_grouped_and_missing_source_ids_fail_explicitly() -> None:
    list_source = provenance("list-1", 1, "list", None)
    items = tuple(
        ListItem(
            f"Risk item {index}",
            index,
            f"list-item-{index}",
            provenance(f"list-item-{index}", 1, "list_item", None),
        )
        for index in range(1, 4)
    )
    list_element = ListElement(True, items, "list-1", 1, list_source, None)

    result = chunker().chunk(make_filing((list_element,)))

    assert len(result.chunks) == 1
    assert result.chunks[0].chunk_type.value == "list"
    assert isinstance(result.chunks[0].structured_content, ListElement)
    assert "1. Risk item 1" in result.chunks[0].content
    assert result.chunks[0].provenance.page_start is None
    assert result.chunks[0].provenance.page_end is None

    missing_id = Paragraph("Text", None, 1, provenance("paragraph-1", 1, "paragraph"))
    with pytest.raises(ChunkingError, match="missing its element ID"):
        chunker().chunk(make_filing((missing_id,)))


def test_oversized_narrative_preserves_exact_text_across_token_slices() -> None:
    text = "Revenue grew by 12% in Tokyo and café sales. " * 25
    paragraph = Paragraph("", "paragraph-1", 1, provenance("paragraph-1", 1, "paragraph"))
    paragraph = Paragraph(
        text, paragraph.element_id, paragraph.document_order, paragraph.provenance
    )
    settings = ChunkingSettings(
        target_chunk_tokens=8,
        max_chunk_tokens=10,
        min_chunk_tokens=0,
        overlap_tokens=0,
    )
    result = StructuredFilingChunker(
        settings, TiktokenTokenizer(settings.tokenizer_encoding)
    ).chunk(make_filing((paragraph,)))

    assert len(result.chunks) > 1
    assert "".join(item.content for item in result.chunks) == text
    assert all(count <= settings.max_chunk_tokens for count in result.token_counts)
    assert all(item.provenance.source_element_ids == ("paragraph-1",) for item in result.chunks)


def test_overlap_is_dropped_when_it_would_exceed_the_maximum() -> None:
    context = StructureContext("Part II", "Item 7", "Management Discussion", None)
    texts = (
        "Revenue grew by 12 percent during the year.",
        "Operating costs also increased by four percent.",
    )
    tokenizer = TiktokenTokenizer("cl100k_base")
    combined_tokens = tokenizer.count_tokens("\n\n".join(texts))
    maximum = max(tokenizer.count_tokens(text) for text in texts) + 1
    assert combined_tokens > maximum
    settings = ChunkingSettings(
        target_chunk_tokens=maximum,
        max_chunk_tokens=maximum,
        min_chunk_tokens=0,
        overlap_tokens=maximum - 1,
    )
    elements = tuple(
        Paragraph(
            text,
            f"paragraph-{index}",
            index,
            provenance(f"paragraph-{index}", index, "paragraph"),
            context,
        )
        for index, text in enumerate(texts, start=1)
    )

    result = StructuredFilingChunker(settings, tokenizer).chunk(make_filing(elements))

    assert [chunk.content for chunk in result.chunks] == list(texts)
    assert all(count <= maximum for count in result.token_counts)


def test_index_preparation_is_idempotent_and_resolves_embeddings() -> None:
    context = StructureContext("Part II", "Item 7", "Management Discussion", None)
    paragraph = Paragraph(
        "Revenue increased by 12 percent.",
        "paragraph-1",
        1,
        provenance("paragraph-1", 1, "paragraph", 4),
        context,
    )
    filing = make_filing((paragraph,))

    class FakeEmbeddingProvider:
        @property
        def embedding_model(self) -> str:
            return "test-vector-v1"

        @property
        def embedding_dimension(self) -> int:
            return 2

        def embed_text(self, text: str) -> tuple[float, ...]:
            return (float(len(text)), 1.0)

        def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
            return tuple(self.embed_text(text) for text in texts)

    repository = InMemoryChunkIndexRepository()
    service = FilingIndexPreparationService(
        chunker(),
        BM25TextRepresentationBuilder(),
        repository,
        FakeEmbeddingProvider(),
    )

    first = service.prepare(filing)
    second = service.prepare(filing)

    assert first.bundle == second.bundle
    assert repository.document_count == 1
    chunk = first.bundle.chunks[0]
    assert repository.resolve_chunk(chunk.chunk_id) == chunk
    assert repository.resolve_metadata(chunk.chunk_id) == chunk.metadata
    bm25 = repository.resolve_bm25(chunk.chunk_id)
    assert bm25 is not None
    assert "EXM" in bm25.tokens
    assert "Revenue" in bm25.tokens
    embedding = repository.resolve_embedding(chunk.chunk_id)
    assert embedding is not None
    assert embedding.embedding_model == "test-vector-v1"
    assert embedding.embedding_dimension == len(embedding.vector) == 2
    assert first.metrics.embedding_count == 1
    assert first.metrics.chunks_with_provenance == 1


def test_large_lists_split_by_item_and_invalid_embeddings_fail() -> None:
    list_provenance = provenance("list-1", 1, "list")
    items = tuple(
        ListItem(
            f"Risk item {index} has material consequences.",
            index,
            f"list-item-{index}",
            provenance(f"list-item-{index}", 1, "list_item"),
        )
        for index in range(1, 9)
    )
    source_list = ListElement(True, items, "list-1", 1, list_provenance)
    list_result = chunker(target=12, maximum=12).chunk(make_filing((source_list,)))
    list_chunks = list_result.chunks

    assert len(list_chunks) > 1
    assert [chunk.metadata.list_chunk_index for chunk in list_chunks] == list(
        range(1, len(list_chunks) + 1)
    )
    assert all(chunk.metadata.total_list_chunks == len(list_chunks) for chunk in list_chunks)
    assert [
        item.element_id for chunk in list_chunks for item in chunk.structured_content.items
    ] == [item.element_id for item in items]

    paragraph = Paragraph(
        "Revenue increased.", "paragraph-1", 1, provenance("paragraph-1", 1, "paragraph")
    )
    filing = make_filing((paragraph,))

    class InvalidEmbeddingProvider:
        @property
        def embedding_model(self) -> str:
            return "invalid-dimension"

        @property
        def embedding_dimension(self) -> int:
            return 2

        def embed_text(self, text: str) -> tuple[float, ...]:
            return (1.0,)

        def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
            return tuple(self.embed_text(text) for text in texts)

    repository = InMemoryChunkIndexRepository()
    service = FilingIndexPreparationService(
        chunker(),
        BM25TextRepresentationBuilder(),
        repository,
        InvalidEmbeddingProvider(),
    )
    with pytest.raises(EmbeddingError, match="dimension is invalid"):
        service.prepare(filing)
    assert repository.document_count == 0


def test_filesystem_index_round_trips_and_replaces_filing(tmp_path: Path) -> None:
    paragraph = Paragraph(
        "Revenue increased by 12 percent.",
        "paragraph-1",
        1,
        provenance("paragraph-1", 1, "paragraph", 2),
        StructureContext("Part II", "Item 7", "Results", None),
    )
    table_provenance = provenance("table-1", 2, "table", 3)
    row = TableRow(
        (
            TableCell(
                "2025", 0, 0, 1, 1, "col", "cell-year", provenance("cell-year", 2, "table_cell", 3)
            ),
            TableCell(
                "100 million dollars",
                0,
                1,
                1,
                1,
                None,
                "cell-value",
                provenance("cell-value", 2, "table_cell", 3),
            ),
        ),
        0,
        "row-1",
        provenance("row-1", 2, "table_row", 3),
    )
    table = Table(
        caption="Annual revenue",
        headers=("Year", "Revenue"),
        rows=(row,),
        table_type=TableType.DATA,
        element_id="table-1",
        document_order=2,
        provenance=table_provenance,
    )
    filing = make_filing((paragraph, table))

    class FakeEmbeddingProvider:
        @property
        def embedding_model(self) -> str:
            return "persisted-test-v1"

        @property
        def embedding_dimension(self) -> int:
            return 2

        def embed_text(self, text: str) -> tuple[float, ...]:
            return (float(len(text)), 0.5)

        def embed_batch(self, texts: tuple[str, ...]) -> tuple[tuple[float, ...], ...]:
            return tuple(self.embed_text(text) for text in texts)

    repository = FileSystemChunkIndexRepository(tmp_path)
    service = FilingIndexPreparationService(
        chunker(),
        BM25TextRepresentationBuilder(),
        repository,
        FakeEmbeddingProvider(),
    )
    first = service.prepare(filing)
    second = service.prepare(filing)
    reopened = FileSystemChunkIndexRepository(tmp_path)

    assert first.bundle == second.bundle
    assert len(tuple(tmp_path.glob("*.json"))) == 1
    assert reopened.document_count == len(first.bundle.chunks)
    for chunk in first.bundle.chunks:
        assert reopened.resolve_chunk(chunk.chunk_id) == chunk
        assert reopened.resolve_bm25(chunk.chunk_id) is not None
        assert reopened.resolve_metadata(chunk.chunk_id) == chunk.metadata
        assert reopened.resolve_embedding(chunk.chunk_id) is not None
    stored_table = next(
        reopened.resolve_chunk(chunk.chunk_id)
        for chunk in first.bundle.chunks
        if chunk.chunk_type.value == "table"
    )
    assert isinstance(stored_table.structured_content, Table)
    assert stored_table.structured_content.rows[0].cells[1].text == "100 million dollars"
