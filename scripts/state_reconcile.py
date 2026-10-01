"""Operator reconciliation of a managed mode-state against the real repository.

Three facts live outside the state and can silently contradict it, so the state
alone can never be trusted to describe them:

* the operator integrates a candidate with commit, fast-forward and push, then
  rewrites that history — the integrated head the record names can disappear
  from the canonical branch without anything in `mode-state` noticing;
* a finding stays `OPEN` in the findings ledger while its work item is already
  `VERIFIED`, because the finding only moves to `RESOLVED` when a later audit
  observes the fix; the queue then offers work that is already done;
* an integrated candidate keeps its worktree and branch on disk until somebody
  remembers to remove them, which is how four integrated candidates once filled
  the operator's disk.

Every operation here is fail-closed and mechanical: it asks git and the state
the same question the operator would ask, and reports what it found instead of
repairing what it did not prove.
"""

import json
import subprocess
from pathlib import Path

from mode_lifecycle import BYTE_LIMITS, LIMITS, _encode_json, _replace_bytes


class ReconcileError(ValueError):
    """A precondition for the requested operation is not proven."""


def _git(product, *arguments, check=True):
    finished = subprocess.run(
        ["git", "-C", str(product), *arguments], capture_output=True, text=True,
        timeout=120)
    if check and finished.returncode != 0:
        raise ReconcileError(
            f"git {' '.join(arguments)} falló: {(finished.stderr or finished.stdout).strip()}")
    return finished


def _read_jsonl(path):
    records = []
    if not path.is_file() or path.is_symlink():
        return records
    data = path.read_bytes()
    if len(data) > BYTE_LIMITS.get(path.name, BYTE_LIMITS["findings.jsonl"]):
        raise ReconcileError(f"{path.name} excede el límite gestionado")
    for number, line in enumerate(data.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ReconcileError(f"{path.name}:{number} no es JSON: {error}") from error
        records.append(record)
    return records


def _work_items(state):
    path = state / "work-items.json"
    if not path.is_file():
        return {"schema_version": 1, "candidate": None, "items": []}
    try:
        value = json.loads(path.read_bytes())
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ReconcileError(f"work-items.json no es JSON: {error}") from error
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        raise ReconcileError("work-items.json no tiene la forma del contrato")
    return value


def _worktree_records(product):
    """Parse `git worktree list --porcelain` into (path, branch, head) records."""
    records, current = [], None
    for line in _git(product, "worktree", "list", "--porcelain").stdout.splitlines():
        if line.startswith("worktree "):
            current = {"path": line[len("worktree "):], "branch": None, "head": None}
            records.append(current)
        elif line.startswith("HEAD ") and current is not None:
            current["head"] = line[len("HEAD "):]
        elif line.startswith("branch ") and current is not None:
            # `worktree list --porcelain` reports the full ref; the state
            # records the short branch name the candidate was created with.
            ref = line[len("branch "):]
            current["branch"] = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
    return records


def _commit_exists(product, revision):
    return _git(product, "cat-file", "-e", f"{revision}^{{commit}}",
                check=False).returncode == 0


def _is_ancestor(product, revision, target="HEAD"):
    return _git(product, "merge-base", "--is-ancestor", revision, target,
                check=False).returncode == 0


def latest_findings(state):
    """Findings keyed by id, keeping the newest record for each one."""
    findings = {}
    for record in _read_jsonl(state / "findings.jsonl"):
        finding_id = record.get("finding_id")
        if isinstance(finding_id, str) and finding_id:
            findings[finding_id] = record
    return findings


def closed_findings(state):
    """Findings the ledger still calls OPEN although their work item is VERIFIED.

    The repair cycle closes a finding by verifying it; the ledger only reaches
    `RESOLVED` when a later audit observes the same finding clean. In between,
    the two files disagree, and a queue built on the ledger alone re-audits work
    that is already done — 30 of the 42 open findings Syncify carried were in
    exactly that state.
    """
    findings = latest_findings(state)
    verified = {
        item["finding_id"] for item in _work_items(state)["items"]
        if isinstance(item, dict) and item.get("status") == "VERIFIED"
        and isinstance(item.get("finding_id"), str)}
    return sorted(finding_id for finding_id, record in findings.items()
                  if record.get("status") == "OPEN" and finding_id in verified)


def uncovered_findings(state):
    """OPEN findings at a base no handoff ever named.

    A1 stops the audit handoff from omitting them, but state written before
    that rule — or state written by hand — can still carry a finding that no
    handoff ever covered, which is how six consecutive Syncify findings had a
    work item and no repair handoff.
    """
    findings = latest_findings(state)
    handed_off = set()
    for record in _read_jsonl(state / "handoffs.jsonl"):
        for finding_id in record.get("finding_ids") or []:
            if isinstance(finding_id, str):
                handed_off.add(finding_id)
    return sorted(finding_id for finding_id, record in findings.items()
                  if record.get("status") == "OPEN" and finding_id not in handed_off)


def reconcile(product, workspace):
    """Describe what the state claims against what the repository actually has."""
    product, workspace = Path(product), Path(workspace)
    state = workspace / "mode-state"
    if not state.is_dir() or state.is_symlink():
        raise ReconcileError(f"mode-state no es un directorio real: {state}")
    candidate = _work_items(state).get("candidate")
    report = {
        "state": str(state),
        "closed_findings": closed_findings(state),
        "uncovered_findings": uncovered_findings(state),
        "limits": LIMITS,
    }
    if not isinstance(candidate, dict):
        report["candidate"] = None
        return report

    head = candidate.get("head")
    exists = isinstance(head, str) and _commit_exists(product, head)
    contained = exists and _is_ancestor(product, head)
    worktrees = {Path(entry["path"]).name: entry for entry in _worktree_records(product)}
    name = Path(candidate.get("path", "")).name
    registered = worktrees.get(name)
    report["candidate"] = {
        "status": candidate.get("status"),
        "path": candidate.get("path"),
        "branch": candidate.get("branch"),
        "head": head,
        "head_exists": exists,
        "head_in_canonical": contained,
        "worktree_present": registered is not None,
        "worktree_head": (registered or {}).get("head"),
        "branch_present": _git(product, "rev-parse", "--verify", "--quiet",
                               str(candidate.get("branch")), check=False).returncode == 0,
        "canonical_head": _git(product, "rev-parse", "HEAD").stdout.strip(),
        "canonical_clean": not _git(product, "status", "--porcelain=v1").stdout.strip(),
    }
    if candidate.get("status") == "INTEGRATED" and exists and not contained:
        report["integrated_head_rewritten"] = True
    return report


def _receipt(state, reason, detail):
    """Append the discard receipt the state already uses for anything it loses."""
    path = state / "overflows.jsonl"
    existing = _read_jsonl(path)
    number = sum(1 for record in existing if record.get("reason") == reason) + 1
    record = {
        "overflow_id": f"OV-{reason}-{number:04d}",
        "file": "work-items.json",
        "reason": reason,
        "dropped_records": detail[:32],
    }
    existing.append(record)
    _replace_bytes(path, b"".join(
        json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
        for item in existing[-LIMITS["overflows.jsonl"]:]))


def repoint(product, workspace, revision):
    """Re-anchor a recorded candidate whose integrated head no longer exists.

    Rewriting integrated history is the operator's decision, not the mode's, so
    this only moves the record onto a revision that git proves is already in the
    canonical branch, and only when the recorded one is gone. The previous value
    stays in `overflows.jsonl`: a record that changes without a trace is the same
    loss the cap receipts exist to prevent.
    """
    product, workspace = Path(product), Path(workspace)
    state = workspace / "mode-state"
    value = _work_items(state)
    candidate = value.get("candidate")
    if not isinstance(candidate, dict):
        raise ReconcileError("no hay candidata registrada que re-apuntar")
    head = candidate.get("head")
    if not isinstance(head, str) or not _commit_exists(product, head):
        raise ReconcileError(f"la cabeza registrada no existe: {head}")
    if _is_ancestor(product, head):
        raise ReconcileError(
            f"{head} sigue en la rama canónica; el registro ya es exacto y no se toca")
    if not _is_ancestor(product, revision):
        raise ReconcileError(
            f"{revision} no es ancestro del HEAD canónico; no se re-apunta historia ajena")
    if _git(product, "status", "--porcelain=v1").stdout.strip():
        raise ReconcileError("el producto canónico no está limpio")
    previous = dict(candidate)
    candidate["head"] = revision
    candidate["base_revision"] = revision
    _replace_bytes(state / "work-items.json", _encode_json(value))
    _receipt(state, "integrated-head-rewritten",
             [f"head {previous['head']} -> {revision}",
              f"status {previous.get('status')}"])
    return {"repointed": True, "from": previous["head"], "to": revision,
            "status": candidate.get("status")}


def retire(product, workspace):
    """Remove an integrated candidate's worktree and branch, or say why not.

    Removing the worktree is only safe once the work it held is provably in the
    canonical branch, so every condition is checked before anything is deleted:
    the candidate is recorded as INTEGRATED, its head is an ancestor of the
    canonical HEAD, the path is a worktree this repository registered, the
    branch is the recorded one at the recorded head, and the worktree is either
    clean or its diff still hashes to what the record says was verified. A
    candidate that fails any of them is left exactly as it is.
    """
    product, workspace = Path(product), Path(workspace)
    state = workspace / "mode-state"
    candidate = _work_items(state).get("candidate")
    if not isinstance(candidate, dict):
        raise ReconcileError("no hay candidata registrada que retirar")
    if candidate.get("status") != "INTEGRATED":
        raise ReconcileError(
            f"la candidata está en {candidate.get('status')!r}; solo se retira una INTEGRATED")

    name = Path(candidate.get("path", "")).name
    registered = next((entry for entry in _worktree_records(product)
                       if Path(entry["path"]).name == name), None)
    branch = candidate.get("branch")
    if registered is None:
        if _git(product, "show-ref", "--verify", "--quiet", str(branch),
                check=False).returncode != 0:
            return {"retired": True, "already": True,
                    "reason": "worktree y rama ya no existen"}
        _git(product, "branch", "-D", str(branch))
        return {"retired": True, "already": False, "worktree": None, "branch": branch}
    if registered.get("branch") != branch:
        raise ReconcileError(
            f"el worktree registrado apunta a {registered.get('branch')!r}, no a {branch!r}")

    head = candidate.get("head")
    if not _is_ancestor(product, head):
        raise ReconcileError(
            f"{head} no está en la rama canónica; retirar el worktree perdería trabajo sin integrar")
    if registered.get("head") != head:
        raise ReconcileError(
            f"el worktree está en {registered.get('head')!r}, no en la cabeza registrada {head}")
    path = Path(registered["path"])
    # The worktree is a linked checkout outside the product's own tree, so its
    # cleanliness is asked from inside it, not with a pathspec the product
    # repository refuses to resolve.
    dirty = _git(path, "status", "--porcelain=v1").stdout.strip()
    if dirty:
        raise ReconcileError(
            "el worktree tiene cambios sin integrar; no se retira nada")

    _git(product, "worktree", "remove", str(path))
    _git(product, "branch", "-D", str(branch))
    return {"retired": True, "already": False, "worktree": str(path), "branch": branch}