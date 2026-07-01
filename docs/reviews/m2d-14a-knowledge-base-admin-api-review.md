# M2D-14A Knowledge Base Admin API Review

## Summary

`M2D-14A` landed on top of the accepted `M2D-13` baseline, not the stale local `M2D-10` checkout.

Delivered surfaces:

- durable knowledge-base CRUD
- document registration and local upload
- job-based index / rebuild / retry / status APIs
- manifest activation
- retrieval-only debug API

Not started in this phase:

- UI console
- worker queue / production hardening
- Data Agent RAG coupling
- evidence/answer debug endpoints

## Engineering Notes

- `KnowledgeBase` durable state was added to `app/knowledge_base` because honest admin CRUD required persistent KB records.
- upload writes are streamed, hashed during write, and atomically renamed under a configured upload root.
- admin indexing reuses the current in-process runtime and adds a pre-created `job_id` seam so APIs can return immediate job metadata.
- runtime status reads tolerate missing Redis state and fall back to durable job data.
- `debug/retrieve` is a deliberate retrieval-only v1 contract and does not call `RiskKnowledgeService`.

## Validation

- `pytest -q tests/risk_knowledge/admin tests/risk_knowledge/service tests/risk_knowledge/evaluation tests/risk_knowledge/evidence tests/risk_knowledge/reranking tests/risk_knowledge/retrieval tests/risk_knowledge/runtime tests/knowledge_base`
- `python -m compileall -q app/risk_knowledge app/knowledge_base tests/risk_knowledge tests/knowledge_base`
- `git diff --check`

## Result

Status wording can now move from:

> `M2D-13 golden-set evaluation landed; no admin API/UI/production-hardening runtime started`

to:

> `M2D-14A Knowledge Base Admin API landed; no UI/production-hardening runtime started`
