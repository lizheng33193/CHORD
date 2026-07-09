# M7A Deployment & Runtime Readiness Plan

## Summary

- Add the minimum Docker-first deployment assets for CHORD.
- Keep startup mock-first and low-dependency.
- Document local Python and Docker Compose bring-up without changing runtime behavior.

## Key Changes

1. Add root deployment assets:
   - `Dockerfile`
   - `docker-compose.yml`
   - `.dockerignore`
2. Normalize startup-facing configuration:
   - update `.env.example` to mock-first defaults
   - keep `MEMORY_VECTOR_CONTEXT_INJECTION_ENABLED=0`
   - keep `HYBRID_RETRIEVAL_ENABLED=0`
3. Add minimum operational scripts:
   - `scripts/bootstrap_runtime_dirs.py`
   - `scripts/smoke_startup_check.py`
4. Add minimum delivery docs:
   - `docs/specs/m7a-deployment-runtime-readiness-contract.md`
   - `docs/runbooks/deployment-runbook.md`
   - `docs/runbooks/local-demo-runbook.md`
5. Update status tracking:
   - `PLANNING.md`
   - `TASK.md`

## Guardrails

- no `app/` changes
- no `tests/` changes
- no `.github/` changes
- no `README.md` changes
- no `docs/reviews/*`
- no invented env flags
- no Docker MySQL dependency in the minimum stack

## Verification

- `python -m compileall -q app data_acquisition_agent tests scripts`
- `python scripts/bootstrap_runtime_dirs.py`
- `docker compose build`
- `docker compose up -d`
- `python scripts/smoke_startup_check.py --base-url http://127.0.0.1:8000 --timeout-seconds 30`
- `docker compose down`
- `git diff --check`
