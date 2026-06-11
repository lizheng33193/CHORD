# App Profile Phase 1 Contract

This document locks the internal App page contracts used by the layered runtime pipeline.

## AppRunContext

| Field | Type | Required | Notes |
|---|---|---|---|
| `uid` | `str` | yes | Stable user id |
| `country_code` | `str` | yes | Current country pack code |
| `application_time` | `str` | yes | ISO datetime used for time decay |
| `trace_id` | `str` | yes | Empty string allowed |
| `source_preference` | `str` | yes | `local` / future warehouse source |
| `enable_llm_explanation` | `bool` | yes | Controls explainer skip logic |
| `language` | `str` | yes | Country default language or override |
| `channel` | `str` | yes | Defaults to `api` |

## AppRawData

Status enum: `ok | missing | invalid`

| Field | Type | Required | Layer | Countryized |
|---|---|---|---|---|
| `uid` | `str` | yes | Data Access | no |
| `country_code` | `str` | yes | Data Access | no |
| `source_meta.source_type` | `str` | yes | Data Access | indirect |
| `source_meta.origin_ref` | `str` | yes | Data Access | yes |
| `source_meta.fetched_at` | `str` | yes | Data Access | no |
| `source_meta.trace_id` | `str` | yes | Data Access | no |
| `records` | `list[dict]` | yes | Data Access | yes |
| `data_status` | `str` | yes | Data Access | no |
| `errors` | `list[str]` | yes | Data Access | no |

## AppFeatureBundle

Status enum: `ok | partial | failed`

| Field | Type | Required | Layer | Countryized |
|---|---|---|---|---|
| `uid` | `str` | yes | Feature Builder | no |
| `country_code` | `str` | yes | Feature Builder | no |
| `application_time` | `str` | yes | Feature Builder | no |
| `normalized_apps` | `list[dict]` | yes | Feature Builder | yes |
| `aggregate_features` | `dict` | yes | Feature Builder | indirect |
| `signal_features` | `dict` | yes | Feature Builder | yes |
| `evidence_features` | `dict` | yes | Feature Builder | indirect |
| `visual_features` | `dict` | yes | Feature Builder | indirect |
| `feature_status` | `str` | yes | Feature Builder | no |
| `errors` | `list[str]` | yes | Feature Builder | no |

Contract rule: `AppFeatureBundle` must not contain legacy bridge fields such as `_prompt_payload`.

## AppDecisionResult

Status enum: `ok | partial | failed`

| Field | Type | Required | Layer | Countryized |
|---|---|---|---|---|
| `uid` | `str` | yes | Decision Engine | no |
| `country_code` | `str` | yes | Decision Engine | no |
| `decision_status` | `str` | yes | Decision Engine | no |
| `summary_seed` | `str` | yes | Decision Engine | yes |
| `app_insight_seed` | `dict` | yes | Decision Engine | yes |
| `activity_level` | `str` | yes | Decision Engine | no |
| `risk_assessment` | `dict` | yes | Decision Engine | indirect |
| `financial_maturity` | `dict` | yes | Decision Engine | indirect |
| `consumption_profile` | `dict` | yes | Decision Engine | indirect |
| `metrics` | `dict` | yes | Decision Engine | no |
| `tags_rule` | `list[str]` | yes | Decision Engine | yes |
| `recommendation` | `dict` | yes | Decision Engine | yes |
| `visuals` | `dict` | yes | Decision Engine | indirect |
| `timeline` | `list[dict]` | yes | Decision Engine | yes |
| `errors` | `list[str]` | yes | Decision Engine | no |

## AppExplanationResult

Status enum: `ok | model_unavailable | partial | skipped`

| Field | Type | Required | Layer | Countryized |
|---|---|---|---|---|
| `uid` | `str` | yes | Explanation | no |
| `country_code` | `str` | yes | Explanation | no |
| `explanation_status` | `str` | yes | Explanation | no |
| `used_llm` | `bool` | yes | Explanation | no |
| `summary` | `str` | yes | Explanation | yes |
| `tags` | `list[str]` | yes | Explanation | yes |
| `app_insight` | `dict` | yes | Explanation | yes |
| `reasoning_texts` | `dict` | yes | Explanation | yes |
| `report_markdown` | `str` | yes | Explanation | yes |
| `model_trace` | `dict` | yes | Explanation | no |
| `errors` | `list[str]` | yes | Explanation | no |

## AppPageResult

| Field | Type | Required | Layer | Countryized |
|---|---|---|---|---|
| `summary` | `str` | yes | Final Assemble | indirect |
| `structured_result` | `dict` | yes | Final Assemble | no |
| `charts` | `list[dict]` | yes | Final Assemble | no |
| `report_markdown` | `str` | yes | Final Assemble | indirect |

## Status Mapping

- `data_status` only reflects repository access and raw-data validity.
- `feature_status` only reflects deterministic feature construction.
- `decision_status` only reflects deterministic rule output readiness.
- `explanation_status` only reflects LLM explanation capability.
- Final `structured_result.status` keeps the existing external page semantics:
  - `data_missing` when App data is unavailable
  - `model_unavailable` when rules exist but the explanation layer failed
  - `ok` otherwise

## Freeze Rules

- Rule outputs own `metrics`, `risk_assessment.level`, `financial_maturity.level`, `consumption_profile.level`, `visuals`, and `timeline`.
- Explanation outputs may only supplement `summary`, `tags`, `app_insight`, reasoning text, and `report_markdown`.
- `AppDataProvider(repository).fetch(uid, context)` is the stable internal data-access interface for future database rollout.
