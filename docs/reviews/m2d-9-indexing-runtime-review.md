# M2D-9 Indexing Runtime Review

## Summary

`M2D-9` landed a real indexing workflow runtime on top of M2D-7 materialization and M2D-8 persistence / embedding / FAISS foundations.

## Scope

This phase starts runtime orchestration only:

- durable indexing jobs
- document-version runtime transitions
- Redis runtime state / heartbeat / lock
- retry lineage
- rebuild flow
- active-manifest activation and supersede behavior

It does not start retrieval, rerank, `RiskKnowledgeService`, NL Chat, Profile Explanation, or API routes.

## Runtime Boundary

Added CHORD-owned runtime modules:

- `IndexingJobRunner`
- `IndexingOrchestrator`
- `RedisIndexingTaskStateStore`
- `RedisVersionLock`
- typed runtime errors and schemas

The runtime is in-process and uses explicit dependency injection. No Celery, RQ, or distributed worker queue was introduced.

## Durable Truth Split

`M2D-9` fixes durable/runtime state ownership:

- MySQL/SQLAlchemy durable state is the source of truth
- Redis is ephemeral runtime state only
- Redis lock is used only for concurrency control, not final ownership truth

## Runtime Flow

The landed chain is:

1. validate inputs and version state
2. create durable job with unique `idxjob_<uuid>` identity
3. acquire version-level Redis lock
4. materialize chunks or reuse persisted chunks
5. persist chunks
6. persist embeddings
7. build and save FAISS artifacts
8. persist manifest
9. activate the manifest in a short transaction
10. complete the durable job and Redis runtime state

## Safety Rules

The phase enforces:

- step-level transaction boundaries
- lock renew/release by owner token only
- lock-loss failure before manifest activation
- atomic FAISS artifact write via temp files plus checksum verification
- manifest supersede and activation in one short transaction

## Validation

Validated with:

- targeted SQLAlchemy repository tests
- Redis task-state and lock tests with `fakeredis`
- indexing runner/orchestrator runtime tests
- legacy `knowledge_base` and `risk_knowledge` contract suites
- default embedding tests remain offline and do not access external APIs
- real embedding smoke remains opt-in and requires local `DASHSCOPE_API_KEY` plus `CHORD_RUN_REAL_EMBEDDING_TESTS=1`
- `compileall`
- `git diff --check`
- coupling guard over new M2D-9 directories

## Acceptance Closure

`M2D-9` is accepted at stage level after targeted runtime validation; full repository regression, real embedding smoke, and real Redis smoke remain optional/pending validation items.

Workspace hygiene preserved:

- unrelated frontend edits remained untouched
- the unrelated untracked PDF remained untouched

## Status

Current `M2D` status:

> `M2D implementation in progress`

Current subphase reading:

> `M2D-9 indexing job runtime landed; no retrieval/rerank/RiskKnowledgeService/API runtime started`

## Next Step

`M2D-10` remains the retrieval foundation / hybrid retrieval stage, not a consumer-service integration phase.
