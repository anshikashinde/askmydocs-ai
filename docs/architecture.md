```md
# AskMyDocs AI — Architecture Document

## 1. Purpose

This document defines the architectural structure and dependency rules for AskMyDocs AI.

It describes how the system is organized and how its components interact.

It does not define specific implementation tasks, evaluation experiments, or individual technology choices. Those belong in phase specifications and project documentation.

This document is authoritative for architectural decisions.

If an implementation conflicts with these rules, the implementation must be changed or the architecture must be explicitly revised.

---

# 2. Architectural Style

AskMyDocs AI is a:

> Modular monolith using Clean Architecture principles with lightweight Domain-Driven Design.

The system is intentionally not a distributed system.

All major capabilities live within one application while maintaining clear internal boundaries.

---

# 3. High-Level Architecture

The system is organized into four primary layers:

```text
┌───────────────────────────────────────┐
│            Presentation               │
│       API + Web Application           │
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│             Application               │
│          Use Cases / Services          │
└───────────────────┬───────────────────┘
                    │
                    ▼
┌───────────────────────────────────────┐
│               Domain                  │
│   Entities / Value Objects / Rules    │
└───────────────────┬───────────────────┘
                    │
                    ▲
                    │ implements interfaces
                    │
┌───────────────────┴───────────────────┐
│            Infrastructure             │
│ SEC / Storage / Retrieval / Models    │
└───────────────────────────────────────┘