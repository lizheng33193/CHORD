# Release Gate Runbook

## Scope

This runbook defines the minimum M7D pre-release flow for CHORD.

It covers startup smoke, runtime status snapshot, load smoke, and the canonical production release gate.

## Pre-release Checklist

- confirm branch changes are ready for release review
- confirm the latest local state backup exists if the release changes runtime-facing assets
- confirm the operator has a rollback path from the M7B runbook
- confirm `.env` matches the intended runtime posture

## Environment Preparation

Before running the wrapper, start the minimum service stack:

```bash
docker compose up -d
```

Do not expect `scripts/run_m7d_release_check.py` to silently skip service-dependent checks.

If the service is not up, startup smoke, runtime status, and load smoke should fail.

## Startup Smoke

Required command:

```bash
python scripts/smoke_startup_check.py --base-url http://127.0.0.1:8000 --timeout-seconds 30
```

This is the M7A startup smoke entrypoint.

## Runtime Status Snapshot

Required command:

```bash
python scripts/collect_runtime_status.py \
  --base-url http://127.0.0.1:8000 \
  --output-dir /tmp/chord-m7d-runtime-status \
  --timeout-seconds 30
```

This is the M7C monitoring boundary snapshot.

## Load Smoke

Required command:

```bash
python scripts/load_smoke.py \
  --base-url http://127.0.0.1:8000 \
  --requests 50 \
  --concurrency 5 \
  --output-dir /tmp/chord-m7d-load-smoke \
  --timeout-seconds 30
```

Default scope:

- `GET /health`

Optional advisory scope:

- `GET /docs` via `--include-docs`

## Production Release Strict Gate

Canonical M7D gate:

```bash
python -m app.eval.runner --profile production_release --strict
```

The M7D wrapper may add `--output-dir` to collect the artifact path, but it must keep this entrypoint and profile unchanged.

Legacy reference only:

```bash
python -m app.release.pre_m3_gate --profile production_release --strict
```

`pre_m3_gate` remains historical / compatibility guidance and is not part of the M7D default wrapper path.

## Release Decision

Recommended combined command:

```bash
python scripts/run_m7d_release_check.py \
  --base-url http://127.0.0.1:8000 \
  --output-dir /tmp/chord-m7d-release-check \
  --run-production-release \
  --timeout-seconds 30 \
  --production-release-timeout-seconds 600
```

Interpretation:

- `overall_status=pass`: release checks passed
- `overall_status=warn`: no required failure, but warnings need operator review
- `overall_status=fail`: do not proceed

## Failure Handling

- startup smoke failed:
  - inspect `docker compose logs`
  - re-run M7A bootstrap and smoke steps
- runtime status failed:
  - inspect M7C snapshot output
  - resolve readiness failures before re-running
- load smoke failed:
  - inspect `load-smoke-*.json`
  - stop release if `/health` has failures or `5xx`
- production release strict failed:
  - inspect the shared eval report
  - treat as no-go until deterministic gate failures are resolved

## Rollback / Restore References

- local state backup and restore: `docs/runbooks/backup-restore-runbook.md`
- rollback sequence: `docs/runbooks/rollback-runbook.md`

## Known Limitations

- no full performance benchmark
- no distributed load test
- no auto-deploy
- no Kubernetes rollout
- no production certification
