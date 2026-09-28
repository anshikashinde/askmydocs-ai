# Datasets

SEC filing datasets used for ingestion, evaluation, and development.

## Corpus

**Source:** SEC EDGAR — 10-K (annual) and 10-Q (quarterly) filings from publicly traded companies.

**Target companies:** AI/tech-adjacent public companies — NVIDIA, Microsoft, Alphabet, Meta, Amazon, AMD, Palantir, Snowflake, Salesforce, Oracle, ServiceNow, C3.ai, and others.

**Volume target:** ~30-50 companies × 2-3 years of filings = 60-150 filings.

## Directory Structure

| Subdirectory | Contents |
|---|---|
| `raw/` | Original unprocessed SEC filings (HTML from EDGAR, converted PDFs) — excluded from git |
| `processed/` | Chunked and embedded representations ready for vector store ingestion — excluded from git |
| `evaluation/` | FinanceBench subset + custom QA pairs for offline evaluation (RAGAS metrics) |
| `sample/` | Small, version-controlled sample filings (1-2 companies) for local development and CI |

## Evaluation

The primary evaluation benchmark is **FinanceBench** (https://github.com/patronus-ai/financebench):
- 10,231 verified QA pairs over real SEC filings
- Questions with answers and evidence strings
- Used as the gold standard for retrieval and generation quality

The `evaluation/` directory contains:
- A curated subset of FinanceBench (150+ pairs matching our ingested filings)
- Custom QA pairs focused on AI risk disclosures (hand-verified)

## Data Management

> `raw/` and `processed/` are excluded from version control via `.gitignore`.
> Store large filing datasets locally in `DATA_DIR` (see `.env.example`).
> Never commit full filings to git — they are large and freely available from EDGAR.
