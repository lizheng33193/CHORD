# M2D Golden Evaluation

## Purpose

This directory documents the M2D golden-set evaluation framework added in `M2D-13`.

The canonical sample dataset lives in:

- `tests/fixtures/golden/risk_knowledge/eval_set.sample.jsonl`

This keeps the executable fixture in the test tree while leaving this directory as the human-readable guide.

## CLI

Fixture mode:

```bash
python -m app.risk_knowledge.evaluation.cli \
  --golden-set tests/fixtures/golden/risk_knowledge/eval_set.sample.jsonl \
  --output-dir /tmp/m2d_eval_report \
  --mode fixture
```

Runtime mode is opt-in only:

```bash
CHORD_RUN_M2D_RUNTIME_EVAL=1 \
python -m app.risk_knowledge.evaluation.cli \
  --golden-set tests/fixtures/golden/risk_knowledge/eval_set.sample.jsonl \
  --output-dir outputs/evals/m2d \
  --mode runtime
```

If runtime mode is requested without `CHORD_RUN_M2D_RUNTIME_EVAL=1`, the CLI emits a skipped report and exits `0`.

## Notes

- v1 is report-only
- advisory regression decision is included in reports
- runtime baseline is intentionally not committed in `M2D-13`
- `answer_point_recall` is deterministic lexical matching in v1, not semantic groundedness
