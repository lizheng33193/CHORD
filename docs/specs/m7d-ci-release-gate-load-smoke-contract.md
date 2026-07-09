# M7D CI / Release Gate / Load Smoke Contract

## Scope

M7D defines the minimum commercial release-check boundary for CHORD after M7A, M7B, and M7C.

It adds a lightweight CI workflow, a release-check wrapper, and a safe load-smoke script.

## CI Boundary

M7D CI is PR acceptance only.

It validates:

- `compileall`
- runtime directory bootstrap
- script CLI availability for:
  - `scripts/load_smoke.py`
  - `scripts/run_m7d_release_check.py`
  - `scripts/collect_runtime_status.py`
  - `scripts/smoke_startup_check.py`

It does not validate:

- live Docker startup
- live HTTP smoke
- live load smoke
- `production_release --strict`
- real API keys, LLMs, or MySQL

## Release Gate Boundary

The canonical M7D production release gate is:

```bash
python -m app.eval.runner --profile production_release --strict
```

`app.release.pre_m3_gate` remains a legacy / compatibility reference only.

M7D does not introduce a second release-gate policy engine.

`scripts/run_m7d_release_check.py` is a thin wrapper that orchestrates:

- `compileall`
- runtime directory bootstrap
- startup smoke
- runtime status snapshot
- load smoke
- the canonical `production_release --strict` gate when explicitly requested

## Load Smoke Boundary

`scripts/load_smoke.py` is a minimum safe GET-only smoke tool.

Default endpoint:

- `GET /health`

Optional advisory endpoint:

- `GET /docs` via `--include-docs`

Load smoke must not:

- call LLMs
- execute SQL
- run profile analysis
- trigger Risk Knowledge indexing
- write memory
- call mutation endpoints

`/health` success means `2xx`.

Any non-`2xx` response counts as a failure, and any `5xx` response also increments `status_5xx_count`.

## Report Contract

`scripts/load_smoke.py` writes:

- `load-smoke-YYYYMMDD-HHMMSS.json`

`scripts/run_m7d_release_check.py` writes:

- `m7d-release-check-YYYYMMDD-HHMMSS.json`

Reports must include:

- report version
- creation time
- overall status
- go / no-go boolean
- warnings
- failures or required failures
- artifact paths or `not_run`

`--no-write` means:

- do not create the output directory
- do not persist JSON files
- write the JSON payload to stdout only

## Production Release Strict Contract

The wrapper must use:

```bash
python -m app.eval.runner --profile production_release --strict
```

It may append `--output-dir` so the artifact path is captured in the M7D report.

`--timeout-seconds` applies only to HTTP and runtime checks.

`production_release --strict` must use the dedicated timeout:

- `--production-release-timeout-seconds`
- default `600`

## Go / No-Go Criteria

Go requires:

- spec / plan / runbooks completed
- `load_smoke.py` exists and generates JSON output
- `run_m7d_release_check.py` exists and generates JSON output
- Docker startup smoke passes
- runtime status snapshot passes
- load smoke passes
- canonical `production_release --strict` passes
- CI workflow exists and remains lightweight
- no `app/*` diff
- no `tests/*` diff

No-go includes:

- `production_release --strict` not run or failed
- load smoke hits unsafe endpoints
- load smoke fails on `/health`
- wrapper reimplements release-gate logic
- workflow depends on real LLM / DB / live service
- runtime behavior changes

## Non-goals

M7D does not provide:

- full load testing
- Locust / k6 / JMeter integration
- automatic CD
- Kubernetes rollout
- Grafana / Prometheus
- runtime behavior change
- production certification

## Validation Contract

Required validation commands:

```bash
python -m compileall -q app data_acquisition_agent tests scripts
python scripts/bootstrap_runtime_dirs.py
python scripts/load_smoke.py --help
python scripts/run_m7d_release_check.py --help
python scripts/collect_runtime_status.py --help
python scripts/smoke_startup_check.py --help
```

Runtime validation requires:

```bash
docker compose up -d
python scripts/smoke_startup_check.py --base-url http://127.0.0.1:8000 --timeout-seconds 30
python scripts/collect_runtime_status.py --base-url http://127.0.0.1:8000 --output-dir /tmp/chord-m7d-runtime-status --timeout-seconds 30
python scripts/load_smoke.py --base-url http://127.0.0.1:8000 --requests 50 --concurrency 5 --output-dir /tmp/chord-m7d-load-smoke --timeout-seconds 30
python scripts/run_m7d_release_check.py --base-url http://127.0.0.1:8000 --output-dir /tmp/chord-m7d-release-check --run-production-release --timeout-seconds 30 --production-release-timeout-seconds 600
docker compose down
```
