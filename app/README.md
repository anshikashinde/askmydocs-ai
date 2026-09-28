# app/

Main application source code, structured following Clean Architecture principles.

Dependencies flow strictly inward:

```
infrastructure  →  application  →  domain
      ↑                                ↑
     api                         orchestration
      ↑                                ↑
                   shared
```

| Package | Clean Architecture Layer | Responsibility |
|---|---|---|
| `domain/` | Domain | Entities, value objects, domain services, repository interfaces |
| `application/` | Application | Use cases, command/query handlers, application services |
| `infrastructure/` | Infrastructure | DB adapters, vector store clients, LLM providers, storage |
| `api/` | Interface Adapters | FastAPI routers, request/response schemas, dependency injection |
| `orchestration/` | Orchestration | LangGraph workflows, multi-step reasoning pipelines |
| `shared/` | Cross-cutting | Logging, config, exceptions, base classes |
| `main.py` | Entrypoint | Application factory and server startup |
