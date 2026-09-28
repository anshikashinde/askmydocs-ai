# Tests

Test suites organized by scope and isolation level.

| Subdirectory | Scope | Speed | Notes |
|---|---|---|---|
| `unit/` | Single function / class | Fast | No I/O; all dependencies mocked |
| `integration/` | Multiple components together | Medium | May use real DB/vector store via Docker |
| `e2e/` | Full API surface | Slow | Spins up full stack; used in CI on main branch |

Run all tests:
```bash
pytest
```

Run a specific scope:
```bash
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/
```
