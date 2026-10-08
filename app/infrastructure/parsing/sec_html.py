from __future__ import annotations

import re
from collections import Counter

from lxml import etree

from app.application.errors import DocumentParseError, UnsupportedFormatError
from app.domain.filings import (
    DocumentElement,
    Footnote,
    Heading,
    Link,
    ListElement,
    ListItem,
    OtherStructuredElement,
    PageBreak,
    Paragraph,
    Provenance,
    RawFiling,
    SourceFormat,
    StructureContext,
    StructuredFiling,
    Table,
    TableCell,
    TableRow,
    ValidationIssue,
    XBRLContext,
    XBRLContinuation,
    XBRLDimension,
    XBRLFact,
    XBRLUnit,
)
from app.infrastructure.parsing.sec_structure import extract_sec_structure

_IX_FACT_TAGS = {"nonnumeric", "nonfraction"}
_HTML_ELEMENTS = {"html", "head", "body"}
_STRUCTURED_TAGS = {"blockquote", "pre", "dl", "dt", "dd", "figure", "figcaption"}
_PART_HEADING = re.compile(r"^\s*part\s+(?:i{1,3}|iv)\b", re.IGNORECASE)
_ITEM_HEADING = re.compile(r"^\s*item\s+\d+[a-z]?\s*[.\-:]", re.IGNORECASE)
_PAGE_NUMBER = re.compile(r"(?:form\s+(?:10-k|10-q)\s*\|\s*)(\d{1,4})\s*$", re.IGNORECASE)
_PAGE_BREAK_STYLE = re.compile(
    r"page-break-(?:after|before|inside)\s*:\s*(?:always|avoid)", re.IGNORECASE
)


class SECHTMLParser:
    def parse(self, raw_filing: RawFiling) -> StructuredFiling:
        source_format = detect_source_format(raw_filing)
        if source_format is SourceFormat.UNSUPPORTED:
            raise UnsupportedFormatError("SEC primary document is not HTML, XHTML, or Inline XBRL")
        if source_format is SourceFormat.MALFORMED:
            raise DocumentParseError("SEC primary document is empty or malformed")

        tree, parser_errors = _parse_tree(raw_filing, source_format)
        if tree is None:
            raise DocumentParseError("Could not construct a document tree")

        root = tree.getroot()
        issues: list[ValidationIssue] = []
        if parser_errors:
            issues.append(
                ValidationIssue(
                    code="recoverable_markup_errors",
                    message=f"lxml recovered from {len(parser_errors)} markup issue(s)",
                )
            )

        document_id = raw_filing.filename
        filing_id = raw_filing.filing_reference.accession_number
        metadata = _extract_document_metadata(root)
        elements = extract_sec_structure(
            _extract_elements(root, raw_filing, filing_id, document_id)
        )
        facts, contexts, units, continuations, xbrl_issues = _extract_xbrl(
            root,
            raw_filing,
            filing_id,
            document_id,
        )
        issues.extend(xbrl_issues)
        issues.extend(_validate_representation(elements, facts, contexts, units))

        return StructuredFiling(
            raw_filing=raw_filing,
            source_format=source_format,
            document_metadata=metadata,
            elements=elements,
            xbrl_facts=facts,
            xbrl_contexts=contexts,
            xbrl_units=units,
            continuations=continuations,
            validation_issues=tuple(issues),
        )


def detect_source_format(raw_filing: RawFiling) -> SourceFormat:
    content = raw_filing.content
    if not content:
        return SourceFormat.MALFORMED

    sample = content[:65536].lstrip(b"\xef\xbb\xbf\x00\t\r\n ").lower()
    content_type = (raw_filing.content_type or "").lower()
    filename = raw_filing.filename.lower()
    if content_type.startswith(("application/pdf", "image/", "application/zip")):
        return SourceFormat.UNSUPPORTED

    if (
        b"ix:" in sample
        or b"inline-xbrl" in sample
        or b"inlinexbrl" in sample
        or "inline xbrl" in content_type
    ):
        return SourceFormat.INLINE_XBRL
    if (
        "application/xhtml+xml" in content_type
        or filename.endswith((".xhtml", ".xml"))
        or b"http://www.w3.org/1999/xhtml" in sample
    ):
        return SourceFormat.XHTML
    if (
        "text/html" in content_type
        or filename.endswith((".htm", ".html"))
        or re.search(rb"<(?:!doctype\s+html|html|head|body)(?:\s|>)", sample)
    ):
        return SourceFormat.HTML
    return SourceFormat.UNSUPPORTED


def _parse_tree(
    raw_filing: RawFiling,
    source_format: SourceFormat,
) -> tuple[etree._ElementTree | None, tuple[str, ...]]:
    try:
        if source_format is SourceFormat.XHTML:
            parser = etree.XMLParser(
                recover=True,
                resolve_entities=False,
                no_network=True,
                load_dtd=False,
                huge_tree=False,
                remove_comments=False,
            )
        else:
            parser = etree.HTMLParser(
                recover=True,
                no_network=True,
                huge_tree=False,
                remove_comments=False,
            )
        root = etree.fromstring(raw_filing.content, parser=parser)
    except (etree.LxmlError, ValueError) as exc:
        raise DocumentParseError("SEC primary document could not be parsed") from exc
    if root is None:
        return None, ()
    errors = tuple(entry.message for entry in parser.error_log)
    return root.getroottree(), errors


def _extract_document_metadata(root: etree._Element) -> tuple[tuple[str, str], ...]:
    metadata: list[tuple[str, str]] = []
    title = next((node for node in root.iter() if _local_name(node) == "title"), None)
    if title is not None:
        metadata.append(("title", _text(title)))
    for node in root.iter():
        if _local_name(node) != "meta":
            continue
        key = node.get("name") or node.get("property") or node.get("http-equiv")
        value = node.get("content")
        if key and value is not None:
            metadata.append((key, value))
    language = root.get("lang") or root.get("xml:lang")
    if language:
        metadata.append(("language", language))
    return tuple(metadata)


def _extract_elements(
    root: etree._Element,
    raw_filing: RawFiling,
    filing_id: str,
    document_id: str,
) -> tuple[DocumentElement, ...]:
    output: list[DocumentElement] = []
    order = 0
    structure_context: StructureContext | None = None
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        tag = _local_name(node)
        if tag in _HTML_ELEMENTS or _inside(node, {"head", "script", "style"}):
            continue
        is_page_break = tag == "hr" or bool(_PAGE_BREAK_STYLE.search(node.get("style", "")))
        is_heading_candidate = tag in {f"h{level}" for level in range(1, 7)} or tag == "p"
        is_styled_block = tag == "div" and bool(
            node.get("style") or node.get("id") or node.get("class")
        )
        if not (
            tag in {"table", "ul", "ol", "a"}
            or is_heading_candidate
            or is_styled_block
            or tag in _STRUCTURED_TAGS
            or is_page_break
            or _is_footnote(node)
        ):
            continue
        if tag == "div" and not _is_footnote(node) and _inside(node, {"table", "li", "ul", "ol"}):
            continue
        text = _text(node)
        is_empty_anchor = tag in {"div", "span"} and bool(node.get("id")) and not text
        if (
            not text
            and tag not in {"hr", "table", "ul", "ol", "a"}
            and not is_page_break
            and not is_empty_anchor
        ):
            continue

        if tag == "table" and not _has_ancestor_tag(node, "table"):
            order += 1
            element = _extract_table(
                node, raw_filing, filing_id, document_id, order, structure_context
            )
            output.append(element)
            continue
        if tag in {"ul", "ol"}:
            items = _extract_list_items(node, raw_filing, filing_id, document_id, order + 1)
            if items:
                order += 1
                parent_item = _nearest_ancestor(node, "li")
                output.append(
                    ListElement(
                        ordered=tag == "ol",
                        items=items,
                        element_id=node.get("id"),
                        document_order=order,
                        provenance=_provenance(
                            raw_filing, filing_id, document_id, order, node, "list"
                        ),
                        structure_context=structure_context,
                        parent_item_id=parent_item.get("id") if parent_item is not None else None,
                    )
                )
            continue
        if _is_footnote(node) and not _has_ancestor_footnote(node):
            order += 1
            output.append(
                Footnote(
                    text=text,
                    reference_id=_footnote_reference(node),
                    element_id=node.get("id"),
                    document_order=order,
                    provenance=_provenance(
                        raw_filing, filing_id, document_id, order, node, "footnote"
                    ),
                    structure_context=structure_context,
                )
            )
            continue
        if tag == "a":
            order += 1
            output.append(
                Link(
                    text=text,
                    href=node.get("href"),
                    element_id=node.get("id"),
                    document_order=order,
                    provenance=_provenance(raw_filing, filing_id, document_id, order, node, "link"),
                    structure_context=structure_context,
                )
            )
            continue
        if is_empty_anchor:
            order += 1
            output.append(
                OtherStructuredElement(
                    tag="anchor",
                    text="",
                    element_id=node.get("id"),
                    document_order=order,
                    provenance=_provenance(
                        raw_filing, filing_id, document_id, order, node, "anchor"
                    ),
                    structure_context=structure_context,
                )
            )
            continue
        if is_page_break:
            order += 1
            output.append(
                PageBreak(
                    page_number=_page_number(node),
                    element_id=node.get("id"),
                    document_order=order,
                    provenance=_provenance(
                        raw_filing, filing_id, document_id, order, node, "page_break"
                    ),
                    structure_context=structure_context,
                )
            )
            continue

        is_sec_heading = bool(_ITEM_HEADING.match(text) or _PART_HEADING.match(text))
        is_heading = (
            tag in {f"h{level}" for level in range(1, 7)}
            or is_sec_heading
            or (is_styled_block and _looks_like_styled_heading(node, text))
        )
        if is_heading and tag in {"p", "div", "span"} and len(text) > 180:
            is_heading = False
        if is_sec_heading and _inside(node, {"table"}):
            is_heading = False
        if is_heading and tag == "div" and _has_same_text_heading_ancestor(node, text):
            is_heading = False
        if is_heading:
            order += 1
            level = int(tag[1]) if len(tag) == 2 and tag[0] == "h" and tag[1].isdigit() else None
            heading = Heading(
                text=text,
                level=level,
                element_id=node.get("id"),
                document_order=order,
                provenance=_provenance(raw_filing, filing_id, document_id, order, node, "heading"),
                structure_context=None,
            )
            output.append(heading)
            continue
        is_leaf_div = tag == "div" and not any(
            isinstance(child.tag, str)
            and _local_name(child) in {"div", "p", "table", "ul", "ol", "blockquote", "pre"}
            for child in node.iterdescendants()
        )
        if tag == "p" or (is_styled_block and is_leaf_div):
            order += 1
            output.append(
                Paragraph(
                    text=text,
                    element_id=node.get("id"),
                    document_order=order,
                    provenance=_provenance(
                        raw_filing, filing_id, document_id, order, node, "paragraph"
                    ),
                    structure_context=structure_context,
                )
            )
            continue
        if tag in _STRUCTURED_TAGS:
            order += 1
            output.append(
                OtherStructuredElement(
                    tag=tag,
                    text=text,
                    element_id=node.get("id"),
                    document_order=order,
                    provenance=_provenance(raw_filing, filing_id, document_id, order, node, tag),
                    structure_context=structure_context,
                )
            )
    return tuple(output)


def _extract_table(
    table_node: etree._Element,
    raw_filing: RawFiling,
    filing_id: str,
    document_id: str,
    order: int,
    structure_context: StructureContext | None,
) -> Table:
    caption_node = next((node for node in table_node if _local_name(node) == "caption"), None)
    headers: list[str] = []
    rows: list[TableRow] = []
    occupied: Counter[int] = Counter()
    for row_index, row_node in enumerate(
        node for node in table_node.iter() if _local_name(node) == "tr"
    ):
        if _nearest_ancestor(row_node, "table") is not table_node:
            continue
        cells: list[TableCell] = []
        column_index = 0
        for cell_node in row_node:
            if _local_name(cell_node) not in {"th", "td"}:
                continue
            while occupied[column_index] > 0:
                occupied[column_index] -= 1
                column_index += 1
            cell_text = _text(cell_node)
            colspan = _positive_int(cell_node.get("colspan"), 1)
            rowspan = _positive_int(cell_node.get("rowspan"), 1)
            role = cell_node.get("scope")
            if _local_name(cell_node) == "th" and role is None:
                role = "column" if row_index == 0 else "row"
            cell = TableCell(
                text=cell_text,
                row_index=row_index,
                column_index=column_index,
                colspan=colspan,
                rowspan=rowspan,
                header_role=role,
                element_id=cell_node.get("id"),
                provenance=_provenance(
                    raw_filing,
                    filing_id,
                    document_id,
                    order,
                    cell_node,
                    "table_header_cell" if _local_name(cell_node) == "th" else "table_cell",
                ),
            )
            cells.append(cell)
            if role and _local_name(cell_node) == "th":
                headers.append(cell_text)
            if rowspan > 1:
                for span_column in range(column_index, column_index + colspan):
                    occupied[span_column] = max(occupied[span_column], rowspan - 1)
            column_index += colspan
        rows.append(
            TableRow(
                cells=tuple(cells),
                row_index=row_index,
                element_id=row_node.get("id"),
                provenance=_provenance(
                    raw_filing, filing_id, document_id, order, row_node, "table_row"
                ),
            )
        )
    return Table(
        caption=_text(caption_node) if caption_node is not None else None,
        headers=tuple(headers),
        rows=tuple(rows),
        element_id=table_node.get("id"),
        document_order=order,
        provenance=_provenance(raw_filing, filing_id, document_id, order, table_node, "table"),
        structure_context=structure_context,
    )


def _extract_list_items(
    list_node: etree._Element,
    raw_filing: RawFiling,
    filing_id: str,
    document_id: str,
    order: int,
) -> tuple[ListItem, ...]:
    result: list[ListItem] = []
    for item in (node for node in list_node.iter() if _local_name(node) == "li"):
        if _nearest_ancestor(item, {"ul", "ol"}) is not list_node:
            continue
        result.append(
            ListItem(
                text=_text_excluding_lists(item),
                position=len(result) + 1,
                element_id=item.get("id"),
                provenance=_provenance(
                    raw_filing, filing_id, document_id, order, item, "list_item"
                ),
            )
        )
    return tuple(result)


def _text_excluding_lists(node: etree._Element) -> str:
    parts: list[str] = []
    for child in node.iter():
        if child is not node and _inside(child, {"ul", "ol"}):
            if child.tail:
                parts.append(child.tail)
            continue
        if child.text:
            parts.append(child.text)
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _extract_xbrl(
    root: etree._Element,
    raw_filing: RawFiling,
    filing_id: str,
    document_id: str,
) -> tuple[
    tuple[XBRLFact, ...],
    tuple[XBRLContext, ...],
    tuple[XBRLUnit, ...],
    tuple[XBRLContinuation, ...],
    tuple[ValidationIssue, ...],
]:
    contexts: list[XBRLContext] = []
    units: list[XBRLUnit] = []
    continuation_nodes: list[etree._Element] = []
    fact_nodes: list[etree._Element] = []
    issues: list[ValidationIssue] = []
    order = 0

    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        tag = _local_name(node)
        if tag == "context":
            order += 1
            contexts.append(_parse_context(node, raw_filing, filing_id, document_id, order))
        elif tag == "unit":
            order += 1
            units.append(_parse_unit(node, raw_filing, filing_id, document_id, order))
        elif tag == "continuation":
            continuation_nodes.append(node)
        elif tag in _IX_FACT_TAGS:
            fact_nodes.append(node)

    continuation_map: dict[str, etree._Element] = {}
    continuations: list[XBRLContinuation] = []
    for node in continuation_nodes:
        order += 1
        continuation_id = node.get("id")
        continued_at = _attribute(node, "continuedAt")
        if continuation_id:
            if continuation_id in continuation_map:
                issues.append(
                    ValidationIssue(
                        code="duplicate_continuation_id",
                        message=f"Duplicate XBRL continuation ID: {continuation_id}",
                        severity="error",
                        element_id=continuation_id,
                    )
                )
            else:
                continuation_map[continuation_id] = node
        continuations.append(
            XBRLContinuation(
                continuation_id=continuation_id,
                continued_at=continued_at,
                text=_text(node),
                source_element_id=node.get("id"),
                provenance=_provenance(
                    raw_filing,
                    filing_id,
                    document_id,
                    order,
                    node,
                    "xbrl_continuation",
                ),
            )
        )

    facts: list[XBRLFact] = []
    for node in fact_nodes:
        order += 1
        continued_at = _attribute(node, "continuedAt")
        continuation_ids: list[str] = []
        continuation_text: list[str] = []
        next_id = continued_at
        visited: set[str] = set()
        while next_id:
            if next_id in visited:
                issues.append(
                    ValidationIssue(
                        code="circular_continuation",
                        message=f"Circular continuation chain at {next_id}",
                        severity="error",
                        element_id=next_id,
                    )
                )
                break
            visited.add(next_id)
            continuation_node = continuation_map.get(next_id)
            if continuation_node is None:
                issues.append(
                    ValidationIssue(
                        code="missing_continuation_target",
                        message=f"XBRL continuation target {next_id} was not found",
                        severity="error",
                        element_id=next_id,
                    )
                )
                break
            continuation_ids.append(next_id)
            continuation_text.append(_text(continuation_node))
            next_id = _attribute(continuation_node, "continuedAt")

        value = _text(node)
        attrs = tuple(sorted((_attribute_name(key), value) for key, value in node.attrib.items()))
        facts.append(
            XBRLFact(
                fact_id=node.get("id"),
                name=_attribute(node, "name"),
                value=value,
                resolved_value=value + "".join(continuation_text),
                fact_type=_local_name(node),
                context_ref=_attribute(node, "contextRef"),
                unit_ref=_attribute(node, "unitRef"),
                decimals=_attribute(node, "decimals"),
                scale=_attribute(node, "scale"),
                sign=_attribute(node, "sign"),
                format=_attribute(node, "format"),
                is_hidden=_inside(node, {"hidden"}),
                continued_at=continued_at,
                continuation_ids=tuple(continuation_ids),
                attributes=attrs,
                normalized_value=None,
                source_element_id=node.get("id"),
                provenance=_provenance(
                    raw_filing,
                    filing_id,
                    document_id,
                    order,
                    node,
                    f"ix:{_local_name(node)}",
                ),
            )
        )

    continuation_ids = [item.continuation_id for item in continuations if item.continuation_id]
    duplicate_ids = {item for item, count in Counter(continuation_ids).items() if count > 1}
    if duplicate_ids:
        # Duplicate nodes were reported above; retain this aggregate issue for a compact summary.
        issues.append(
            ValidationIssue(
                code="duplicate_continuation_ids_present",
                message=f"Duplicate continuation identifiers: {', '.join(sorted(duplicate_ids))}",
                severity="error",
            )
        )

    return tuple(facts), tuple(contexts), tuple(units), tuple(continuations), tuple(issues)


def _parse_context(
    node: etree._Element,
    raw_filing: RawFiling,
    filing_id: str,
    document_id: str,
    order: int,
) -> XBRLContext:
    entity = _first_descendant(node, "identifier")
    instant = _first_descendant(node, "instant")
    start_date = _first_descendant(node, "startdate")
    end_date = _first_descendant(node, "enddate")
    dimensions = tuple(
        XBRLDimension(
            dimension=_attribute(member, "dimension") or "",
            value=_text(member),
            member_type=_local_name(member),
        )
        for member in node.iter()
        if _local_name(member) in {"explicitmember", "typedmember"}
    )
    return XBRLContext(
        context_id=node.get("id", ""),
        entity_identifier=_text(entity) if entity is not None else None,
        period_instant=_text(instant) if instant is not None else None,
        period_start=_text(start_date) if start_date is not None else None,
        period_end=_text(end_date) if end_date is not None else None,
        dimensions=dimensions,
        provenance=_provenance(raw_filing, filing_id, document_id, order, node, "xbrl_context"),
    )


def _parse_unit(
    node: etree._Element,
    raw_filing: RawFiling,
    filing_id: str,
    document_id: str,
    order: int,
) -> XBRLUnit:
    return XBRLUnit(
        unit_id=node.get("id", ""),
        measures=tuple(
            _text(measure) for measure in node.iter() if _local_name(measure) == "measure"
        ),
        provenance=_provenance(raw_filing, filing_id, document_id, order, node, "xbrl_unit"),
    )


def _validate_representation(
    elements: tuple[DocumentElement, ...],
    facts: tuple[XBRLFact, ...],
    contexts: tuple[XBRLContext, ...],
    units: tuple[XBRLUnit, ...],
) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    for element in elements:
        if element.provenance.document_order != element.document_order:
            issues.append(
                ValidationIssue(
                    code="provenance_order_mismatch",
                    message="Element order does not match its provenance order",
                    severity="error",
                    element_id=element.element_id,
                )
            )
    context_ids = {context.context_id for context in contexts}
    unit_ids = {unit.unit_id for unit in units}
    for fact in facts:
        if fact.context_ref and fact.context_ref not in context_ids:
            issues.append(
                ValidationIssue(
                    code="missing_xbrl_context",
                    message=f"Fact references missing XBRL context {fact.context_ref}",
                    element_id=fact.fact_id,
                )
            )
        if fact.unit_ref and fact.unit_ref not in unit_ids:
            issues.append(
                ValidationIssue(
                    code="missing_xbrl_unit",
                    message=f"Fact references missing XBRL unit {fact.unit_ref}",
                    element_id=fact.fact_id,
                )
            )
    return tuple(issues)


def _provenance(
    raw_filing: RawFiling,
    filing_id: str,
    document_id: str,
    order: int,
    node: etree._Element,
    source_element_type: str,
) -> Provenance:
    element_id = node.get("id")
    return Provenance(
        filing_id=filing_id,
        document_id=document_id,
        element_id=element_id,
        source_url=raw_filing.source_url,
        document_order=order,
        start_offset=None,
        end_offset=None,
        html_anchor=element_id,
        page_number=_page_number(node),
        source_element_type=source_element_type,
    )


def _text(node: etree._Element | None) -> str:
    return "".join(node.itertext()) if node is not None else ""


def _local_name(node: etree._Element) -> str:
    tag = node.tag
    if not isinstance(tag, str):
        return ""
    if tag.startswith("{"):
        tag = tag.split("}", 1)[1]
    return tag.rsplit(":", 1)[-1].lower()


def _attribute(node: etree._Element, name: str) -> str | None:
    return next(
        (
            value
            for key, value in node.attrib.items()
            if _attribute_name(key).lower() == name.lower()
        ),
        None,
    )


def _attribute_name(name: str) -> str:
    if name.startswith("{"):
        return name.split("}", 1)[1]
    return name


def _first_descendant(node: etree._Element, name: str) -> etree._Element | None:
    return next((child for child in node.iter() if _local_name(child) == name), None)


def _inside(node: etree._Element, tags: set[str]) -> bool:
    parent = node.getparent()
    while parent is not None:
        if _local_name(parent) in tags:
            return True
        parent = parent.getparent()
    return False


def _has_ancestor_tag(node: etree._Element, tags: str | set[str]) -> bool:
    return _nearest_ancestor(node, tags) is not None


def _nearest_ancestor(node: etree._Element, tags: str | set[str]) -> etree._Element | None:
    expected = {tags} if isinstance(tags, str) else tags
    parent = node.getparent()
    while parent is not None:
        if _local_name(parent) in expected:
            return parent
        parent = parent.getparent()
    return None


def _is_footnote(node: etree._Element) -> bool:
    identity = f"{node.get('id', '')} {node.get('class', '')}".lower()
    return _local_name(node) == "footnote" or "footnote" in identity


def _looks_like_styled_heading(node: etree._Element, text: str) -> bool:
    if len(text) > 180:
        return False
    style_text = " ".join(
        item.get("style", "").lower()
        for item in (node, *node.iterdescendants())
        if isinstance(item.tag, str)
    )
    is_bold = "font-weight:700" in style_text or "font-weight:bold" in style_text
    is_centered = "text-align:center" in style_text
    return is_bold and (is_centered or not text.endswith((".", ";", ",")))


def _has_same_text_heading_ancestor(node: etree._Element, text: str) -> bool:
    parent = node.getparent()
    while parent is not None:
        if _local_name(parent) in {"div", "p", "span"} and _text(parent) == text:
            return True
        parent = parent.getparent()
    return False


def _has_ancestor_footnote(node: etree._Element) -> bool:
    parent = node.getparent()
    while parent is not None:
        if _is_footnote(parent):
            return True
        parent = parent.getparent()
    return False


def _footnote_reference(node: etree._Element) -> str | None:
    href = next(
        (_attribute(item, "href") for item in node.iter() if _local_name(item) == "a"),
        None,
    )
    if href and href.startswith("#"):
        return href[1:]
    role = _attribute(node, "role")
    described_by = _attribute(node, "aria-describedby")
    return role if role is not None else described_by


def _page_number(node: etree._Element) -> int | None:
    for sibling in (node.getprevious(), node.getnext()):
        if sibling is None:
            continue
        match = _PAGE_NUMBER.search(_text(sibling))
        if match:
            return int(match.group(1))
    return None


def _positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value or default)
    except ValueError:
        return default
    return parsed if parsed > 0 else default
