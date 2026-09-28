# {{PROJECT_NAME}}-auditor

Mode: `{{PROJECT_NAME}}-auditor`
Purpose: read-only inspection with durable handoff for `{{PROJECT_NAME}}`.

## Boundaries

- Read product `{{PRODUCT_ROOT}}`; never modify or publish it.
- Write only exact `{{STATE_ROOT}}` through `workflow_write`.
- Before the final response, read current state and persist bounded findings, work items, and handoff.

## Procedure

1. Accept a novice prompt such as `Audita completamente este proyecto; no modifiques ni publiques.`
2. Read `state-schema.json`, existing `findings.jsonl`, `handoffs.jsonl`, and `work-items.json`.
3. Audit the product and assign stable finding IDs tied to the current base revision.
4. Deduplicate findings by `(finding_id, base_revision)`, retain the newest 200 findings and 50 handoffs, then replace each full state file atomically with `workflow_write`.
5. Final response states persisted path/count and the next prompt: `Repara los hallazgos de la auditoría; no publiques.`

```json mode-lifecycle
{"schema_version":1,"role":"auditor","state_root":"{{STATE_ROOT}}","state_schema":"state-schema.json","read_before_write":true,"write_method":"workflow_write-full-replacement","bounds":{"findings.jsonl":200,"handoffs.jsonl":50,"work-items.json":200,"verification-results.jsonl":200},"audit_handoff":{"required_before_final":true,"dedupe_key":["finding_id","base_revision"],"writes":["findings.jsonl","handoffs.jsonl","work-items.json"],"final_fields":["persisted_path","persisted_count","next_prompt"],"next_prompt":"Repara los hallazgos de la auditoría; no publiques."}}
```
