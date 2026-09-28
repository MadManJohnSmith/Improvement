# {{PROJECT_NAME}}-continuous-repair

Mode: `{{PROJECT_NAME}}-continuous-repair`
Purpose: provision and repair a managed candidate for `{{PROJECT_NAME}}`.

## Boundaries

- First action: load exact skill `{{PROJECT_NAME}}-continuous-repair`; do not answer before successful load.
- Never send `sandbox_permissions` or `justification`, with any value. Denial or schema error means RETAINED with no retry or escalation.
- A simple repair prompt authorizes candidate creation/reuse and edits only, never a commit.
- Never use write/edit tools. Code-changing bash calls use workdir exactly equal to the candidate.
- Never write the canonical checkout; never commit, merge, push, or publish without a separate explicit user prompt.
- Write operational state only to exact `{{STATE_ROOT}}` through `workflow_write`.

## Procedure

1. Accept `Repara los hallazgos de la auditoría; no publiques.` or named persisted IDs without asking for paths.
2. Read `state-schema.json`, findings, work items, verification results, and handoffs.
3. Capture canonical full HEAD/status, require clean base, and recheck unchanged after every phase; drift means RETAINED and no further action.
4. Hash full base plus sorted unique selected finding IDs; use digest16 for sibling and branch. Run the exact centrally generated provisioning command. Its preflight checks only canonical invariants and the target path/branch; full worktree-list inspection is permitted only to match that target identity. Never validate assumptions about unrelated candidates. Preserve and ignore every unrelated worktree/branch regardless of cleanliness, staleness, or base.
5. Persist candidate identity, patch only with bash whose workdir is the exact candidate, run documented tests, and verify candidate-only diff. Leave it dirty or produce a patch; `candidate_commit` is null.
6. Validate byte caps, compact and replace full state files with `workflow_write` without claiming multi-file atomicity. Report candidate path, branch, null commit, tests, and retained integration boundary.

```json mode-lifecycle
{"schema_version":1,"role":"continuous-repair","state_root":"{{STATE_ROOT}}","state_schema":"state-schema.json","read_before_write":true,"write_method":"workflow_write-full-replacement-not-atomic","bounds":{"findings.jsonl":200,"handoffs.jsonl":50,"work-items.json":200,"verification-results.jsonl":200},"tool_policy":{"session_workdir":"common-parent","state_writes":{"tool":"workflow_write","root":"{{STATE_ROOT}}"},"write_edit_tools":"forbidden","bash":"code-changes-require-workdir-exact-candidate"},"repair_candidate":{"simple_prompt_authorizes":["named-persisted","all-persisted"],"simple_prompt_does_not_authorize":["commit","merge","push","publish"],"canonical_invariant":{"capture_before":["HEAD","status-porcelain-v1"],"verify_after_each_phase":true,"on_drift":"RETAINED-no-further-action"},"candidate_location":"sibling","identity":"sha256(full-base-lf-sorted-unique-finding-ids)","directory_template":"{{PRODUCT_ROOT}}-repair-<digest16>","branch_template":"dsh/repair-<digest16>","provision_checks":["canonical-real-directory-not-symlink","canonical-git-clean","full-base-revision-matches","target-path-absent-or-real-directory-not-symlink","target-path-listed-worktree-if-present","target-branch-absent-or-target-reuse","target-path-and-branch-identify-same-worktree-on-reuse","target-head-equals-full-base-on-reuse","target-clean-on-reuse","no-target-path-branch-worktree-collision"],"unrelated_candidates":"ignore-preserve","worktree_list_scope":"target-path-and-target-branch-only","provision":"git-worktree-add-or-exact-safe-reuse","collision_policy":"retain-target-collision-no-improvisation","patch_root":"candidate-only","candidate_diff_check":"git-diff-from-full-base-candidate-only","commit":"forbidden-without-separate-explicit-user-prompt","forbidden":["canonical-product-write","write-tool","edit-tool","merge","push","publish"],"writes":["work-items.json","verification-results.jsonl","handoffs.jsonl"],"final_fields":["candidate_path","candidate_branch","candidate_commit","tests","integration_status"],"candidate_commit_nullable":true,"integration_status":"dirty-candidate-or-patch-awaiting-user-authorized-integration"}}
```
