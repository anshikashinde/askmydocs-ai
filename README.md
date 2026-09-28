# AskMyDocs AI

AskMyDocs AI is a foundation-stage, evidence-grounded Retrieval-Augmented Generation (RAG) system for analyzing public-company SEC filings. The project is currently in Phase 0, which focuses on the engineering foundation and repository readiness required before later RAG and retrieval work begins.

## Current project status

This repository has the required project structure and implements the minimum viable foundation:

- Python packaging and dependency configuration
- FastAPI application entry point
- minimal health endpoint at `/health`
- environment-based configuration
- basic logging setup
- test harness with pytest
- Ruff and mypy configuration
- Docker build and runtime wiring
- GitHub Actions CI checks

No SEC ingestion, retrieval, reranking, or generation logic is implemented in this phase.

## High-level architecture

The system follows a modular monolith with Clean Architecture boundaries:

- Presentation: API surface and future UI
- Application: orchestration and use cases
- Domain: business concepts and rules
- Infrastructure: adapters for external systems

This aligns with the project architecture described in [docs/architecture.md](docs/architecture.md).

## Documentation

- [docs/product.md](docs/product.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/phases.md](docs/phases.md)

## Environment setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .[dev]
cp .env.example .env
```

The repository includes a minimal environment example in [.env.example](.env.example). Keep a real `.env` file local only and never commit secrets.

## Run the application

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then verify the health endpoint:

```bash
curl http://localhost:8000/health
```

## Run tests

```bash
pytest
```

## Run Ruff

```bash
ruff check .
```

## Run mypy

```bash
mypy app
```

## Run with Docker

```bash
docker build -t askmydocs-ai .
docker run --rm -p 8000:8000 askmydocs-ai
```

Or use Docker Compose:

```bash
docker compose up --build
```

The service exposes the health endpoint at `/health`.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
