# M7 Minimum Commercial Production Readiness Plan

## Current State

- `M6 completed`
- `M7 not started` before this scope lock
- `M6A completed`
- `M6B completed / merged`
- `M6C completed / merged`
- `MEMORY_VECTOR_CONTEXT_INJECTION_ENABLED` remains default-off
- SQL/Data Agent semantic supplement remains disabled
- full semantic-memory trace remains metadata-only
- no dashboard / CI integration / online monitoring / release automation was added in M6

## M7 Goal

M7 targets minimum commercial production readiness.

It does not target full enterprise production infrastructure.

M7 should make CHORD deployable, verifiable, recoverable, observable, auditable, and commercially handoff-ready under explicit limitations.

The goal is to close the minimum commercial delivery boundary around deployment, startup, backup and restore, rollback, monitoring and alerting boundaries, audit boundaries, SLO and release gates, load smoke, and final acceptance without expanding back into runtime feature work.

## M7 In Scope

1. Deployment runbook
2. Runtime bootstrap / startup smoke
3. Environment configuration readiness
4. Backup / restore runbook
5. Rollback runbook
6. Monitoring / alerting boundary
7. Audit boundary
8. SLO / SLA boundary
9. CI / release gate runbook
10. Load smoke
11. Final commercial delivery checklist
12. M7 final acceptance review

## M7 Out of Scope

1. Kubernetes / Helm
2. Full automatic CD
3. Full Grafana / Prometheus deployment
4. Distributed multi-node HA
5. Distributed session coordination
6. DB audit stream implementation
7. SIEM integration
8. Full security compliance program
9. Full capacity planning report
10. LangGraph migration
11. General multi-agent runtime
12. Semantic memory default-on rollout
13. SQL/Data Agent semantic memory supplement
14. Large UI redesign
15. Full enterprise tenant isolation rewrite

## Task Packages

### M7A Deployment & Runtime Readiness

**Goal**

Lock the minimum deployment and startup path so the current system can be brought up reproducibly under documented runtime assumptions.

**Deliverables**

- `.env.example` readiness review
- `deployment-runbook.md`
- runtime directory bootstrap plan
- startup smoke path and command inventory
- explicit decision on whether Docker / compose is part of minimum M7 scope

**Non-goals**

- no Kubernetes / Helm rollout
- no deployment automation platform
- no runtime behavior refactor
- no new API / worker / dashboard work

**Validation**

- deployment commands and prerequisites match the current repo
- startup smoke steps are deterministic and human-runnable
- environment variables and required directories are explicitly documented

**Acceptance Criteria**

- a deployment operator can identify prerequisites, startup order, and minimum bring-up checks from the runbook alone
- the runtime bootstrap path is no longer ambiguous
- M6 conservative defaults remain unchanged

### M7B Backup / Restore / Rollback

**Goal**

Define what must be backed up, how it is restored, and how the system is rolled back without guessing about state ownership.

**Deliverables**

- `backup-restore-runbook.md`
- `rollback-runbook.md`
- state inventory across runtime data, memory DB, and knowledge artifacts
- backup boundary for memory DB, risk knowledge uploads / manifests / FAISS artifacts
- restore verification checklist

**Non-goals**

- no backup scheduler implementation
- no restore automation
- no database migration rewrite
- no persistent audit stream

**Validation**

- all critical stateful assets have an owner and backup boundary
- restore verification steps exist for each protected state class
- rollback path distinguishes code rollback from state rollback

**Acceptance Criteria**

- backup targets are explicit
- restore steps are documented and checkable
- rollback steps exist for minimum commercial support expectations

### M7C Monitoring / Alerting / Audit Boundary

**Goal**

Define what operational signals must exist for minimum commercial readiness without expanding into a full observability platform.

**Deliverables**

- `monitoring-alerting-runbook.md`
- readiness / health boundary
- worker health boundary
- memory vector status boundary
- risk knowledge indexing job status boundary
- `audit-boundary-runbook.md`
- high-risk action audit inventory

**Non-goals**

- no full Grafana / Prometheus deployment
- no Alertmanager rollout
- no SIEM integration
- no DB audit stream implementation

**Validation**

- each high-risk action has an audit expectation
- each critical runtime slice has a minimum health / alerting boundary
- known blind spots are explicitly documented

**Acceptance Criteria**

- operators can identify what must be observed before commercial handoff
- missing observability platform work is documented as a limitation, not hidden
- audit expectations are clear for high-risk actions

### M7D CI / Release Gate / Load Smoke

**Goal**

Define the minimum release gate and post-deploy confidence path needed to ship commercially without pretending a full CI/CD platform already exists.

**Deliverables**

- `final-release-gate-runbook.md`
- GitHub Actions decision for minimum scope
- documented `pr_acceptance` and `production_release --strict` expectations
- `load-smoke-runbook.md`
- explicit decision on whether a script is needed or documentation is sufficient

**Non-goals**

- no full automatic CD
- no large workflow matrix expansion
- no performance platform buildout
- no new runtime feature implementation

**Validation**

- release gate commands are explicit and repo-accurate
- load smoke scope is bounded to minimum commercial verification
- CI expectations are separated from future platform ambitions

**Acceptance Criteria**

- commercial release decision inputs are documented
- strict release gate usage is unambiguous
- load smoke has a minimum executable plan or script requirement

### M7E Final Acceptance & Commercial Delivery Docs

**Goal**

Close M7 with clear delivery evidence, known limitations, and a final Go / No-Go decision package.

**Deliverables**

- `final-commercial-delivery-checklist.md`
- `m7-minimum-commercial-production-readiness-review.md`
- `final-system-architecture.md`
- `final-runtime-flow.md`
- known limitations summary
- final Go / No-Go decision record

**Non-goals**

- no new runtime capability
- no product scope expansion
- no large README rewrite
- no enterprise operations platform commitments beyond minimum scope

**Validation**

- final checklist covers all M7 scope commitments
- final review references actual runbooks and release gate evidence
- limitations and deferrals remain explicit

**Acceptance Criteria**

- a commercial handoff package exists
- Go / No-Go can be decided from documented evidence
- minimum-scope limitations are preserved and visible

## Go Criteria

M7 can be considered minimum-commercial-ready only when:

1. Deployment runbook exists and matches current repo commands.
2. Runtime bootstrap / startup smoke path exists.
3. Backup / restore boundaries are documented.
4. Rollback process is documented.
5. Monitoring / alerting boundaries are documented.
6. High-risk audit boundary is documented.
7. SLO / SLA boundary is documented.
8. Release gate runbook exists.
9. `pr_acceptance` and `production_release --strict` commands are documented.
10. Load smoke plan or script exists.
11. Final commercial delivery checklist exists.
12. M7 final acceptance review exists.
13. No M6 conservative defaults were weakened.
14. `MEMORY_VECTOR_CONTEXT_INJECTION_ENABLED` remains default-off.
15. SQL/Data Agent semantic supplement remains disabled.

## No-Go Criteria

M7 cannot be considered ready if:

1. `README.md`, `PLANNING.md`, and `TASK.md` disagree on the M6/M7 state.
2. Startup path is unclear.
3. Backup targets are unclear.
4. Restore or rollback process is missing.
5. `production_release --strict` is missing or unclear.
6. The semantic memory default-off boundary is weakened.
7. SQL/Data Agent semantic supplement is enabled accidentally.
8. Monitoring / alerting boundaries are not defined.
9. High-risk audit boundary is missing.
10. Known limitations are not documented.

## Known Limitations

1. Minimum commercial readiness is not full enterprise production.
2. No Kubernetes / Helm in M7 minimum scope.
3. No distributed HA in M7 minimum scope.
4. No full monitoring dashboard in M7 minimum scope.
5. No automatic CD in M7 minimum scope.
6. No DB audit stream in M7 minimum scope.
7. Semantic memory context injection remains controlled and default-off.
8. SQL/Data Agent semantic supplement remains disabled.

## Recommended Next PR

`M7A Deployment & Runtime Readiness`
