# M3 Minimum Closure Before M4

## 1. Scope

This PR does not complete `M3`.

This closure only stabilizes the minimum boundary required before `M4 Unified Memory & Memory Isolation` can begin:

- real `comprehensive -> product/ops` advice contract
- stable `ProfileMemorySnapshot`
- explicit `profile_result` memory isolation boundary

## 2. M3 Current Truth

- `M3-1 Profile DAG Runtime Skeleton`: completed
- `M3-2 Core Profile Skills`: legacy runtime implemented, not M3-certified
- `M3-3 Profile Data Access Integration`: deferred
- `M3-4 Risk Domain Evidence Integration`: deferred
- `M3-5 Profile Result UI`: deferred
- `M3-6 Profile Golden Set & Regression`: deferred
- `M3-7 Profile Acceptance Review`: deferred

## 3. Minimum Fixes Landed

- `comprehensive` now emits stable top-level advice fields and mirrors them in `structured_result.metrics`
- `product_advice` and `ops_advice` now consume top-level comprehensive fields first, with metrics fallback only for compatibility
- advice outputs now expose `missing_comprehensive_advice_fields` and `used_default_advice_inputs`
- `app/services/profile_dag/memory_snapshot.py` now defines a pure `build_profile_memory_snapshot(...)` helper
- snapshot output now carries explicit allowed/forbidden memory-use boundaries
- targeted regression tests now cover the real DAG contract and snapshot boundary

## 4. Why M4 May Start

`M4` may start only because it can consume `ProfileMemorySnapshot` rather than raw profile internals.

This keeps `M4` decoupled from:

- unstable internal `TypedDict` shapes
- partial `comprehensive -> advice` assumptions
- accidental cross-agent memory reuse

## 5. Explicit Non-Completion Statement

This closure does not complete `M3`.

`M3-3 / M3-4 / M3-5 / M3-6 / M3-7` remain deferred.

`M4` may start only because it consumes `ProfileMemorySnapshot` and not raw profile internals.

## 6. Explicit Forbidden Promotions

- `profile_result` memory must not become Risk Knowledge source-document authority
- `profile_result` memory must not become Risk Knowledge document evidence
- `profile_result` memory must not ground SQL generation
- `profile_result` memory must not become approved strategy or policy truth

## 7. Decision

`M4` may start after this minimum closure.

Whole `M3` remains incomplete.
