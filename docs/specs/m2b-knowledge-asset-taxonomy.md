# M2B Knowledge Asset Taxonomy

## Purpose

This document defines the knowledge asset types that may be extracted from legacy raw documents and explains whether each asset is allowed in runtime retrieval.

The raw documents themselves are never runtime assets.

## Runtime Allowed Enum

Only these values are allowed for `runtime_allowed`:

- `no_raw_runtime`
- `sanitized_only`
- `eval_only`
- `future_profile_skill_only`

Definitions:

- `no_raw_runtime`: the raw source must never enter runtime retrieval or prompt assembly directly.
- `sanitized_only`: sanitized structured derivatives may enter runtime retrieval later, but the raw source must not.
- `eval_only`: use only for tests, baseline comparison, anti-pattern review, or retrieval evaluation.
- `future_profile_skill_only`: not part of current Data Agent retrieval; may be useful later for profile-skill DAG work.

## Asset Types

### `catalog_table`

- Source: schema docs, table dictionaries, DWD/DWB/DWS/DWT table descriptions
- Purpose: help choose the correct table for a request
- Runtime allowed: `sanitized_only`
- Notes: must be normalized into structured fields such as table name, grain, time field, and join hints

### `catalog_field`

- Source: schema docs, field dictionaries, DESC snapshots, CSV field exports
- Purpose: field grounding and canonical field selection
- Runtime allowed: `sanitized_only`
- Notes: must remove copied SQL and keep only safe structured metadata

### `glossary_term`

- Source: business logic docs, domain definitions, lifecycle shorthand
- Purpose: map user language to business meaning, tables, and fields
- Runtime allowed: `sanitized_only`
- Notes: terms such as `mob1`, `first_loan`, `never_overdue`, and `high_risk` belong here after extraction

### `business_rule`

- Source: business logic docs and domain definitions
- Purpose: capture hidden business constraints and cohort logic
- Runtime allowed: `sanitized_only`
- Notes: must be rewritten into explicit structured rules instead of raw prose

### `cohort_definition`

- Source: business logic docs, historical cohort explanations, lifecycle documents
- Purpose: define reusable cohort semantics for retrieval and later planning
- Runtime allowed: `sanitized_only`
- Notes: examples include settlement windows, reborrow exclusions, and observation-period requirements

### `sql_example_pattern`

- Source: `few.md`, `all_examples .md`, historical safe SQL references
- Purpose: provide safe structural guidance without literal copying
- Runtime allowed: `sanitized_only`
- Notes: only sanitized pattern summaries are eligible; raw SQL text with secrets or historical literals is not

### `sql_error_case`

- Source: `few.md`, `all_examples .md`, historical failure notes, review artifacts
- Purpose: teach anti-patterns and known bad query shapes
- Runtime allowed: `eval_only` during `M2B-0`, potentially `sanitized_only` later if formalized
- Notes: fixed dates, source-filter inheritance, placeholder UID use, and broad scans belong here as structured error cases

### `canonical_field_policy`

- Source: legacy prompt guidance, schema normalization rules, field-family drift findings
- Purpose: steer canonical field selection and reviewer warnings
- Runtime allowed: `sanitized_only`
- Notes: raw prompt files are `no_raw_runtime`; only extracted policy statements are candidates for runtime use

### `feature_definition`

- Source: feature logic code blocks and fraud-analysis snippets in legacy docs
- Purpose: preserve potentially reusable feature engineering logic
- Runtime allowed: `future_profile_skill_only`
- Notes: not part of current Data Agent M2B runtime scope

### `domain_definition`

- Source: asset/risk/user/third-party domain overview docs
- Purpose: explain business domain boundaries and semantic table selection
- Runtime allowed: `sanitized_only`
- Notes: useful for retrieval grounding and later review prompts

### `table_lineage_hint`

- Source: schema docs, data dictionary lineage columns, domain flow descriptions
- Purpose: help understand upstream/downstream dependencies and likely join paths
- Runtime allowed: `sanitized_only`
- Notes: lineage hints must be concise and structured

### `retrieval_eval_case`

- Source: prompt docs, error cases, runtime-quality findings, legacy examples
- Purpose: seed or explain retrieval golden cases and anti-pattern coverage
- Runtime allowed: `eval_only`
- Notes: these support measurement, not runtime prompt assembly

## Source-Class Guidance

- `business_logic` raw docs are `no_raw_runtime`, but they are high-value sources for glossary, business rules, and cohort definitions.
- `schema_doc`, `table_dictionary`, and `domain_definition` raw docs are inventory sources whose sanitized structured derivatives are later `sanitized_only`.
- `old_prompt` raw docs are `no_raw_runtime`; only extracted policy statements may become structured assets later.
- `mixed_legacy_doc` raw docs such as `few.md` and `all_examples .md` are high-risk and must be split into sanitized patterns and eval-only error cases before any later use.
