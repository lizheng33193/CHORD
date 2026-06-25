# M2B Retrieval Golden Set

## Purpose

This document defines the first retrieval evaluation set for `M2B`.

The golden set measures whether future retrieval layers can surface the right tables, fields, glossary terms, and safe SQL patterns before SQL generation. It is the reference set for later deterministic and hybrid retrieval comparison.

## Case Schema

Each case includes:

- `case_id`
- `country`
- `domain`
- `run_type`
- `output_bucket`
- `request`
- `expected_tables`
- `expected_fields`
- `expected_glossary_terms`
- `expected_sql_examples`
- `forbidden_examples`
- `notes`

## Initial Case Groups

### Mexico

- `mx-high-risk-cohort`
- `mx-recent-7d-risk-users`
- `mx-first-loan-never-overdue`
- `mx-mob1-settled-7d-churn`
- `mx-behavior-writeback`
- `mx-glossary-combo-writeback`
- `mx-no-apply-cohort`
- `mx-no-withdraw-cohort`
- `mx-withdraw-cohort`
- `mx-app-profile-query`
- `mx-credit-profile-query`

### Philippines

- `ph-first-loan-never-overdue`
- `ph-withdraw-uuid-negative`

### Thailand

- `th-asset-snapshot-query`
- `th-risk-apply-query`
- `th-ask-loan-risk-query`
- `th-third-party-risk-query`

### Cross-Table / DWS

- `dws-renewal-loan-segment-query`
- `dws-fox-boc-behavior-query`

## Interpretation

- `expected_tables` and `expected_fields` capture grounding targets, not final SQL guarantees.
- `forbidden_examples` capture anti-patterns that retrieval should not reinforce.
- Notes may encode business semantics such as observation windows, anti-joins, or partition-vs-business-time guidance.
