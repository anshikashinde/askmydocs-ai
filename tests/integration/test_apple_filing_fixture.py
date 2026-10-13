from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.application.chunk_indexing import FilingIndexPreparationService
from app.application.chunking import StructuredFilingChunker
from app.application.errors import EmbeddingError
from app.application.filing_normalization import normalize_structured_filing
from app.application.ingestion import FilingIngestionService
from app.config import ChunkingSettings
from app.domain.chunks import (
    Chunk,
    ChunkEmbedding,
    ChunkMetadata,
    ChunkProvenance,
    ChunkRelationships,
)
from app.domain.filings import (
    FilingReference,
    Heading,
    ListElement,
    PageBreak,
    Paragraph,
    Provenance,
    RawFiling,
    SourceFormat,
    StructureContext,
    StructuredFiling,
    Table,
)
from app.infrastructure.bm25 import BM25TextRepresentationBuilder
from app.infrastructure.chunk_index import InMemoryChunkIndexRepository
from app.infrastructure.parsing.sec_html import SECHTMLParser
from app.infrastructure.tokenization import TiktokenTokenizer
from app.infrastructure.vector_index import LocalVectorIndex


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


@pytest.mark.parametrize(
    ("ticker", "environment_variable"),
    [
        ("AAPL", "ASKMYDOCS_APPLE_10K_RESPONSE"),
        ("MSFT", "ASKMYDOCS_MICROSOFT_10K_RESPONSE"),
    ],
)
def test_issuer_10k_passes_phase_1b_pipeline(
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
    settings = ChunkingSettings()
    repository = InMemoryChunkIndexRepository()
    prepared = FilingIndexPreparationService(
        StructuredFilingChunker(settings, TiktokenTokenizer(settings.tokenizer_encoding)),
        BM25TextRepresentationBuilder(),
        repository,
    ).prepare(structured)

    valid_source_ids: set[str] = set()
    for element in structured.elements:
        if element.element_id:
            valid_source_ids.add(element.element_id)
        if isinstance(element, Table):
            valid_source_ids.update(row.element_id for row in element.rows if row.element_id)
            valid_source_ids.update(
                cell.element_id for row in element.rows for cell in row.cells if cell.element_id
            )
        if isinstance(element, ListElement):
            valid_source_ids.update(item.element_id for item in element.items if item.element_id)

    chunk_ids = {chunk.chunk_id for chunk in prepared.bundle.chunks}
    assert len(chunk_ids) == len(prepared.bundle.chunks)
    assert {item.chunk_id for item in prepared.bundle.bm25_representations} == chunk_ids
    assert prepared.metrics.index_document_count == len(chunk_ids)
    assert prepared.metrics.table_chunk_count > 0
    assert all(
        source_id is not None and source_id in valid_source_ids
        for chunk in prepared.bundle.chunks
        for source_id in chunk.provenance.source_element_ids
    )
    for chunk in prepared.bundle.chunks:
        source_pages = [
            source.page_number
            for source in chunk.provenance.source_references
            if source.page_number is not None
        ]
        assert chunk.provenance.page_start == (min(source_pages) if source_pages else None)
        assert chunk.provenance.page_end == (max(source_pages) if source_pages else None)
        assert repository.resolve_chunk(chunk.chunk_id) == chunk
    assert all(
        token_count <= settings.max_chunk_tokens
        for token_count, chunk in zip(
            StructuredFilingChunker(
                settings,
                TiktokenTokenizer(settings.tokenizer_encoding),
            )
            .chunk(structured)
            .token_counts,
            prepared.bundle.chunks,
            strict=True,
        )
    )


class DeterministicEmbeddingProvider:
    embedding_model = "test-model"
    embedding_dimension = 3

    def embed_text(self, text: str) -> list[float]:
        return [float(len(text) % 7), float(len(text) % 5), 1.0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]


class FailingEmbeddingProvider(DeterministicEmbeddingProvider):
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding backend unavailable")


def _sample_structured_filing() -> StructuredFiling:
    reference = FilingReference(
        company_name="Acme Corp",
        ticker="ACME",
        cik="0000000001",
        filing_type="10-K",
        filing_date="2024-01-31",
        report_date="2023-12-31",
        accession_number="0000000001-24-000001",
        primary_document="acme-2023.htm",
        source_url="https://example.com/acme-2023.htm",
    )
    raw_filing = RawFiling(
        content=b"<html><body><h1>Item 1</h1><p>Revenue increased this year.</p></body></html>",
        source_url=reference.source_url,
        filename=reference.primary_document,
        filing_reference=reference,
        retrieved_at=datetime.now(UTC),
        content_type="text/html",
    )
    heading = Heading(
        text="Item 1",
        level=1,
        element_id="h-1",
        document_order=1,
        provenance=Provenance(
            filing_id=reference.accession_number,
            document_id=reference.primary_document,
            source_url=reference.source_url,
            document_order=1,
            start_offset=0,
            end_offset=15,
            html_anchor="h-1",
            page_number=1,
            source_element_type="heading",
            element_id="h-1",
        ),
        structure_context=StructureContext(part="Part I", item="Item 1"),
    )
    paragraph = Paragraph(
        text="Revenue increased this year.",
        element_id="p-1",
        document_order=2,
        provenance=Provenance(
            filing_id=reference.accession_number,
            document_id=reference.primary_document,
            source_url=reference.source_url,
            document_order=2,
            start_offset=16,
            end_offset=42,
            html_anchor="p-1",
            page_number=1,
            source_element_type="paragraph",
            element_id="p-1",
        ),
        structure_context=StructureContext(part="Part I", item="Item 1"),
    )
    return StructuredFiling(
        raw_filing=raw_filing,
        source_format=SourceFormat.HTML,
        document_metadata=(),
        elements=(heading, paragraph),
        xbrl_facts=(),
        xbrl_contexts=(),
        xbrl_units=(),
        continuations=(),
        validation_issues=(),
    )


def test_filing_ingestion_persists_embedded_index(tmp_path: Path) -> None:
    filing = _sample_structured_filing()
    chunker = StructuredFilingChunker(ChunkingSettings(), TiktokenTokenizer("cl100k_base"))
    service = FilingIngestionService(
        filing_service=None,
        parser=None,
        chunker=chunker,
        bm25_builder=BM25TextRepresentationBuilder(),
        index_repository=InMemoryChunkIndexRepository(),
        embedding_provider=DeterministicEmbeddingProvider(),
        vector_index=LocalVectorIndex(model_name="test-model", dimension=3),
        storage_directory=tmp_path,
    )

    result = service.ingest_filing(filing)

    assert result.bundle.chunks
    assert result.vector_index is not None
    assert result.vector_index.document_count == len(result.bundle.chunks)
    assert tmp_path.joinpath("chunk-index.json").exists()
    assert result.bundle.embeddings
    assert {entry.chunk_id for entry in result.bundle.embeddings} == {
        chunk.chunk_id for chunk in result.bundle.chunks
    }


def test_vector_index_search_resolves_chunk_and_provenance() -> None:
    index = LocalVectorIndex(model_name="test-model", dimension=3)
    first = Chunk(
        chunk_id="chunk-a",
        chunk_type="narrative",
        content="revenue increased",
        metadata=ChunkMetadata(
            company="Acme Corp",
            ticker="ACME",
            cik="0000000001",
            accession_number="0000000001-24-000001",
            form_type="10-K",
            filing_date="2024-01-31",
            period_of_report="2023-12-31",
            part="Part I",
            item="Item 1",
            section="Business",
            subsection=None,
            document_id="acme-2023.htm",
            source_element_ids=("h-1",),
            source_url="https://example.com/acme-2023.htm",
            html_anchors=("h-1",),
            page_start=1,
            page_end=1,
        ),
        provenance=ChunkProvenance(
            filing_id="0000000001-24-000001",
            document_id="acme-2023.htm",
            source_element_ids=("h-1",),
            source_url="https://example.com/acme-2023.htm",
            html_anchors=("h-1",),
            start_offset=0,
            end_offset=16,
            page_start=1,
            page_end=1,
            source_references=(),
        ),
        relationships=ChunkRelationships(),
        chunking_version="1",
    )
    second = Chunk(
        chunk_id="chunk-b",
        chunk_type="narrative",
        content="costs remained stable",
        metadata=ChunkMetadata(
            company="Acme Corp",
            ticker="ACME",
            cik="0000000001",
            accession_number="0000000001-24-000001",
            form_type="10-K",
            filing_date="2024-01-31",
            period_of_report="2023-12-31",
            part="Part I",
            item="Item 1",
            section="Business",
            subsection=None,
            document_id="acme-2023.htm",
            source_element_ids=("p-1",),
            source_url="https://example.com/acme-2023.htm",
            html_anchors=("p-1",),
            page_start=1,
            page_end=1,
        ),
        provenance=ChunkProvenance(
            filing_id="0000000001-24-000001",
            document_id="acme-2023.htm",
            source_element_ids=("p-1",),
            source_url="https://example.com/acme-2023.htm",
            html_anchors=("p-1",),
            start_offset=17,
            end_offset=44,
            page_start=1,
            page_end=1,
            source_references=(),
        ),
        relationships=ChunkRelationships(),
        chunking_version="1",
    )
    index.add_or_replace(first, ChunkEmbedding("chunk-a", "test-model", 3, (1.0, 0.0, 0.0)))
    index.add_or_replace(second, ChunkEmbedding("chunk-b", "test-model", 3, (0.8, 0.6, 0.0)))

    matches = index.search((1.0, 0.0, 0.0), top_k=2)

    assert matches[0].chunk_id == "chunk-a"
    assert matches[0].chunk is first
    assert matches[0].metadata == first.metadata
    assert matches[0].provenance == first.provenance


def test_filing_ingestion_reports_embedding_failures() -> None:
    filing = _sample_structured_filing()
    service = FilingIngestionService(
        filing_service=None,
        parser=None,
        chunker=StructuredFilingChunker(ChunkingSettings(), TiktokenTokenizer("cl100k_base")),
        bm25_builder=BM25TextRepresentationBuilder(),
        index_repository=InMemoryChunkIndexRepository(),
        embedding_provider=FailingEmbeddingProvider(),
        vector_index=LocalVectorIndex(model_name="test-model", dimension=3),
    )

    with pytest.raises(EmbeddingError, match="Batch embedding generation failed"):
        service.ingest_filing(filing)
