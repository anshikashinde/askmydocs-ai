# Documentation

## Directory Structure

| Directory | Contents |
|---|---|
| `architecture/` | System design, data model, component diagrams |
| `phases/` | Detailed specification for each implementation stage (0–11) |
| `decisions/` | Architecture Decision Records (ADRs) |
| `development/` | Local setup, contribution guide, phase workflow |
| `api/` | API reference and endpoint documentation (populated in Phase 2+) |
| `diagrams/` | Source files for diagrams (Mermaid) |
| `operations/` | Deployment runbooks, scaling guides (populated in Phase 11) |

## Reading Order

If you are new to this project:

1. Start with `../README.md` (project root)
2. Read `../.kiro/steering/product.md` — what we're building and why
3. Read `../.kiro/steering/architecture.md` — how the system is structured
4. Read `phases/stage-00-foundation.md` through the current active phase
5. Read `decisions/` for context on key architectural choices

## Phase Documentation

Each stage has a dedicated document in `phases/` that defines:

- **Objective** — what this stage delivers
- **Inputs** — what must exist before this stage begins
- **Outputs** — what is produced when this stage is complete
- **Key decisions** — design choices specific to this stage
- **Acceptance criteria** — how we know the stage is done
