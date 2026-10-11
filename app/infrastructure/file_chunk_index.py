from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.application.errors import IndexPersistenceError
from app.domain.chunks import (
    BM25Representation,
    Chunk,
    ChunkEmbedding,
    ChunkIndexBundle,
    ChunkMetadata,
    ChunkProvenance,
    ChunkRelationships,
    ChunkSourceReference,
    ChunkType,
)
from app.domain.filings import (
    Footnote,
    Heading,
    Link,
    ListElement,
    ListItem,
    OtherStructuredElement,
    PageBreak,
    Paragraph,
    Provenance,
    StructureContext,
    Table,
    TableCell,
    TableRow,
    TableType,
)
from app.infrastructure.chunk_index import InMemoryChunkIndexRepository


class FileSystemChunkIndexRepository:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._cache = InMemoryChunkIndexRepository()
        if not directory.exists():
            return
        for snapshot in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(snapshot.read_text(encoding="utf-8"))
                self._cache.replace_filing(_bundle_from_dict(payload))
            except (IndexPersistenceError, OSError, TypeError, ValueError, KeyError) as exc:
                raise IndexPersistenceError(f"Cannot load chunk index snapshot {snapshot}") from exc

    def replace_filing(self, bundle: ChunkIndexBundle) -> None:
        temporary_path: Path | None = None
        destination = self._snapshot_path(bundle)
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._directory,
                prefix=".chunk-index-",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(
                    _bundle_to_dict(bundle), temporary_file, ensure_ascii=False, sort_keys=True
                )
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            self._cache.replace_filing(bundle)
            os.replace(temporary_path, destination)
        except IndexPersistenceError:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise
        except (OSError, TypeError, ValueError) as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise IndexPersistenceError("Chunk index snapshot could not be persisted") from exc

    def resolve_chunk(self, chunk_id: str) -> Chunk | None:
        return self._cache.resolve_chunk(chunk_id)

    def resolve_bm25(self, chunk_id: str) -> BM25Representation | None:
        return self._cache.resolve_bm25(chunk_id)

    def resolve_embedding(self, chunk_id: str) -> ChunkEmbedding | None:
        return self._cache.resolve_embedding(chunk_id)

    def resolve_metadata(self, chunk_id: str) -> ChunkMetadata | None:
        return self._cache.resolve_metadata(chunk_id)

    @property
    def document_count(self) -> int:
        return self._cache.document_count

    def _snapshot_path(self, bundle: ChunkIndexBundle) -> Path:
        identity = f"{bundle.filing_id}\0{bundle.document_id}".encode()
        digest = hashlib.sha256(identity).hexdigest()
        return self._directory / f"{digest}.json"


def _bundle_to_dict(bundle: ChunkIndexBundle) -> dict[str, Any]:
    return {
        "filing_id": bundle.filing_id,
        "document_id": bundle.document_id,
        "chunks": [_chunk_to_dict(chunk) for chunk in bundle.chunks],
        "bm25_representations": [asdict(entry) for entry in bundle.bm25_representations],
        "embeddings": [asdict(entry) for entry in bundle.embeddings],
    }


def _chunk_to_dict(chunk: Chunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "chunk_type": chunk.chunk_type.value,
        "content": chunk.content,
        "metadata": asdict(chunk.metadata),
        "provenance": asdict(chunk.provenance),
        "relationships": asdict(chunk.relationships),
        "chunking_version": chunk.chunking_version,
        "structured_content": _structured_content_to_dict(chunk.structured_content),
        "xbrl_fact_ids": chunk.xbrl_fact_ids,
    }


def _structured_content_to_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    return {"kind": type(value).__name__, "value": asdict(value)}


def _bundle_from_dict(value: dict[str, Any]) -> ChunkIndexBundle:
    return ChunkIndexBundle(
        filing_id=value["filing_id"],
        document_id=value["document_id"],
        chunks=tuple(_chunk_from_dict(chunk) for chunk in value["chunks"]),
        bm25_representations=tuple(
            BM25Representation(
                chunk_id=entry["chunk_id"],
                text=entry["text"],
                tokens=tuple(entry["tokens"]),
            )
            for entry in value["bm25_representations"]
        ),
        embeddings=tuple(
            ChunkEmbedding(
                chunk_id=entry["chunk_id"],
                embedding_model=entry["embedding_model"],
                embedding_dimension=entry["embedding_dimension"],
                vector=tuple(entry["vector"]),
            )
            for entry in value["embeddings"]
        ),
    )


def _chunk_from_dict(value: dict[str, Any]) -> Chunk:
    metadata = dict(value["metadata"])
    metadata["source_element_ids"] = tuple(metadata["source_element_ids"])
    metadata["html_anchors"] = tuple(metadata["html_anchors"])
    return Chunk(
        chunk_id=value["chunk_id"],
        chunk_type=ChunkType(value["chunk_type"]),
        content=value["content"],
        metadata=ChunkMetadata(**metadata),
        provenance=_provenance_from_dict(value["provenance"]),
        relationships=ChunkRelationships(**value["relationships"]),
        chunking_version=value["chunking_version"],
        structured_content=_structured_content_from_dict(value["structured_content"]),
        xbrl_fact_ids=tuple(value["xbrl_fact_ids"]),
    )


def _provenance_from_dict(value: dict[str, Any]) -> ChunkProvenance:
    return ChunkProvenance(
        filing_id=value["filing_id"],
        document_id=value["document_id"],
        source_element_ids=tuple(value["source_element_ids"]),
        source_url=value["source_url"],
        html_anchors=tuple(value["html_anchors"]),
        start_offset=value["start_offset"],
        end_offset=value["end_offset"],
        page_start=value["page_start"],
        page_end=value["page_end"],
        source_references=tuple(
            ChunkSourceReference(**reference) for reference in value["source_references"]
        ),
    )


def _structured_content_from_dict(value: dict[str, Any] | None) -> Any:
    if value is None:
        return None
    kind = value["kind"]
    content = dict(value["value"])
    if kind == "Table":
        content["headers"] = tuple(content["headers"])
        content["table_type"] = TableType(content["table_type"])
        content["provenance"] = Provenance(**content["provenance"])
        content["structure_context"] = _structure_context_from_dict(content["structure_context"])
        content["rows"] = tuple(_table_row_from_dict(row) for row in content["rows"])
        return Table(**content)
    if kind == "ListElement":
        content["items"] = tuple(_list_item_from_dict(item) for item in content["items"])
        content["provenance"] = Provenance(**content["provenance"])
        content["structure_context"] = _structure_context_from_dict(content["structure_context"])
        return ListElement(**content)
    source_types = {
        "Footnote": Footnote,
        "Heading": Heading,
        "Link": Link,
        "OtherStructuredElement": OtherStructuredElement,
        "PageBreak": PageBreak,
        "Paragraph": Paragraph,
    }
    source_type = source_types.get(kind)
    if source_type is None:
        raise ValueError(f"Unsupported structured chunk content type: {kind}")
    content["provenance"] = Provenance(**content["provenance"])
    if "structure_context" in content:
        content["structure_context"] = _structure_context_from_dict(content["structure_context"])
    return source_type(**content)


def _table_row_from_dict(value: dict[str, Any]) -> TableRow:
    return TableRow(
        cells=tuple(_table_cell_from_dict(cell) for cell in value["cells"]),
        row_index=value["row_index"],
        element_id=value["element_id"],
        provenance=Provenance(**value["provenance"]),
    )


def _table_cell_from_dict(value: dict[str, Any]) -> TableCell:
    return TableCell(**{**value, "provenance": Provenance(**value["provenance"])})


def _list_item_from_dict(value: dict[str, Any]) -> ListItem:
    return ListItem(**{**value, "provenance": Provenance(**value["provenance"])})


def _structure_context_from_dict(value: dict[str, Any] | None) -> StructureContext | None:
    return StructureContext(**value) if value is not None else None
