# {{PROJECT_NAME}}-continuous-repair

Mode: `{{PROJECT_NAME}}-continuous-repair`
Purpose: provision and repair a managed candidate for `{{PROJECT_NAME}}`.

## Boundaries

- A simple repair prompt authorizes candidate creation/reuse and a tested candidate commit only.
- Never write the canonical checkout; never merge, push, or publish.
- Write operational state only to exact `{{STATE_ROOT}}` through `workflow_write`.

## Procedure

1. Accept `Repara los hallazgos de la auditoría; no publiques.` or named persisted IDs without asking for paths.
2. Read `state-schema.json`, findings, work items, verification results, and handoffs.
3. Verify canonical Git checkout is clean and its revision matches the finding base. Otherwise retain with one concrete action.
4. Derive sibling `{{PRODUCT_ROOT}}-repair-<base12>` and branch `dsh/repair-<base12>`; create or safely reuse it using `git worktree add` via bash. Retain incompatible collisions.
5. Persist candidate identity in `work-items.json`, patch only that candidate, run documented tests, and optionally commit there.
6. Compact and replace full state files with `workflow_write`. Report candidate path, branch, commit, tests, and readiness for Host/user-authorized integration.

```json mode-lifecycle
{"schema_version":1,"role":"continuous-repair","state_root":"{{STATE_ROOT}}","state_schema":"state-schema.json","read_before_write":true,"write_method":"workflow_write-full-replacement","bounds":{"findings.jsonl":200,"handoffs.jsonl":50,"work-items.json":200,"verification-results.jsonl":200},"repair_candidate":{"simple_prompt_authorizes":["named-persisted","all-persisted"],"canonical_preconditions":["git-clean","base-revision-matches"],"candidate_location":"sibling","directory_template":"{{PRODUCT_ROOT}}-repair-<base12>","branch_template":"dsh/repair-<base12>","provision":"git-worktree-add-or-reuse","collision_policy":"retain-with-action","patch_root":"candidate-only","commit":"allowed-after-tests","forbidden":["canonical-product-write","merge","push","publish"],"writes":["work-items.json","verification-results.jsonl","handoffs.jsonl"],"final_fields":["candidate_path","candidate_branch","candidate_commit","tests","integration_status"],"integration_status":"ready-for-host-or-user-authorized-integration"}}
```
