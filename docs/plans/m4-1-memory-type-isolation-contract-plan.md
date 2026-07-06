# M4-1 Memory Type & Isolation Contract Plan

## Goal

Implement a dedicated M4 contract layer that defines memory source types,
authority levels, allowed/forbidden use boundaries, deterministic isolation
validation, and candidate adapters without changing persistence or retrieval.

## Implementation

1. Add `app/services/memory/` with:
   - `contracts.py`
   - `candidates.py`
   - `policy.py`
   - `isolation.py`
   - `adapters.py`
   - `__init__.py`
2. Keep the new layer independent from `app/services/orchestrator_agent/memory_*`.
3. Upgrade `app/services/profile_dag/memory_snapshot.py` to emit
   `MemoryUsePurpose.value` strings from the new policy source.
4. Add focused contract tests and update the existing profile snapshot test.
5. Add review/spec artifacts and update `PLANNING.md` / `TASK.md` with
   `M4-1 implemented / pending acceptance` wording.

## Verification

- `python -m compileall -q app data_acquisition_agent tests scripts`
- `AUTH_ENABLED=0 pytest tests/test_memory_type_isolation_contract.py -q`
- `AUTH_ENABLED=0 pytest tests/test_profile_memory_snapshot.py -q`
- `git diff --check`

Full regression is not required for M4-1. This stage is accepted only as a
focused contract slice, not as whole-M4 delivery.
