from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.application.chunk_indexing import FilingIndexPreparationService
from app.application.chunking import StructuredFilingChunker
from app.application.chunking_ports import (
    BM25RepresentationBuilder,
    ChunkIndexRepository,
    EmbeddingProvider,
)
from app.application.filing_normalization import normalize_structured_filing
from app.domain.chunks import ChunkIndexBundle
from app.domain.filings import StructuredFiling
from app.infrastructure.vector_index import LocalVectorIndex


@dataclass(frozen=True)
class IngestionResult:
    bundle: ChunkIndexBundle
    vector_index: LocalVectorIndex | None
    metrics: Any


class FilingIngestionService:
    def __init__(
        self,
        *,
        filing_service: Any | None = None,
        parser: Any | None = None,
        chunker: StructuredFilingChunker,
        bm25_builder: BM25RepresentationBuilder,
        index_repository: ChunkIndexRepository,
        embedding_provider: EmbeddingProvider,
        vector_index: LocalVectorIndex | None = None,
        storage_directory: str | Path | None = None,
    ) -> None:
        self._filing_service = filing_service
        self._parser = parser
        self._prepare_service = FilingIndexPreparationService(
            chunker=chunker,
            bm25_builder=bm25_builder,
            index_repository=index_repository,
            embedding_provider=embedding_provider,
        )
        self._vector_index = vector_index
        self._storage_directory = Path(storage_directory) if storage_directory is not None else None
        if self._vector_index is None and self._storage_directory is not None:
            self._vector_index = LocalVectorIndex(
                model_name=embedding_provider.embedding_model,
                dimension=embedding_provider.embedding_dimension,
                directory=self._storage_directory,
            )

    def ingest_filing(self, filing: StructuredFiling) -> IngestionResult:
        prepared = self._prepare_service.prepare(filing)
        if self._vector_index is not None:
            self._vector_index.replace_filing(prepared.bundle)
            if self._storage_directory is not None:
                self._vector_index.persist(self._storage_directory / "vector-index.json")
                self._vector_index.persist(self._storage_directory / "chunk-index.json")
        return IngestionResult(
            bundle=prepared.bundle,
            vector_index=self._vector_index,
            metrics=prepared.metrics,
        )

    def ingest_latest_filing(self, ticker: str, filing_type: str) -> IngestionResult:
        if self._filing_service is None or self._parser is None:
            raise ValueError("The ingestion service requires both a filing service and parser")
        reference, raw_filing = self._filing_service.fetch_latest_filing(ticker, filing_type)
        structured = self._parser.parse(raw_filing)
        structured = normalize_structured_filing(structured)
        return self.ingest_filing(structured)

    def ensure_indexed(self, filing: StructuredFiling) -> IngestionResult:
        if self._vector_index is not None:
            filing_id = filing.raw_filing.filing_reference.accession_number
            if self._vector_index.has_filing(filing_id):
                prepared = self._prepare_service.prepare(filing)
                return IngestionResult(
                    bundle=prepared.bundle,
                    vector_index=self._vector_index,
                    metrics=prepared.metrics,
                )
        return self.ingest_filing(filing)


__all__ = ["FilingIngestionService", "IngestionResult"]
