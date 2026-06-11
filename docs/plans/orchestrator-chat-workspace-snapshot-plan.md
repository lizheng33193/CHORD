# Orchestrator Chat Workspace Snapshot Plan

## Goal

Fix two coupled UX problems in NL Chat:

- viewing short-term history should not wipe the current profiling workspace;
- read-only follow-up questions should reuse existing profile results instead of
  re-running `run_profile` by default.

## Scope

This plan covers three harness layers together:

- frontend workspace state and history interactions;
- orchestrator session API contract;
- backend deterministic reuse guard before the normal LLM tool loop.

## Decisions

1. Session history and workspace restoration are separate actions.
2. Left-side workspace state is browser-tab state and is persisted with
   `sessionStorage`.
3. Chat sessions may carry a compact `workspace_snapshot`, but long-term memory
   still stores only preferences, task facts, and project facts.
4. Read-only follow-ups reuse durable `tool_calls` first, then the compact
   snapshot, and only fall back to `run_profile` when required data is missing
   or the user explicitly asks for rerun/refresh/latest output.

## Implementation Tasks

- Add `workspace_snapshot` to session create/send routes and store it under
  `active_entities.workspace_snapshot`.
- Persist left-side dashboard workspace into `sessionStorage` and restore it on
  same-tab refresh.
- Change history click behavior from full-page navigation to in-place chat
  session switching.
- Add an explicit `恢复该次分析结果` action that rebuilds workspace state from
  historical `tool_calls`.
- Add a deterministic snapshot reuse guard in `agent_loop` for read-only
  follow-ups.
- Cover the new behavior with frontend, route, and agent-loop tests.

## Verification

- `tests/frontend/test_chat_phase3_capabilities.py`
- `tests/frontend/test_chat_skeleton.py`
- `tests/test_orchestrator_chat_routes.py`
- `tests/test_orchestrator_phase3.py`
- `tests/test_orchestrator_golden.py`
