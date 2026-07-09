# M7C Audit Boundary Runbook

## Scope

This runbook defines the minimum audit boundary for CHORD in M7C.

It records what must be auditable and what remains future work.

## Audit Boundary

M7C documents audit requirements and current coverage.

M7C does not implement a persistent DB audit stream.

## High-risk Action Inventory

Auth:

- login
- logout
- register

Profile:

- profile run
- batch profile run
- profile export
- degraded result return

Data Agent:

- SQL generate
- SQL approve
- SQL reject
- SQL execute
- SQL execute failure

Risk Knowledge:

- document upload
- indexing job start
- indexing retry
- indexing cancel
- manifest activation
- manifest rollback

Memory:

- memory create
- memory archive
- memory restore
- memory delete
- semantic memory context decision

Operations:

- backup created
- restore executed
- rollback executed
- runtime status snapshot collected

## Existing Audit Coverage

Current persistent audit base:

- `audit_events` table
- `record_audit_event(...)`
- `record_runtime_audit_event(...)`

Current persisted field set:

- `user_id`
- `project_id`
- `country`
- `event_type`
- `resource_type`
- `resource_id`
- `action`
- `status`
- `request_id`
- `session_id`
- `trace_id`
- `metadata_json`
- `created_at`

## Recommended Future Audit Fields

These are future boundary recommendations, not current M7C persisted facts:

- `risk_level`
- `decision`
- `input_hash`
- `output_hash`
- `artifact_id`
- `approval_id`
- `error_code`
- `reason`

## What Is Not Implemented In M7C

- persistent DB audit stream
- SIEM export
- audit dashboard
- audit retention policy automation

## Operator Responsibility

Operators should use:

- `request_id`
- `trace_id`
- current audit event rows
- runtime logs

to reconstruct incident timelines.

## Future DB Audit Stream Boundary

If a future phase implements DB audit streaming, it should extend rather than replace the current audit boundary.

M7C only documents the boundary and inventory.
