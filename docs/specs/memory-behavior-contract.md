# Orchestrator Memory Behavior Contract

## Purpose

This contract defines how the Orchestrator chat memory subsystem behaves in the
SQLite v1 implementation.

The memory subsystem serves only `/api/orchestrator/*` chat. It must not affect
App Profile, Behavior Profile, Credit Profile, Comprehensive Profile, product
advice, or ops advice outputs unless those flows are explicitly invoked through
the Orchestrator chat.

## Memory Boundaries

- Short-term memory is the active `OrchestratorSession.messages` history. It is
  responsible for questions such as "what did I just say?" within the same chat
  session.
- Rolling summary is session-local compression context. It helps preserve long
  session continuity, but it is not a durable user fact by itself.
- Long-term memory is persisted in SQLite at `outputs/memory/memory.sqlite3`.
  It can be recalled across sessions only after passing the strict write policy.

## Long-Term Write Policy

Long-term memory is strict whitelist by default.

Allowed categories:

- `preference`: explicit user preferences, defaults, durable output style
  requests, or "please remember" statements.
- `feedback`: user corrections about the agent's behavior or prior output.
- `project`: project facts, accepted decisions, implementation state, durable
  domain constraints, or current operating assumptions.
- `reference`: URLs, local paths, API entry points, documents, or other durable
  reference locations.
- `task`: real analysis or engineering task requests such as profile analysis,
  data query, trace investigation, implementation, testing, or debugging.

Rejected by default:

- Greetings, thanks, short confirmations, filler, and casual chat.
- Model identity questions such as "what model are you?".
- Generic assistant self-introductions or fallback replies.
- Standalone credentials or secret-looking values.
- Content that does not match the target category whitelist.
- Automatic `orchestrator_final -> insight` writes. Assistant final messages
  are not persisted as long-term memory in v1.

Sensitive fragments may be redacted and kept only when the remaining content is
still useful, such as "user prefers Chinese output, token=<TOKEN>".

## Identity And Recall

Every long-term memory is scoped by:

- `user_id`
- `project_id`
- `country`
- `status`

Default identity:

- `user_id=local-default-user`
- `project_id=agent-user-profile-fork`
- `country=mx`

Routes may override identity through `X-User-ID`, `X-Project-ID`, and
`X-Country`. The debug query API may also accept identity in the request body.

Recall uses hard identity filters first, then SQLite FTS5/LIKE retrieval, then
score ranking by relevance, importance, confidence, and recency. Empty query
means "list recent active memories" under the same filters.

## Debug Interfaces

- `GET /api/orchestrator/memory/status`
  returns backend, database path, total count, category counts, and status
  counts.
- `POST /api/orchestrator/memory/query`
  accepts `query`, `user_id`, `project_id`, `country`, `category`, and `top_k`.
  It returns retrieved memory rows with `score` and `score_parts`.

## Management Interfaces

Memory management is available only under `/api/orchestrator/memory/*`.

- `GET /api/orchestrator/memory/list`
  lists rows by `user_id`, `project_id`, `country`, optional `category`, optional
  `status`, and `limit`. The default status is `active`; `status=all` lists all
  statuses under the same identity.
- `POST /api/orchestrator/memory`
  manually creates a memory row. The row still passes redaction, length limits,
  category whitelist checks, low-value rejection, and credential rejection.
- `PATCH /api/orchestrator/memory/{memory_id}`
  edits `content`, `category`, `importance`, `confidence`, `tags`, or
  `expires_at`. Editing content or category refreshes FTS and dedupe keys.
- `POST /api/orchestrator/memory/{memory_id}/archive`
  sets `status=archived`.
- `POST /api/orchestrator/memory/{memory_id}/restore`
  sets `status=active`.
- `DELETE /api/orchestrator/memory/{memory_id}`
  performs soft delete by setting `status=deleted`.

All management operations must match `user_id`, `project_id`, and `country`.
When the identity does not match, the API returns 404 so memory ids cannot be
used to discover or mutate another user's rows. Duplicate update conflicts
return 409. Manual create/edit rows use `source=memory_admin`.

The NL Chat Memory Inspector is the first UI for these APIs. It supports list,
search, create, edit, archive, restore, and soft delete, but it does not hard
delete SQLite rows or perform batch import/export in v1.

## Testing Contract

Stable regression tests should use pytest with fake or isolated stores.

Offline memory quality eval uses:

```bash
python -m tests.golden.memory_eval --dataset tests/fixtures/golden/memory/eval_set.json
```

The runner uses a temporary SQLite database by default and writes reports to
`outputs/evals/memory/`. Required v1 gates are:

- `policy_accuracy = 1.0`
- `no_leak_rate = 1.0`
- `redaction_pass_rate = 1.0`
- `management_pass_rate = 1.0`
- `recall_at_8 >= 0.90`

Live E2E uses:

```bash
conda activate maps
uvicorn app.main:app --reload
python scripts/memory_e2e_live.py --base-url http://127.0.0.1:8000
```

The live script requires a usable real model configuration, typically
`MODEL_MODE=gemini` and `GEMINI_API_KEY`.

## Future Upgrade Conditions

Do not add embedding, vector search, consolidation, or dreaming until at least
one of these conditions is true:

- A single identity regularly has more than roughly 100 active memories.
- SQLite FTS/LIKE retrieval misses important memories in manual or automated
  evals.
- Duplicate or conflicting memories become common enough to require background
  consolidation.
- Product requirements exceed the current edit/archive/restore/soft-delete
  governance model.

When that happens, extend the existing management APIs with conflict resolution
and audit history before connecting an external vector database.
