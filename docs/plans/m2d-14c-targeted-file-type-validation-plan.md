# M2D-14C Targeted File-Type Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate that the accepted local `M2D-14A/M2D-14B` knowledge-base runtime can parse, index, activate, and retrieve small `DOCX`, small `PDF`, and one real large `PDF` in local development without expanding runtime scope.

**Architecture:** `M2D-14C` is a targeted local validation phase, not a new runtime delivery phase. It reuses the existing admin API, in-process indexing runtime, parser path, FAISS activation path, and retrieval debug path exactly as-is, and only adds validation artifacts plus status closure. This plan explicitly does not start `M2D-15 Production Hardening`.

**Tech Stack:** FastAPI admin API, `scripts.local_mysql.local_stack`, MySQL, Redis, FAISS, DashScope embeddings, SWXY parser adapter, `python-docx`, `tika`, PDF parser path, local browser/UI Console.

---

## Validation Scope

`M2D-14C` validates only local runtime file-type behavior for:

- small `DOCX`
- small `PDF`
- one real large `PDF`

Explicit non-goals:

- not `M2D-15 Production Hardening`
- no new API
- no UI changes
- no retrieval / rerank / answer logic changes
- no worker queue
- no SSE / WebSocket
- no parser rework
- no production observability expansion
- no Data Agent RAG mixing

## File Structure

Files involved in executing this plan:

- Create: `docs/reviews/m2d-14c-targeted-file-type-validation-review.md`
- Modify: `PLANNING.md`
- Modify: `TASK.md`
- Reuse only: `docs/reviews/m2d-14b-local-kb-smoke-acceptance-review.md`
- Reuse only: `scripts/local_mysql/local_stack.py`

Local validation artifacts are runtime-only and should not be committed:

- local `DOCX/PDF` input files
- `storage/risk_knowledge/uploads/*`
- `outputs/risk_knowledge/*`
- local `.env.local-mysql`

## Test Matrix

| Case | File Type | Size Class | Primary Goal | Expected Terminal Result |
|---|---|---|---|---|
| `FTV-1` | `DOCX` | small | prove local parser + chunk + index path works for office docs | `index completed`, `manifest present`, `activate ok`, retrieval candidate returned |
| `FTV-2` | `PDF` | small | prove local PDF parser + index path works for simple PDF | `index completed`, `manifest present`, `activate ok`, retrieval candidate returned |
| `FTV-3` | `PDF` | real large | prove current local runtime can finish one realistic large-file validation without changing architecture | terminal result recorded with latency + blocker evidence; pass only if `index completed` and retrieval candidate returned |

## Local Prerequisites

Required local prerequisites before running any case:

- valid local `DASHSCOPE_API_KEY`
- `.env.local-mysql` contains:
  - `SSL_CERT_FILE`
  - `REQUESTS_CA_BUNDLE`
  - `CURL_CA_BUNDLE`
- CA bundle paths resolve to local `certifi` `cacert.pem`
- NLTK runtime data exists:
  - `punkt`
  - `punkt_tab`
  - `wordnet`
  - `omw-1.4`
  - `stopwords`
- parser dependencies are installed:
  - `python-docx`
  - `tika`
- local parser/PDF runtime prerequisites remain usable:
  - Java/Tika path
  - libomp availability
  - PDF parser dependency chain

## Expected Outputs

Expected per-case outputs:

- `kb_id`, `document_id`, `version_id`, `job_id`
- job terminal state
- `latest_manifest_index_id`
- activate result
- retrieval debug candidate count
- top retrieval text preview
- if failed, full `error_message`
- local notes on elapsed time and any parser/runtime warnings

Expected phase outputs:

- `docs/reviews/m2d-14c-targeted-file-type-validation-review.md`
- `PLANNING.md` and `TASK.md` updated from `planned/not started` to the accepted status only after all targeted validation cases are complete

## Failure Handling

When a case fails:

- stop at the failing case
- capture the exact failing step:
  - upload
  - index launch
  - job polling
  - activate
  - retrieval debug
- record full `error_message`
- classify blocker into one of:
  - local prerequisite missing
  - parser dependency issue
  - Java/Tika issue
  - libomp / native dependency issue
  - PDF parser path issue
  - embedding / network / TLS issue
  - large-file latency / timeout issue
- do not broaden scope into runtime redesign
- do not start `M2D-15`

If `FTV-1` or `FTV-2` fails, do not proceed to `FTV-3`.

## Known Risks

- Java / Tika availability may differ across local machines
- `libomp` or other native dependency gaps may affect PDF parsing paths
- PDF parser path may behave differently for image-heavy, scanned, or structurally complex documents
- large-file latency may exceed expectations even if small-file validation passes
- large `PDF` may expose memory, chunk-count, or embedding throughput limits without implying a production-hardening scope expansion

## Acceptance Criteria

`M2D-14C` is accepted only if:

- `FTV-1 small DOCX` passes end-to-end
- `FTV-2 small PDF` passes end-to-end
- `FTV-3 real large PDF` reaches a clearly recorded terminal outcome
- at least one successful retrieval candidate is returned for each passing case
- the final review clearly distinguishes local validation success from production readiness
- `M2D-15 Production Hardening` remains explicitly not started

If only markdown, small `DOCX`, and small `PDF` pass, but the real large `PDF` fails, `M2D-14C` remains incomplete and the blocker must be recorded rather than reclassified as `M2D-15`.

### Task 1: Prepare Validation Inputs And Closure Skeleton

**Files:**
- Create: `docs/reviews/m2d-14c-targeted-file-type-validation-review.md`
- Modify: `PLANNING.md`
- Modify: `TASK.md`

- [ ] **Step 1: Confirm baseline before file-type validation**

Run:

```bash
git rev-parse --short HEAD
git status --short
```

Expected:

- baseline includes `M2D-14B` local smoke closure commit `3dc01be`
- working tree is clean before runtime validation begins

- [ ] **Step 2: Prepare one small DOCX, one small PDF, and one real large PDF input set**

Prepare:

- one small `DOCX` with short risk-domain text
- one small text-based `PDF` with short risk-domain text
- one real large `PDF` intended for final validation

Expected:

- all three files are local-only artifacts
- none are committed into the repository

- [ ] **Step 3: Create the closure review skeleton before runtime execution**

Create `docs/reviews/m2d-14c-targeted-file-type-validation-review.md` with sections for:

- scope
- environment / prerequisites
- per-case results
- failures / blockers
- acceptance conclusion

- [ ] **Step 4: Commit plan-only preparation if needed**

Run:

```bash
git add docs/reviews/m2d-14c-targeted-file-type-validation-review.md PLANNING.md TASK.md
git commit -m "docs: scaffold m2d14c validation closure"
```

Expected:

- only docs/status files are committed

### Task 2: Run Small DOCX Validation

**Files:**
- Modify: `docs/reviews/m2d-14c-targeted-file-type-validation-review.md`

- [ ] **Step 1: Reset local KB state**

Run:

```bash
python -m scripts.local_mysql.local_stack down
python -m scripts.local_mysql.local_stack up --no-reload --no-smoke
```

Expected:

- local stack restarts cleanly
- no code changes are required

- [ ] **Step 2: Execute the full DOCX admin smoke flow**

Run the same validated admin sequence used in markdown smoke:

1. login
2. create KB
3. create document
4. upload small `DOCX`
5. index
6. poll job
7. activate
8. `debug/retrieve`

Expected:

- terminal `job status=completed`
- `manifest_index_id` returned
- retrieval candidate returned

- [ ] **Step 3: Record DOCX case outcome**

Record in the review:

- file type
- file size class
- job status
- manifest id
- activate result
- candidate count
- top text preview
- any warnings

- [ ] **Step 4: Stop if DOCX fails**

If failed:

- capture full `error_message`
- classify blocker
- stop the plan here

### Task 3: Run Small PDF Validation

**Files:**
- Modify: `docs/reviews/m2d-14c-targeted-file-type-validation-review.md`

- [ ] **Step 1: Reset local KB state again**

Run:

```bash
python -m scripts.local_mysql.local_stack down
python -m scripts.local_mysql.local_stack up --no-reload --no-smoke
```

Expected:

- runtime state is clean before the PDF case

- [ ] **Step 2: Execute the full small PDF admin smoke flow**

Repeat the same admin sequence, replacing the input file with the small `PDF`.

Expected:

- terminal `job status=completed`
- `manifest_index_id` returned
- retrieval candidate returned

- [ ] **Step 3: Record PDF case outcome**

Record the same output fields as the DOCX case, plus any parser-path-specific warnings.

- [ ] **Step 4: Stop if small PDF fails**

If failed:

- capture full `error_message`
- classify blocker
- stop before real large `PDF`

### Task 4: Run Real Large PDF Final Validation

**Files:**
- Modify: `docs/reviews/m2d-14c-targeted-file-type-validation-review.md`

- [ ] **Step 1: Reset local KB state once more**

Run:

```bash
python -m scripts.local_mysql.local_stack down
python -m scripts.local_mysql.local_stack up --no-reload --no-smoke
```

Expected:

- large-file validation starts from a clean local state

- [ ] **Step 2: Execute the full real large PDF admin flow**

Run the same sequence used in prior cases, but with the real large `PDF`.

Expected:

- terminal job outcome is explicitly recorded, pass or fail

- [ ] **Step 3: Capture latency and blocker evidence**

Record:

- total polling duration
- final job status
- full `error_message` if failed
- whether activate succeeded
- whether retrieval candidate returned
- whether large-file latency was materially higher than small-file cases

- [ ] **Step 4: Do not widen scope if large PDF fails**

If failed:

- record blocker
- do not redesign runtime
- do not start `M2D-15`

### Task 5: Close Status And Documentation

**Files:**
- Modify: `docs/reviews/m2d-14c-targeted-file-type-validation-review.md`
- Modify: `PLANNING.md`
- Modify: `TASK.md`

- [ ] **Step 1: Decide closure state from the matrix**

Apply:

- all three cases pass -> `M2D-14C accepted`
- small-file pass but large-file fail -> `M2D-14C incomplete, blocker recorded`

- [ ] **Step 2: Update status docs without reclassifying `M2D-15`**

Update:

- `PLANNING.md`
- `TASK.md`

Expected:

- `M2D-14C` status is accurate
- `M2D-15 Production Hardening` remains `not started`

- [ ] **Step 3: Run final docs-only verification**

Run:

```bash
git diff --check
git status --short
```

Expected:

- no whitespace or patch-formatting errors
- only intended docs/status changes are present

- [ ] **Step 4: Commit closure**

Run:

```bash
git add docs/reviews/m2d-14c-targeted-file-type-validation-review.md PLANNING.md TASK.md
git commit -m "docs: close m2d14c targeted file-type validation"
```

Expected:

- only docs/status changes are committed
