from __future__ import annotations

from collections import Counter

from lxml import etree


class ElementIdentityRegistry:
    def __init__(self, root: etree._Element) -> None:
        source_ids = [node.get("id") for node in root.iter() if node.get("id")]
        self._source_id_counts = Counter(source_ids)
        self._reserved_ids = set(source_ids)
        self._assigned_ids: set[str] = set()
        self._identities: dict[etree._Element, tuple[str, str | None]] = {}
        self._next_generated_id = 1

    def identify(self, node: etree._Element) -> tuple[str, str | None]:
        existing = self._identities.get(node)
        if existing is not None:
            return existing

        source_anchor = node.get("id") or None
        if source_anchor and self._source_id_counts[source_anchor] == 1:
            element_id = source_anchor
        else:
            element_id = self._new_generated_id()
        self._assigned_ids.add(element_id)
        identity = (element_id, source_anchor)
        self._identities[node] = identity
        return identity

    def _new_generated_id(self) -> str:
        while True:
            candidate = f"elem-{self._next_generated_id:06d}"
            self._next_generated_id += 1
            if candidate not in self._reserved_ids and candidate not in self._assigned_ids:
                return candidate
