# M7C Operator Checklist Runbook

## Daily Startup Check

- `docker compose ps`
- `curl http://127.0.0.1:8000/health`
- `python scripts/collect_runtime_status.py --base-url http://127.0.0.1:8000 --output-dir /tmp/chord-m7c-monitoring`

## Before Deployment

- verify current backup exists
- verify backup manifest has `archive_sha256`
- confirm conservative defaults remain unchanged
- run startup smoke

## After Deployment

- run startup smoke
- collect runtime status snapshot
- inspect advisory warnings
- record request IDs for any user-visible error

## Before Rollback

- create a fresh backup
- record current commit
- confirm why rollback is required
- follow rollback runbook

## After Restore

- bootstrap runtime directories
- re-run startup smoke
- collect runtime status snapshot
- inspect latest warnings and required failures

## Escalation

- `P0`: stop rollout or operator action immediately
- `P1`: investigate the same day and record mitigation
- `P2`: record and schedule follow-up
