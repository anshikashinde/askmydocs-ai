# Phase 1A — SEC Filing Parsing & Structured Representation

**Project:** AskMyDocs AI  
**Domain:** SEC Filing Intelligence / Document Ingestion  
**Phase:** 1A  
**Status:** Ready for implementation

---

## 1. Purpose

Phase 1A transforms a successfully retrieved SEC filing into a deterministic, structured, provenance-preserving representation suitable for downstream ingestion.

The phase begins with a `RawFiling` containing the original SEC primary document and produces a `StructuredFiling`.

The pipeline MUST preserve the original filing as the source of truth.

The system MUST NOT reduce the filing directly to plain text because SEC filings contain important structure that is required for accurate retrieval, financial reasoning, and citations:

- document hierarchy
- headings
- paragraphs
- tables
- lists
- footnotes
- links
- page boundaries
- HTML anchors/IDs
- Inline XBRL facts
- XBRL contexts
- XBRL units
- continuation relationships
- filing metadata

---

# 2. Scope

Phase 1A includes:

1. Source format detection
2. HTML/iXBRL parsing
3. Document element extraction
4. XBRL fact extraction
5. XBRL continuation resolution
6. Conservative normalization
7. Provenance attachment
8. SEC document structure extraction
9. Construction of the `StructuredFiling`
10. Validation of the resulting representation

Phase 1A does NOT include:

- embeddings
- vector databases
- BM25 indexing
- retrieval
- reranking
- LLM-based parsing
- LLM-based summarization
- answer generation
- citation generation for final user responses
- semantic chunking
- document rewriting
- financial calculations

These belong to later phases.

---

# 3. Architectural Position

The pipeline follows the project's Clean Architecture boundaries.

```text
                    API / Application
                           │
                           ▼
                 ┌───────────────────┐
                 │ SECFilingService   │
                 └─────────┬─────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │ RawFiling   │
                    └──────┬──────┘
                           │
                           ▼
              ┌────────────────────────┐
              │ Document Parser        │
              │        lxml             │
              └───────────┬────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │ Element Extraction     │
              └───────────┬────────────┘
                          │
              ┌───────────┴────────────┐
              ▼                        ▼
       Visible Elements           XBRL Facts
              │                        │
              └───────────┬────────────┘
                          ▼
                  Normalization
                          │
                          ▼
                    Provenance
                          │
                          ▼
              SEC Structure Extraction
                          │
                          ▼
                 StructuredFiling
                          │
                          ▼
                    Phase 1B
```

The parser and SEC-specific extraction logic belong in infrastructure/application processing boundaries.

The domain model MUST remain independent of `lxml`, HTML parser objects, HTTP clients, or other infrastructure implementations.

---

# 4. Canonical Source

The canonical source is the original SEC primary HTML/iXBRL document.

The system MUST preserve:

```text
raw_document_bytes
source_url
content_type
document_filename
filing metadata
```

The normalized representation is derived from this source and MUST NOT replace it.

The raw document must remain available for future provenance resolution and debugging.

---

# 5. Input Contract

Phase 1A receives:

```text
RawFiling
```

Conceptually:

```python
RawFiling
├── content: bytes
├── source_url: str
├── filename: str
├── content_type: str | None
├── filing_reference: FilingReference
└── retrieved_at: datetime
```

`FilingReference` contains the filing identity established during Phase 1 retrieval:

```text
company
ticker
CIK
accession_number
form_type
filing_date
period_of_report
```

The parser MUST NOT rediscover filing identity if it is already available from the retrieval phase.

---

# 6. Format Detection

The first processing step determines the document representation.

Expected primary format:

```text
HTML / XHTML / Inline XBRL
```

The actual SEC filing used during design contains:

- XHTML/HTML
- Inline XBRL namespace declarations
- `ix:header`
- `ix:hidden`
- `ix:nonNumeric`
- `ix:nonFraction`
- `ix:continuation`
- real HTML tables
- page-break markers
- document IDs/anchors

Therefore the parser must explicitly support Inline XBRL.

Format detection should identify:

```text
HTML
XHTML
Inline XBRL
Unsupported
Malformed
```

Detection should be deterministic.

---

# 7. HTML Parsing

Use `lxml` as the core parser.

Do NOT use an LLM for parsing.

Do NOT use an LLM to infer document structure.

Do NOT use BeautifulSoup as the primary parser.

The parser should produce a tree from which the extraction layer can deterministically identify document elements.

The parser should be configured to handle large SEC documents safely.

The implementation should:

- avoid unnecessary DOM copies
- avoid retaining parser nodes longer than required
- handle malformed-but-recoverable HTML where appropriate
- preserve element IDs
- preserve document order
- preserve text
- preserve table structure
- preserve XBRL elements
- avoid executing JavaScript

Scripts must never be executed.

---

# 8. Canonical Internal Representation

The parser MUST NOT expose raw `lxml` nodes outside the infrastructure/parser boundary.

Instead, extraction produces domain-neutral intermediate representations.

Example:

```text
ParsedDocument
├── document_metadata
├── elements[]
├── xbrl_facts[]
├── xbrl_contexts[]
├── xbrl_units[]
├── continuations[]
└── source_metadata
```

---

# 9. Document Elements

The system should represent meaningful document elements explicitly.

Minimum supported element types:

```text
DocumentElement
├── Heading
├── Paragraph
├── Table
├── TableRow
├── TableCell
├── List
├── ListItem
├── Footnote
├── Link
├── PageBreak
└── OtherStructuredElement
```

Not every HTML element should become a domain element.

Presentation-only wrappers such as:

```html
<div>
<span>
```

should not automatically become semantic document elements.

The extraction layer determines whether an element has semantic value.

---

# 10. Heading Representation

A heading should preserve:

```text
Heading
├── text
├── level
├── element_id
├── document_order
├── provenance
└── structure_context
```

The implementation should preserve the original heading text exactly apart from normalization that does not alter meaning.

Examples from SEC filings include:

```text
Item 1. Business
Item 1A. Risk Factors
Item 7. Management’s Discussion and Analysis...
Item 8. Financial Statements...
```

Heading level must not be assumed solely from HTML tags.

SEC-specific structural interpretation may require the heading text itself.

---

# 11. Paragraph Representation

A paragraph should preserve:

```text
Paragraph
├── text
├── element_id
├── document_order
├── provenance
└── structure_context
```

Text normalization may:

- collapse repeated whitespace
- normalize line breaks
- remove presentation-only spacing

It MUST NOT:

- rewrite sentences
- paraphrase content
- remove financial values
- alter numbers
- remove meaningful punctuation
- remove footnote references
- merge unrelated paragraphs

---

# 12. Table Representation

Tables are first-class domain elements.

A financial table MUST NOT be flattened into an ambiguous text string.

Represent tables structurally:

```text
Table
├── caption
├── headers[]
├── rows[]
│   └── cells[]
├── element_id
├── document_order
├── provenance
└── structure_context
```

Cells should preserve:

```text
TableCell
├── text
├── row_index
├── column_index
├── colspan
├── rowspan
├── header_role
├── element_id
└── provenance
```

The implementation should preserve enough structure for Phase 1B to later perform table-aware chunking.

---

# 13. Lists

Lists must preserve list semantics.

```text
List
├── ordered / unordered
├── items[]
├── element_id
└── provenance
```

Each item:

```text
ListItem
├── text
├── position
└── provenance
```

Do not concatenate list items into a single paragraph.

---

# 14. Footnotes

Footnotes are important for financial interpretation.

They must remain identifiable.

```text
Footnote
├── text
├── reference_id
├── element_id
├── document_order
└── provenance
```

Footnote references appearing in tables or paragraphs should remain connected to the underlying footnote where the source document provides such a relationship.

---

# 15. Links and Anchors

Preserve links and HTML IDs whenever available.

For example:

```text
Link
├── text
├── href
├── element_id
└── provenance
```

HTML IDs/anchors are important because they may provide a stable way to locate a source fragment within the original filing.

They should therefore NOT be discarded during normalization.

---

# 16. Page Boundaries

Page boundaries should be represented when they can be deterministically identified.

The provided SEC filing contains markers such as:

```html
<hr style="page-break-after:always"/>
```

and visible page-number text such as:

```text
Apple Inc. | 2025 Form 10-K | 58
```

Page information should therefore be extracted where possible.

Represent:

```text
PageBreak
├── page_number
└── provenance
```

Page numbers are useful citation metadata, but they are NOT the primary identity of a source fragment.

A page number alone is insufficient as a provenance key.

---

# 17. Provenance Model

Every meaningful extracted element MUST have provenance.

Provenance should contain as much of the following as can be established deterministically:

```text
Provenance
├── filing_id
├── document_id
├── element_id
├── source_url
├── document_order
├── start_offset
├── end_offset
├── html_anchor
├── page_number
└── source_element_type
```

Where exact character offsets cannot be reliably calculated during HTML parsing, they should not be fabricated.

Optional values must remain `None` rather than using inaccurate values.

---

# 18. Source-of-Truth Rule

The hierarchy is:

```text
Original Raw Filing
        ↓
Parsed Document
        ↓
Structured Element
        ↓
Chunk
        ↓
Retrieval Result
        ↓
Answer Citation
```

A lower-level representation must never become the authoritative replacement for the original source.

The system must always be capable of tracing:

```text
Answer
 → Retrieved Chunk
 → Document Element
 → Original Filing
```

---

# 19. Inline XBRL

Inline XBRL is a first-class part of the representation.

The implementation must recognize and extract at minimum:

```text
ix:nonNumeric
ix:nonFraction
ix:continuation
ix:header
ix:hidden
```

The parser must preserve important XBRL attributes including, where present:

```text
name
contextRef
unitRef
decimals
scale
sign
format
id
continuedAt
```

Do not discard XBRL simply because visible text has also been extracted.

---

# 20. XBRL Fact Model

Represent facts independently from visible document elements.

Example:

```text
XBRLFact
├── fact_id
├── name
├── value
├── fact_type
├── context_ref
├── unit_ref
├── decimals
├── scale
├── sign
├── format
├── source_element_id
└── provenance
```

For example:

```text
name:
us-gaap:OperatingIncomeLoss

value:
36,587

unit:
usd

scale:
6

sign:
-
```

The system should preserve the raw lexical value as well as a normalized value when safe.

Do not silently reinterpret financial semantics.

---

# 21. XBRL Contexts

The parser should extract XBRL contexts referenced by facts.

A context may contain information such as:

```text
context_id
entity
identifier
period
instant
start_date
end_date
dimensions
```

The exact model should remain extensible because SEC filings may contain dimensional XBRL data.

The system should preserve the original context reference.

---

# 22. XBRL Units

Extract unit information where present.

Example:

```text
XBRLUnit
├── unit_id
├── measure
└── source
```

Support composite units where necessary.

Do not assume all units are currencies.

---

# 23. XBRL Continuations

This is mandatory.

The provided filing contains:

```html
<ix:continuation ... continuedAt="...">
```

Therefore the parser must resolve continuation chains.

Example:

```text
Fact A
  ↓
continuation-1
  ↓
continuation-2
```

The resulting semantic representation should allow consumers to understand the complete fact/content sequence.

The original continuation IDs and relationships must still be preserved for provenance.

The parser must detect:

- missing continuation targets
- circular continuation chains
- duplicate continuation IDs
- unresolved references

These should produce validation errors/warnings rather than silently corrupting the data.

---

# 24. Normalization

Normalization is conservative.

The goal is:

```text
remove presentation noise
+
preserve semantic information
```

Remove or ignore:

- CSS
- JavaScript
- style attributes where not semantically relevant
- presentation-only wrappers
- empty decorative elements
- duplicated visual markup
- excessive whitespace

Preserve:

- text
- headings
- paragraphs
- tables
- lists
- footnotes
- links
- anchors
- page information
- numbers
- dates
- units
- currencies
- punctuation
- XBRL facts
- XBRL context references
- document ordering

Normalization MUST be deterministic and idempotent.

Running normalization twice should not continue changing the representation.

---

# 25. SEC Structure Extraction

After parsing and normalization, identify SEC-level document structure.

At minimum:

```text
Filing
├── Part
│   ├── Item
│   │   ├── Section
│   │   │   ├── Paragraph
│   │   │   ├── Table
│   │   │   ├── List
│   │   │   └── Footnote
```

Examples:

```text
Part I
  Item 1. Business

Part I
  Item 1A. Risk Factors

Part II
  Item 7. Management’s Discussion and Analysis...

Part II
  Item 8. Financial Statements...
```

Structure extraction should be rule-based.

Do not use an LLM to infer SEC structure.

---

# 26. Structure Context

Every meaningful document element should carry its current structural context.

Example:

```text
StructureContext
├── part
├── item
├── section
└── subsection
```

For example:

```text
part = "Part II"
item = "Item 7"
section = "Segment Operating Performance"
```

This metadata will be critical during Phase 1B chunking.

---

# 27. Document Order

Every extracted semantic element must have deterministic document order.

Example:

```text
document_order = 0
document_order = 1
document_order = 2
...
```

This must represent source order.

Document order is required for:

- reconstruction
- chunking
- previous/next relationships
- citation resolution
- debugging
- testing

---

# 28. StructuredFiling

The output of Phase 1A is:

```text
StructuredFiling
├── filing_metadata
├── source_document
├── elements[]
├── xbrl
└── validation
```

Conceptually:

```text
StructuredFiling
│
├── FilingMetadata
│   ├── company
│   ├── ticker
│   ├── cik
│   ├── accession_number
│   ├── form_type
│   ├── filing_date
│   └── period_of_report
│
├── SourceDocument
│   ├── document_id
│   ├── filename
│   ├── source_url
│   ├── format
│   └── raw_source_reference
│
├── DocumentStructure
│   └── elements[]
│
├── XBRLData
│   ├── facts[]
│   ├── contexts[]
│   ├── units[]
│   └── continuations[]
│
└── ValidationResult
    ├── errors[]
    └── warnings[]
```

---

# 29. Domain Invariants

The following must always hold.

### Invariant 1 — Source preservation

The original filing must remain recoverable.

### Invariant 2 — No fabricated provenance

Unknown provenance must be represented as unknown.

### Invariant 3 — Determinism

The same source document and configuration must produce the same structured representation.

### Invariant 4 — Document ordering

Elements must preserve source order.

### Invariant 5 — Table preservation

Tables must retain row/column semantics.

### Invariant 6 — XBRL preservation

XBRL facts must not be lost merely because their visible representation exists.

### Invariant 7 — Continuation integrity

Continuation relationships must be preserved and resolved.

### Invariant 8 — Structural context

Elements inside a known Part/Item must inherit that context.

### Invariant 9 — No semantic rewriting

The parser must never paraphrase or summarize source content.

### Invariant 10 — Phase separation

Phase 1A must not perform retrieval, embeddings, vector indexing, BM25 indexing, reranking, or answer generation.

---

# 30. Error Handling

Errors should be classified.

```text
ParsingError
NormalizationError
StructureExtractionError
XBRLParsingError
XBRLContinuationError
ValidationError
UnsupportedFormatError
```

The pipeline should distinguish:

### Fatal errors

The document cannot safely be represented.

Example:

```text
Unable to parse document
```

### Recoverable warnings

Some optional information could not be extracted.

Example:

```text
Page number could not be identified
```

A recoverable issue must not cause the entire filing to fail unless the resulting representation violates a domain invariant.

---

# 31. Testing Requirements

Testing must include unit and integration coverage.

Minimum test cases:

### HTML parsing

- valid SEC HTML
- XHTML
- large HTML document
- malformed-but-recoverable markup

### Element extraction

- headings
- paragraphs
- lists
- tables
- footnotes
- links
- page breaks

### Table extraction

- simple table
- multi-column table
- colspan
- rowspan
- financial table
- table containing XBRL facts

### XBRL

- `ix:nonNumeric`
- `ix:nonFraction`
- context references
- units
- scale
- decimals
- sign
- formats
- IDs
- hidden facts
- continuations

### Continuations

- single continuation
- multiple continuation chain
- missing target
- circular continuation

### Provenance

Verify that every extracted semantic element has valid provenance.

### Normalization

Verify:

```text
normalize(normalize(document)) == normalize(document)
```

### Structure extraction

Verify:

```text
Part → Item → Section → Element
```

### Regression

Use the uploaded Apple 2025 Form 10-K HTML as a real integration fixture.

The fixture should verify that important structures from the actual filing survive the pipeline.

---

# 32. Phase 1A Output Contract

Phase 1B must be able to consume:

```text
StructuredFiling
```

without needing to know:

- how HTML was parsed
- which HTML parser was used
- how SEC HTTP retrieval worked
- how XBRL tags were located in the DOM

Phase 1B should only depend on the structured representation.

This creates the boundary:

```text
Infrastructure-specific source
        ↓
Phase 1A
        ↓
StructuredFiling
        ↓
Phase 1B
```

---

# 33. Phase 1B Compatibility Requirements

The output must support future:

- structure-aware chunking
- semantic chunking
- table-aware chunking
- metadata enrichment
- BM25 indexing
- vector embeddings
- hybrid retrieval
- reranking
- citation generation

Every chunk created later must be traceable to one or more Phase 1A elements.

Therefore:

```text
Chunk
├── chunk_id
├── content
├── element_ids[]
├── structure_context
└── provenance[]
```

must be possible without reparsing the original HTML.

---

# 34. Design Principle

The central design principle of Phase 1A is:

> **Parse once, preserve everything important, normalize conservatively, attach provenance early, and expose a clean structured representation to downstream stages.**

The system should prefer preserving information over aggressively simplifying the document.
