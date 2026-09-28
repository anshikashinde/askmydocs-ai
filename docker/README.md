# Docker

Supplementary Docker configuration files.

The root `Dockerfile` and `docker-compose.yml` cover the primary development stack.
This directory holds any additional Dockerfiles or compose overrides needed for specific environments.

Examples:
- `docker-compose.prod.yml` — production overrides (resource limits, secrets management)
- `docker-compose.test.yml` — isolated test environment
- `Dockerfile.worker` — separate image for background ingestion workers
