# Load Smoke Runbook

## Scope

This runbook defines the minimum M7D load smoke boundary for CHORD.

## What Load Smoke Tests

Load smoke verifies that safe GET endpoints remain stable under light concurrent access.

Default endpoint:

- `GET /health`

Optional advisory endpoint:

- `GET /docs`

## What Load Smoke Does Not Test

Load smoke does not test:

- profile analysis endpoints
- SQL execution
- LLM-dependent routes
- Risk Knowledge indexing
- memory writes
- authentication mutations
- write APIs
- production-scale performance

## Default Command

```bash
python scripts/load_smoke.py \
  --base-url http://127.0.0.1:8000 \
  --requests 50 \
  --concurrency 5 \
  --output-dir /tmp/chord-m7d-load-smoke \
  --timeout-seconds 30
```

Optional docs coverage:

```bash
python scripts/load_smoke.py \
  --base-url http://127.0.0.1:8000 \
  --requests 50 \
  --concurrency 5 \
  --output-dir /tmp/chord-m7d-load-smoke \
  --timeout-seconds 30 \
  --include-docs
```

## Thresholds

Required `/health` gate:

- `2xx` responses are success
- non-`2xx` responses are failures
- `5xx` responses also increment `status_5xx_count`
- `status_5xx_count` must stay at `0`
- `error_rate` must stay at or below `0.01`

Warning-only threshold:

- `p95 > 1000ms`

## Report Format

Output file:

- `load-smoke-YYYYMMDD-HHMMSS.json`

Report fields include:

- `report_version`
- `created_at`
- `base_url`
- `requests`
- `concurrency`
- `overall_status`
- `go`
- `endpoints`
- `warnings`
- `failures`
- `thresholds`

## Failure Handling

- if `/health` reports any `5xx`, stop release
- if `/health` error rate exceeds `1%`, stop release
- if `/docs` only has non-`2xx` non-`5xx` responses, treat as advisory
- if `/docs` reports `5xx`, treat as a release warning that must be reviewed before proceeding

## Known Limitations

- not a full performance benchmark
- not a saturation or soak test
- not a distributed test harness
- only safe GET endpoints are allowed
