# M2B-1 Extracted Assets

This directory stores first-batch structured knowledge assets extracted from `docs/knowledge-base/` during `M2B-1`.

- These files are candidate assets only.
- They are sanitized derivatives, not raw source documents.
- They are not yet imported into the runtime knowledge store.
- They are not yet connected to prompt assembly or runtime retrieval.
- `M2B-2` is the first phase allowed to consider seed promotion and runtime integration.

Asset files in this directory must not contain:

- raw legacy document prose copied verbatim
- host, user, password, jdbc strings, or real IP addresses
- fixed historical dates copied from old SQL templates
- temp table literals such as `dm_model.yx_tmp_*`
- unresolved placeholders such as `uid_str`

Coverage and status are tracked separately through:

- `asset_source_map.yaml`
- `extraction_coverage.yaml`
- `docs/reviews/m2b-1-golden-set-coverage.md`
