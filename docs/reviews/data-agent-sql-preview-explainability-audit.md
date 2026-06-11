# Data Agent SQL Preview Explainability Audit

## Current Contract

- `query_data` HITL preview currently emits `awaiting_user_ack` with only:
  - `ack_id`
  - `tool_call_id`
  - `sql_text`
  - `rows_estimated`
- Frontend `ChatAckCard` renders `pendingAck.sql_text` directly inside a `<pre>` block.
- `pending_ack.sql_text` is also restored through session history and reducer state.

## Current Execution Boundary

- `QueryDataThenProfileFlow` and `GeneralChatFlow` both build query-data preview ACK payloads in their local `_preview_query()` choke points.
- `approved` execution continues from `DataQueryPreview.raw_preview["sql_text"]`.
- `awaiting_user_ack.sql_text` is not the execution source in the live approve path.
- Current “resume” is page/session restore against the same live worker, not process-restart reconstruction of a query worker.

## D1.2 Change

- ACK payload shape remains unchanged.
- `awaiting_user_ack.sql_text` and `pending_ack.sql_text` become display-oriented preview text:
  - readable summary
  - filter/time-window hints when available
  - confirmation guidance
  - raw SQL section at the end
- `rows_estimated` remains unchanged.
- No new SSE fields, reducer fields, or assistant messages are added.

## Critical Boundary

- After D1.2, `awaiting_user_ack.sql_text` is **display preview text**, not execution SQL.
- Execution SQL must continue to come from internal `raw_preview["sql_text"]`.
- `single-shot` `QueryDataOutput.sql_text` remains raw SQL and is not wrapped by this change.
- Repair ACK preview is out of scope for D1.2.

## Compatibility Notes

- Frontend restore must preserve multi-line wrapped preview text without schema changes.
- Same-process approve after page/session restore must still execute raw SQL through the live worker path.
- D1.2 does **not** introduce process-restart resume of query-data ACK execution.
