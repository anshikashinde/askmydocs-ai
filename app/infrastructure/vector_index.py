from __future__ import annotations

import json
import math
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from app.application.errors import EmbeddingError, IndexPersistenceError
from app.domain.chunks import (
    Chunk,
    ChunkEmbedding,
    ChunkIndexBundle,
    ChunkMetadata,
    ChunkProvenance,
)


@dataclass(frozen=True)
class VectorSearchResult:
    chunk_id: str
    score: float
    chunk: Chunk | None
    metadata: ChunkMetadata | None
    provenance: ChunkProvenance | None


class LocalVectorIndex:
    def __init__(
        self,
        model_name: str,
        dimension: int | None = None,
        *,
        directory: str | Path | None = None,
    ) -> None:
        self._model_name = model_name.strip() or "unknown-model"
        self._dimension = int(dimension) if dimension is not None else None
        self._directory = Path(directory) if directory is not None else None
        self._chunks: dict[str, Chunk] = {}
        self._embeddings: dict[str, ChunkEmbedding] = {}

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int | None:
        return self._dimension

    @property
    def document_count(self) -> int:
        return len(self._embeddings)

    def add_or_replace(self, chunk: Chunk, embedding: ChunkEmbedding) -> None:
        self._validate_embedding(embedding)
        self._chunks[chunk.chunk_id] = chunk
        self._embeddings[chunk.chunk_id] = embedding
        if self._dimension is None:
            self._dimension = embedding.embedding_dimension
        if self._dimension != embedding.embedding_dimension:
            raise EmbeddingError(
                f"Embedding dimension mismatch for {chunk.chunk_id}: expected {self._dimension}, got {embedding.embedding_dimension}"
            )
        if self._model_name != "unknown-model":
            self._model_name = embedding.embedding_model

    def replace_filing(self, bundle: ChunkIndexBundle) -> None:
        if not bundle.chunks:
            return
        if self._dimension is None:
            self._dimension = max(
                (entry.embedding_dimension for entry in bundle.embeddings), default=0
            )
        if bundle.embeddings:
            if any(
                entry.embedding_model != bundle.embeddings[0].embedding_model
                for entry in bundle.embeddings
            ):
                raise IndexPersistenceError(
                    "Filing vector index mixes incompatible embedding models"
                )
            self._model_name = bundle.embeddings[0].embedding_model
        for chunk in bundle.chunks:
            embedding = next(
                (entry for entry in bundle.embeddings if entry.chunk_id == chunk.chunk_id), None
            )
            if embedding is None:
                raise IndexPersistenceError(
                    f"Missing embedding for canonical chunk {chunk.chunk_id}"
                )
            self.add_or_replace(chunk, embedding)

    def search(
        self,
        query_vector: Iterable[float],
        *,
        top_k: int = 10,
    ) -> tuple[VectorSearchResult, ...]:
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero")
        if not self._embeddings:
            return ()
        query = self._normalize_vector(query_vector)
        if self._dimension is not None and len(query) != self._dimension:
            raise EmbeddingError(
                f"Query vector dimension mismatch: expected {self._dimension}, got {len(query)}"
            )

        ranked: list[tuple[float, str]] = []
        for chunk_id, embedding in self._embeddings.items():
            score = _cosine_similarity(query, embedding.vector)
            ranked.append((score, chunk_id))
        ranked.sort(key=lambda item: (-item[0], item[1]))

        results: list[VectorSearchResult] = []
        for score, chunk_id in ranked[:top_k]:
            chunk = self._chunks.get(chunk_id)
            results.append(
                VectorSearchResult(
                    chunk_id=chunk_id,
                    score=score,
                    chunk=chunk,
                    metadata=chunk.metadata if chunk is not None else None,
                    provenance=chunk.provenance if chunk is not None else None,
                )
            )
        return tuple(results)

    def persist(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path is not None else self._directory
        if target is None:
            raise IndexPersistenceError("A directory is required to persist the vector index")
        target = target if target.suffix == ".json" else target / "vector-index.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_name": self._model_name,
            "dimension": self._dimension,
            "entries": [
                {"chunk_id": chunk_id, "vector": list(entry.vector)}
                for chunk_id, entry in sorted(self._embeddings.items())
            ],
        }
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(target.parent),
                prefix=".vector-index-",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(payload, temporary_file, ensure_ascii=False, sort_keys=True)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, target)
        except (OSError, TypeError, ValueError) as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise IndexPersistenceError("Vector index snapshot could not be persisted") from exc
        return target

    @classmethod
    def load(cls, path: str | Path, model_name: str | None = None) -> LocalVectorIndex:
        target = Path(path)
        if not target.exists():
            raise IndexPersistenceError(f"Vector index snapshot does not exist: {target}")
        payload = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise IndexPersistenceError("Vector index snapshot is not a JSON object")
        dimension = payload.get("dimension")
        loaded_model_name = payload.get("model_name", model_name or "unknown-model")
        index = cls(
            model_name=str(loaded_model_name),
            dimension=int(dimension) if dimension is not None else None,
        )
        for entry in payload.get("entries", []):
            if not isinstance(entry, dict):
                raise IndexPersistenceError("Vector index snapshot contains malformed entries")
            chunk_id = str(entry["chunk_id"])
            vector = tuple(float(value) for value in entry["vector"])
            if index.dimension is not None and len(vector) != index.dimension:
                raise IndexPersistenceError(
                    f"Vector index entry {chunk_id} has the wrong dimension"
                )
            index._embeddings[chunk_id] = ChunkEmbedding(
                chunk_id=chunk_id,
                embedding_model=index.model_name,
                embedding_dimension=index.dimension or len(vector),
                vector=vector,
            )
        if index.dimension is None and index._embeddings:
            index._dimension = len(next(iter(index._embeddings.values())).vector)
        return index

    def has_filing(self, filing_id: str) -> bool:
        return any(chunk.provenance.filing_id == filing_id for chunk in self._chunks.values())

    @staticmethod
    def _normalize_vector(vector: Iterable[float]) -> tuple[float, ...]:
        values = tuple(float(value) for value in vector)
        if not values:
            raise EmbeddingError("Vector input is empty")
        if not all(math.isfinite(value) for value in values):
            raise EmbeddingError("Vector input contains non-finite values")
        return values

    @staticmethod
    def _validate_embedding(embedding: ChunkEmbedding) -> None:
        if not embedding.embedding_model.strip():
            raise EmbeddingError("Embedding model identity cannot be blank")
        if embedding.embedding_dimension <= 0:
            raise EmbeddingError("Embedding dimension must be positive")
        if len(embedding.vector) != embedding.embedding_dimension:
            raise EmbeddingError("Embedding metadata does not match the vector length")
        if not all(math.isfinite(value) for value in embedding.vector):
            raise EmbeddingError("Embedding vector contains non-finite values")


def _cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise EmbeddingError("Cosine similarity requires equal-length vectors")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    return dot / (left_norm * right_norm)


InMemoryVectorIndex = LocalVectorIndex
CosineVectorIndex = LocalVectorIndex
__all__ = ["LocalVectorIndex", "InMemoryVectorIndex", "CosineVectorIndex", "VectorSearchResult"]
