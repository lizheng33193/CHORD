# M7D CI / Release Gate / Load Smoke Plan

## Current State

- `M7-0 scope lock completed`
- `M7A Deployment & Runtime Readiness completed`
- `M7B Backup / Restore / Rollback completed`
- `M7C Monitoring / Alerting / Audit Boundary completed`
- `M7 implementation in progress`
- `M7D CI / Release Gate / Load Smoke not started`
- next step is `M7D CI / Release Gate / Load Smoke`

## Goal

Close the minimum M7D release-check loop so operators can run one repeatable sequence for startup smoke, runtime status, load smoke, and canonical production release gating.

## Implementation Changes

- add an M7D contract spec
- add an M7D execution plan
- add release-gate and load-smoke runbooks
- add `scripts/load_smoke.py`
- add `scripts/run_m7d_release_check.py`
- add a lightweight PR acceptance workflow
- update `PLANNING.md` and `TASK.md`

## Release Check Script

`scripts/run_m7d_release_check.py` remains a thin wrapper.

It must:

- run `compileall`
- run runtime directory bootstrap
- run startup smoke
- run runtime status snapshot
- run load smoke unless explicitly skipped
- run canonical `production_release --strict` when `--run-production-release` is passed
- generate a single JSON report

It must not:

- reimplement release-gate logic
- silently skip runtime checks when the service is down
- mutate `.env`
- execute SQL or profile flows

## Load Smoke Script

`scripts/load_smoke.py` provides safe GET-only smoke coverage.

It must:

- default to `GET /health`
- optionally include `GET /docs`
- validate `requests`, `concurrency`, and `timeout`
- record success / failure / `5xx` counts
- record latency summary
- emit JSON to file or stdout

It must not:

- call arbitrary endpoints
- call write APIs
- trigger LLM, SQL, indexing, or memory writes

## CI Workflow

`.github/workflows/m7d-pr-acceptance.yml` must stay lightweight.

It only validates:

- `compileall`
- runtime dir bootstrap
- `--help` entrypoints for M7A, M7C, and M7D scripts

It does not run live Docker or release-gate acceptance.

## Runbooks

- `docs/runbooks/release-gate-runbook.md`
  - operator sequence and release decision
  - explicit `docker compose up -d` prerequisite
  - `pre_m3_gate` noted as legacy reference only
- `docs/runbooks/load-smoke-runbook.md`
  - safe endpoint boundary
  - thresholds
  - failure interpretation

## Validation

Static validation:

```bash
python -m compileall -q app data_acquisition_agent tests scripts
python scripts/bootstrap_runtime_dirs.py
python scripts/load_smoke.py --help
python scripts/run_m7d_release_check.py --help
python scripts/collect_runtime_status.py --help
python scripts/smoke_startup_check.py --help
```

Runtime validation:

```bash
docker compose up -d
python scripts/smoke_startup_check.py --base-url http://127.0.0.1:8000 --timeout-seconds 30
python scripts/collect_runtime_status.py --base-url http://127.0.0.1:8000 --output-dir /tmp/chord-m7d-runtime-status --timeout-seconds 30
python scripts/load_smoke.py --base-url http://127.0.0.1:8000 --requests 50 --concurrency 5 --output-dir /tmp/chord-m7d-load-smoke --timeout-seconds 30
python scripts/run_m7d_release_check.py --base-url http://127.0.0.1:8000 --output-dir /tmp/chord-m7d-release-check --run-production-release --timeout-seconds 30 --production-release-timeout-seconds 600
docker compose down
git diff --check
git status --short
```

## Go Criteria

- all M7D docs and scripts exist
- `load_smoke.py` generates a valid JSON report
- `run_m7d_release_check.py` generates a valid JSON report
- Docker startup smoke passes
- runtime status snapshot passes
- load smoke passes
- canonical `production_release --strict` passes
- workflow exists and stays lightweight
- no runtime or test file diffs appear

## No-Go Criteria

- production release gate not run or failed
- load smoke failed on required `/health`
- wrapper introduced new release-gate logic
- workflow depends on real credentials or live service
- runtime behavior changed
- documentation claims `M7 completed`

## Known Limitations

- no full load-testing platform
- no auto-deploy or CD
- no Kubernetes rollout
- no Grafana / Prometheus deployment
- no runtime behavior change

## Next Step: M7E Final Acceptance & Commercial Delivery Docs

M7D completion leads to `M7E Final Acceptance & Commercial Delivery Docs`.
