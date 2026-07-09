# M7A Deployment Runbook

## Scope

This runbook covers minimum commercial deployment readiness for M7A.

It does not cover Kubernetes, automatic CD, monitoring platforms, backup and restore, rollback implementation, or load testing.

## Runtime Modes

- local Python mode
- Docker Compose mode

## Required Dependencies

- Python 3.11+
- Docker and Docker Compose
- Redis

Optional dependencies:

- Gemini / Vertex / other real model credentials
- Data Acquisition database dependencies

## Environment Setup

Create the runtime environment file:

```bash
cp .env.example .env
```

Default posture:

- `MODEL_MODE=mock`
- `AUTH_ENABLED=0`
- `DATA_ACQUISITION_ENABLED=false`
- `MEMORY_VECTOR_CONTEXT_INJECTION_ENABLED=0`
- `HYBRID_RETRIEVAL_ENABLED=0`

Docker-specific overrides are documented inline in `.env.example`.

## Runtime Directory Bootstrap

Initialize runtime directories before bring-up:

```bash
python scripts/bootstrap_runtime_dirs.py
```

This step is idempotent and does not delete or rewrite existing business data.

## Local Python Start

Start the service in minimum startup mode:

```bash
MODEL_MODE=mock AUTH_ENABLED=0 DATA_ACQUISITION_ENABLED=false uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Docker Compose Start

Build and start the minimum stack:

```bash
docker compose up --build
```

The minimum M7A stack is:

- `api`
- `redis`

MySQL is intentionally out of scope for this stage.

## Health Check

Required check:

```bash
curl http://127.0.0.1:8000/health
```

Expected result:

- HTTP `200`
- body contains `{"status":"ok"}` or equivalent JSON payload

## Startup Smoke

Run the minimum smoke script after local or Docker startup:

```bash
python scripts/smoke_startup_check.py --base-url http://127.0.0.1:8000 --timeout-seconds 30
```

Smoke semantics:

- `/health` is required
- `/docs` is checked as a second endpoint
- no LLM calls
- no profile analysis
- no indexing jobs
- no release gate
- no memory writes

## Conservative Defaults

M7A must preserve the current conservative posture:

- semantic memory context injection remains default-off
- Data Agent hybrid retrieval remains disabled
- Data Acquisition stays disabled in the minimum startup flow

## Troubleshooting

### Port 8000 already in use

- stop the conflicting process
- or change the local bind port before retrying

### Redis unavailable

- confirm Docker Compose started the `redis` service
- confirm the Redis URL points to `redis://redis:6379/15` inside Docker

### `.env` missing

- re-run `cp .env.example .env`

### outputs / storage permission issue

- re-run `python scripts/bootstrap_runtime_dirs.py`
- verify host permissions on `outputs/` and `storage/`

### real model key missing

- keep `MODEL_MODE=mock` for M7A
- only switch to real providers after minimum startup is already working

## Known Limitations

- no Kubernetes / Helm
- no automatic CD
- no monitoring or alerting implementation
- no backup / restore or rollback implementation
- no load smoke
- no final commercial acceptance

## Explicit Non-Goals

- changing application runtime behavior
- enabling semantic memory by default
- enabling Data Agent hybrid retrieval by default
- introducing MySQL as a minimum startup dependency
