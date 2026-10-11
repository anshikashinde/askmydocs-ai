from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.domain.chunks import (
    BM25Representation,
    Chunk,
    ChunkEmbedding,
    ChunkIndexBundle,
    ChunkMetadata,
)


class Tokenizer(Protocol):
    def encode(self, text: str) -> tuple[int, ...]: ...

    def decode(self, tokens: Sequence[int]) -> str: ...

    def split_text(self, text: str, max_tokens: int) -> tuple[str, ...]: ...


class BM25RepresentationBuilder(Protocol):
    def build(self, chunks: Sequence[Chunk]) -> tuple[BM25Representation, ...]: ...


class EmbeddingProvider(Protocol):
    @property
    def embedding_model(self) -> str: ...

    @property
    def embedding_dimension(self) -> int: ...

    def embed_text(self, text: str) -> Sequence[float]: ...

    def embed_batch(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class ChunkIndexRepository(Protocol):
    def replace_filing(self, bundle: ChunkIndexBundle) -> None: ...

    def resolve_chunk(self, chunk_id: str) -> Chunk | None: ...

    def resolve_bm25(self, chunk_id: str) -> BM25Representation | None: ...

    def resolve_embedding(self, chunk_id: str) -> ChunkEmbedding | None: ...

    def resolve_metadata(self, chunk_id: str) -> ChunkMetadata | None: ...

    @property
    def document_count(self) -> int: ...
