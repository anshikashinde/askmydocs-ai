from __future__ import annotations

from app.application.errors import IndexPersistenceError
from app.domain.chunks import (
    BM25Representation,
    Chunk,
    ChunkEmbedding,
    ChunkIndexBundle,
    ChunkMetadata,
)


class InMemoryChunkIndexRepository:
    def __init__(self) -> None:
        self._chunks: dict[str, Chunk] = {}
        self._bm25: dict[str, BM25Representation] = {}
        self._embeddings: dict[str, ChunkEmbedding] = {}
        self._metadata: dict[str, ChunkMetadata] = {}
        self._filing_chunks: dict[tuple[str, str], set[str]] = {}

    def replace_filing(self, bundle: ChunkIndexBundle) -> None:
        chunk_map = {chunk.chunk_id: chunk for chunk in bundle.chunks}
        bm25_map = {entry.chunk_id: entry for entry in bundle.bm25_representations}
        embedding_map = {entry.chunk_id: entry for entry in bundle.embeddings}
        if len(chunk_map) != len(bundle.chunks):
            raise IndexPersistenceError("Index bundle contains duplicate chunk IDs")
        if len(bm25_map) != len(bundle.bm25_representations):
            raise IndexPersistenceError("Index bundle contains duplicate BM25 IDs")
        if len(embedding_map) != len(bundle.embeddings):
            raise IndexPersistenceError("Index bundle contains duplicate embedding IDs")
        if set(chunk_map) != set(bm25_map):
            raise IndexPersistenceError("Every canonical chunk must have one BM25 representation")
        if not set(embedding_map).issubset(chunk_map):
            raise IndexPersistenceError("Embedding references an unknown canonical chunk")

        for chunk_id, chunk in chunk_map.items():
            if bm25_map[chunk_id].text != chunk.content:
                raise IndexPersistenceError(f"BM25 text differs from canonical chunk {chunk_id}")
            if chunk.provenance.filing_id != bundle.filing_id:
                raise IndexPersistenceError(f"Chunk {chunk_id} has the wrong filing identity")
            if chunk.metadata.document_id not in (None, bundle.document_id):
                raise IndexPersistenceError(f"Chunk {chunk_id} has the wrong document identity")
        for chunk_id, embedding in embedding_map.items():
            if (
                not embedding.embedding_model
                or embedding.embedding_dimension <= 0
                or embedding.embedding_dimension != len(embedding.vector)
            ):
                raise IndexPersistenceError(f"Embedding metadata is invalid for chunk {chunk_id}")

        filing_key = (bundle.filing_id, bundle.document_id)
        old_ids = self._filing_chunks.get(filing_key, set())
        collisions = set(chunk_map).intersection(self._chunks).difference(old_ids)
        if collisions:
            raise IndexPersistenceError(
                f"Chunk IDs already belong to another filing: {sorted(collisions)}"
            )

        for chunk_id in old_ids:
            self._chunks.pop(chunk_id, None)
            self._bm25.pop(chunk_id, None)
            self._embeddings.pop(chunk_id, None)
            self._metadata.pop(chunk_id, None)
        self._chunks.update(chunk_map)
        self._bm25.update(bm25_map)
        self._embeddings.update(embedding_map)
        self._metadata.update({chunk_id: chunk.metadata for chunk_id, chunk in chunk_map.items()})
        self._filing_chunks[filing_key] = set(chunk_map)

    def resolve_chunk(self, chunk_id: str) -> Chunk | None:
        return self._chunks.get(chunk_id)

    def resolve_bm25(self, chunk_id: str) -> BM25Representation | None:
        return self._bm25.get(chunk_id)

    def resolve_embedding(self, chunk_id: str) -> ChunkEmbedding | None:
        return self._embeddings.get(chunk_id)

    def resolve_metadata(self, chunk_id: str) -> ChunkMetadata | None:
        return self._metadata.get(chunk_id)

    @property
    def document_count(self) -> int:
        return len(self._chunks)
