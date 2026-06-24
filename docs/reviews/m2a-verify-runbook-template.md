# M2A-Verify Runbook Template

## Meta

- Case ID:
- Date:
- Operator:
- Branch / Commit:

## Request

- User request:
- Country:
- Run type:
- Output bucket:
- Expected business meaning:

## Preconditions

- Required seed rows:
- Required example status:
- Required error case status:
- Manual setup notes:

## Retrieval Result

### Tables

- Retrieved tables:
- Missing expected tables:
- Wrong-country tables:

### Fields

- Retrieved fields:
- Missing expected fields:

### Glossary

- Retrieved terms:
- Missing expected terms:

### Examples / Error Cases

- Retrieved examples:
- Retrieved error cases:
- Missing expected examples:
- Missing expected error cases:

## Prompt Context

- Assembled knowledge prompt context summary:
- Did context contain irrelevant tables:
- Did context include writeback constraints when expected:

## Generation Result

- Generated SQL:
- SQL kind:
- Safety Gate result:
- Human review result:

## Evaluation

- What improved because of M2A:
- What is still wrong:
- Root cause:
  - catalog gap
  - glossary gap
  - SQL example gap
  - error case gap
  - retriever scoring gap
  - prompt context gap
  - non-knowledge issue

## Seed / Memory Follow-ups

- Seed rows to add or update:
- Examples to promote from draft to active:
- Error cases to capture:

## Final Verdict

- Pass / Partial / Fail:
- Notes:
