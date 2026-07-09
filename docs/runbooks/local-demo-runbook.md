# M7A Local Demo Runbook

## Goal

Demonstrate that CHORD can be started and sanity-checked in minimum M7A mode.

This is not a feature-complete commercial demo.

## Demo Preconditions

- `.env` created from `.env.example`
- runtime directories bootstrapped
- service started locally or via Docker Compose

## Demo 1: Health Check

Verify the API is alive:

```bash
curl http://127.0.0.1:8000/health
```

Expected:

- HTTP `200`
- JSON status payload

## Demo 2: API Docs

Open:

- [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

This confirms the service is serving the FastAPI docs surface in minimum startup mode.

## Demo 3: Basic Startup Smoke

Run:

```bash
python scripts/smoke_startup_check.py --base-url http://127.0.0.1:8000 --timeout-seconds 30
```

Expected:

- `health: ok`
- `docs: ok` or a clearly reported non-5xx advisory result

## Recommended Demo Posture

- `MODEL_MODE=mock`
- `AUTH_ENABLED=0`
- `DATA_ACQUISITION_ENABLED=false`

This keeps the demo focused on startup readiness instead of external dependency setup.

## What This Demo Does Not Cover

- M7B backup / restore / rollback
- M7C monitoring / alerting / audit boundary
- M7D CI / release gate / load smoke
- M7E final acceptance / commercial delivery docs
- real model-backed profile generation
- Risk Knowledge indexing workflows
- Data Acquisition live database workflows
