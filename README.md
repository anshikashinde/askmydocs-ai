# AskMyDocs AI

AskMyDocs AI is a document intelligence and question-answering project for SEC filings. It ingests public-company filing data, structures the content into canonical chunks, indexes the content for retrieval, and supports grounded question answering over those filings with citations back to the original source material.

## What the project does

- Fetches SEC filing metadata and source documents for public companies
- Parses structured filing content into a normalized document model
- Splits filings into chunked, provenance-aware sections for downstream retrieval
- Builds embeddings and stores them in a local vector index
- Resolves questions about a filing to relevant evidence in the index
- Answers using the retrieved evidence and returns citation-backed responses
- Provides a FastAPI-based application interface for filing and question workflows

## Architecture

The project follows a modular monolith with clear separation between:

- presentation/API layer
- application orchestration and use cases
- domain models and business rules
- infrastructure adapters for SEC access, parsing, indexing, and embeddings

## Repository structure

- [app](app) — application, domain, and infrastructure code
- [docs](docs) — architecture and product documentation
- [prompts](prompts) — prompt templates for grounding and answer generation
- [tests](tests) — unit and integration tests
- [docker](docker) — container setup and runtime assets

## Running locally

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

Start the app:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Check the health endpoint:

```bash
curl http://localhost:8000/health
```

Run tests:

```bash
pytest
```

Run lint and type checks:

```bash
ruff check .
mypy app
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

Current phase: Phase 2 baseline RAG implementation.
