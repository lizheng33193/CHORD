# M2D-13 Golden Set Evaluation Spec

## Status

Current `M2D` status:

> `M2D implementation in progress`

Current subphase reading:

> `M2D-13 golden-set evaluation landed; no admin API/UI/production-hardening runtime started`

## 1. Goal

`M2D-13` adds a CHORD-owned golden-set evaluation framework for the existing M2D runtime chain:

- retrieval
- rerank
- evidence selection and gate
- citation rendering
- `RiskKnowledgeService` answer / refusal

This phase does not add admin API/UI, upload / reindex / status runtime, frontend work, ES / SWXY runtime coupling, Data Agent RAG mixing, or production hardening.

## 2. Evaluation Boundary

The canonical M2D evaluation logic lives under:

- `app/risk_knowledge/evaluation`

This package owns:

- case schema
- JSONL loader
- evidence / citation matchers
- retrieval / rerank / evidence / gate / citation / answer metrics
- evaluator
- advisory regression decision
- JSON / Markdown report builder
- CLI entrypoint

`app/risk_knowledge/evaluation` must not import `tests.golden`.

## 3. Trace Seam Boundary

Evaluation uses read-only trace seams to observe the existing runtime pipeline:

- `RiskEvidenceBundleBuilder.build_with_trace(...)`
- `RiskEvidencePipeline.build_trace(...)`
- `RiskKnowledgeService.answer_with_trace(...)`

These seams only add observability.

They must not:

- change `build_bundle()` behavior
- change `answer()` behavior
- fork a parallel retrieval / rerank / answer implementation

## 4. Dataset And Report Contract

The canonical sample dataset lives at:

- `tests/fixtures/golden/risk_knowledge/eval_set.sample.jsonl`

Manual report output lives under:

- `outputs/evals/m2d/`

Default tests must use temporary directories and must not write real runtime reports.

## 5. Fixture And Runtime Modes

`M2D-13` supports two modes:

- `fixture`
- `runtime`

`fixture` mode is the default validation path and must remain offline-safe.

It must not require:

- MySQL
- Redis
- DashScope
- real LLMs

`runtime` mode is opt-in only and requires:

- `CHORD_RUN_M2D_RUNTIME_EVAL=1`

If runtime mode is requested without that environment variable, the CLI must emit a skipped report with exit code `0`.

## 6. Scoring Rules

Expected evidence matching priority is fixed to:

- `chunk_id`
- `content_hash`
- `section_path_contains`
- `text_contains`

Expected citation matching priority is fixed to:

- `chunk_id`
- `version_id`
- `document_id`
- `section_path_contains`

Refusal cases do not require retrieval or rerank hits.

They are primarily scored on:

- `actual_should_answer == false`
- refusal reason match when specified
- no unsupported answer
- valid citation contract

Answer-point scoring in v1 is deterministic lexical matching only.

It is not a semantic groundedness judge and does not introduce LLM-as-judge.

## 7. Ambiguous Cases

`expected_behavior="ambiguous"` cases:

- appear in the report
- preserve diagnostics and calculable metrics
- do not participate in advisory regression thresholds
- do not enter the default denominator for `gate_accuracy`, `false_answer_rate`, or `false_refusal_rate`

## 8. Regression Contract

`RegressionThresholds` and `RegressionDecision` are implemented in v1, but the phase remains report-only:

- no committed runtime baseline
- no threshold-based default acceptance blocker
- no required branch-vs-baseline comparison

## 9. Renumbering

The previous `M2D-13 Upload/Reindex/Status API` milestone is renumbered to:

- `M2D-14A Knowledge Base Admin API`

This change prioritizes evaluation before admin runtime expansion.
