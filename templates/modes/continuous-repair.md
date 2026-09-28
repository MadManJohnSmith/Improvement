# {{PROJECT_NAME}}-continuous-repair

Mode: `{{PROJECT_NAME}}-continuous-repair`
Purpose: provision and repair a managed candidate for `{{PROJECT_NAME}}`.

## Boundaries

- First action: load exact skill `{{PROJECT_NAME}}-continuous-repair`; do not answer before successful load.
- A simple repair prompt authorizes candidate creation/reuse and edits only, never a commit.
- Never use write/edit tools. Code-changing bash calls use workdir exactly equal to the candidate.
- Never write the canonical checkout; never commit, merge, push, or publish without a separate explicit user prompt.
- Write operational state only to exact `{{STATE_ROOT}}` through `workflow_write`.

## Procedure

1. Accept `Repara los hallazgos de la auditoría; no publiques.` or named persisted IDs without asking for paths.
2. Read `state-schema.json`, findings, work items, verification results, and handoffs.
3. Capture canonical full HEAD/status, require clean base, and recheck unchanged after every phase; drift means RETAINED and no further action.
4. Hash full base plus sorted unique selected finding IDs; use digest16 for sibling and branch. Execute every structured path/symlink/worktree/branch/HEAD/dirty/stale/collision check before exact create or reuse; never improvise.
5. Persist candidate identity, patch only with bash whose workdir is the exact candidate, run documented tests, and verify candidate-only diff. Leave it dirty or produce a patch; `candidate_commit` is null.
6. Validate byte caps, compact and replace full state files with `workflow_write` without claiming multi-file atomicity. Report candidate path, branch, null commit, tests, and retained integration boundary.

```json mode-lifecycle
{"schema_version":1,"role":"continuous-repair","state_root":"{{STATE_ROOT}}","state_schema":"state-schema.json","read_before_write":true,"write_method":"workflow_write-full-replacement-not-atomic","bounds":{"findings.jsonl":200,"handoffs.jsonl":50,"work-items.json":200,"verification-results.jsonl":200},"tool_policy":{"session_workdir":"common-parent","state_writes":{"tool":"workflow_write","root":"{{STATE_ROOT}}"},"write_edit_tools":"forbidden","bash":"code-changes-require-workdir-exact-candidate"},"repair_candidate":{"simple_prompt_authorizes":["named-persisted","all-persisted"],"simple_prompt_does_not_authorize":["commit","merge","push","publish"],"canonical_invariant":{"capture_before":["HEAD","status-porcelain-v1"],"verify_after_each_phase":true,"on_drift":"RETAINED-no-further-action"},"candidate_location":"sibling","identity":"sha256(full-base-lf-sorted-unique-finding-ids)","directory_template":"{{PRODUCT_ROOT}}-repair-<digest16>","branch_template":"dsh/repair-<digest16>","provision_checks":["canonical-real-directory-not-symlink","canonical-git-clean","full-base-revision-matches","candidate-path-absent-or-real-directory-not-symlink","candidate-listed-worktree-if-present","branch-absent-or-head-equals-full-base","candidate-head-equals-full-base-on-reuse","candidate-clean-on-reuse","no-stale-prunable-worktree","no-path-branch-worktree-collision"],"provision":"git-worktree-add-or-exact-safe-reuse","collision_policy":"retain-with-action-no-improvisation","patch_root":"candidate-only","candidate_diff_check":"git-diff-from-full-base-candidate-only","commit":"forbidden-without-separate-explicit-user-prompt","forbidden":["canonical-product-write","write-tool","edit-tool","merge","push","publish"],"writes":["work-items.json","verification-results.jsonl","handoffs.jsonl"],"final_fields":["candidate_path","candidate_branch","candidate_commit","tests","integration_status"],"candidate_commit_nullable":true,"integration_status":"dirty-candidate-or-patch-awaiting-user-authorized-integration"}}
```
