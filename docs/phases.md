# AskMyDocs AI — Development Phases



This document defines the implementation sequence for AskMyDocs AI.

# Phase Overview

The project is divided into six implementation phases:

| Phase | Name                        | Primary Outcome                                                      |
| ----- | --------------------------- | -------------------------------------------------------------------- |
| 0     | Foundation                  | Reproducible development environment and application skeleton        |
| 1     | Document Ingestion          | Real SEC filings converted into searchable, citation-ready knowledge |
| 2     | Basic RAG                   | End-to-end question answering with semantic retrieval                |
| 3     | Retrieval Quality           | Hybrid retrieval and cross-encoder reranking                         |
| 4     | Grounding & Evaluation      | Measurable retrieval/generation quality and citation validation      |
| 5     | Productization & Deployment | Publicly usable application and demo                |

The phases are sequential.

---

# Phase 0 — Foundation
## Objective
Establish the project foundation before implementing RAG functionality.

The goal is to make the repository:

* reproducible;
* testable;
* structurally aligned with the architecture;
* ready for incremental implementation.

## Scope
Implement the initial project skeleton and development tooling.

This includes:

* repository structure;
* Python environment;
* dependency management;
* configuration management;
* environment-variable handling;
* logging foundation;
* error-handling foundation;
* FastAPI application skeleton;
* Streamlit application skeleton;
* pytest configuration;
* Ruff configuration;
* mypy configuration;
* Docker configuration;
* Docker Compose where useful for local development;
* GitHub Actions CI foundation;
* `.env.example`;
* `.gitignore`.

## Required Architectural Structure

The implementation must follow the architecture defined in `architecture.md`.

The initial application structure should include appropriate boundaries for:

```text
app/
├── api/
├── application/
├── domain/
├── infrastructure/
└── shared/
```

The exact internal module structure may evolve during later phases.

Do not create empty abstractions for capabilities that do not yet exist.

Create interfaces when they are required by an actual implementation.

## Configuration
Configuration must be externalized.
At minimum, provide a configuration mechanism for:

* environment;
* model configuration;
* retrieval parameters;
* chunking parameters;
* application settings;
* external service configuration.

Secrets must never be committed.

Provide:

```text
.env.example
```

with safe placeholder values.

## Testing

Establish:

* pytest;
* test discovery;
* test configuration;
* basic unit-test structure.

## Quality Tooling

Configure:

```text
ruff format
ruff check
mypy --strict
pytest
```

The project should be able to run these checks locally.

## Docker

Create a reproducible development container configuration.

Docker should simplify environment setup.

Do not introduce multiple containers unless a real dependency requires them.

## CI

Create a GitHub Actions workflow that runs at minimum:

```text
format/lint checks
type checks
unit tests
```

CI must not require paid services.

AI evaluation is not required in Phase 0.

## Phase 0 Quality Gate

Phase 0 is complete when:

* the repository structure exists;
* the application starts locally;
* the API skeleton starts;
* the Streamlit skeleton starts;
* tests run successfully;
* Ruff passes;
* mypy passes for configured code;
* Docker setup works;
* CI passes;
* no secrets are committed;
* setup instructions work from a clean environment.

Only then may Phase 1 begin.

---

# Phase 1 — Document Ingestion

## Objective

Build the complete pipeline for converting real SEC filings into structured, retrievable, citation-ready knowledge.

This phase establishes the data foundation for the entire RAG system.

## Core Pipeline

Implement:

```text
SEC EDGAR
    ↓
Fetch Filing
    ↓
Parse Filing
    ↓
Normalize Content
    ↓
Extract Structure
    ↓
Chunk
    ↓
Attach Metadata
    ↓
Generate Embeddings
    ↓
Persist Index
```

## SEC Filing Retrieval

Implement an Infrastructure component responsible for retrieving SEC filings.

The component must:

* retrieve supported filings from SEC EDGAR;
* handle HTTP failures;
* identify the source filing;
* preserve filing metadata;
* avoid leaking SEC-specific implementation details outside Infrastructure.

The application must not directly perform SEC HTTP requests.

## Filing Metadata

A filing should retain information such as:

* company name;
* ticker where available;
* filing type;
* fiscal period;
* filing identifier;
* filing date where available;
* source URL.

Do not assume every SEC filing has identical HTML structure.

## Parsing

Implement a structure-aware parser.

The parser should preserve useful document structure such as:

* section headings;
* paragraphs;
* tables where practical;
* footnotes where practical;
* source positions.

The first implementation should favour robustness and simplicity over a highly sophisticated document-understanding system.

## Normalization

Normalize extracted content before chunking.

Handle common issues such as:

* excessive whitespace;
* repeated formatting artifacts;
* unnecessary HTML elements;
* malformed text;
* irrelevant page/navigation content.

The normalized representation must retain enough information for later citation.

## Chunking

Implement an initial structure-aware chunking strategy.

The initial configuration should be approximately:

* 550–800 tokens per chunk;
* approximately 100-token overlap.

These values are starting points, not permanent constants.

They must be configurable and may be changed later based on retrieval evaluation.

Do not prematurely implement multiple chunking algorithms.

## Chunk Metadata

Every chunk must retain enough information to identify its source.

At minimum:

```text
chunk_id
document_id
company
filing_type
fiscal_period
section
text
source_url
source_position
```

Additional metadata may be introduced if it improves retrieval or citation quality.

## Embeddings

Generate embeddings for chunks using a free/open-weight embedding model.

The embedding implementation must be behind an abstraction.

The rest of the application must not depend directly on the embedding library.

## Knowledge Storage

Persist:

* filing metadata;
* document metadata;
* chunks;
* embeddings;
* retrieval index information.

The initial implementation should favour simple local storage.

Do not introduce a managed vector database unless a demonstrated requirement justifies it.

## Ingestion Modes

The same ingestion pipeline must support:

### Pre-indexed ingestion

Used to prepare the public demo dataset.

### On-demand ingestion

Used when a requested filing is not already indexed.

The pipeline itself must remain identical.

## Testing

Add tests for:

* SEC client behaviour;
* parsing;
* normalization;
* chunking;
* metadata preservation;
* embedding interface;
* storage;
* ingestion use case.

Network-dependent behaviour should be mocked in unit tests.

Integration tests may use controlled real components where appropriate.

## Phase 1 Deliverable

Given a real supported SEC filing, the system can:

```text
fetch
→ parse
→ normalize
→ chunk
→ attach metadata
→ embed
→ persist
```

and later retrieve the resulting chunks.

---

## Phase 1 Quality Gate

Phase 1 is complete when:

* at least one real 10-K can be processed successfully;
* the same pipeline works independently of whether ingestion was pre-triggered or on-demand;
* chunks retain citation metadata;
* embeddings are generated locally/free;
* persisted data can be loaded again;
* malformed or failed filings produce explicit errors;
* ingestion tests pass;
* no paid API is required;
* documentation explains the ingestion pipeline.

Only then may Phase 2 begin.

---

# Phase 2 — Basic RAG

## Objective

Build the first complete question-answering pipeline.

At the end of this phase, a user should be able to ask a question about an indexed filing and receive an answer grounded in retrieved evidence.

---

## Core Pipeline

Implement:

```text
User Question
      ↓
Query Understanding
      ↓
Filing Resolution
      ↓
Semantic Retrieval
      ↓
Prompt Construction
      ↓
Answer Generation
      ↓
Citation Formatting
      ↓
Response
```

---

## Query Understanding

Implement lightweight query understanding.

Extract relevant information where possible:

* company;
* filing type;
* fiscal period;
* underlying question.

Do not build a complex agent or multi-step planner.

If the required filing cannot be identified reliably, return an explicit ambiguity or unsupported-query response.

---

## Filing Resolution

Implement filing resolution.

The flow is:

```text
Question
   ↓
Required Filing
   ↓
Already Indexed?
   ├── Yes → continue
   └── No  → ingest filing
                ↓
             continue
```

Filing resolution must use the same ingestion use case implemented in Phase 1.

---

## Semantic Retrieval

Implement the first retrieval strategy:

> dense vector retrieval.

The retriever should:

* embed the query;
* search the vector index;
* return ranked chunks;
* include relevance information and metadata.

Do not implement BM25 or reranking yet.

The purpose of this phase is to establish a measurable baseline.

---

## Prompt Construction

Create a versioned generation prompt.

The prompt must:

* include the user question;
* include retrieved evidence;
* instruct the model to stay grounded;
* require citations;
* instruct the model to abstain when evidence is insufficient.

Prompts must live under `prompts/`.

---

## Answer Generation

Use a free/open-weight generation model.

The model must receive retrieved evidence as context.

The generation component must not independently retrieve external information.

---

## Citation Formatting

The answer must include citations referring to retrieved evidence.

Citations should expose enough metadata for the user to identify the source.

---

## Basic Abstention

Implement basic evidence-based abstention.

If no sufficiently relevant evidence is retrieved, the system should not produce a fabricated answer.

---

## Testing

Add tests for:

* query parsing;
* filing resolution;
* semantic retrieval;
* prompt construction;
* generation interface;
* citation formatting;
* insufficient-evidence behaviour.

Add at least one end-to-end test using controlled data and a test model/fake model where practical.

---

## Phase 2 Deliverable

A user can ask a question such as:

```text
What were the major risk factors disclosed by the company?
```

and receive:

```text
Grounded answer

Source:
Company 10-K
Relevant section
Citation/evidence
```

---

## Phase 2 Quality Gate

Phase 2 is complete when:

* a complete question-to-answer flow works;
* filing resolution works;
* on-demand ingestion can feed retrieval;
* semantic retrieval returns relevant chunks;
* answers use retrieved context;
* citations point to retrieved evidence;
* unsupported questions can trigger abstention;
* tests pass;
* the baseline RAG pipeline is documented.

The semantic retrieval pipeline established here becomes the baseline for Phase 3.

---

# Phase 3 — Retrieval Quality

## Objective

Improve retrieval quality systematically and determine whether hybrid retrieval and reranking provide measurable benefits over the Phase 2 baseline.

This phase is the main retrieval-engineering phase of the project.

---

# 7.1 BM25 Retrieval

Implement BM25 retrieval as an independent retrieval strategy.

The BM25 implementation must use the same underlying chunk corpus as semantic retrieval.

Evaluate it independently before combining it with dense retrieval.

---

# 7.2 Hybrid Retrieval

Combine:

```text
Dense Retrieval
       +
BM25 Retrieval
       ↓
Reciprocal Rank Fusion
       ↓
Combined Ranking
```

Implement Reciprocal Rank Fusion as an isolated component.

Fusion parameters must be configurable.

---

# 7.3 Cross-Encoder Reranking

Implement reranking after initial retrieval.

The intended flow is:

```text
Hybrid Retrieval
      ↓
Top-N Candidates
      ↓
Cross-Encoder
      ↓
Top-K Evidence
```

The reranker must be independently replaceable.

---

# 7.4 Retrieval Experiments

Run controlled experiments comparing:

1. dense retrieval;
2. BM25;
3. hybrid retrieval;
4. hybrid retrieval + reranking.

Where practical, keep other variables constant.

Record:

* retrieval configuration;
* model configuration;
* dataset;
* metrics;
* results;
* observations.

Do not claim an improvement without measured evidence.

---

# 7.5 Retrieval Metrics

Introduce retrieval evaluation metrics appropriate to the available evaluation dataset.

At minimum, implement:

* Recall@K;
* Precision@K where applicable;
* MRR.

The implementation should be deterministic where possible.

---

# 7.6 Retrieval Configuration

Make the following configurable:

* dense top-k;
* BM25 top-k;
* fusion parameters;
* reranking candidate count;
* final context count.

Do not hardcode experimental values throughout the codebase.

---

# 7.7 Testing

Add tests for:

* BM25 retrieval;
* rank fusion;
* reranking;
* retrieval configuration;
* ranking behaviour;
* failure cases.

Add regression tests for previously identified retrieval issues.

---

# 7.8 Phase 3 Deliverable

A measurable retrieval pipeline exists:

```text
Dense
  ↓
BM25
  ↓
Hybrid
  ↓
Hybrid + Reranker
```

and the project can demonstrate how retrieval quality changes at each stage.

---

# 7.9 Phase 3 Quality Gate

Phase 3 is complete when:

* BM25 works;
* hybrid retrieval works;
* RRF works;
* reranking works;
* retrieval metrics can be calculated;
* experiments are reproducible;
* the baseline and improved approaches have been compared;
* tests pass;
* the results are documented.

The system must not move to Phase 4 without a functioning measurable retrieval pipeline.

---

# 8. Phase 4 — Grounding & Evaluation

## Objective

Prove that the complete system produces answers that are supported by evidence and establish measurable quality gates.

This phase connects retrieval quality with generation quality.

---

# 8.1 Citation Validation

Implement post-generation citation validation.

The validator should check:

* citations reference retrieved evidence;
* referenced evidence exists;
* source metadata is valid;
* factual claims are not presented as supported when the required evidence is absent.

The exact validation strategy should remain simple enough to understand and test.

---

# 8.2 Grounding

Strengthen generation constraints so that:

* answers use retrieved evidence;
* unsupported claims are avoided;
* citations are attached to supported claims;
* insufficient evidence leads to abstention.

---

# 8.3 FinanceBench Evaluation

Use the publicly available FinanceBench subset as a primary external evaluation dataset.

Do not claim to evaluate the full benchmark unless the full benchmark has actually been obtained and run.

Record the exact dataset version used.

---

# 8.4 Generation Metrics

Evaluate appropriate metrics such as:

* faithfulness;
* answer correctness;
* context recall.

RAGAS may be used where appropriate.

The core project must remain executable without paid APIs.

If an evaluation metric requires an external model, it must be treated as an evaluation dependency rather than a mandatory runtime dependency.

---

# 8.5 Additional Project Metrics

Track project-specific metrics such as:

* citation coverage;
* citation validity;
* abstention rate;
* retrieval success rate.

These metrics should complement rather than replace established evaluation methods.

---

# 8.6 Error Analysis

Do not only report aggregate metrics.

Inspect representative failures.

Categorize failures such as:

* incorrect filing resolution;
* poor chunking;
* missing evidence;
* retrieval failure;
* reranking failure;
* generation error;
* unsupported claim;
* citation error;
* insufficient evidence.

Use this analysis to identify meaningful improvements.

---

# 8.7 Evaluation Reports

Create reproducible evaluation reports containing:

* dataset;
* configuration;
* retrieval approach;
* model;
* metrics;
* results;
* representative failures;
* conclusions supported by the data.

Do not present unsupported claims such as "the model is better" without corresponding measurements.

---

# 8.8 Quality Gate

Define reasonable project-specific thresholds after establishing the baseline.

Do not invent thresholds before seeing the actual system performance.

Thresholds should be:

* documented;
* reproducible;
* justified by the project;
* version controlled.

---

# 8.9 CI Evaluation

Once evaluation is stable, add a lightweight CI quality gate where practical.

The CI process should avoid:

* mandatory paid APIs;
* long-running expensive evaluations;
* nondeterministic external dependencies.

A suitable approach may be:

```text
Pull Request
     ↓
Unit Tests
     ↓
Integration Tests
     ↓
Small deterministic evaluation set
     ↓
Quality threshold
```

A larger FinanceBench evaluation can remain an explicit evaluation workflow rather than running on every pull request if runtime or resource constraints make that more appropriate.

---

# 8.10 Phase 4 Deliverable

The project can demonstrate:

```text
Question
   ↓
Retrieval
   ↓
Reranking
   ↓
Generation
   ↓
Citation Validation
   ↓
Grounded Answer / Abstention
```

with measurable quality results.

---

# 8.11 Phase 4 Quality Gate

Phase 4 is complete when:

* citation validation works;
* unsupported answers can be rejected or abstained;
* FinanceBench subset evaluation runs;
* retrieval metrics are available;
* generation metrics are available;
* retrieval and generation quality are reported separately;
* representative failures have been analysed;
* evaluation results are documented;
* tests pass;
* an appropriate lightweight CI quality gate exists.

Only then may Phase 5 begin.

---

# 9. Phase 5 — Productization & Deployment

## Objective

Turn the completed RAG system into a polished, publicly accessible portfolio project.

This phase focuses on usability, deployment, documentation, and recruiter-facing presentation rather than adding new RAG complexity.

---

# 9.1 Streamlit Interface

Build a simple web interface containing:

* question input;
* answer display;
* citations;
* source information;
* loading/progress state;
* errors;
* abstention messages.

The UI should remain simple.

Do not build a complex frontend framework unless a real requirement appears.

---

# 9.2 API

Expose the core question-answering capability through the API layer.

The API should provide a clean interface for:

* submitting a question;
* receiving an answer;
* receiving citations;
* receiving meaningful error responses.

The UI should use the same application use case rather than implementing its own RAG logic.

---

# 9.3 Demo Dataset

Prepare a small curated set of pre-indexed filings for the public demo.

The demo dataset should be:

* small enough for free deployment;
* representative of the supported use case;
* documented;
* reproducible.

Large raw filings and generated indexes must not be committed unnecessarily to Git.

---

# 9.4 Deployment

Deploy the application using free infrastructure where practical.

The deployed version must:

* start successfully;
* answer supported questions;
* display citations;
* handle failures gracefully;
* avoid requiring paid API credentials.

Document any limitations of the free deployment environment.

---

# 9.5 Docker

Ensure the application can still be run locally through Docker.

A recruiter or developer should be able to follow the README and reproduce the application without manually reconstructing the environment.

---

# 9.6 CI/CD

Final CI should run appropriate checks such as:

```text
format
lint
type checking
unit tests
integration tests
```

Evaluation workflows may be separate when they are too expensive or slow for every commit.

---

# 9.7 README

The final README should explain:

1. what AskMyDocs AI is;
2. the problem;
3. key capabilities;
4. architecture;
5. RAG pipeline;
6. technology stack;
7. retrieval experiments;
8. evaluation results;
9. example questions;
10. local setup;
11. live demo;
12. limitations;
13. future improvements.

The README should focus on demonstrated engineering work rather than marketing language.

---

# 9.8 Architecture Documentation

Include a simple architecture diagram showing:

```text
User
 ↓
Streamlit
 ↓
Application
 ↓
Query Understanding
 ↓
Filing Resolution
 ↓
Retrieval
 ↓
Reranking
 ↓
Generation
 ↓
Citation Validation
 ↓
Answer
```

Also document the ingestion pipeline.

---

# 9.9 Evaluation Documentation

The repository should contain a concise evaluation report showing:

```text
Dense Retrieval
vs
BM25
vs
Hybrid
vs
Hybrid + Reranking
```

Include actual measured results.

Explain what changed and why.

Do not hide negative results.

A component that did not improve the system is still a useful engineering finding.

---

# 9.10 Project Limitations

Document limitations honestly.

Potential areas include:

* free deployment resource constraints;
* model latency;
* SEC parsing edge cases;
* limited evaluation dataset;
* limited pre-indexed demo filings;
* model quality;
* citation granularity;
* table extraction limitations.

---

# 9.11 Phase 5 Quality Gate

Phase 5 is complete when:

* the web UI works;
* the API works;
* the demo dataset is available;
* the application is publicly deployed;
* citations are visible;
* the application runs without mandatory paid APIs;
* Docker setup works;
* CI passes;
* README is complete;
* architecture documentation is complete;
* evaluation results are documented;
* limitations are documented;
* the public demo can be accessed by an external user.

---

# 10. Final Definition of Done

AskMyDocs AI is considered complete when all six phases have passed their respective quality gates.

The final system must demonstrate:

```text
SEC Filing
    ↓
Structure-aware Ingestion
    ↓
Chunking + Metadata
    ↓
Embeddings
    ↓
Dense Retrieval
    +
BM25
    ↓
Hybrid Retrieval
    ↓
Cross-Encoder Reranking
    ↓
Prompt Construction
    ↓
Generation
    ↓
Citation Validation
    ↓
Grounded Answer
       OR
Abstention
```

The completed project must also provide:

* automated tests;
* type and lint checks;
* reproducible evaluation;
* documented retrieval experiments;
* documented limitations;
* a GitHub repository;
* a publicly accessible demo;
* no mandatory paid API dependency.

---

# 11. Rules for Future Phase Changes

If implementation reveals that a phase is too large, split the implementation work internally without automatically creating a new project phase.

If a new requirement appears, determine first whether it belongs inside an existing phase.

Do not create a new phase merely because a new library or technology is introduced.

A new phase should only be created when it represents a meaningful independently verifiable product capability.

---

# 12. Explicit Non-Goals During Development

Do not pause or expand the project to implement:

* microservices;
* Kubernetes;
* authentication;
* multi-tenancy;
* autonomous agents;
* multi-agent systems;
* complex LangGraph workflows;
* paid model infrastructure;
* distributed databases;
* enterprise observability platforms;

unless the project requirements are explicitly changed.

The goal is to complete a strong, understandable, measurable RAG system.

---

# 13. Phase Completion Rule

At the end of every phase:

1. implementation must satisfy the phase scope;
2. tests must pass;
3. quality gates must pass;
4. required documentation must be updated;
5. the phase must be marked complete;
6. only then may the next phase begin.

The implementation must never silently skip a phase requirement.

---

# 14. Guiding Principle

> Build the simplest complete version first, measure it, improve it, and only then add complexity that the evidence justifies.

AskMyDocs AI should demonstrate that the developer understands not only how to use AI models, but also how to build, evaluate, debug, and deploy a complete RAG system.
