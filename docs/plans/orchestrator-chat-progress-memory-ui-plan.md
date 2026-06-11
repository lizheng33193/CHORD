# Orchestrator Chat Progress And Memory UI Plan

## Summary

Implement module-level progress for NL Chat profile runs, add a read-only
session history surface, and clarify long-term memory copy so users can
distinguish chat history from durable recalled memory.

## Implementation

- Add `tool_progress` events for each completed `run_profile` `{uid, module}`.
- Keep final `tool_completed` unchanged as the durable session output.
- Add `GET /api/orchestrator/sessions` for recent session metadata.
- Update Chat UI to ingest module progress immediately and show completed
  module buttons only.
- Split the Memory Inspector surface into `短期会话历史` and `长期记忆`.
- Keep long-term memory delete as soft delete; do not add hard delete.

## Verification

- Golden/contract tests cover generic UID analysis vs explicit trace requests.
- Agent loop e2e verifies `tool_started -> tool_progress -> tool_completed`.
- Frontend reducer/static tests cover `tool_progress` and memory/session copy.
- Memory API tests cover session list identity isolation, sorting, previews,
  and limit.
