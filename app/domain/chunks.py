from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

from app.domain.filings import DocumentElement


class ChunkType(StrEnum):
    NARRATIVE = "narrative"
    TABLE = "table"
    LIST = "list"
    OTHER = "other"


@dataclass(frozen=True)
class ChunkMetadata:
    company: str | None
    ticker: str | None
    cik: str | None
    accession_number: str | None
    form_type: str | None
    filing_date: str | None
    period_of_report: str | None
    part: str | None
    item: str | None
    section: str | None
    subsection: str | None
    document_id: str | None
    source_element_ids: tuple[str | None, ...]
    source_url: str | None
    html_anchors: tuple[str | None, ...]
    page_start: int | None
    page_end: int | None
    table_id: str | None = None
    parent_table_id: str | None = None
    table_chunk_index: int | None = None
    total_table_chunks: int | None = None
    list_id: str | None = None
    list_chunk_index: int | None = None
    total_list_chunks: int | None = None


@dataclass(frozen=True)
class ChunkSourceReference:
    element_id: str | None
    filing_id: str | None
    document_id: str | None
    document_order: int | None
    source_element_type: str | None
    source_url: str | None
    html_anchor: str | None
    start_offset: int | None
    end_offset: int | None
    page_number: int | None


@dataclass(frozen=True)
class ChunkProvenance:
    filing_id: str | None
    document_id: str | None
    source_element_ids: tuple[str | None, ...]
    source_url: str | None
    html_anchors: tuple[str | None, ...]
    start_offset: int | None
    end_offset: int | None
    page_start: int | None
    page_end: int | None
    source_references: tuple[ChunkSourceReference, ...]


@dataclass(frozen=True)
class ChunkRelationships:
    previous_chunk_id: str | None = None
    next_chunk_id: str | None = None
    parent_chunk_id: str | None = None


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    chunk_type: ChunkType
    content: str
    metadata: ChunkMetadata
    provenance: ChunkProvenance
    relationships: ChunkRelationships
    chunking_version: str
    structured_content: DocumentElement | None = None
    xbrl_fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class BM25Representation:
    chunk_id: str
    text: str
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class ChunkEmbedding:
    chunk_id: str
    embedding_model: str
    embedding_dimension: int
    vector: tuple[float, ...]


@dataclass(frozen=True)
class ChunkIndexBundle:
    filing_id: str
    document_id: str
    chunks: tuple[Chunk, ...]
    bm25_representations: tuple[BM25Representation, ...]
    embeddings: tuple[ChunkEmbedding, ...] = ()


def generate_chunk_id(
    *,
    filing_id: str | None,
    document_id: str | None,
    source_element_ids: tuple[str | None, ...],
    source_position: int,
    chunking_version: str,
    configuration_key: str,
    content: str,
) -> str:
    identity = json.dumps(
        {
            "filing_id": filing_id,
            "document_id": document_id,
            "source_element_ids": source_element_ids,
            "source_position": source_position,
            "chunking_version": chunking_version,
            "configuration_key": configuration_key,
            "content": content,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"chunk-{digest}"
