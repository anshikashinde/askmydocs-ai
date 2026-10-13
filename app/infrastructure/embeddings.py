from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from app.application.errors import EmbeddingError


class SentenceTransformerEmbeddingProvider:
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        *,
        cache_dir: str | None = None,
        device: str = "cpu",
    ) -> None:
        self._model_name = model_name.strip() or "sentence-transformers/all-MiniLM-L6-v2"
        self._cache_dir = cache_dir
        self._device = device or "cpu"
        self._model: Any | None = None
        self._embedding_dimension: int | None = None

    @property
    def embedding_model(self) -> str:
        return self._model_name

    @property
    def embedding_dimension(self) -> int:
        return self._resolve_dimension()

    def embed_text(self, text: str) -> Sequence[float]:
        if not isinstance(text, str):
            raise EmbeddingError("Embedding input must be a string")
        values = self._encode((text,))
        return values[0]

    def embed_batch(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        if texts is None:
            raise EmbeddingError("Embedding input cannot be null")
        normalized = tuple(str(text) for text in texts)
        return self._encode(normalized)

    def _encode(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            return ()
        model = self._load_model()
        try:
            encoded = model.encode(
                list(texts),
                convert_to_numpy=True,
                normalize_embeddings=False,
                device=self._device,
            )
        except Exception as exc:
            raise EmbeddingError("Batch embedding generation failed") from exc
        vectors = encoded if isinstance(encoded, list) else encoded.tolist()
        if len(vectors) != len(texts):
            raise EmbeddingError("Embedding provider returned an incomplete batch")
        output: list[tuple[float, ...]] = []
        for index, raw in enumerate(vectors):
            vector = tuple(float(value) for value in raw)
            if not vector:
                raise EmbeddingError(f"Embedding vector for text {index} is empty")
            if not all(math.isfinite(value) for value in vector):
                raise EmbeddingError(f"Embedding vector for text {index} is non-finite")
            if self.embedding_dimension > 0 and len(vector) != self.embedding_dimension:
                raise EmbeddingError(
                    f"Embedding dimension is invalid for text {index}: expected {self.embedding_dimension}, got {len(vector)}"
                )
            output.append(vector)
        return tuple(output)

    def _load_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise EmbeddingError(
                    "sentence-transformers is required for local embedding generation"
                ) from exc
            try:
                self._model = SentenceTransformer(
                    self._model_name,
                    cache_folder=self._cache_dir,
                    device=self._device,
                )
            except Exception as exc:
                raise EmbeddingError(
                    f"Model '{self._model_name}' could not be loaded locally"
                ) from exc
            self._embedding_dimension = self._detect_dimension(self._model)
        return self._model

    def _resolve_dimension(self) -> int:
        if self._embedding_dimension is not None:
            return self._embedding_dimension
        model = self._load_model()
        self._embedding_dimension = self._detect_dimension(model)
        return self._embedding_dimension

    @staticmethod
    def _detect_dimension(model: Any) -> int:
        if hasattr(model, "get_sentence_embedding_dimension"):
            return int(model.get_sentence_embedding_dimension())
        try:
            sample = model.encode(["test"], convert_to_numpy=True, normalize_embeddings=False)
        except Exception as exc:  # pragma: no cover - fallback guard
            raise EmbeddingError(
                "Embedding model did not produce a valid output dimension"
            ) from exc
        dimension = sample.shape[-1] if hasattr(sample, "shape") else len(sample[0])
        if dimension <= 0:
            raise EmbeddingError("Embedding model did not produce a valid output dimension")
        return int(dimension)


__all__ = ["SentenceTransformerEmbeddingProvider"]
