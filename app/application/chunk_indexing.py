from __future__ import annotations

import math
from dataclasses import dataclass

from app.application.chunking import ChunkingResult, StructuredFilingChunker
from app.application.chunking_ports import (
    BM25RepresentationBuilder,
    ChunkIndexRepository,
    EmbeddingProvider,
)
from app.application.errors import ChunkingError, EmbeddingError, IndexPersistenceError
from app.domain.chunks import (
    BM25Representation,
    ChunkEmbedding,
    ChunkIndexBundle,
    ChunkMetadata,
)
from app.domain.filings import StructureContext, StructuredFiling


@dataclass(frozen=True)
class ChunkingMetrics:
    input_element_count: int
    output_chunk_count: int
    narrative_chunk_count: int
    table_chunk_count: int
    list_chunk_count: int
    other_chunk_count: int
    average_chunk_tokens: float
    maximum_chunk_tokens: int
    chunks_with_page_references: int
    chunks_without_page_references: int
    chunks_with_provenance: int
    chunks_with_missing_provenance: int
    embedding_count: int
    embedding_failures: int
    index_document_count: int


@dataclass(frozen=True)
class FilingIndexPreparationResult:
    bundle: ChunkIndexBundle
    metrics: ChunkingMetrics


class FilingIndexPreparationService:
    def __init__(
        self,
        chunker: StructuredFilingChunker,
        bm25_builder: BM25RepresentationBuilder,
        index_repository: ChunkIndexRepository,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._chunker = chunker
        self._bm25_builder = bm25_builder
        self._index_repository = index_repository
        self._embedding_provider = embedding_provider

    def prepare(self, filing: StructuredFiling) -> FilingIndexPreparationResult:
        chunking = self._chunker.chunk(filing)
        bm25 = self._bm25_builder.build(chunking.chunks)
        self._validate_bm25(chunking, bm25)
        embeddings = self._embed(chunking)
        reference = filing.raw_filing.filing_reference
        bundle = ChunkIndexBundle(
            filing_id=reference.accession_number,
            document_id=reference.primary_document,
            chunks=chunking.chunks,
            bm25_representations=bm25,
            embeddings=embeddings,
        )
        self._validate_bundle(filing, bundle)
        try:
            self._index_repository.replace_filing(bundle)
        except IndexPersistenceError:
            raise
        except Exception as exc:
            raise IndexPersistenceError("Prepared filing index could not be persisted") from exc
        self._validate_index_resolution(bundle)
        return FilingIndexPreparationResult(bundle, self._metrics(filing, chunking, embeddings))

    @staticmethod
    def _validate_bm25(
        chunking: ChunkingResult,
        representations: tuple[BM25Representation, ...],
    ) -> None:
        chunk_ids = {chunk.chunk_id for chunk in chunking.chunks}
        representation_ids = [entry.chunk_id for entry in representations]
        if len(representation_ids) != len(set(representation_ids)):
            raise ChunkingError("BM25 representations contain duplicate chunk IDs")
        if set(representation_ids) != chunk_ids:
            raise ChunkingError("BM25 representations do not resolve one-to-one to chunks")
        chunks = {chunk.chunk_id: chunk for chunk in chunking.chunks}
        for entry in representations:
            if entry.text != chunks[entry.chunk_id].content:
                raise ChunkingError(f"BM25 source text differs from chunk {entry.chunk_id}")

    def _embed(self, chunking: ChunkingResult) -> tuple[ChunkEmbedding, ...]:
        provider = self._embedding_provider
        if provider is None or not chunking.chunks:
            return ()
        if not provider.embedding_model.strip() or provider.embedding_dimension <= 0:
            raise EmbeddingError("Embedding provider model and dimension must be configured")
        try:
            vectors = provider.embed_batch(tuple(chunk.content for chunk in chunking.chunks))
        except Exception as exc:
            raise EmbeddingError("Batch embedding generation failed") from exc
        if len(vectors) != len(chunking.chunks):
            raise EmbeddingError("Embedding provider returned an incomplete batch")
        embeddings: list[ChunkEmbedding] = []
        for chunk, vector in zip(chunking.chunks, vectors, strict=True):
            values = tuple(float(value) for value in vector)
            if len(values) != provider.embedding_dimension:
                raise EmbeddingError(f"Embedding dimension is invalid for chunk {chunk.chunk_id}")
            if not all(math.isfinite(value) for value in values):
                raise EmbeddingError(f"Embedding vector is non-finite for chunk {chunk.chunk_id}")
            embeddings.append(
                ChunkEmbedding(
                    chunk_id=chunk.chunk_id,
                    embedding_model=provider.embedding_model,
                    embedding_dimension=provider.embedding_dimension,
                    vector=values,
                )
            )
        return tuple(embeddings)

    @staticmethod
    def _validate_bundle(filing: StructuredFiling, bundle: ChunkIndexBundle) -> None:
        reference = filing.raw_filing.filing_reference
        if bundle.filing_id != reference.accession_number:
            raise ChunkingError("Index bundle filing ID does not match the input filing")
        if bundle.document_id != reference.primary_document:
            raise ChunkingError("Index bundle document ID does not match the input filing")
        source_contexts: dict[str, StructureContext | None] = {}
        for element in filing.elements:
            if element.element_id:
                source_contexts[element.element_id] = getattr(element, "structure_context", None)
        for chunk in bundle.chunks:
            metadata = chunk.metadata
            if (
                metadata.company != reference.company_name
                or metadata.ticker != reference.ticker
                or metadata.cik != reference.cik
                or metadata.accession_number != reference.accession_number
                or metadata.form_type != reference.filing_type
                or metadata.filing_date != reference.filing_date
                or metadata.period_of_report != reference.report_date
            ):
                raise ChunkingError(f"Chunk {chunk.chunk_id} filing metadata is inconsistent")
            contexts: list[StructureContext] = []
            for source_id in chunk.provenance.source_element_ids:
                context = source_contexts.get(source_id) if source_id is not None else None
                if context is not None:
                    contexts.append(context)
            if contexts:
                expected = contexts[0]
                if any(context != expected for context in contexts):
                    raise ChunkingError(f"Chunk {chunk.chunk_id} spans conflicting SEC structure")
                _validate_structure_metadata(chunk.chunk_id, metadata, expected)
        for embedding in bundle.embeddings:
            if embedding.chunk_id not in {chunk.chunk_id for chunk in bundle.chunks}:
                raise EmbeddingError("Embedding does not resolve to a canonical chunk")

    def _validate_index_resolution(self, bundle: ChunkIndexBundle) -> None:
        bm25_by_id = {entry.chunk_id: entry for entry in bundle.bm25_representations}
        embedding_by_id = {entry.chunk_id: entry for entry in bundle.embeddings}
        for chunk in bundle.chunks:
            if self._index_repository.resolve_chunk(chunk.chunk_id) != chunk:
                raise IndexPersistenceError(
                    f"Index cannot resolve canonical chunk {chunk.chunk_id}"
                )
            if self._index_repository.resolve_bm25(chunk.chunk_id) != bm25_by_id[chunk.chunk_id]:
                raise IndexPersistenceError(f"Index cannot resolve BM25 for chunk {chunk.chunk_id}")
            if self._index_repository.resolve_metadata(chunk.chunk_id) != chunk.metadata:
                raise IndexPersistenceError(
                    f"Index cannot resolve metadata for chunk {chunk.chunk_id}"
                )
            expected_embedding = embedding_by_id.get(chunk.chunk_id)
            if self._index_repository.resolve_embedding(chunk.chunk_id) != expected_embedding:
                raise IndexPersistenceError(
                    f"Index cannot resolve embedding for chunk {chunk.chunk_id}"
                )

    def _metrics(
        self,
        filing: StructuredFiling,
        chunking: ChunkingResult,
        embeddings: tuple[ChunkEmbedding, ...],
    ) -> ChunkingMetrics:
        counts = chunking.token_counts
        chunks = chunking.chunks
        page_count = sum(
            chunk.provenance.page_start is not None or chunk.provenance.page_end is not None
            for chunk in chunks
        )
        provenance_count = sum(
            bool(chunk.provenance.source_element_ids) and all(chunk.provenance.source_element_ids)
            for chunk in chunks
        )
        return ChunkingMetrics(
            input_element_count=len(filing.elements),
            output_chunk_count=len(chunks),
            narrative_chunk_count=sum(chunk.chunk_type.value == "narrative" for chunk in chunks),
            table_chunk_count=sum(chunk.chunk_type.value == "table" for chunk in chunks),
            list_chunk_count=sum(chunk.chunk_type.value == "list" for chunk in chunks),
            other_chunk_count=sum(chunk.chunk_type.value == "other" for chunk in chunks),
            average_chunk_tokens=sum(counts) / len(counts) if counts else 0.0,
            maximum_chunk_tokens=max(counts, default=0),
            chunks_with_page_references=page_count,
            chunks_without_page_references=len(chunks) - page_count,
            chunks_with_provenance=provenance_count,
            chunks_with_missing_provenance=len(chunks) - provenance_count,
            embedding_count=len(embeddings),
            embedding_failures=0,
            index_document_count=self._index_repository.document_count,
        )


def _validate_structure_metadata(
    chunk_id: str,
    metadata: ChunkMetadata,
    context: StructureContext,
) -> None:
    if (
        metadata.part != context.part
        or metadata.item != context.item
        or metadata.section != context.section
        or metadata.subsection != context.subsection
    ):
        raise ChunkingError(f"Chunk {chunk_id} SEC structure metadata is inconsistent")
