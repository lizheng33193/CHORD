# M7B Backup / Restore / Rollback Contract

## Scope

M7B adds minimum local backup, restore, and rollback readiness for CHORD.

It protects local runtime state that is required to recover a minimum commercial deployment after operator error, local state corruption, or a failed rollout.

## State Inventory

M7B treats the following local state as operator-relevant runtime assets:

- `outputs/memory/`
- `outputs/risk_knowledge/`
- `outputs/orchestrator_sessions/`
- `outputs/evals/`
- `storage/risk_knowledge/`

These paths cover the current minimum local state boundary:

- SQLite long-term memory and related WAL/SHM files
- risk knowledge FAISS artifacts and related local retrieval files
- orchestrator session snapshots
- evaluation outputs used for operational evidence
- uploaded risk knowledge source documents

## Backup Targets

The local backup script must use an explicit allowlist.

Default targets are:

- `outputs/memory/`
- `outputs/risk_knowledge/`
- `outputs/orchestrator_sessions/`
- `outputs/evals/`
- `storage/risk_knowledge/`

`data/` is excluded by default and may be included only via an explicit `--include-data` flag.

## Excluded Secrets

The local backup script must not place secrets or secret-like local credential files into ordinary backup archives.

Minimum exclusions:

- `.env`
- `.env.*`
- `key.json`
- `app/key.json`
- `*.pem`
- `*.key`
- `*.crt`
- `*.p12`
- `*.p8`

Secrets must be backed up through a secure secret manager or controlled vault outside M7B local state archives.

If `AUTH_ENABLED=1` or `AUTH_DATABASE_URL` points to an external DB, that external auth database is operator-owned and must be backed up outside M7B local state scripts.

## Symlink Policy

M7B uses a conservative symlink policy:

- backup does not follow symlinks
- backup skips symlink entries and records warnings
- restore skips symlink and hardlink entries by default and records warnings
- unsafe symlink targets, including absolute targets or targets containing `..`, must never be restored

## Restore Safety Contract

The restore script must:

- support `--dry-run`
- default to non-overwriting behavior
- require `--overwrite` for replacement of existing files
- reject archive entries that attempt path traversal
- reject archive entries that resolve outside the requested target root
- fail with non-zero exit if an unsafe archive entry is detected

## Rollback Contract

Rollback is a documented operator workflow, not an automated deployment platform.

The rollback runbook must distinguish:

- code rollback to a previous known-good commit or tag
- local state restore from a local backup archive
- operator-owned external systems, including external auth databases and secrets, that must be handled outside M7B scripts

## Validation Contract

M7B can be marked completed only if:

- backup archive generation succeeds
- manifest generation succeeds
- archive `sha256` generation succeeds
- restore dry-run succeeds
- restore into a temporary target succeeds
- restore non-overwrite behavior is proven
- restore `--overwrite` behavior is proven
- unsafe archive validation proves path traversal is blocked
- no runtime behavior changes are introduced

## Non-goals

M7B does not provide:

- cloud backup
- scheduled backup
- encrypted secret vault management
- Kubernetes rollback
- full disaster recovery
- multi-region recovery
- database migration or schema downgrade framework
- runtime behavior changes
