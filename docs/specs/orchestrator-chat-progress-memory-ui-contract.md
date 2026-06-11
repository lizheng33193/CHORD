# Orchestrator Chat Progress And Memory UI Contract

## Purpose

This contract defines the NL Chat progress events and the UI boundary between
short-term chat history and long-term memory.

## Three-State Model

The dashboard now treats these as separate state layers:

- `workspace state`: the left-side profiling workspace rendered by the browser.
- `chat session`: the right-side NL Chat transcript stored under
  `outputs/orchestrator_sessions/`.
- `workspace snapshot`: a compact, reusable profile snapshot attached to the
  active chat session for read-only follow-up questions.

Session switching must not imply workspace replacement. Viewing history and
restoring a profiling workspace are separate actions.

## Profile Progress Events

`run_profile` keeps its final `tool_completed` event, but may also emit
module-level progress events while the tool is still running.

Event shape:

```json
{
  "type": "tool_progress",
  "tool_call_id": "<tool call id>",
  "tool_name": "run_profile",
  "progress_type": "profile_module_completed",
  "uid": "<uid>",
  "module": "app|behavior|credit|comprehensive|product|ops",
  "result": {"uid": "...", "module": "...", "status": "ok", "data": {}, "error": null},
  "status": "ok|error",
  "completed": 1,
  "total": 6
}
```

The frontend must treat `tool_progress` and `tool_completed` as idempotent
sources for the same module result. `tool_completed` remains the durable final
tool output written into the session.

The backend should log module progress with enough fields to locate a stuck
profile run: `session_id`, `tool_call_id`, `uid`, `module`, `completed`,
`total`, `status`, and elapsed time where available. These logs are
observability-only and do not change the SSE wire shape.

## Session History

Short-term chat history is stored as session JSON under
`outputs/orchestrator_sessions/`.

`GET /api/orchestrator/sessions?limit=20` returns recent session metadata for
the request identity. It does not return full messages.

Each session list item contains:

- `session_id`
- `created_at`
- `updated_at`
- `status`
- `user_id`
- `project_id`
- `country`
- `message_count`
- `last_user_message_preview`
- `final_message_preview`

The v1 UI supports listing and opening sessions only. It does not delete or
hard-delete session files.

Opening a history row now means:

- switch the right-side chat transcript to that session;
- keep the current left-side workspace untouched;
- update the URL session pointer without forcing a full page reload.

Restoring the left-side workspace is a second, explicit action:

- `恢复该次分析结果` fetches `GET /api/orchestrator/sessions/{id}`;
- the frontend rebuilds `analysisResults`, `moduleStatesByUid`, and
  `traceSeedByUid` from durable `tool_calls` first;
- if a matching module result is not present in `tool_calls`, the frontend may
  fall back to `active_entities.workspace_snapshot`.

The UI may add client-side search and filters over this metadata. Search must
not require full message payloads and must keep session history read-only.

## Workspace Snapshot Contract

`POST /api/orchestrator/sessions` and
`POST /api/orchestrator/sessions/{id}/messages` accept an optional
`workspace_snapshot` field.

Stored location:

- `OrchestratorSession.active_entities.workspace_snapshot`

Snapshot wire shape:

```json
{
  "country": "mx",
  "applicationTime": "2026-04-15T12:00:00Z",
  "results": [
    {
      "uid": "8248...",
      "module": "behavior",
      "summary": "行为画像摘要",
      "structured_result": {}
    }
  ]
}
```

Frontend constraints:

- only include the currently selected UID;
- only include successful modules;
- only include `summary` and `structured_result`;
- do not send charts or full markdown reports.

The browser also keeps a richer `sessionStorage` snapshot for same-tab refresh
recovery. That browser-local snapshot is not part of long-term memory and is
not a server API contract.

## Snapshot Reuse Guard

Before the agent enters the normal LLM decision loop, it may answer directly
from reusable profiling state when all of these are true:

- the user message is a read-only follow-up such as comprehensive summary,
  behavior summary, credit summary, product advice, or ops advice;
- the message does not explicitly ask for rerun/refresh/latest regeneration;
- the current session already contains matching successful `run_profile`
  results, or a matching `workspace_snapshot`.

Priority:

1. successful `session.tool_calls`
2. `active_entities.workspace_snapshot`

Direct snapshot answers are deterministic template responses. They bypass both
`run_profile` and the LLM decision step so that already analyzed users do not
re-trigger full profiling on simple follow-up questions.

## Long-Term Memory

Long-term memory remains SQLite + FTS5 at `outputs/memory/memory.sqlite3`.

UI language must make these statuses explicit:

- `active`: participates in future recall.
- `archived`: does not participate in recall, but can be restored.
- `deleted`: soft-deleted, does not participate in recall, but can still be
  listed and restored.

The v1 UI does not hard delete memory rows and does not clear deleted rows.

The UI should explain recall eligibility in user-facing language:

- Active rows for the current identity can be recalled when query/list filters
  match their content, category, tags, or country.
- Archived and deleted rows do not participate in recall, but can be viewed and
  restored through the inspector.
