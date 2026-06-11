# Memory Recovery Audit — 2026-05-25

## Purpose

This note records the recovery check after the user reported that the afternoon
SQLite memory management/evaluation work and local data appeared to be missing.
It is a repository-facing audit note, not a runtime prompt.

## Git Checkpoints

- `3c10d85 checkpoint(memory): sqlite long-term memory baseline`
  - SQLite memory store.
  - Strict memory policy.
  - Orchestrator session identity fields.
  - Memory context injection.
  - Memory Inspector read/query surface.
  - Live memory E2E script.
  - Memory behavior contract.

- `bd0d6b7 feat(memory): add management api and offline eval`
  - Memory management API.
  - Memory Inspector management drawer.
  - Store `get/update/set_status/list_records`.
  - Offline memory eval dataset and runner.
  - Management, policy, API, store, frontend tests.

- `32cdf4e chore: sync latest local changes`
  - Large repository sync after the memory checkpoints.
  - Memory implementation files remain content-identical to `bd0d6b7` for the
    main store/API/Inspector/eval files.
  - `README.md` contains the expanded project architecture and usage guide.

## Memory Feature Inventory

The following files were verified as present:

- `app/services/orchestrator_agent/memory_store.py`
- `app/services/orchestrator_agent/memory_policy.py`
- `app/services/orchestrator_agent/memory_context.py`
- `app/api/orchestrator_routes.py`
- `app/static/js/components/panels/chat/MemoryInspector.jsx`
- `app/static/js/services/api.js`
- `scripts/memory_e2e_live.py`
- `tests/fixtures/golden/memory/eval_set.json`
- `tests/golden/memory_eval.py`
- `tests/golden/test_memory_eval.py`
- `docs/specs/memory-behavior-contract.md`

Implemented behavior still includes:

- SQLite + FTS5 long-term memory.
- `user_id/project_id/country/status` isolation.
- Strict write policy for durable memories.
- Rejection of greeting, model-identity, short confirmation, casual chat, and
  credential-like content.
- Memory management endpoints:
  - `GET /api/orchestrator/memory/list`
  - `POST /api/orchestrator/memory`
  - `PATCH /api/orchestrator/memory/{memory_id}`
  - `POST /api/orchestrator/memory/{memory_id}/archive`
  - `POST /api/orchestrator/memory/{memory_id}/restore`
  - `DELETE /api/orchestrator/memory/{memory_id}`
- Memory Inspector list/search/create/edit/archive/restore/soft-delete UI.
- Offline eval metrics:
  - `policy_accuracy`
  - `recall_at_8`
  - `no_leak_rate`
  - `redaction_pass_rate`
  - `management_pass_rate`

## Local Data Recovery

The project intentionally ignores local data/secrets:

- `.env`
- `key.json`
- `app/key.json`
- `data/**/*.csv`
- `data/**/*.json`
- `data/**/*.txt`
- `outputs/`

These files do not appear in normal `git status` because of `.gitignore`.

Recovered locally from git history:

- `.env`
- `key.json`
- `app/key.json`
- `data/app/by_uid/*.csv` — 7 files.
- `data/behavior/by_uid/*.csv` — 9 files.
- `data/credit/by_uid/*.csv` — 9 files.
- `data/credit/by_uid/824812551379353600.json`
- `data/sample_credit_data.json`
- `data/sample_ids.txt`

Recreated locally from the test contract because no git-history copy was found:

- `data/sample_behavior_data.csv`

These restored files are intentionally not committed because they are ignored
runtime/local data or secrets.

## Known Non-Recoverable Runtime State

The default runtime database exists at:

```text
outputs/memory/memory.sqlite3
```

The current database schema exists, but it has no memory records. The previous
manual Memory Inspector rows shown during afternoon testing were local runtime
state under `outputs/`, not tracked git content. No exact backup of that
runtime SQLite file was found in the repository, Trash, or obvious workspace
paths.

## Verification Commands

Memory eval:

```bash
python -m tests.golden.memory_eval --dataset tests/fixtures/golden/memory/eval_set.json --no-report
```

Expected result:

```text
policy_accuracy = 1.0
recall_at_8 = 1.0
no_leak_rate = 1.0
redaction_pass_rate = 1.0
management_pass_rate = 1.0
```

Memory/orchestrator tests:

```bash
python -m pytest tests/orchestrator_agent -q
```

Data recovery smoke tests:

```bash
python -m pytest tests/test_app_profile_phase1.py tests/test_data_prep_phase15.py tests/test_data_prep_phase16.py -q
python -m pytest tests/test_behavior_profile_phase18.py tests/test_credit_profile_phase17.py -q
```

Frontend/chat route tests:

```bash
python -m pytest tests/frontend/test_chat_phase3_capabilities.py tests/frontend/test_chat_skeleton.py tests/test_orchestrator_chat_routes.py tests/golden/test_memory_eval.py -q
```

## Manual Memory Inspector Acceptance

1. Start the service:

```bash
conda activate maps
uvicorn app.main:app --reload
```

2. Open `http://127.0.0.1:8000/`.
3. Open `自然语言对话 / NL Chat`.
4. Expand the `记忆` drawer.
5. Create a durable preference:

```text
category=preference
content=请记住：我的名字叫 Tom，我偏好中文简洁回答。
```

6. Use `列表` with `status=active` and `category=preference`; the row should
   appear.
7. Search with query `名字 偏好`; the row should be recalled.
8. Edit `Tom` to `Thomas`; searching `Thomas` should hit the updated content.
9. Archive it; normal query should no longer recall it.
10. List `status=archived`; the archived row should be visible.
11. Restore it; it should return to `active`.
12. Delete it; it should move to `deleted` and stay hidden from normal recall.

If `category_whitelist` appears, the content does not match the chosen category
or is too low-value for long-term memory. For example, `category=task` with
`你好，我叫 Tom` is rejected by design.
