# M7 Operator Quickstart

## 1. Prepare Environment

```bash
cp .env.example .env
```

Notes:

- `.env` is local-only and must not be committed
- M7 defaults to a mock-first posture
- real model, DB, auth, and other deployment-specific overrides are operator-owned

## 2. Start

```bash
docker compose up -d
```

## 3. Startup Smoke

```bash
python scripts/smoke_startup_check.py --base-url http://127.0.0.1:8000 --timeout-seconds 30
```

## 4. Runtime Status Snapshot

```bash
python scripts/collect_runtime_status.py --base-url http://127.0.0.1:8000 --output-dir /tmp/chord-runtime-status --timeout-seconds 30
```

## 5. Backup

```bash
python scripts/backup_local_state.py --output-dir /tmp/chord-backups
```

Do not place secrets in the backup archive. `.env`, keys, and certificates are excluded by design.

## 6. Load Smoke

```bash
python scripts/load_smoke.py --base-url http://127.0.0.1:8000 --requests 50 --concurrency 5 --output-dir /tmp/chord-load-smoke --timeout-seconds 30
```

## 7. Release Check

```bash
python scripts/run_m7d_release_check.py --base-url http://127.0.0.1:8000 --output-dir /tmp/chord-release-check --run-production-release --timeout-seconds 30 --production-release-timeout-seconds 600
```

Canonical strict gate inside that flow:

```bash
python -m app.eval.runner --profile production_release --strict
```

## 8. Stop

```bash
docker compose down
```

## 9. Important Boundaries

- `app.release.pre_m3_gate` is legacy / compatibility reference only
- if local `.env` sets `AUTH_ENABLED=true`, startup also requires a reachable auth DB and no longer matches the M7 mock-first minimum posture
- external DB backup is not handled by the local M7 backup scripts
- M7 is minimum commercial readiness, not enterprise production certification
