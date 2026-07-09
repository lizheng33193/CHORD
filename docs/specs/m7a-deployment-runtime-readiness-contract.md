# M7A Deployment & Runtime Readiness Contract

## Goal

M7A establishes the minimum deployment and startup contract for CHORD.

It is Docker-first, mock-first, and limited to runtime readiness.

It does not attempt to deliver full production infrastructure.

## In Scope

- top-level `Dockerfile`
- top-level `docker-compose.yml` for `api + redis`
- `.dockerignore` with secret and runtime-artifact exclusions
- `.env.example` aligned to mock-first local/Docker startup
- runtime directory bootstrap script
- startup smoke script
- deployment runbook
- local demo runbook
- minimal `PLANNING.md` / `TASK.md` status updates

## Non-Goals

- no Kubernetes / Helm
- no CI/CD implementation
- no monitoring / alerting implementation
- no backup / restore / rollback implementation
- no load smoke
- no README rewrite
- no docs review / architecture / checklist artifacts
- no app runtime behavior change

## Startup Contract

- `cp .env.example .env` must produce a minimum startup-friendly environment.
- `MODEL_MODE=mock` is the default runtime mode for M7A.
- `DATA_ACQUISITION_ENABLED=false` is the default minimum startup posture.
- `AUTH_ENABLED=0` is the default minimum startup posture.
- `MEMORY_VECTOR_CONTEXT_INJECTION_ENABLED=0` remains the default.
- `HYBRID_RETRIEVAL_ENABLED=0` remains the default Data Agent hybrid posture.

## Docker Contract

- `docker compose up --build` must start:
  - `api`
  - `redis`
- the API service must bootstrap runtime directories before starting `uvicorn`
- runtime outputs and storage remain mounted from the host
- repository `data/` remains read-only inside the container
- MySQL is not part of the M7A minimum stack

## Smoke Contract

- `/health` is a required check and must return `200`
- `/docs` is a second check and must not fail with `5xx`
- the smoke script must retry `/health` until success or timeout
- the smoke script must not call real LLM providers, indexing jobs, profile analysis, release gates, or memory writes

## Blocker Rule

If minimum Docker/local startup requires modifying `app/` runtime behavior, M7A must stop and report a blocker instead of expanding scope.

## Completion Rule

M7A can be marked completed only if:

- compileall passes
- runtime directory bootstrap passes
- Docker build passes
- Docker Compose startup passes
- startup smoke passes
- conservative defaults remain unchanged

Otherwise the state must remain:

- `M7A implemented; pending acceptance`
