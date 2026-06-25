# Knowledge Base Raw Inputs

`docs/knowledge-base` contains local legacy source documents for `M2B-0` knowledge inventory work only.

These raw files may contain:

- sensitive connection details
- internal infrastructure references
- historical SQL examples
- fixed dates, source filters, temporary tables, and other unsafe prompt material

Rules for this directory:

- raw files in this directory must not be committed unless sanitized
- runtime Data Agent retrieval must not read raw files here directly
- raw files here must not be chunked or embedded directly for RAG
- only sanitized inventory, taxonomy, golden-set, baseline, and extracted seed assets are commit-safe
- if raw files under this directory are ever git-tracked, stop and resolve that risk before continuing normal work
