# M2B Seed Patch

This directory contains isolated evaluation seed patches produced by `M2B`.

## Rules

- `m2b_legacy_v1.yaml` is an experimental seed namespace for `M2B` evaluation.
- It is not part of the public `mx/ph/common` bundle import flow.
- It must stay sanitized:
  - no raw docs
  - no credentials
  - no connection strings
  - no dirty SQL templates
- Pattern examples in this namespace are non-executable guidance, not runnable SQL.
- Assets marked `manifest_only` in `seed_promotion_manifest.yaml` do not belong in runtime seed import yet.
