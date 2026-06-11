# Agent User Profile — Full Codebase Learning Summary

> Project: agent-user-profile
> Date: 2026-04-28
> Coverage: All ~112 Python source files, 193 total project files (excl. .git/__pycache__)
> Purpose: Reference blueprint for upcoming code improvements — covers data flows, module boundaries, LLM integration, and extensibility analysis

---

## Table of Contents

- [1. Architecture Overview](#1-architecture-overview)
  - [1.1 Full Architecture Diagram](#11-full-architecture-diagram)
  - [1.2 Architecture in One Paragraph](#12-architecture-in-one-paragraph)
  - [1.3 Five-Layer Runtime Architecture](#13-five-layer-runtime-architecture)
  - [1.4 Why This System Exists](#14-why-this-system-exists)
  - [1.5 Usage Flow and Core Capabilities](#15-usage-flow-and-core-capabilities)
  - [1.6 Four Profile Modules — Relationships](#16-four-profile-modules--relationships)
- [2. Technology Stack](#2-technology-stack)
- [3. Core Design Patterns](#3-core-design-patterns)
- [4. Module Dependency Graph](#4-module-dependency-graph)
- [5. Data Flow Panorama](#5-data-flow-panorama)
  - [5.1 Full Request Path](#51-full-request-path)
  - [5.2 App Profile Data Flow](#52-app-profile-data-flow)
  - [5.3 Behavior Profile Data Flow](#53-behavior-profile-data-flow)
  - [5.4 Credit Profile Data Flow](#54-credit-profile-data-flow)
  - [5.5 Comprehensive Profile Data Flow](#55-comprehensive-profile-data-flow)
  - [5.6 LLM Interaction Pipeline](#56-llm-interaction-pipeline)
  - [5.7 Offline Data Preprocessing Pipeline](#57-offline-data-preprocessing-pipeline)
- [6. Key Business Flows and Design Decisions](#6-key-business-flows-and-design-decisions)
  - [6.1 End-to-End Single User Analysis](#61-end-to-end-single-user-analysis)
  - [6.2 Rule Engine Decision Logic](#62-rule-engine-decision-logic)
  - [6.3 LLM Prompt Template Design](#63-llm-prompt-template-design)
  - [6.4 Fallback and Degradation Strategy](#64-fallback-and-degradation-strategy)
  - [6.5 Core Design Decisions](#65-core-design-decisions)
- [7. File Inventory and Quick Reference](#7-file-inventory-and-quick-reference)
- [8. Current Architecture — Problem Diagnosis](#8-current-architecture--problem-diagnosis)
- [9. Extensibility Analysis and Improvement Roadmap](#9-extensibility-analysis-and-improvement-roadmap)
- [10. Appendix](#10-appendix)

---

## 1. Architecture Overview

### 1.1 Full Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                  Browser / API Client                           │
│  Embedded React dashboard (live_frontend.py, 2000+ lines)       │
│  or curl / Postman calling REST API directly                    │
└────────────────────────┬────────────────────────────────────────┘
                         │ POST /api/analyze  or  /api/analyze-file
┌────────────────────────▼────────────────────────────────────────┐
│              FastAPI Backend (Python 3.x)                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ API Layer (app/api/analyze.py, 2 endpoints)              │   │
│  └──────────────────────┬───────────────────────────────────┘   │
│  ┌──────────────────────▼───────────────────────────────────┐   │
│  │ Orchestration Layer (app/services/)                       │   │
│  │ ├── BatchAnalysisService (batch wrapper)                  │   │
│  │ ├── AnalysisOrchestrator (4-skill scheduler,              │   │
│  │ │   ThreadPoolExecutor)                                   │   │
│  │ └── ReportRenderer (Markdown rendering)                   │   │
│  └──────────────────────┬───────────────────────────────────┘   │
│  ┌──────────────────────▼───────────────────────────────────┐   │
│  │ Skill Execution Layer (app/runtime_skills/)               │   │
│  │ ├── AppProfileSkill → 6-step pipeline                    │   │
│  │ ├── BehaviorProfileSkill → 6-step pipeline (dual LLM)    │   │
│  │ ├── CreditProfileSkill → 6-step pipeline                 │   │
│  │ └── ComprehensiveProfileSkill → fusion (single file)     │   │
│  └──────────────────────┬───────────────────────────────────┘   │
│  ┌──────────────────────▼───────────────────────────────────┐   │
│  │ Data Access Layer (app/repositories/)                     │   │
│  │ ├── BaseUserRepository (abstract, 3 methods)             │   │
│  │ ├── LocalUserRepository (file-based, 600+ lines)         │   │
│  │ └── WarehouseUserRepository (stub)                       │   │
│  └──────────────────────┬───────────────────────────────────┘   │
│  ┌──────────────────────▼───────────────────────────────────┐   │
│  │ External Services                                         │   │
│  │ ├── Google Gemini API (API key mode)                     │   │
│  │ ├── Google Vertex AI (GCP service account)               │   │
│  │ └── Local filesystem (CSV / JSON / Prepared JSON)        │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Architecture in One Paragraph

Agent User Profile is a **five-layer Python backend** that profiles users for Mexico-market fintech lending. The API layer (FastAPI, 2 POST endpoints) receives UID requests → the Orchestration layer dispatches App / Behavior / Credit skills in parallel via `ThreadPoolExecutor(3)`, then runs the Comprehensive skill sequentially after all three complete → each Skill internally follows a standardized **six-step pipeline** (Context → DataAccess → FeatureBuild → Decision → Explain → Assemble), where Decision is a deterministic rule engine and Explain calls an LLM for natural-language enhancement → the Data Access layer abstracts data sources behind a Repository interface (currently only local files with multi-format fallback) → the External Services layer provides LLM access (Google Gemini / Vertex AI) and local file I/O. The system takes a UID as input, ingests multi-source data (app install lists, behavior event streams, credit bureau reports), and outputs four-dimensional user profiles as a JSON API response containing structured results, natural-language summaries, chart configurations, and Chinese-language Markdown reports.

### 1.3 Five-Layer Runtime Architecture

**Layer 1 — API**: [app/main.py](app/main.py) (50 lines) creates the FastAPI instance; [app/api/analyze.py](app/api/analyze.py) (37 lines) defines `POST /api/analyze` (JSON body with uid/uids) and `POST /api/analyze-file` (file upload). Request validation enforces 18-digit numeric UIDs.

**Layer 2 — Orchestration**: [app/services/orchestrator.py](app/services/orchestrator.py) (109 lines) is the core scheduler. Per UID, it submits App/Behavior/Credit skills to a thread pool (max 3 workers), waits for all three, then calls Comprehensive. Timing is logged for each skill.

**Layer 3 — Skill Execution**: Each of the three primary skills (App, Behavior, Credit) follows the **six-step pipeline**:

| Step | Responsibility | Input → Output |
|------|---------------|----------------|
| 1. Context | Build run context | UID + config → `*RunContext` TypedDict |
| 2. DataAccess | Fetch & validate raw data | Repository → `*RawData` TypedDict |
| 3. FeatureBuild | Extract features & derive signals | RawData → `*FeatureBundle` TypedDict |
| 4. Decision | Deterministic rule engine | FeatureBundle → `*DecisionResult` TypedDict |
| 5. Explain | LLM natural-language enhancement | DecisionResult + prompt → `*ExplanationResult` |
| 6. Assemble | Merge rule + LLM results | → `AgentOutput` (summary + structured_result + charts + report_markdown) |

The Comprehensive module is a **single 398-line file** that fuses the three upstream outputs — it does not follow the six-step pattern.

**Layer 4 — Data Access**: [app/repositories/local_repository.py](app/repositories/local_repository.py) (600+ lines) implements **multi-path fallback** for each data type (Prepared JSON → Raw CSV → Legacy JSON → Legacy sample). All methods are fail-open — errors return empty dicts, never throw.

**Layer 5 — External Services**: [app/core/model_client.py](app/core/model_client.py) (475 lines) abstracts LLM calls across three modes: `mock` (return fallback immediately), `gemini` (Google GenAI API key), `vertex` (GCP service account). Includes retry logic, JSON repair, error classification, and graceful degradation.

### 1.4 Why This System Exists

Mexico's cash-lending market requires multi-dimensional user assessment: app installs reveal multi-loan risk and financial maturity; behavior events reveal engagement and repayment willingness; credit bureau reports reveal debt pressure and credit stability. Before this system, these data sources were scattered across different systems, analyzed manually by risk and operations teams. Agent User Profile automates the entire pipeline — from data ingestion through feature extraction, rule-based decision, LLM-enhanced explanation, to report generation — so that submitting a single UID produces a complete four-dimensional profile ready for product and operations teams to act on.

### 1.5 Usage Flow and Core Capabilities

A user (risk analyst / operations staff) opens the embedded Dashboard or calls the API, submitting one or more 18-digit UIDs. The system runs three profile skills in parallel: **App Skill** analyzes installed apps for multi-loan risk (high/medium/low), financial maturity (banked/semi-banked/non-banked), and consumption capacity; **Behavior Skill** processes event streams to assess engagement, repayment willingness, product sensitivity, churn risk, and optimal contact channel; **Credit Skill** parses Buró de Crédito reports for financial maturity, debt pressure, credit stability, and borrowing urgency. After all three complete, the **Comprehensive Skill** fuses the results into S1-S6 segment classification, cross-signal conflict detection, and value signal derivation. The final JSON response contains four `AgentOutput` objects (one per module), each with a summary, structured result, chart configs, and a Chinese Markdown report.

### 1.6 Four Profile Modules — Relationships

```
                    ┌─────────────────────────────────┐
                    │        UID Input                 │
                    └──────────┬──────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │ (parallel)     │                │
       ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
       │  App Profile │ │  Behavior   │ │  Credit     │
       │             │ │  Profile    │ │  Profile    │
       │ In: app     │ │ In: event   │ │ In: Buró    │
       │   installs  │ │   stream    │ │   report    │
       │             │ │             │ │             │
       │ Out:        │ │ Out:        │ │ Out:        │
       │ multi-loan  │ │ engagement  │ │ maturity    │
       │ maturity    │ │ repayment   │ │ debt press. │
       │ consumption │ │ churn risk  │ │ stability   │
       │ risk advice │ │ contact rec │ │ urgency     │
       └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
              │                │                │
              └────────────────┼────────────────┘
                               │ (sequential, waits for all 3)
                    ┌──────────▼──────────────────────┐
                    │    Comprehensive Profile        │
                    │    (Fusion Layer)               │
                    │                                 │
                    │ Out: S1-S6 segment, persona,    │
                    │ conflict explanations,          │
                    │ overall risk + value assessment  │
                    └─────────────────────────────────┘
```

App / Behavior / Credit are **fully independent** — any module's data missing or LLM failure does not affect the others. Comprehensive **depends on all three** and only accesses their `AgentOutput`, never raw data sources.

---

## 2. Technology Stack

| Technology | Version | Usage in This Project |
|-----------|---------|----------------------|
| **Python** | 3.x | Runtime language |
| **FastAPI** | latest (no version pin) | Web framework, 2 POST endpoints + health check |
| **Uvicorn** | standard extras | ASGI server |
| **Pydantic** | v2 (compat layer for v1) | Request validation, response schemas, Settings config |
| **Pandas** | latest | CSV reading, grouping, aggregation in data prep |
| **google-genai** | latest | Unified SDK for Google Gemini API + Vertex AI |
| **Jinja2** | latest | Prompt template variable substitution |
| **python-multipart** | latest | File upload parsing for /api/analyze-file |
| **python-dotenv** | latest | .env file loading |

**Notable gap**: `requirements.txt` has **no version pinning** and no lock file — a deployment stability risk.

---

## 3. Core Design Patterns

| Pattern | Where | Problem Solved |
|---------|-------|---------------|
| **Six-step pipeline** | `runtime_skills/*/` | Standardize each profile module's processing flow with clear separation of concerns |
| **Rule + LLM dual-track** | DecisionEngine + Explainer | Decision engine guarantees deterministic reproducible results; Explainer adds LLM natural-language polish — LLM failure still yields complete structured output |
| **Country Pack** | `country_packs/mx/` | Isolate country-specific config (stage keywords, score thresholds, label maps) into frozen dataclasses for multi-market extension |
| **Repository abstraction** | `repositories/base.py` | Decouple data source from business logic — swap Local → Warehouse by changing one injected implementation |
| **Mock/Real switch** | `model_client.py` | `MODEL_MODE=mock` returns fallback instantly; `gemini`/`vertex` calls real API — zero business code changes |
| **Multi-path fallback** | `local_repository.py` | Tolerate inconsistent data quality: Prepared JSON → Raw CSV → Legacy JSON → Legacy sample |
| **TypedDict contracts** | `*/contracts.py` | Type hints without Pydantic runtime validation overhead for pipeline-internal data passing |
| **Unified AgentOutput** | `schemas/final_response.py` | All four modules produce identical output shape: summary + structured_result + charts + report_markdown |

---

## 4. Module Dependency Graph

```
app/api/analyze.py
    └── app/services/batch_service.py
        └── app/services/orchestrator.py
            ├── runtime_skills/app_profile_agent.py
            │   ├── app_profile/contracts.py
            │   ├── app_profile/data_access.py → repositories/*
            │   ├── app_profile/feature_builder.py → scripts/app_profile_payload_builder.py (1300+ lines)
            │   ├── app_profile/decision_engine.py → scripts/app_profile_payload_builder.py
            │   ├── app_profile/explainer.py → core/model_client.py + prompts/app_profile_prompt.md
            │   └── app_profile/assembler.py → schemas/app_profile.py
            │
            ├── runtime_skills/behavior_profile_agent.py
            │   └── behavior_profile/{contracts,data_access,feature_builder,decision_engine,explainer,assembler}.py
            │       └── explainer uses TWO prompts: behavior_profile_prompt.md + behavior_timeline_prompt.md
            │
            ├── runtime_skills/credit_profile_agent.py
            │   └── credit_profile/{contracts,data_access,feature_builder,decision_engine,explainer,assembler}.py
            │
            └── runtime_skills/comprehensive_agent.py (single 398-line file, no sub-pipeline)

Shared dependencies:
    core/config.py → all modules
    core/model_client.py → all Explainers
    country_packs/ → all modules (country-specific config)
    scripts/chart_builder.py → all modules (chart construction)
```

---

## 5. Data Flow Panorama

### 5.1 Full Request Path

```
Client POST /api/analyze {"uid": "123456789012345678"}
    │
    ▼
API Layer → validate UID (18-digit) → extract uid_list + application_time
    │
    ▼
BatchService → per uid → orchestrator.analyze()
    │
    ▼
Orchestrator:
    ┌─── ThreadPoolExecutor(3) ────────────────────┐
    │  App Skill         Behavior Skill    Credit   │
    │  .analyze()        .analyze()        .analyze()│
    └───────────────────────┬──────────────────────┘
                            │ wait all
                            ▼
    Comprehensive Skill.analyze(app_result, behavior_result, credit_result)
    │
    ▼
UserAnalysisResult {
  uid, app_profile: AgentOutput, behavior_profile: AgentOutput,
  credit_profile: AgentOutput, comprehensive_profile: AgentOutput
}
    │
    ▼
JSON response → client
```

### 5.2 App Profile Data Flow

```
Repository.get_app_data(uid) → CSV with {app_name, app_package, first_install_time,
                                          last_update_time, gp_category, ai_category}
    │
    ▼ AppDataProvider.fetch() → validate fields, check non-empty
AppRawData {data_status: ok|missing, apps: [...], source_ref}
    │
    ▼ AppFeatureBuilder.build() → dedupe apps, add time features (days_since_install,
                                   install_bucket), category inference, aggregation
AppFeatureBundle {normalized_apps, aggregate_features, signal_features}
    │
    ▼ AppDecisionEngine.decide() → multi-loan risk, financial maturity,
                                    consumption level, activity level, recommendation
AppDecisionResult {activity_level, risk_assessment, financial_maturity,
                   consumption_profile, metrics, tags, recommendation}
    │
    ▼ AppExplainer.explain() → trim app list → build prompt → call LLM → parse response
AppExplanationResult {status, summary, tags, reasoning texts, report_markdown}
    │
    ▼ AppPageAssembler.assemble() → merge rule + LLM results → Pydantic validation → charts
AgentOutput {summary, structured_result, charts, report_markdown}
```

### 5.3 Behavior Profile Data Flow

**Unique feature — dual LLM chains**:
1. **Profile Chain** (`behavior_profile_prompt.md`): engagement summary, tags, strategy suggestions
2. **Timeline Chain** (`behavior_timeline_prompt.md`): journey narrative, stage insights

Either chain can fail independently. Status: both OK → "ok"; one OK → "partial"; both fail → "model_unavailable".

The behavior decision engine (713 lines, largest file) builds **five dimensions**: engagement profile, repayment willingness, product sensitivity, churn risk, and contact preference. Signal score formula: `max(0, min(100, (engagement + repayment)/2 - churn_penalty - journey_risk*3))`.

### 5.4 Credit Profile Data Flow

Based on **Buró de Crédito** (Mexico's credit bureau). Feature builder derives **six signals** with a radar chart: financial_maturity, repayment_pressure_index, credit_stability, borrowing_urgency, credit_history_depth, cash_tightness.

Credit signal score: `max(0, min(100, int((risk_buffer + score_hint)/2 + band_bonus + stability_bonus)))`.

### 5.5 Comprehensive Profile Data Flow

Consumes all three upstream `AgentOutput` objects. Key processing:
- **Segment assignment** (S1-S6): S1=high-value/low-risk, S5=multi-loan/high-risk, S6=silent/wait-and-see
- **Conflict detection**: e.g., multi-loan medium/high but credit_risk==low → "early warning vs confirmed risk"
- **Value signal derivation**: high if app_activity==high && consumption≥medium_high && engagement≥70
- **Confidence level**: count of upstream statuses == "ok"; 3→high, 2→medium, 1→low

### 5.6 LLM Interaction Pipeline

```
Explainer prepares:
  1. Build prompt_payload (subset of features + decision results)
  2. Trim data (App: max_apps limit; Behavior: compress timeline)
  3. Load prompt template (app/prompts/*.md)
  4. Jinja2 variable substitution
  5. Build response_schema (Pydantic → JSON Schema)
  6. Build fallback_result (rule engine output as degraded default)
         │
         ▼
ModelClient.generate_structured(prompt, schema, fallback):
  mock mode → return fallback + status:"model_unavailable"
  real mode → _generate_with_retry(max=2):
    ├── call Gemini or Vertex AI
    ├── extract text from response
    ├── strip markdown code fences
    ├── _repair_json_candidate() (fix escapes, control chars, trailing commas)
    ├── _parse_json_text() → _extract_first_json_object()
    └── parse failure? retry up to 2x
  all failed → return fallback + error_category
         │
         ▼
Explainer post-processes:
  1. Validate response meaningfulness (non-empty summary/report/tags)
  2. Set explanation_status: ok / partial / skipped
  3. Build model_trace (used_llm, model_name, fallback_reason)
```

**Five prompt templates**:

| File | Lines | Language | Key Constraints |
|------|-------|----------|-----------------|
| `app_profile_prompt.md` | 152 | Chinese | Four-section report structure; progress values 0-100 |
| `behavior_profile_prompt.md` | 88 | Chinese | Don't enumerate events; elevate to stages/frictions/turning-points |
| `behavior_timeline_prompt.md` | 83 | Chinese | Compress repeated events; 2-5 timeline insights |
| `credit_profile_prompt.md` | 94 | Chinese | credit_summary ≥260 chars; don't alter prepared record values |
| `comprehensive_prompt.md` | 42 | English | Don't rewrite upstream evidence; S1-S6 segment guidance |

### 5.7 Offline Data Preprocessing Pipeline

```
Merged CSV → uid_csv_splitter.py → per-uid CSV files
                                        │
         (App only) ─── applist_joiner.py (usage + labels join)
                                        │
         (Behavior) ── behavior_prepared_builder.py → uid.json (schema v1)
         (Credit) ──── credit_prepared_builder.py → uid.json (schema v1)
```

Entry point: `python -m app.scripts.data_prep.prepare_local_data --module all`

---

## 6. Key Business Flows and Design Decisions

### 6.1 End-to-End Single User Analysis

UID submitted → API validates → BatchService forwards to Orchestrator → Orchestrator dispatches App/Behavior/Credit in parallel (ThreadPoolExecutor, 3 workers) → each Skill runs six-step pipeline internally (Context → Data → Features → Rules → LLM → Assembly) → all three complete → Comprehensive fuses outputs (S1-S6 segmentation, conflict detection, value signals) → four AgentOutputs assembled into UserAnalysisResult → JSON response.

### 6.2 Rule Engine Decision Logic

**App**: Multi-loan risk: ≥2 lending apps in 7d → high; ≥3 in 30d → high; 1-2 in 30d → medium. Financial maturity: bank+gov apps → banked; e-wallet → semi-banked; else → non-banked.

**Behavior**: Five dimensions scored independently. Signal score = `(engagement + repayment)/2 - churn_penalty - journey_risk*3`, clamped to 0-100.

**Credit**: Debt pressure scored by total debt + monthly payment + utilization (each scored 0-2, summed). Credit stability mapped from max days-past-due.

### 6.3 LLM Prompt Template Design

**Principles**: (1) Output only JSON, no extra text; (2) Never fabricate data not present in input; (3) Structured fields must match rule engine output; (4) Chinese output (except comprehensive); (5) Both machine-readable fields and human-readable narratives.

### 6.4 Fallback and Degradation Strategy

| Level | Scenario | Handling | Impact |
|-------|----------|----------|--------|
| L1 | Data source missing | Repository returns empty dict + `data_status=missing` | Module outputs `status=data_missing`, others unaffected |
| L2 | Data format error | Multi-path fallback (Prepared JSON → Raw CSV → Legacy) | Auto-tries next format |
| L3 | LLM call failure | Return rule engine result + `status=model_unavailable` | Structured data complete, only missing NL enhancement |
| L4 | LLM returns invalid JSON | `_repair_json_candidate()` attempts fix, else degrade | Same as L3 |

**Core design**: Rule engine results **always exist as fallback** — even with LLM completely unavailable, the system outputs full structured profiles.

### 6.5 Core Design Decisions

**Decision 1: Rule Engine + LLM Enhancement, not pure LLM** — Deterministic rules generate all structured fields; LLM only adds natural-language polish. Benefits: reproducible results, no hallucinated data, system works offline.

**Decision 2: TypedDict over Pydantic for pipeline internals** — Pipeline-internal data is already validated by upstream steps; TypedDict provides type hints without runtime validation overhead. Trade-off: no runtime data validation safety net.

**Decision 3: Comprehensive as single file vs six-step pipeline** — It doesn't need DataAccess or FeatureBuild (upstream outputs are already processed). Trade-off: structural inconsistency with other three modules; 398-line monolith mixes decision, LLM, and assembly logic.

**Decision 4: Embedded frontend** — `live_frontend.py` is a 2000+ line HTML/JS string in a Python file. Quick prototyping benefit; but blocks frontend toolchain (TypeScript, ESLint, HMR) and requires backend restart for UI changes.

---

## 7. File Inventory and Quick Reference

### Core Application

| File | Lines | Purpose |
|------|-------|---------|
| `app/main.py` | 50 | FastAPI entry, route registration, exception handlers |
| `app/api/analyze.py` | 37 | Two POST endpoints (single/batch + file upload) |
| `app/core/config.py` | 73 | Pydantic Settings, 25+ config fields |
| `app/core/model_client.py` | 475 | LLM abstraction (Gemini/Vertex/Mock), retry+repair+fallback |
| `app/services/orchestrator.py` | 109 | Four-skill parallel orchestrator (ThreadPoolExecutor) |
| `app/services/batch_service.py` | 23 | Batch request wrapper |

### Runtime Skills

| File | Lines | Purpose |
|------|-------|---------|
| `runtime_skills/app_profile_agent.py` | 83 | App profile pipeline entry |
| `runtime_skills/app_profile/{contracts,data_access,feature_builder,decision_engine,explainer,assembler}.py` | ~1,082 total | App six-step pipeline |
| `runtime_skills/behavior_profile_agent.py` | 83 | Behavior pipeline entry |
| `runtime_skills/behavior_profile/*.py` | ~1,739 total | Behavior six-step pipeline (dual LLM) |
| `runtime_skills/credit_profile_agent.py` | 75 | Credit pipeline entry |
| `runtime_skills/credit_profile/*.py` | ~1,232 total | Credit six-step pipeline |
| `runtime_skills/comprehensive_agent.py` | 398 | Fusion layer (S1-S6 segmentation, conflict detection) |

### Data Scripts

| File | Lines | Purpose |
|------|-------|---------|
| `scripts/app_profile_payload_builder.py` | 1300+ | App feature extraction + decision + prompt building |
| `scripts/behavior_prepared_builder.py` | 1200+ | Behavior event normalization (CSV → Prepared JSON v1) |
| `scripts/credit_prepared_builder.py` | 1000+ | Credit data normalization (CSV → Prepared JSON v1) |
| `scripts/chart_builder.py` | 400 | Chart configs for all four modules |
| `scripts/data_prep/prepare_local_data.py` | 240 | Preprocessing pipeline CLI entry |

### Legacy (to be deprecated)

| File | Lines | Purpose |
|------|-------|---------|
| `agents/{app,behavior,credit,comprehensive}_profile_agent.py` | 416 total | **Legacy** simple rule-based agents, not used by Orchestrator |

---

## 8. Current Architecture — Problem Diagnosis

### 8.1 LLM Integration Stalled

System defaults to `model_mode: mock`. All Explainers return rule-engine fallback. Blockers: API key provisioning, prompt output stability validation, JSON parse fragility.

### 8.2 agents/ vs runtime_skills/ Redundancy

`agents/` (416 lines, 4 files) is dead code — the Orchestrator only calls `runtime_skills/`. Should be deleted or archived.

### 8.3 Schema Imbalance

App Profile schema: 98 lines with full Pydantic models (RiskAssessment, FinancialMaturity, etc.). Behavior and Credit schemas: 17 lines each — most fields buried in `dict[str, Any]`, losing type safety.

### 8.4 Comprehensive Structural Inconsistency

App/Behavior/Credit each have 6-file sub-pipeline directories. Comprehensive is a single 398-line file mixing decision, LLM, and assembly logic.

### 8.5 Data Source Bottleneck

Only `LocalUserRepository` is implemented (600+ lines). WarehouseRepository is an empty stub. No caching layer.

### 8.6 Embedded Frontend

2000+ lines of HTML/JS inside a Python string. Cannot use frontend toolchain. UI changes require backend restart.

### 8.7 No Version Pinning

`requirements.txt` lists 8 bare package names with no versions and no lock file.

---

## 9. Extensibility Analysis and Improvement Roadmap

### 9.1 From Scripts to Pluggable Skills

**Current**: Skills are hardcoded in the Orchestrator. **Target**: Define `BaseSkill(ABC)` interface, `SkillRegistry` for dynamic registration, Orchestrator reads from registry and schedules by dependency DAG.

### 9.2 New Agent Insertion Points

Planned: **Product Agent** (lending strategy recommendations) and **Operations Agent** (retention/contact strategies). Both consume Comprehensive output. Requires Orchestrator to support **multi-stage scheduling**: Stage 1 parallel (App/Behavior/Credit) → Stage 2 sequential (Comprehensive) → Stage 3 parallel (Product/Ops Agents).

### 9.3 LangGraph Migration Feasibility

LangGraph replaces the hardcoded Orchestrator with a declarative `StateGraph`. Each skill becomes a graph node; edges define dependencies. Benefits: built-in checkpointing, conditional routing, interrupt/resume for human-in-the-loop. Migration cost: medium — skill internals unchanged, only orchestration rewiring needed.

### 9.4 Real Data Source Integration

Implement `WarehouseRepository`, add connection config, add `CachedRepository` decorator with UID+TTL caching.

### 9.5 Recommended Priority

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| **P0** | Activate LLM (API key + end-to-end validation) | 1-2 days | Unlocks core capability |
| **P0** | Remove legacy `agents/` | 0.5 day | Eliminate confusion |
| **P1** | Complete Behavior/Credit schemas | 1 day | Type safety |
| **P1** | Split Comprehensive into six-step pipeline | 1-2 days | Structural consistency |
| **P1** | Pin dependency versions | 0.5 day | Build stability |
| **P2** | Skill interface + registry | 2-3 days | Pluggable extension |
| **P2** | Implement WarehouseRepository | 3-5 days | Real data source |
| **P2** | Separate frontend | 3-5 days | Dev efficiency |
| **P3** | LangGraph migration | 5-7 days | Agent collaboration |
| **P3** | Add Product/Ops Agents | 3-5 days each | Business expansion |

---

## 10. Appendix

### 10.1 Project Statistics

| Metric | Value |
|--------|-------|
| Total files (excl .git/__pycache__) | ~193 |
| Python source files | ~112 |
| Test files | 5 |
| API endpoints | 2 |
| Profile modules | 4 |
| LLM prompt templates | 5 |
| Six-step pipeline sub-files | 18 (3 modules × 6 steps) |
| Largest single file | `app_profile_payload_builder.py` (1300+ lines) |
| Most complex decision engine | `behavior_profile/decision_engine.py` (713 lines) |
| Dependencies | 8 |
| Country packs | 1 (Mexico/mx) |

### 10.2 Key Terms

| Term | Meaning |
|------|---------|
| **UID** | 18-digit numeric user identifier |
| **Skill** | A profile analysis module implementing the six-step pipeline |
| **AgentOutput** | Unified output: summary + structured_result + charts + report_markdown |
| **Prepared JSON** | Pre-processed standardized data format with schema_version tag |
| **Decision Engine** | Deterministic rule engine, generates all structured fields, no LLM dependency |
| **Explainer** | LLM enhancement layer adding natural-language descriptions to rule results |
| **Country Pack** | Country-specific config (thresholds, keywords, label maps) in frozen dataclasses |
| **Buró de Crédito** | Mexico's credit bureau (equivalent to Experian/TransUnion) |
| **S1-S6** | Comprehensive segment labels (S1 high-value/low-risk → S6 silent/wait-and-see) |
| **mock mode** | LLM degradation mode: returns rule engine results directly |
| **Codex Skill** | Editor-side skill in `.agents/skills/`, NOT used at runtime |
| **Runtime Skill** | Production skill in `app/runtime_skills/`, used by Orchestrator |
