from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkingSettings:
    target_chunk_tokens: int = 800
    max_chunk_tokens: int = 1000
    min_chunk_tokens: int = 100
    overlap_tokens: int = 100
    chunking_version: str = "1"
    tokenizer_encoding: str = "cl100k_base"

    def __post_init__(self) -> None:
        if self.target_chunk_tokens <= 0 or self.max_chunk_tokens <= 0:
            raise ValueError("Chunk token limits must be positive")
        if self.target_chunk_tokens > self.max_chunk_tokens:
            raise ValueError("Target chunk tokens cannot exceed the maximum")
        if self.min_chunk_tokens < 0 or self.min_chunk_tokens > self.max_chunk_tokens:
            raise ValueError("Minimum chunk tokens must be between zero and the maximum")
        if self.overlap_tokens < 0 or self.overlap_tokens >= self.max_chunk_tokens:
            raise ValueError("Overlap tokens must be non-negative and below the maximum")
        if not self.chunking_version.strip() or not self.tokenizer_encoding.strip():
            raise ValueError("Chunking version and tokenizer encoding are required")
