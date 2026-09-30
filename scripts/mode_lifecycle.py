"""Versioned lifecycle contract and bounded shared state for generated modes."""

import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import tempfile
from pathlib import Path


SCHEMA_VERSION = 1
LIMITS = {
    "findings.jsonl": 200,
    "handoffs.jsonl": 50,
    "work-items.json": 200,
    "verification-results.jsonl": 200,
    "overflows.jsonl": 100,
}
BYTE_LIMITS = {
    "project.json": 8_192,
    "state-schema.json": 32_768,
    "findings.jsonl": 262_144,
    "handoffs.jsonl": 131_072,
    "work-items.json": 262_144,
    "verification-results.jsonl": 262_144,
    "overflows.jsonl": 131_072,
}
RECORD_BYTE_LIMIT = 4_096
LEGACY_FILE_BYTE_LIMIT = 8 * 1024 * 1024
LEGACY_TOTAL_BYTE_LIMIT = 32 * 1024 * 1024
LEGACY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_LIFECYCLE_FENCE = "mode-lifecycle"
SUCCESS_SENTINEL = "__IMPROVEMENT_LAYOUT_OK__"


def startup_check(layout):
    return ("set -eu; pwd; test \"$(basename \"$PWD\")\" = "
            f"{shlex.quote(layout['session_root'])}"
            f" -a -d {shlex.quote('./' + layout['product_root'])}"
            f" -a -d {shlex.quote('./' + layout['workspace_root'])}; "
            f"printf '{SUCCESS_SENTINEL}\\n'")


def _repair_target(layout):
    product = shlex.quote("./" + layout["product_root"])
    candidate_prefix = shlex.quote(layout["product_root"] + "-repair-")
    return (
        f"product={product}; candidate_name={candidate_prefix}\"$digest16\"; "
        "branch=\"dsh/repair-$digest16\"; expected=\"$PWD/$candidate_name\"; "
        "candidate=\"$expected\"; test -d \"$product\" -a ! -L \"$product\"; "
        "test \"$(git -C \"$product\" rev-parse HEAD)\" = \"$full_base\"; "
        "test -z \"$(git -C \"$product\" status --porcelain=v1)\"; "
        "test \"$(realpath -m -- \"$candidate\")\" = \"$expected\"; "
        "worktrees=\"$(git -C \"$product\" worktree list --porcelain)\"; "
        "path_count=$(printf '%s\\n' \"$worktrees\" | grep -Fxc -- \"worktree $expected\" || :); "
        "branch_count=$(printf '%s\\n' \"$worktrees\" | grep -Fxc -- \"branch refs/heads/$branch\" || :); ")


def repair_provision_command(layout):
    """Return the exact target-scoped clean create/reuse command."""
    return (
        "set -eu; digest16='<digest16>'; full_base='<full-base>'; "
        + _repair_target(layout) +
        "if test ! -e \"$candidate\" -a ! -L \"$candidate\" && "
        "! git -C \"$product\" show-ref --verify --quiet \"refs/heads/$branch\"; then "
        "test \"$path_count\" = 0 -a \"$branch_count\" = 0; "
        "git -C \"$product\" worktree add -b \"$branch\" \"$candidate\" \"$full_base\"; "
        "else test -d \"$candidate\" -a ! -L \"$candidate\"; "
        "test \"$path_count\" = 1 -a \"$branch_count\" = 1; "
        "test \"$(realpath -- \"$candidate\")\" = \"$expected\"; "
        "test \"$(git -C \"$candidate\" rev-parse --show-toplevel)\" = \"$expected\"; "
        "test \"$(git -C \"$candidate\" symbolic-ref --short HEAD)\" = \"$branch\"; "
        "test \"$(git -C \"$candidate\" rev-parse HEAD)\" = \"$full_base\"; "
        "test -z \"$(git -C \"$candidate\" status --porcelain=v1)\"; fi; "
        "test \"$(realpath -- \"$candidate\")\" = \"$expected\"; "
        "test \"$(git -C \"$candidate\" rev-parse --show-toplevel)\" = \"$expected\"; "
        "test \"$(git -C \"$candidate\" symbolic-ref --short HEAD)\" = \"$branch\"; "
        "worktrees=\"$(git -C \"$product\" worktree list --porcelain)\"; "
        "test \"$(printf '%s\\n' \"$worktrees\" | grep -Fxc -- \"worktree $expected\" || :)\" = 1; "
        "test \"$(printf '%s\\n' \"$worktrees\" | grep -Fxc -- \"branch refs/heads/$branch\" || :)\" = 1")


_CANDIDATE_DIFF_SCRIPT = r'''import hashlib,json,os,stat,subprocess,sys
root,expected=sys.argv[1:]
raw=subprocess.check_output(["git","-C",root,"status","--porcelain=v1","-z","--untracked-files=all"])
entries=raw.split(b"\0"); paths=[]; i=0
while i < len(entries) and entries[i]:
    entry=entries[i]; status_code=entry[:2]; paths.append(entry[3:]); i += 1
    if status_code[:1] in (b"R",b"C"):
        if i >= len(entries) or not entries[i]: raise SystemExit(1)
        paths.append(entries[i]); i += 1
if not paths: raise SystemExit(1)
paths=sorted(set(paths)); digest=hashlib.sha256()
for raw_path in paths:
    path=os.fsdecode(raw_path)
    if not path or os.path.isabs(path) or "\0" in path or ".." in path.split("/"): raise SystemExit(1)
    index=subprocess.run(["git","-C",root,"ls-files","-s","--",path],capture_output=True,text=True,check=True).stdout
    if any(line.startswith("160000 ") or line.startswith("120000 ") for line in index.splitlines()): raise SystemExit(1)
    target=os.path.join(root,path); digest.update(len(raw_path).to_bytes(8,"big")); digest.update(raw_path)
    try: mode=os.lstat(target).st_mode
    except FileNotFoundError: digest.update(b"D"); continue
    if not stat.S_ISREG(mode): raise SystemExit(1)
    data=open(target,"rb").read(); digest.update(b"F"); digest.update(len(data).to_bytes(8,"big")); digest.update(data)
actual=digest.hexdigest()
if expected != "-" and actual != expected: raise SystemExit(1)
print("__IMPROVEMENT_CANDIDATE_DIFF__ "+actual+" "+json.dumps([os.fsdecode(p) for p in paths],ensure_ascii=True,separators=(",",":")))
'''


def _candidate_diff_invocation(expected):
    encoded = base64.b64encode(_CANDIDATE_DIFF_SCRIPT.encode()).decode()
    return ("python3 -c 'import base64;exec(base64.b64decode(\"" + encoded +
            "\"))' \"$candidate\" " + expected)


def repair_candidate_diff_command(layout):
    """Capture the dirty candidate digest and complete safe changed-path list."""
    return ("set -eu; digest16='<digest16>'; full_base='<full-base>'; " +
            _repair_target(layout) +
            "test -d \"$candidate\" -a ! -L \"$candidate\"; "
            "test \"$path_count\" = 1 -a \"$branch_count\" = 1; "
            "test \"$(git -C \"$candidate\" rev-parse HEAD)\" = \"$full_base\"; " +
            _candidate_diff_invocation("-"))


def _candidate_diff_capture_shell():
    """Capture the diff line and split it into guarded digest and JSON paths."""
    return (
        "diff_line=\"$(" + _candidate_diff_invocation("-") + ")\"; "
        "case \"$diff_line\" in \"__IMPROVEMENT_CANDIDATE_DIFF__ \"*) ;; *) exit 1;; esac; "
        "diff_digest=\"${diff_line#__IMPROVEMENT_CANDIDATE_DIFF__ }\"; "
        "diff_paths=\"${diff_digest#* }\"; "
        "diff_digest=\"${diff_digest%% *}\"; "
        "case \"$diff_digest\" in ''|*[!0-9a-f]*) exit 1;; esac; "
        "case \"$diff_paths\" in \\[*\\]) ;; *) exit 1;; esac; ")


def _candidate_record_json(marker, dirty):
    """printf of the exact candidate object the mode must persist verbatim.

    Field order matches the state schema required list; the path is the
    relative candidate name (the schema forbids a leading slash) and head is
    the base revision the candidate was provisioned at. DIRTY adds the diff
    digest and the changed-path array captured by the guarded diff command.
    """
    fields = ('{"base_revision":"%s","finding_ids_digest":"%s","path":"%s",'
              '"branch":"%s","head":"%s","status":"%s"')
    args = ('"$full_base" "$finding_ids_digest" "$candidate_name" "$branch" '
            '"$full_base"')
    if dirty:
        return ("printf '" + marker + " " + fields +
                ",\"candidate_diff_digest\":\"%s\",\"changed_paths\":%s}\\n' "
                + args + " 'DIRTY' \"$diff_digest\" \"$diff_paths\"")
    return ("printf '" + marker + " " + fields + "}\\n' "
            + args + " 'PROVISIONED'")


def repair_recording_command(layout):
    """Return the exact command that records candidate evidence into mode state.

    The command prints the exact JSON object to persist verbatim as
    work-items.json.candidate after the __IMPROVEMENT_CANDIDATE_RECORD__
    marker. The single recorded transition is PROVISIONED (clean, no diff) ->
    DIRTY (diff captured). A candidate is only ever touched by the mode after
    its identity is already durably recorded, so an interrupted turn never
    strands a dirty worktree that the strict resume path would refuse. The
    object is schema-valid by construction (relative candidate path, head at
    base), so persistence requires no hand-assembly: any field the mode adds,
    removes, or rewrites is a deviation from the contract, not a fix.
    """
    return (
        "set -eu; digest16='<digest16>'; full_base='<full-base>'; "
        "finding_ids_digest='<finding-ids-digest>'; " + _repair_target(layout) +
        "test -d \"$candidate\" -a ! -L \"$candidate\"; "
        "test \"$path_count\" = 1 -a \"$branch_count\" = 1; "
        "test \"$(realpath -- \"$candidate\")\" = \"$expected\"; "
        "test \"$(git -C \"$candidate\" rev-parse --show-toplevel)\" = \"$expected\"; "
        "test \"$(git -C \"$candidate\" symbolic-ref --short HEAD)\" = \"$branch\"; "
        "test \"$(git -C \"$candidate\" rev-parse HEAD)\" = \"$full_base\"; "
        "if test -n \"$(git -C \"$candidate\" status --porcelain=v1)\"; then "
        + _candidate_diff_capture_shell() + _candidate_record_json(
            "__IMPROVEMENT_CANDIDATE_RECORD__", True) +
        "; else " + _candidate_record_json(
            "__IMPROVEMENT_CANDIDATE_RECORD__", False) + "; fi")


_RECONCILE_IDENTITY_SCRIPT = r'''import hashlib,sys
full_base,raw=sys.argv[1],sys.argv[2]
ids=sorted({part.strip() for part in raw.replace(",", "\n").split("\n") if part.strip()})
if not ids: raise SystemExit(1)
sys.stdout.write(hashlib.sha256((full_base+"\n"+"\n".join(ids)).encode()).hexdigest())
'''


def repair_reconcile_command(layout):
    """Return the exact command that re-captures a stale recorded diff.

    Ownership is already proven by the record itself: path, branch, base and
    finding digest all matched the deterministic target. Only the diff
    evidence is stale, so the current diff is re-measured on that same proven
    candidate instead of stranding the repair for an operator. The command
    never trusts the caller's identity: it recomputes the finding digest and
    digest16 from the base revision plus the actual finding IDs, so a record
    that disagrees about path, branch, base or findings cannot be reconciled.
    """
    encoded = base64.b64encode(_RECONCILE_IDENTITY_SCRIPT.encode()).decode()
    return (
        "set -eu; full_base='<full-base>'; "
        "finding_ids_digest=$(python3 -c 'import base64;exec(base64.b64decode(\"" +
        encoded + "\"))' \"$full_base\" '<finding-ids-lf-separated>'); "
        "digest16=$(printf '%s' \"$finding_ids_digest\" | cut -c1-16); " +
        _repair_target(layout) +
        "test -d \"$candidate\" -a ! -L \"$candidate\"; "
        "test \"$path_count\" = 1 -a \"$branch_count\" = 1; "
        "test \"$(realpath -- \"$candidate\")\" = \"$expected\"; "
        "test \"$(git -C \"$candidate\" rev-parse --show-toplevel)\" = \"$expected\"; "
        "test \"$(git -C \"$candidate\" symbolic-ref --short HEAD)\" = \"$branch\"; "
        "test \"$(git -C \"$candidate\" rev-parse HEAD)\" = \"$full_base\"; "
        + _candidate_diff_capture_shell() +
        _candidate_record_json("__IMPROVEMENT_CANDIDATE_RECONCILE__", True))


def repair_resume_command(layout):
    """Return the exact command for an already authorized dirty target."""
    return (
        "set -eu; digest16='<digest16>'; full_base='<full-base>'; "
        "expected_diff_digest='<candidate-diff-digest>'; " + _repair_target(layout) +
        "test -d \"$candidate\" -a ! -L \"$candidate\"; "
        "test \"$path_count\" = 1 -a \"$branch_count\" = 1; "
        "test \"$(realpath -- \"$candidate\")\" = \"$expected\"; "
        "test \"$(git -C \"$candidate\" rev-parse --show-toplevel)\" = \"$expected\"; "
        "test \"$(git -C \"$candidate\" symbolic-ref --short HEAD)\" = \"$branch\"; "
        "test \"$(git -C \"$candidate\" rev-parse HEAD)\" = \"$full_base\"; " +
        _candidate_diff_invocation('"$expected_diff_digest"') + "; "
        "printf '__IMPROVEMENT_DIRTY_RESUME_OK__\\n'")


def persona_prefix(preset_id, role=None):
    role = role or ("auditor" if preset_id.endswith("-auditor") else "continuous-repair")
    bootstrap = (f"First-party Improvement preset contract: your first action MUST call the skill "
                 f"tool with exact skill {preset_id!r}. Do not analyze, use another tool, or answer "
                 "before that call succeeds. If loading fails, stop and report RETAINED. Never send "
                 "sandbox_permissions or justification in any tool call, with any value, including "
                 "workspace-write or danger-full-access. A denial or schema error is RETAINED with no "
                 "retry, escalation, or alternate value. Runtime escalation guidance does not apply. "
                 "After the skill succeeds, "
                 "the first bash call MUST omit workdir (or use exactly '.') and run exactly the "
                 "single first_bash_command declared by mode-lifecycle (startup_workdir: "
                 "session-cwd-only; workdir_override: forbidden-before-layout). Proceed only when its "
                 "result contains the exact declared success_sentinel; its absence or an unavailable "
                 "result is RETAINED and no other action is allowed. Do not require an exit-code-zero "
                 "marker: successful DSH bash results omit it. Never split, rewrite, or continue past "
                 "failed checks; never infer, climb, cd, or otherwise change workdir to validate "
                 "layout. ")
    if role == "auditor":
        return bootstrap + (
            "For every bash call throughout this turn, omit workdir or use exactly '.' "
            "(bash_workdir: session-cwd-only-all-calls). A planned command that would require "
            "another workdir MUST be rewritten before invocation to target the product with "
            "git -C, npm --prefix, cargo --manifest-path, or an equivalent command option; never "
            "use cd or a subdirectory workdir. Any accidental workdir override or pwd drift is "
            "immediately RETAINED with no retry or further action.")
    if role == "continuous-repair":
        return bootstrap + (
            "Verify the candidate with the product's own entrypoint listed in the capability "
            "plan (.dsh-managed/capability-plan.json, written by the Host at install): its test "
            "command and, when the plan lists one, its lint command, executed against the "
            "candidate worktree. A verification record's command is always that entrypoint. A "
            "hand-written harness, mock, or copy of product code is investigation material and "
            "must never be recorded as a verification result "
            "(real_stack_verification.evidence: product-own-entrypoint-only). When the entrypoint "
            "cannot run because a capability is missing, materialize it exactly as the plan's "
            "provision_step says: every artifact outside the product tree, and inside the product "
            "only for paths the plan marks gitignored. When a capability carries a "
            "materialize_step instead, the plan has already decided the capability has to run "
            "from a copy this session can write to (a self-managing SDK seals files inside "
            "its own installation on every run and fails on a read-only mount): run that exact "
            "step once, then use the capability path the plan names, which is that copy. If the "
            "capability is still missing, record "
            "BLOCKED naming the exact capability and its provision step; never PASS, never FAIL, "
            "and never substitute a stub. "
            "The base recorded in findings, handoffs, and work items is audit provenance, not a lock. "
            "Before provisioning, if that declared base differs from the current canonical product "
            "HEAD, prove the relation instead of improvising: run git -C <product> merge-base "
            "--is-ancestor <declared-base> HEAD and require the canonical product clean. If and only "
            "if the declared base is an ancestor of HEAD and the product is clean, re-anchor "
            "(stale_base_policy: re-anchor-when-declared-base-is-ancestor-of-clean-head): full_base "
            "is the current canonical HEAD, the candidate identity derives from that effective base, "
            "the recorded candidate base_revision is the effective base, and the final report states "
            "the declared base, the effective base, and the ancestry proof. Findings and handoffs "
            "keep their declared base unchanged. Any other relation (divergent history, rewritten or "
            "force-pushed history, dirty canonical product, unknown base) is a hard RETAINED with no "
            "further action. "
            "Before provisioning, read and strictly validate work-items.json candidate. Use the exact "
            "centrally generated resume_command only when that record exactly matches target path, "
            "branch, base, finding digest, stored candidate_diff_digest, and status DIRTY or RETAINED; "
            "otherwise dirty target collision is RETAINED. Never adopt an unrecorded dirty worktree. "
            "The resume command must prove registered identity, HEAD at base, canonical unchanged and "
            "clean, a nonempty byte-identical candidate diff, safe regular changed paths, and no "
            "submodule or symlink. "
            "Every candidate record is the exact JSON object the central commands print after their "
            "marker: persist it verbatim, field-for-field, with no field added, removed, renamed, "
            "reordered, or reformatted, and no value altered (the path is the relative candidate "
            "name the object carries, never an absolute path). Hand-editing, re-keying, or wrapping "
            "the emitted object to make it fit is forbidden; if the verbatim object cannot be "
            "persisted, make no code change and report RETAINED. "
            "If the resume command fails ONLY because the stored candidate_diff_digest is stale while "
            "the record already matches target path, branch, base and finding digest exactly, that is "
            "not a collision and never needs an operator: run the exact centrally generated "
            "reconcile_command, persist the JSON object it prints after the "
            "__IMPROVEMENT_CANDIDATE_RECONCILE__ marker verbatim as the new DIRTY record, and resume "
            "normally (stale_record_policy: reconcile-then-resume). Re-capture "
            "is allowed only after that exact identity match and only with the canonical product still "
            "unchanged and clean. Any mismatch of path, branch, base or finding digest remains a hard "
            "RETAINED. "
            "Claim the candidate before you edit it: immediately after the provisioning command "
            "succeeds and before the first code-changing call, run the exact centrally generated "
            "recording_command and persist the JSON object it prints after the "
            "__IMPROVEMENT_CANDIDATE_RECORD__ marker verbatim as "
            "work-items.json.candidate (status PROVISIONED, with path, branch, head, base, and "
            "finding_ids_digest exactly as emitted). Re-run the same recording command after the "
            "first code change and persist the newly emitted object the same verbatim way (it "
            "already carries status DIRTY with candidate_diff_digest and "
            "changed_paths). A claimed candidate that is PROVISIONED but already dirty is a turn that "
            "was interrupted: recover it with the recording command, never with a fresh create, and "
            "never by discarding its diff. If that first claim cannot be persisted, make no code "
            "change at all and report RETAINED. "
            "Provision only from the unchanged session cwd: the provisioning bash call "
            "MUST omit workdir (never use '.' as a code-changing workdir) and run the exact centrally "
            "generated provision_command after substituting only validated digest16 and full_base. "
            "candidate_root is ${session-cwd}/<candidate-name>; never resolve it under the product. "
            "The command may inspect the full worktree list only to match that target path and target "
            "branch. Never validate assumptions about, modify, delete, or let unrelated candidates "
            "block provisioning; unrelated_candidates is ignore-preserve. After provisioning, verify "
            "the target realpath and registered worktree path equal that exact sibling. Every later "
            "code-changing bash call MUST use workdir exactly equal to the candidate_workdir relative "
            "to session cwd, never '.'. Any target collision, mismatch, nested candidate, or other pwd "
            "drift is RETAINED with no further action.")
    raise ValueError(f"unsupported mode role: {role!r}")


def expected_lifecycle(role, layout):
    common = {
        "schema_version": SCHEMA_VERSION,
        "role": role,
        "state_root": layout["state_root"],
        "state_schema": "state-schema.json",
        "read_before_write": True,
        "write_method": "workflow_write-full-replacement-not-atomic",
        "bounds": LIMITS,
        "overflow_receipt": {
            "file": "overflows.jsonl",
            "when": "any-write-that-drops-records-beyond-limits-or-dedupe",
            "append_before_replacement": True,
            "record_fields": ["overflow_id", "file", "reason", "dropped_records"],
            "dropped_records_cap": 32,
            "dedupe_key": ["overflow_id"],
        },
        "real_stack_verification": {
            "plan": ".dsh-managed/capability-plan.json",
            "evidence": "product-own-entrypoint-only",
            "stubs": "investigation-material-never-verification-evidence",
            "missing_capability": "materialize-per-plan-else-BLOCKED-naming-the-step",
            "install_inside_product": "only-when-plan-marks-path-gitignored",
            "sandbox_readonly_sdk": "run-plan-materialize_step-then-use-the-copy-the-plan-names",
        },
        "startup": {
            "startup_workdir": "session-cwd-only",
            "workdir_override": "forbidden-before-layout",
            "first_post_skill_tool": "bash",
            "first_bash_workdir": "omitted-or-dot",
            "first_bash_command": startup_check(layout),
            "success_sentinel": SUCCESS_SENTINEL,
            "expected_cwd_basename": layout["session_root"],
            "relative_layout_checks": [
                f"./{layout['product_root']}", f"./{layout['workspace_root']}"],
            "path_resolution": "observed-unchanged-session-cwd",
            "pwd_drift": "RETAINED",
        },
        "tool_policy": {
            "session_workdir": "observed-unchanged-session-cwd",
            "state_writes": {"tool": "workflow_write", "root": layout["state_root"]},
            "write_edit_tools": "forbidden",
            "candidate_status": {"modes": "preserve", "INTEGRATED": "host-or-operator-only"},
            "escalation_channel": "forbidden",
            "forbidden_arguments": ["sandbox_permissions", "justification"],
            "forbidden_argument_values": "all-including-workspace-write-and-danger-full-access",
            "denial_policy": "RETAINED-no-retry-on-denial-or-schema-error",
        },
    }
    if role == "auditor":
        common["tool_policy"]["bash"] = "read-only"
        common["tool_policy"]["bash_workdir"] = "session-cwd-only-all-calls"
        common["audit_handoff"] = {
            "required_before_final": True,
            "dedupe_key": ["finding_id", "base_revision"],
            "writes": ["findings.jsonl", "handoffs.jsonl", "work-items.json"],
            "candidate_state": "preserve-existing",
            "final_fields": ["persisted_path", "persisted_count", "next_prompt"],
            "next_prompt": "Repara los hallazgos de la auditoría; no publiques.",
        }
    elif role == "continuous-repair":
        common["tool_policy"]["bash"] = "code-changes-require-workdir-exact-candidate"
        common["repair_candidate"] = {
            "simple_prompt_authorizes": ["named-persisted", "all-persisted"],
            "simple_prompt_does_not_authorize": ["commit", "merge", "push", "publish"],
            "canonical_invariant": {
                "capture_before": ["HEAD", "status-porcelain-v1"],
                "verify_after_each_phase": True,
                "on_drift": "RETAINED-no-further-action",
            },
            "candidate_location": "sibling-of-product-from-session-cwd",
            "identity": "sha256(full-base-lf-sorted-unique-finding-ids)",
            "directory_template": f"{layout['product_root']}-repair-<digest16>",
            "branch_template": "dsh/repair-<digest16>",
            "candidate_root": "${session-cwd}/<candidate-name>",
            "forbidden_candidate_location": "under-product-root",
            "candidate_workdir": f"{layout['product_root']}-repair-<digest16>",
            "provision_workdir": "omitted-session-cwd",
            "provision_command": repair_provision_command(layout),
            "recording_command": repair_recording_command(layout),
            "record_before_first_edit": True,
            "record_statuses": ["PROVISIONED", "DIRTY"],
            "candidate_diff_command": repair_candidate_diff_command(layout),
            "reconcile_command": repair_reconcile_command(layout),
            "resume_command": repair_resume_command(layout),
            "resume_policy": "exact-recorded-only",
            "resume_statuses": ["DIRTY", "RETAINED-pending-verification"],
            "stale_record_policy": "reconcile-then-resume",
        "stale_base_policy": "re-anchor-when-declared-base-is-ancestor-of-clean-head",
            "stale_record_precondition": [
                "strict-work-items-candidate", "exact-target-path-branch-base-finding-digest",
                "registered-worktree-exact-identity", "target-head-equals-full-base",
                "canonical-head-and-clean-unchanged", "candidate-diff-nonempty",
                "changed-paths-candidate-confined-regular-no-symlink", "no-submodules",
            ],
            "resume_required_checks": [
                "strict-work-items-candidate", "exact-target-path-branch-base-finding-digest",
                "stored-candidate-diff-digest", "registered-worktree-exact-identity",
                "target-head-equals-full-base", "canonical-head-and-clean-unchanged",
                "candidate-diff-nonempty-and-digest-matches", "changed-path-list-complete",
                "changed-paths-candidate-confined-regular-no-symlink", "no-submodules",
            ],
            "unrecorded_dirty_target": "RETAINED-never-adopted",
            "interrupted_turn_recovery": "recorded-PROVISIONED-target-may-become-DIRTY-by-recording-command",
            "provision_checks": [
                "canonical-real-directory-not-symlink", "canonical-git-clean",
                "full-base-revision-matches", "target-path-absent-or-real-directory-not-symlink",
                "target-path-listed-worktree-if-present", "target-branch-absent-or-target-reuse",
                "target-path-and-branch-identify-same-worktree-on-reuse",
                "target-head-equals-full-base-on-clean-reuse", "target-clean-on-clean-reuse",
                "dirty-reuse-exact-recorded-resume-command-only",
                "no-target-path-branch-worktree-collision",
            ],
            "unrelated_candidates": "ignore-preserve",
            "worktree_list_scope": "target-path-and-target-branch-only",
            "provision": "git-worktree-add-or-exact-safe-reuse",
            "collision_policy": "retain-target-collision-no-improvisation",
            "patch_root": "candidate-only",
            "candidate_diff_check": "git-diff-from-full-base-candidate-only",
            "commit": "forbidden-without-separate-explicit-user-prompt",
            "forbidden": ["canonical-product-write", "write-tool", "edit-tool", "merge", "push", "publish"],
            "writes": ["work-items.json", "verification-results.jsonl", "handoffs.jsonl"],
            "final_fields": [
                "candidate_path", "candidate_branch", "candidate_commit",
                "tests", "integration_status",
            ],
            "candidate_commit_nullable": True,
            "integration_status": "dirty-candidate-or-patch-awaiting-user-authorized-integration",
        }
    else:
        raise ValueError(f"unsupported mode role: {role!r}")
    return common


def lifecycle_block(document):
    marker = f"```json {_LIFECYCLE_FENCE}\n"
    parts = document.split(marker)
    if len(parts) != 2:
        raise ValueError("SKILL.md must contain exactly one json mode-lifecycle block")
    body, suffix = parts[1].split("\n```", 1) if "\n```" in parts[1] else (None, None)
    if body is None or marker in suffix:
        raise ValueError("SKILL.md mode-lifecycle block is malformed")
    try:
        value = json.loads(body)
    except json.JSONDecodeError as error:
        raise ValueError(f"SKILL.md mode-lifecycle is invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("SKILL.md mode-lifecycle must be an object")
    return value


def validate_lifecycle_contract(value, role, layout=None):
    if not isinstance(value, dict):
        raise ValueError("mode_lifecycle must be an object")
    if layout is None:
        state_root = value.get("state_root")
        if not isinstance(state_root, str) or not state_root.endswith("/mode-state"):
            raise ValueError("mode_lifecycle state_root must end in /mode-state")
        startup = value.get("startup", {})
        checks = startup.get("relative_layout_checks", [])
        if not isinstance(checks, list) or len(checks) != 2:
            raise ValueError("mode_lifecycle startup requires two relative layout checks")
        product_root = checks[0][2:] if isinstance(checks[0], str) and checks[0].startswith("./") else None
        workspace_root = state_root.rsplit("/mode-state", 1)[0]
        session_root = startup.get("expected_cwd_basename")
        layout = {"session_root": session_root, "state_root": state_root,
                  "product_root": product_root, "workspace_root": workspace_root}
    expected = expected_lifecycle(role, layout)
    if value != expected:
        raise ValueError("mode_lifecycle does not match the role contract")


def validate_mode_lifecycle(mode_dir, expected_layout):
    mode_dir = Path(mode_dir)
    mode = json.loads((mode_dir / "mode.json").read_text(encoding="utf-8"))
    expected = expected_lifecycle(mode.get("role"), expected_layout)
    if mode.get("mode_lifecycle") != expected:
        raise ValueError("mode.json mode_lifecycle does not match the role contract")
    skill = (mode_dir / "SKILL.md").read_text(encoding="utf-8")
    if lifecycle_block(skill) != expected:
        raise ValueError("SKILL.md mode-lifecycle does not match the role contract")


def compact_records(records, key_fields, limit):
    """Keep the newest record per key, then the newest bounded records."""
    if not isinstance(records, list) or not isinstance(limit, int) or limit < 1:
        raise ValueError("invalid compaction input")
    latest = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("state records must be objects")
        try:
            key = tuple(record[field] for field in key_fields)
        except KeyError as error:
            raise ValueError(f"state record missing dedupe field: {error.args[0]}") from error
        if key in latest:
            del latest[key]
        latest[key] = record
    return list(latest.values())[-limit:]


def _record_schema(required, properties, example):
    return {"type": "object", "required": required, "additionalProperties": False,
            "properties": properties, "example": example, "max_bytes": RECORD_BYTE_LIMIT}


def _legacy_state_schema():
    return {
        "schema_version": 1,
        "files": {
            "findings.jsonl": {"format": "jsonl", "limit": LIMITS["findings.jsonl"],
                               "dedupe_key": ["finding_id", "base_revision"]},
            "handoffs.jsonl": {"format": "jsonl", "limit": LIMITS["handoffs.jsonl"],
                               "dedupe_key": ["handoff_id", "base_revision"]},
            "work-items.json": {"format": "object", "limit": LIMITS["work-items.json"],
                                "items_key": "items", "candidate_key": "candidate"},
            "verification-results.jsonl": {
                "format": "jsonl", "limit": LIMITS["verification-results.jsonl"],
                "dedupe_key": ["finding_id", "candidate_commit"],
            },
        },
    }


def state_schema():
    # A record is already bounded as a whole by RECORD_BYTE_LIMIT, so every text
    # field shares that single bound. A tighter per-field cap would make the
    # preflight drop records the modes write routinely (a finding summary with
    # its evidence runs past 1 KiB), and that loss is invisible afterwards:
    # the finding's repair can land in the product while its record never
    # reaches the live state again.
    text = {"type": "string", "minLength": 1, "maxLength": RECORD_BYTE_LIMIT}
    revision = {"type": "string", "pattern": "^[0-9a-f]{40,64}$"}
    return {
        "schema_version": SCHEMA_VERSION,
        "record_max_bytes": RECORD_BYTE_LIMIT,
        "files": {
            "findings.jsonl": {"format": "jsonl", "limit": LIMITS["findings.jsonl"],
                "max_bytes": BYTE_LIMITS["findings.jsonl"], "dedupe_key": ["finding_id", "base_revision"],
                "record": _record_schema(["finding_id", "base_revision", "severity", "summary", "status"],
                    {"finding_id": text, "base_revision": revision, "severity": {"enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]}, "summary": text, "status": {"enum": ["OPEN", "RESOLVED", "RETAINED"]}},
                    {"finding_id": "A-01", "base_revision": "a" * 40, "severity": "HIGH", "summary": "Missing validation", "status": "OPEN"})},
            "handoffs.jsonl": {"format": "jsonl", "limit": LIMITS["handoffs.jsonl"],
                "max_bytes": BYTE_LIMITS["handoffs.jsonl"], "dedupe_key": ["handoff_id", "base_revision"],
                "record": _record_schema(["handoff_id", "base_revision", "finding_ids", "next_prompt"],
                    {"handoff_id": text, "base_revision": revision, "finding_ids": {"type": "array", "items": text, "maxItems": 200}, "next_prompt": text},
                    {"handoff_id": "audit-1", "base_revision": "a" * 40, "finding_ids": ["A-01"], "next_prompt": "Repara A-01; no publiques."})},
            "work-items.json": {"format": "object", "limit": LIMITS["work-items.json"],
                "max_bytes": BYTE_LIMITS["work-items.json"], "items_key": "items", "candidate_key": "candidate",
                "item": _record_schema(["work_item_id", "finding_id", "base_revision", "status"],
                    {"work_item_id": text, "finding_id": text, "base_revision": revision, "status": {"enum": ["PENDING", "IN_PROGRESS", "VERIFIED", "RETAINED"]}},
                    {"work_item_id": "W-01", "finding_id": "A-01", "base_revision": "a" * 40, "status": "PENDING"}),
                "candidate": {"type": ["object", "null"], "required": ["base_revision", "finding_ids_digest", "path", "branch", "head", "status"], "additionalProperties": False,
                    "properties": {"base_revision": revision, "finding_ids_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "path": {"type": "string", "pattern": "^[^/][^\\0]*$"}, "branch": {"type": "string", "pattern": "^dsh/repair-[0-9a-f]{16}$"}, "head": revision, "status": {"enum": ["PROVISIONED", "DIRTY", "PATCH_READY", "RETAINED", "INTEGRATED"]}, "candidate_diff_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"}, "changed_paths": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 4096}, "maxItems": 200}},
                    "example": {"base_revision": "a" * 40, "finding_ids_digest": "b" * 64, "path": "Product-repair-bbbbbbbbbbbbbbbb", "branch": "dsh/repair-bbbbbbbbbbbbbbbb", "head": "a" * 40, "status": "DIRTY", "candidate_diff_digest": "c" * 64, "changed_paths": ["src/example.py"]}}},
            "verification-results.jsonl": {"format": "jsonl", "limit": LIMITS["verification-results.jsonl"],
                "max_bytes": BYTE_LIMITS["verification-results.jsonl"], "dedupe_key": ["finding_id", "candidate_head"],
                "record": _record_schema(["finding_id", "candidate_head", "result", "command"],
                    {"finding_id": text, "candidate_head": revision, "result": {"enum": ["PASS", "FAIL", "BLOCKED"]}, "command": text},
                    {"finding_id": "A-01", "candidate_head": "a" * 40, "result": "PASS", "command": "pytest"})},
            "overflows.jsonl": {"format": "jsonl", "limit": LIMITS["overflows.jsonl"],
                "max_bytes": BYTE_LIMITS["overflows.jsonl"], "dedupe_key": ["overflow_id"],
                "record": _record_schema(["overflow_id", "file", "reason", "dropped_records"],
                    {"overflow_id": text,
                     "file": {"enum": sorted(name for name in LIMITS if name != "overflows.jsonl")},
                     "reason": text,
                     "dropped_records": {"type": "array", "items": text, "maxItems": 32}},
                    {"overflow_id": "OV-01", "file": "handoffs.jsonl",
                     "reason": "limit-overflow", "dropped_records": ["audit-3"]})},
        },
    }


def _valid(value, schema, label):
    types = schema.get("type")
    if types:
        choices = types if isinstance(types, list) else [types]
        mapping = {"object": dict, "array": list, "string": str, "null": type(None)}
        if not any(type(value) is mapping[kind] for kind in choices):
            raise ValueError(f"{label} has invalid type")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", 1 << 30):
            raise ValueError(f"{label} has invalid length")
        import re
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            raise ValueError(f"{label} has invalid format")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{label} has invalid value")
    if isinstance(value, list):
        if len(value) > schema.get("maxItems", 1 << 30):
            raise ValueError(f"{label} has too many items")
        for index, item in enumerate(value):
            _valid(item, schema.get("items", {}), f"{label}[{index}]")
    if isinstance(value, dict):
        required = schema.get("required", [])
        if any(key not in value for key in required):
            raise ValueError(f"{label} missing required fields")
        if schema.get("additionalProperties") is False and set(value) - set(schema.get("properties", {})):
            raise ValueError(f"{label} has unknown fields")
        for key, item in value.items():
            _valid(item, schema.get("properties", {}).get(key, {}), f"{label}.{key}")
        if label.endswith(".candidate") and value.get("status") in ("DIRTY", "RETAINED"):
            if "candidate_diff_digest" not in value or "changed_paths" not in value:
                raise ValueError(f"{label} dirty resume evidence missing")


def _encode_json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _preflight_file(path, max_bytes):
    stat = path.lstat()
    if not path.is_file() or path.is_symlink() or stat.st_nlink != 1:
        raise ValueError(f"unsafe mode-state file: {path}")
    if stat.st_size > max_bytes:
        raise ValueError(f"oversized mode-state file: {path}")
    return path.read_bytes()


def _is_valid(value, schema, label):
    try:
        _valid(value, schema, label)
        return True
    except ValueError:
        return False


def _adapt_record(record, spec, label):
    if _is_valid(record, spec["record"], label):
        return record, False
    if (label.startswith("findings.jsonl:") and isinstance(record, dict) and
            "finding_id" not in record and set(record) == {
                "id", "base_revision", "severity", "summary", "status"}):
        adapted = {"finding_id": record["id"], **{
            key: value for key, value in record.items() if key != "id"}}
        if _is_valid(adapted, spec["record"], label):
            return adapted, True
    return None, True


def _jsonl(data, spec, label):
    records = []
    incompatible = False
    dropped = []
    identity_keys = tuple(spec["dedupe_key"][:1]) + ("id",)

    def identity(raw_line, parsed):
        """Name a dropped record by its own identity, or by its line if it has none."""
        if isinstance(parsed, dict):
            for key in identity_keys:
                value = parsed.get(key)
                if isinstance(value, str) and value.strip():
                    return f"{label}#{value.strip()}"
        return f"{label}:{raw_line}"

    for number, raw in enumerate(data.splitlines(), 1):
        if not raw.strip():
            continue
        if len(raw) > RECORD_BYTE_LIMIT:
            incompatible = True
            dropped.append(identity(number, None))
            continue
        try:
            record = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            incompatible = True
            dropped.append(identity(number, None))
            continue
        adapted, changed = _adapt_record(record, spec, f"{label}:{number}")
        incompatible |= changed
        if adapted is None:
            dropped.append(identity(number, record))
            continue
        records.append(adapted)
    compacted = compact_records(records, spec["dedupe_key"], spec["limit"])
    encoded = b"".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode() + b"\n" for record in compacted)
    return encoded, incompatible, dropped


def _replace_bytes(path, encoded):
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _legacy_inventory(entries, metadata):
    return [{"name": name, **metadata[name],
             "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
            for name, data in sorted(entries.items())]


def _verified_legacy_archive(root, digest, inventory, descriptor):
    destination = root / digest
    if not destination.is_dir() or destination.is_symlink():
        return False
    try:
        receipt = json.loads((destination / "receipt.json").read_bytes())
        recorded = json.loads((destination / "inventory.json").read_bytes())
    except (OSError, json.JSONDecodeError):
        return False
    if (recorded != inventory or receipt.get("schema_version") != 1 or
            receipt.get("set_sha256") != digest or receipt.get("files") != inventory or
            receipt.get("state_root") != descriptor.get("state_root")):
        return False
    files = destination / "files"
    if not files.is_dir() or files.is_symlink():
        return False
    try:
        return ({entry.name for entry in files.iterdir()} ==
                {item["name"] for item in inventory} and
                all(hashlib.sha256(_preflight_file(
                    files / item["name"], LEGACY_FILE_BYTE_LIMIT)).hexdigest() ==
                    item["sha256"] for item in inventory))
    except (OSError, ValueError):
        return False


def _archive_legacy(entries, metadata, descriptor, archive_root):
    inventory = _legacy_inventory(entries, metadata)
    digest = hashlib.sha256(_encode_json(inventory)).hexdigest()
    root = Path(archive_root)
    if root.exists() and (not root.is_dir() or root.is_symlink()):
        raise ValueError(f"unsafe legacy mode-state archive root: {root}")
    destination = root / digest
    if destination.exists():
        if not _verified_legacy_archive(root, digest, inventory, descriptor):
            raise ValueError(f"legacy mode-state archive conflicts or is damaged: {destination}")
        return destination

    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{digest}.", dir=root))
    published = False
    try:
        files = stage / "files"
        files.mkdir(mode=0o700)
        for name, data in entries.items():
            _replace_bytes(files / name, data)
        _replace_bytes(stage / "inventory.json", _encode_json(inventory))
        _replace_bytes(stage / "receipt.json", _encode_json({
            "schema_version": 1,
            "set_sha256": digest,
            "state_root": descriptor.get("state_root"),
            "files": inventory,
            "file_count": len(inventory),
            "total_bytes": sum(item["size"] for item in inventory),
            "limits": {"per_file_bytes": LEGACY_FILE_BYTE_LIMIT,
                       "total_bytes": LEGACY_TOTAL_BYTE_LIMIT},
        }))
        stage.rename(destination)
        published = True
        if not _verified_legacy_archive(root, digest, inventory, descriptor):
            raise ValueError(f"legacy mode-state archive verification failed: {destination}")
    except BaseException:
        cleanup = destination if published else stage
        if cleanup.exists():
            shutil.rmtree(cleanup)
        raise
    return destination


def initialize_state(state, descriptor, archive_root=None):
    """Preflight state, archive bounded legacy evidence, then migrate strict files.

    Returns a report ({"state", "dropped", "archive"}) naming every file the
    preflight replaced or discarded and the identities of the dropped records,
    so the caller surfaces what left the live state instead of leaving it
    discoverable only inside the legacy archive.
    """
    state = Path(state)
    if state.exists():
        if not state.is_dir() or state.is_symlink():
            raise ValueError(f"unsafe mode-state root: {state}")
    allowed = {"project.json", "state-schema.json", *LIMITS}
    existing = set()
    legacy = {}
    legacy_metadata = {}
    notes = []
    if state.exists():
        existing = {entry.name for entry in state.iterdir()}
        for name in existing - allowed:
            if not LEGACY_NAME.fullmatch(name):
                raise ValueError(f"unsafe legacy mode-state name: {name!r}")
            legacy[name] = _preflight_file(state / name, LEGACY_FILE_BYTE_LIMIT)
            legacy_metadata[name] = {"source_path": name, "reason": "unexpected-evidence"}

    schema = state_schema()
    staged = {"project.json": _encode_json(descriptor), "state-schema.json": _encode_json(schema)}
    originals = {}

    def preserve_expected(name, data, reason, **extra):
        archive_name = f"active-{name}"
        if archive_name in legacy:
            archive_name = f"active-{hashlib.sha256(name.encode()).hexdigest()[:16]}-{name}"
        legacy[archive_name] = data
        legacy_metadata[archive_name] = {"source_path": name, "reason": reason, **extra}
        notes.append({"file": name, "reason": reason, **extra})
    for name in existing & allowed:
        data = _preflight_file(state / name, LEGACY_FILE_BYTE_LIMIT)
        originals[name] = data
        if name == "project.json":
            try:
                project = json.loads(data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                project = None
            if project != descriptor:
                if (isinstance(project, dict) and
                        {key: project.get(key) for key in descriptor} == descriptor):
                    preserve_expected(name, data, "legacy-equivalent-descriptor")
                else:
                    raise ValueError(f"mode-state file conflicts with descriptor: {state / name}")
        if len(data) > BYTE_LIMITS[name]:
            preserve_expected(name, data, "oversized-incompatible-expected-file")
            continue
        if name == "state-schema.json":
            try:
                stored_schema = json.loads(data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                stored_schema = None
            if stored_schema not in (schema, _legacy_state_schema()):
                preserve_expected(name, data, "incompatible-expected-file")
        if name.endswith(".jsonl"):
            staged[name], incompatible, dropped = _jsonl(data, schema["files"][name], name)
            if incompatible:
                # The receipt names what could not be activated, so a record that
                # leaves the live state is visible here instead of being
                # rediscovered months later by cross-referencing identifiers.
                preserve_expected(name, data, "incompatible-records",
                                   dropped_records=dropped[:32])
        if name == "work-items.json":
            incompatible = False
            invalid_items = []
            try:
                current = json.loads(data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                current = None
                incompatible = True
            if isinstance(current, list):
                current = {"schema_version": SCHEMA_VERSION, "candidate": None, "items": current}
                incompatible = True
            elif isinstance(current, dict) and set(current) == {"candidate", "items"}:
                current = {"schema_version": SCHEMA_VERSION, **current}
                incompatible = True
            if not (isinstance(current, dict) and set(current) == {"schema_version", "candidate", "items"}
                    and current["schema_version"] == SCHEMA_VERSION and isinstance(current["items"], list)):
                current = {"schema_version": SCHEMA_VERSION, "candidate": None, "items": []}
                incompatible = True
            else:
                item_spec = schema["files"][name]["item"]
                items = []
                for index, item in enumerate(current["items"]):
                    if (len(json.dumps(item, ensure_ascii=False).encode()) <= RECORD_BYTE_LIMIT and
                            _is_valid(item, item_spec, f"work-items.json.items[{index}]")):
                        items.append(item)
                    else:
                        incompatible = True
                        if isinstance(item, dict):
                            invalid_items.append(str(
                                item.get("work_item_id") or item.get("finding_id")
                                or f"items[{index}]"))
                        else:
                            invalid_items.append(f"items[{index}]")
                candidate_spec = schema["files"][name]["candidate"]
                if not _is_valid(current["candidate"], candidate_spec, "work-items.json.candidate"):
                    if isinstance(current["candidate"], dict) and current["candidate"].get("path"):
                        invalid_items.append(f"candidate:{current['candidate']['path']}")
                    else:
                        invalid_items.append("candidate")
                    current["candidate"] = None
                    incompatible = True
                current["items"] = compact_records(items, ("work_item_id", "base_revision"), LIMITS[name])
            staged[name] = _encode_json(current)
            if incompatible:
                extra = {"dropped_records": invalid_items[:32]} if invalid_items else {}
                preserve_expected(name, data, "legacy-or-incompatible-work-items", **extra)

    for name in LIMITS:
        if name not in staged:
            staged[name] = (_encode_json({"schema_version": 1, "candidate": None, "items": []})
                            if name == "work-items.json" else b"")
        if len(staged[name]) > BYTE_LIMITS[name]:
            raise ValueError(f"compacted mode-state file remains oversized: {name}")

    legacy_total = sum(map(len, legacy.values()))
    if legacy_total > LEGACY_TOTAL_BYTE_LIMIT:
        raise ValueError(
            f"legacy mode-state evidence exceeds total cap of {LEGACY_TOTAL_BYTE_LIMIT} bytes")
    archive_destination = None
    if legacy:
        if archive_root is None:
            raise ValueError("legacy mode-state evidence requires a managed archive root")
        archive_destination = _archive_legacy(legacy, legacy_metadata, descriptor, archive_root)
    state.mkdir(mode=0o700, exist_ok=True)
    removed = []
    try:
        removals = {metadata["source_path"]: originals.get(metadata["source_path"], legacy[name])
                    for name, metadata in legacy_metadata.items()}
        for name, data in removals.items():
            path = state / name
            if _preflight_file(path, LEGACY_FILE_BYTE_LIMIT) != data:
                raise ValueError(f"legacy mode-state file changed during migration: {path}")
            path.unlink()
            removed.append((path, data))
        for name, encoded in staged.items():
            _replace_bytes(state / name, encoded)
    except BaseException:
        for name in staged:
            path = state / name
            if name in originals:
                _replace_bytes(path, originals[name])
            elif path.exists():
                path.unlink()
        for path, data in removed:
            if not path.exists():
                _replace_bytes(path, data)
        raise
    return {"state": str(state), "dropped": notes,
            "archive": str(archive_destination) if archive_destination else None}
