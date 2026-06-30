# M2D Risk Domain Knowledge RAG Contract

## Status

Current `M2D` status:

> `M2D implementation in progress`

Current subphase reading:

> `M2D-7 metadata and evidence builder landed; no embedding/retrieval/ES runtime started`

This document remains the long-term contract source. `M2D-7` only materializes draft chunk/evidence objects in memory and does not start retrieval runtime behavior.

## 1. Purpose

`M2D` introduces a dedicated risk-domain document knowledge layer for evidence-grounded natural conversation and profile explanation.

Its purpose is to provide stable retrieval, evidence selection, and refusal behavior over curated risk documents without reusing raw SQL-grounding logic from the Data Agent path.

## 2. Target Consumers

The target consumers are:

- `NL Chat Agent`
- `Profile Explanation Agent`
- `Orchestrator Router`

These consumers may use `M2D` through a single service boundary in the future, but they must not access retrieval infrastructure directly.

## 3. Goals

`M2D` goals are:

- risk-domain knowledge Q&A
- profile explanation evidence enhancement
- risk concept explanation
- policy and strategy wording explanation
- evidence-grounded answers based on managed documents

## 4. Non-Goals

`M2D` is not responsible for:

- SQL generation
- schema grounding
- SQL example retrieval
- SQL validator behavior
- Data Agent table selection
- runtime memory
- temporary session file Q&A

## 5. Knowledge Source Scope

In-scope knowledge sources include:

- `智能风控指南`
- 风控术语文档
- 信贷生命周期文档
- 逾期 / 催收 / 还款 / 授信 / 申请 / 放款文档
- 风险标签解释
- 策略分析说明
- 业务规则说明

## 6. Out-of-Scope Knowledge

The following are out of scope for `M2D` knowledge retrieval:

- 数据库 schema
- 字段字典
- SQL few-shot
- SQL 错误案例
- Data Agent grounding seed
- 用户记忆
- 临时上传文件

## 7. Document Metadata Schema

Each managed document must at minimum support the following metadata contract:

```json
{
  "kb_id": "risk_domain_knowledge",
  "doc_id": "risk_guide_v1",
  "doc_title": "智能风控指南",
  "doc_name": "智能风控指南.pdf",
  "source_type": "pdf",
  "source_uri": "knowledge/risk/智能风控指南.pdf",
  "current_version_id": "risk_guide_v1_202606",
  "status": "active",
  "permission_scope": "internal"
}
```

## 8. Chunk Metadata Schema

Each retrievable chunk must at minimum support the following metadata contract:

```json
{
  "chunk_id": "risk_guide_v1_202606_chunk_000123",
  "kb_id": "risk_domain_knowledge",
  "doc_id": "risk_guide_v1",
  "version_id": "risk_guide_v1_202606",
  "chunk_type": "paragraph",
  "chunk_order": 123,
  "section_title": "贷后风险识别",
  "section_path": ["智能风控指南", "贷后管理", "贷后风险识别"],
  "page_start": 12,
  "page_end": 13,
  "content": "...",
  "content_hash": "...",
  "embedding_model": "text-embedding-v3",
  "embedding_dim": 1024,
  "parser_version": "swxy_deepdoc_v1",
  "chunker_version": "m2d_chunker_v1"
}
```

## 9. Evidence Schema

Each consumer-facing evidence record must at minimum support the following contract:

```json
{
  "evidence_id": "ev_risk_guide_v1_202606_chunk_000123",
  "kb_id": "risk_domain_knowledge",
  "doc_id": "risk_guide_v1",
  "doc_title": "智能风控指南",
  "version_id": "risk_guide_v1_202606",
  "chunk_id": "risk_guide_v1_202606_chunk_000123",
  "section_title": "贷后风险识别",
  "page_start": 12,
  "page_end": 13,
  "score": null,
  "text": "...",
  "usage": "supporting_evidence"
}
```

In `M2D-7`, `RiskEvidence` is draft evidence only:

- `evidence_id = "ev_" + chunk_id`
- `score = None`
- retrieval-time `fulltext_score / vector_score / rerank_score / final_score` remain deferred to later retrieval phases

## 10. Retrieval Routing Contract

Routing into `M2D` must follow these rules:

- 风控概念解释 -> `M2D`
- 风控策略分析 -> `M2D`
- 画像解释增强 -> `Profile Result + M2D`
- SQL 查询 -> `Data Agent`
- 表字段解释 -> `Data Knowledge RAG`
- 闲聊 -> 普通 `NL Chat`

`M2D` must not be used as a generic fallback for every user request. It is a scoped risk-domain document knowledge route.

## 11. Refusal Policy

`M2D` must refuse or degrade under the following conditions:

- refuse when evidence `final_score` is below threshold
- refuse when valid evidence count is insufficient
- refuse or reroute when the request is outside risk-domain knowledge scope
- degrade when the user asks for a deterministic risk conclusion but profile data is missing
- surface conflict instead of certainty when retrieved evidence conflicts
- never present model priors or generic world knowledge as if they were knowledge-base evidence

## 12. Evaluation Contract

The `M2D` evaluation contract must include at least:

- `retrieval_hit@5`
- `evidence_precision`
- `citation_accuracy`
- `refusal_accuracy`
- `routing_accuracy`
- `answer_groundedness`

## 13. Trace Contract

The future trace contract must preserve this sequence:

`query -> route_decision -> retrieve -> rerank -> evidence_select -> refusal_check -> answer`

This trace contract is required to support explainability, debugging, and acceptance review.

## 14. Consumer Boundary

Future consumers must access risk-domain retrieval only through `RiskKnowledgeService`.

The following are forbidden consumer patterns:

- querying ES directly
- reading bare chunks directly
- bypassing routing and refusal checks
- constructing evidence payloads independently in consumer code

## 15. Acceptance Conditions

Future implementation acceptance must prove:

- routing sends only in-scope requests to `M2D`
- evidence payloads conform to the contract
- refusal behavior is explicit and testable
- profile explanation can consume evidence without direct ES access
- SQL / schema / field-grounding requests are kept out of the `M2D` path
- final answers remain evidence-grounded rather than model-invented
