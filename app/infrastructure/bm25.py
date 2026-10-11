from __future__ import annotations

import re
from collections.abc import Sequence

from app.domain.chunks import BM25Representation, Chunk

_TOKEN = re.compile(r"\$?\d+(?:[,.]\d+)*(?:\.\d+)?%?|[A-Za-z0-9]+(?:[&'’./-][A-Za-z0-9]+)*")


class BM25TextRepresentationBuilder:
    def build(self, chunks: Sequence[Chunk]) -> tuple[BM25Representation, ...]:
        seen_ids: set[str] = set()
        representations: list[BM25Representation] = []
        for chunk in chunks:
            if chunk.chunk_id in seen_ids:
                raise ValueError(f"Duplicate chunk ID in BM25 input: {chunk.chunk_id}")
            seen_ids.add(chunk.chunk_id)
            searchable_text = "\n".join(
                value
                for value in (
                    chunk.metadata.company,
                    chunk.metadata.ticker,
                    chunk.metadata.part,
                    chunk.metadata.item,
                    chunk.metadata.section,
                    chunk.metadata.subsection,
                    chunk.content,
                )
                if value
            )
            representations.append(
                BM25Representation(
                    chunk_id=chunk.chunk_id,
                    text=chunk.content,
                    tokens=tuple(_TOKEN.findall(searchable_text)),
                )
            )
        return tuple(representations)
