"""Operator reconciliation of a managed mode-state against the real repository.

Three facts live outside the state and can silently contradict it, so the state
alone can never be trusted to describe them:

* the operator integrates a candidate with commit, fast-forward and push, then
  rewrites that history — the integrated head the record names can disappear
  from the canonical branch without anything in `mode-state` noticing;
* a finding stays `OPEN` in the findings ledger while its work item is already
  `VERIFIED`, because the finding only moves to `RESOLVED` when a later audit
  observes the fix; the queue then offers work that is already done;
* an integrated candidate keeps its shadow (or historical worktree) on disk
  until somebody retires it; independent shadow history cannot prove product
  integration from commit ancestry alone.

Every operation here is fail-closed and mechanical: it asks git and the state
the same question the operator would ask, and reports what it found instead of
repairing what it did not prove.
"""

import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path

from mode_lifecycle import BYTE_LIMITS, LIMITS, _encode_json, _replace_bytes
import stack


class ReconcileError(ValueError):
    """A precondition for the requested operation is not proven."""


def _git(product, *arguments, check=True):
    try:
        finished = subprocess.run(
            ["git", "-C", str(product), *arguments], capture_output=True, text=True,
            timeout=120, env={**os.environ, "GIT_NO_LAZY_FETCH": "1",
                              "GIT_NO_REPLACE_OBJECTS": "1",
                              "GIT_TERMINAL_PROMPT": "0"})
    except subprocess.TimeoutExpired as error:
        raise ReconcileError("ABSTAINED: git excedió 120s; no se retira nada; "
                             "el operador debe verificar acceso al repositorio") from error
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


def anchored_findings(state):
    """Split the ledger by whether its evidence carries a located anchor.

    A finding with no anchor is not a defect — an architecture problem has no
    line — but it is a claim nobody can check, and the ratio is the honest
    measure of how much of the queue can be verified without reading the
    product. The line itself was located by the write tool, so this counts what
    the state says, not what the mode claimed.
    """
    anchored, unanchored = 0, 0
    for record in latest_findings(state).values():
        evidence = record.get("evidence")
        if isinstance(evidence, dict) and evidence.get("located") is True:
            anchored += 1
        else:
            unanchored += 1
    return {"anchored": anchored, "unanchored": unanchored}


def memory(workspace):
    """What the framework remembers about this project, and how much.

    The ledger and its index existed and were correct; nothing surfaced them,
    so "the framework applies memory to itself" was a sentence in the README
    rather than something an operator could check. The count is the honest
    measure: a project with no closed repair has nothing remembered, and that
    is zero episodes rather than a failure.
    """
    import episodes

    state = Path(workspace) / "mode-state"
    counted = episodes.stats(workspace)
    units = sorted({entry.get("unit") for entry in episodes.read_episodes(workspace)
                    if isinstance(entry.get("unit"), str) and entry["unit"]})
    signatures = set(episodes.read_index(workspace)["signatures"])
    claimed, contradicted = set(), set()
    for record in latest_findings(state).values():
        evidence = record.get("evidence")
        prior = evidence.get("prior_episode") if isinstance(evidence, dict) else None
        if not isinstance(prior, dict) or not isinstance(prior.get("unit"), str):
            continue
        claimed.add(prior["unit"])
        # The citation is recalled by the fingerprint of the quoted code, which
        # the tool puts on `evidence.fingerprint` and the mode is not allowed to
        # write. A citation naming a unit that closed a *different* defect is not
        # a deletion, and checking the unit alone would wave it through: the unit
        # is there, so is the memory, and the finding still says a repeat nobody
        # proved. Stale in that specific way it names a repair that does not
        # close the defect it is filed against, which is exactly the duplicate
        # the memory exists to stop. It is reported separately from
        # `unknown_claimed_units` because the two mean different repairs: one
        # needs the memory restored, the other needs the finding re-derived.
        if prior["unit"] in units and not episodes.citation_valid(
                workspace, prior, evidence.get("fingerprint")):
            contradicted.add(prior["unit"])
    return {
        "signatures": counted["signatures"],
        "episodes": counted["episodes"],
        "ledger_bytes": counted["ledger_bytes"],
        "units": units,
        # A finding claiming an episode the ledger no longer holds is drift
        # between two files that are supposed to agree, and it is reported
        # rather than tolerated: a repeat nobody can trace is not a repeat the
        # memory proved.
        "unknown_claimed_units": sorted(claimed - set(units)),
        "contradicted_claims": sorted(contradicted),
        "known_signatures": len(signatures),
    }


def verification_verdicts(state):
    """What each finding's verification records actually add up to.

    `verification-results.jsonl` holds one record per entrypoint a plan named,
    on purpose: a stack with a test command and a lint command produces two,
    and the mode cannot collapse them into a single friendlier answer. The
    finding-level verdict is therefore *derived*, and the plugin deliberately
    refuses to derive it — its own comment says the Host does that, which is
    true and was, until now, the only place it was true. Nothing called
    `stack.derived_verdicts`: the contract promised
    `worst-result-per-finding-and-candidate-partial-is-derived-not-written`, the
    persona told the mode the name would be derived from the records, and no
    code in this repository ever derived it. A finding verified in part had no
    verdict anywhere.

    This is that derivation, at read time and never written back. `partial` is
    reported because it is the difference between "the tests ran and said so,
    the linter could not run" and "nothing ran": both are not-PASS, and only one
    of them is progress.
    """
    records = _read_jsonl(state / "verification-results.jsonl")
    usable = [record for record in records
              if isinstance(record.get("finding_id"), str)
              and isinstance(record.get("candidate_head"), str)
              and record.get("result") in ("PASS", "BLOCKED", "FAIL")]
    derived = stack.derived_verdicts(usable)
    counts = {"PASS": 0, "BLOCKED": 0, "FAIL": 0, "PARTIAL": 0}
    unverified = []
    for (finding_id, head), group in sorted(derived.items()):
        if group["verdict"] == "PASS":
            counts["PASS"] += 1
            continue
        if group["partial"]:
            counts["PARTIAL"] += 1
        else:
            counts[group["verdict"]] += 1
        unverified.append({
            "finding_id": finding_id, "candidate_head": head,
            "verdict": "PARTIAL" if group["partial"] else group["verdict"],
            "entries": group["entries"],
        })
    return {"counts": counts, "unverified": unverified,
            "records": len(records), "usable": len(usable)}


def repeat_findings(state):
    """OPEN findings the memory had already closed by a verified repair.

    `prior_episode` is stamped by the write tool, not claimed by the mode, from
    the same fingerprint it uses to make a finding countable, so this counts
    defects that came back rather than ones an auditor called new. A non-zero
    number here is not a failure of the ledger: it is the prevention failing
    where the repair worked, which is a different defect from the first one and
    only visible because the memory is consulted.
    """
    repeats, units = 0, set()
    for record in latest_findings(state).values():
        if record.get("status") != "OPEN":
            continue
        evidence = record.get("evidence")
        if not isinstance(evidence, dict):
            continue
        prior = evidence.get("prior_episode")
        if isinstance(prior, dict) and isinstance(prior.get("unit"), str) and prior["unit"]:
            repeats += 1
            units.add(prior["unit"])
    return {"open": repeats, "prior_units": sorted(units)}


def audit_scopes(state):
    """How much of the ledger came from complete audits and how much from partial ones.

    An audit that names the whole project has to observe before it reads the
    queue, or it re-reports what the queue already had. That distinction is a
    claim until it is countable, and the handoff_id prefix carries it.
    """
    counts = {"complete": 0, "incremental": 0}
    for record in _read_jsonl(state / "handoffs.jsonl"):
        handoff_id = record.get("handoff_id")
        if not isinstance(handoff_id, str):
            continue
        if handoff_id.startswith("audit-complete-"):
            counts["complete"] += 1
        elif handoff_id.startswith("audit-"):
            counts["incremental"] += 1
    return counts


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
        "anchors": anchored_findings(state),
        "memory": memory(workspace),
        "repeats": repeat_findings(state),
        "verifications": verification_verdicts(state),
        "audit_scopes": audit_scopes(state),
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


def _abstain(reason):
    raise ReconcileError(
        "ABSTAINED: " + reason + "; decisión del operador: conservar la sombra "
        "y el recibo, revisar git diff del producto desde la base y de la "
        "sombra desde shadow-base, integrar/verificar el patch manualmente; "
        "si no se puede demostrar equivalencia exacta, decidir su custodia "
        "o retirada manual fuera de --retire")


def _entry(root, revision, path):
    """Read an exact path from a Git tree, without using a glob pathspec."""
    result = _git(root, "ls-tree", "-r", "-z", "--full-tree", revision,
                  "--", f":(literal){path}").stdout
    if not result:
        return None
    entries = [line for line in result.split("\0") if line]
    if len(entries) != 1 or "\t" not in entries[0]:
        _abstain("el árbol Git no identifica una única ruta")
    meta, name = entries[0].split("\t", 1)
    fields = meta.split()
    if name != path or len(fields) != 3 or fields[0] not in ("100644", "100755") or fields[1] != "blob":
        _abstain(f"ruta Git no regular: {path}")
    return (fields[0], fields[2])


def _safe_path(root, path):
    if (not isinstance(path, str) or not path or path.startswith("/") or
            any(part in ("", ".", "..") for part in path.split("/"))):
        _abstain("changed_paths contiene ruta insegura")
    target = root
    for part in path.split("/")[:-1]:
        target /= part
        if target.is_symlink():
            _abstain("changed_paths atraviesa un enlace simbólico")
    return root / path


def _shadow_status(shadow):
    """The entire dirty inventory (not just the paths asserted by the state)."""
    # A cone makes whole paths invisible to this inventory. `git
    # sparse-checkout set --cone` marks every out-of-cone tracked path
    # `S` (skip-worktree), and `git status` then reports nothing for them --
    # deleting such a file by hand would print ` D outside.txt`, the same
    # deletion performed by the cone prints nothing -- so the output below can
    # call a shadow clean while it still holds content. The three ignore
    # sources need no separate ask: `.gitignore`, `.git/info/exclude` and
    # `core.excludesFile` are all reported by `--ignored=matching` as `!!`,
    # which this loop abstains on.
    if _git(shadow, "config", "core.sparseCheckout",
            check=False).stdout.strip().lower() in ("true", "1", "yes", "on"):
        _abstain("la sombra tiene checkout disperso y git status omite rutas del cono")
    data = _git(shadow, "status", "--porcelain=v1", "-z", "--untracked-files=all",
                "--ignored=matching").stdout
    paths = []
    for entry in data.split("\0"):
        if not entry:
            continue
        if len(entry) < 4 or entry[2] != " " or entry[:2] not in (" M", " D", "??"):
            _abstain("la sombra contiene cambios preparados, ignorados o no previstos")
        paths.append(entry[3:])
    return paths


def _shadow_retire(product, workspace, candidate):
    """Refuse to delete a Host shadow, even when the patch is proven exactly.

    Histories are independent. A common SHA or an INTEGRATED status cannot prove
    anything, so every gate below compares each changed path's *before* tree at
    the product's recorded base with shadow-base, and its *after* tree at the
    canonical HEAD with the recorded, still-dirty candidate. The gates are kept
    and unchanged: they prove the patch reached the canonical tree. They cannot
    prove the converse, that the shadow is nothing *but* that patch, so nothing
    here deletes — see the retirement block at the end.
    """
    from onboard import checked

    try:
        product, workspace = checked(product), checked(workspace)
    except ValueError:
        _abstain("producto/workspace con enlace simbólico o ruta no absoluta")
    if (not product.is_dir() or not workspace.is_dir() or
            product.parent != workspace.parent or not (workspace / "mode-state").is_dir() or
            (workspace / "mode-state").is_symlink() or
            (workspace / "mode-state" / "work-items.json").is_symlink()):
        _abstain("producto/workspace/estado fuera del layout Host")
    digest = candidate.get("finding_ids_digest")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        _abstain("digest de hallazgos inválido")
    name = f"repair-{digest[:16]}"
    if (candidate.get("path") != f"{workspace.name}/candidates/{name}" or
            candidate.get("branch") != "candidate"):
        _abstain("ruta o rama no coinciden con la identidad Host")
    shadow = workspace / "candidates" / name
    receipt = workspace / f"{name}.receipt"
    try:
        checked(shadow)
        checked(receipt)
    except ValueError:
        _abstain("enlace simbólico en candidata o recibo")
    if (not shadow.is_dir() or not receipt.is_file() or
            receipt.stat().st_size > 256 or
            not (shadow / ".git").is_dir() or (shadow / ".git").is_symlink() or
            (shadow / ".gitmodules").exists() or (shadow / ".gitmodules").is_symlink() or
            (shadow / ".git" / "objects" / "info" / "alternates").exists() or
            (shadow / ".git" / "commondir").exists()):
        _abstain("sombra/recibo ausente o Git no independiente; no se infiere retiro anterior")
    base, head = candidate.get("base_revision"), candidate.get("head")
    if (not isinstance(base, str) or not re.fullmatch(r"[0-9a-f]{40,64}", base) or
            not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40,64}", head)):
        _abstain("revisiones de candidata inválidas")
    try:
        contents = receipt.read_text(encoding="ascii")
    except (OSError, UnicodeError):
        _abstain("recibo Host ilegible")
    if contents != f"{base}\n{digest}\n{head}\n":
        _abstain("recibo Host no corresponde exactamente al estado")
    if (_git(shadow, "rev-parse", "--absolute-git-dir").stdout.strip() != str(shadow / ".git") or
            _git(shadow, "rev-parse", "--show-toplevel").stdout.strip() != str(shadow) or
            _git(shadow, "symbolic-ref", "--short", "HEAD").stdout.strip() != "candidate" or
            _git(shadow, "rev-parse", "--verify", "refs/tags/shadow-base").stdout.strip() != head or
            _git(shadow, "rev-parse", "HEAD").stdout.strip() != head):
        _abstain("sombra derivó de la identidad recibida o contiene commits propios")
    refs = set(_git(shadow, "for-each-ref", "--format=%(refname)").stdout.splitlines())
    if refs != {"refs/heads/candidate", "refs/tags/shadow-base"}:
        _abstain("sombra contiene referencias Git ajenas al patch verificado")
    if (_git(shadow, "fsck", "--full", "--no-reflogs", "--unreachable",
             check=False).stdout.strip()):
        _abstain("sombra contiene objetos Git sin integrar que la retirada borraría")
    worktrees = _git(shadow, "worktree", "list", "--porcelain").stdout.count("worktree ")
    if worktrees != 1:
        _abstain("sombra contiene worktrees Git registrados además del principal")
    canonical = _git(product, "rev-parse", "HEAD").stdout.strip()
    if (not _is_ancestor(product, base, canonical) or
            _git(product, "rev-parse", "--show-toplevel").stdout.strip() != str(product) or
            _git(product, "status", "--porcelain=v1", "--untracked-files=all").stdout):
        _abstain("producto no está limpio o su base no pertenece a la historia canónica")
    paths = candidate.get("changed_paths")
    digest_recorded = candidate.get("candidate_diff_digest")
    if (not isinstance(paths, list) or not paths or len(paths) != len(set(paths)) or
            not isinstance(digest_recorded, str) or
            not re.fullmatch(r"[0-9a-f]{64}", digest_recorded)):
        _abstain("no existe huella exacta del patch registrado")
    if set(_shadow_status(shadow)) != set(paths):
        _abstain("sombra limpia o su inventario difiere del patch registrado")
    fingerprint = hashlib.sha256()
    for path in sorted(paths, key=os.fsencode):
        target = _safe_path(shadow, path)
        raw = os.fsencode(path)
        fingerprint.update(len(raw).to_bytes(8, "big"))
        fingerprint.update(raw)
        try:
            mode = target.lstat().st_mode
        except FileNotFoundError:
            fingerprint.update(b"D")
            after = None
        else:
            if not stat.S_ISREG(mode):
                _abstain(f"la candidata contiene entrada no regular: {path}")
            data = target.read_bytes()
            fingerprint.update(b"F")
            fingerprint.update(len(data).to_bytes(8, "big"))
            fingerprint.update(data)
            after = ("100755" if mode & 0o111 else "100644",
                     _git(shadow, "hash-object", "--no-filters", str(target)).stdout.strip())
        before = _entry(shadow, head, path)
        product_before = _entry(product, base, path)
        product_after = _entry(product, canonical, path)
        if before != product_before or after != product_after or before == after:
            _abstain(f"no se prueba la integración exacta del patch en {path}")
    if fingerprint.hexdigest() != digest_recorded:
        _abstain("la huella actual difiere del patch verificado")

    if (_git(product, "rev-parse", "HEAD").stdout.strip() != canonical or
            _git(product, "status", "--porcelain=v1", "--untracked-files=all").stdout or
            set(_shadow_status(shadow)) != set(paths)):
        _abstain("producto o sombra cambiaron durante la comprobación")
    # Reject symlinks and mounted subtrees, even though retirement abstains.
    root_device = shadow.stat().st_dev
    for directory, names, files in os.walk(shadow, followlinks=False):
        for name in names + files:
            member = Path(directory) / name
            mode = member.lstat().st_mode
            if (not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)) or
                    member.lstat().st_dev != root_device or os.path.ismount(member)):
                _abstain("sombra contiene enlace, entrada especial o montaje")
    # ------------------------------------------------------------------
    # Retirada automática DESHABILITADA (2026-10-11).
    #
    # Todas las puertas de arriba se mantienen: demuestran que el patch
    # verificado está en el árbol canónico. Lo que ninguna puede demostrar es
    # lo contrario, que la sombra no contiene nada más, y el borrado automático
    # se llevaría también eso:
    #   * `git status` nunca inventa el contenido de `.git/`: un archivo en
    #     `.git/operator-notes` o `.git/lfs/objects/private` se borraría con
    #     `shutil.rmtree` sin que ninguna puerta lo viera.
    #   * la inspección de `git fsck` miraba solo `stdout` con `check=False`:
    #     los códigos de salida no se leían y `GIT_OBJECT_DIRECTORY` en el
    #     entorno puede ocultar un objeto local.
    #   * los flags `skip-worktree`/`assume-unchanged` esconden de `git status`
    #     ediciones sobre un archivo trackeado, así que esas ediciones privadas
    #     de un trackeado también se borrarían.
    #   * las comparaciones finales miran hashes de contenido, pero el borrado
    #     venía después: una edición concurrente, o un archivo que aparece tras
    #     el walk final, se pierde; `shutil.rmtree` no es atómico y puede borrar
    #     en parte antes de fallar.
    # La retirada queda aquí como decisión manual del operador.
    # ------------------------------------------------------------------
    _abstain("la sombra no está inventariada como conjunto de contenido exclusivo y "
             "desechable —`git status` no ve `.git/` ni los flags `skip-worktree`/"
             "`assume-unchanged`— y retirarla automáticamente podría borrar contenido "
             "sin dueño; la retirada es una decisión manual del operador: listar a mano "
             "la sombra y su `.git/` (por ejemplo con `du -sh` y `find`) y borrarla solo "
             "cuando se confirme que no hay nada que conservar")


def retire(product, workspace):
    """Check recorded integration; never automatically delete a candidate."""
    product, workspace = Path(product), Path(workspace)
    state = workspace / "mode-state"
    candidate = _work_items(state).get("candidate")
    if not isinstance(candidate, dict):
        raise ReconcileError("no hay candidata registrada que retirar")
    if candidate.get("status") != "INTEGRATED":
        raise ReconcileError(
            f"la candidata está en {candidate.get('status')!r}; solo se retira una INTEGRATED")

    recorded_path = candidate.get("path")
    if not isinstance(recorded_path, str):
        _abstain("ruta registrada inválida")
    # Dispatch by exact namespace, not a candidate basename. A legacy worktree
    # with the same suffix cannot be adopted as a shadow (or vice versa).
    if recorded_path.startswith(f"{workspace.name}/candidates/"):
        return _shadow_retire(product, workspace, candidate)

    name = Path(recorded_path).name
    if (recorded_path != name or not re.fullmatch(r"[A-Za-z0-9_.-]+-repair-[0-9a-f]{16}", name) or
            not isinstance(candidate.get("branch"), str) or
            not re.fullmatch(r"dsh/repair-[0-9a-f]{16}", candidate["branch"])):
        _abstain("identidad de worktree legacy inválida")
    path = product.parent / name
    if path.is_symlink() or product.is_symlink() or workspace.is_symlink():
        _abstain("enlace simbólico en ruta legacy")
    branch = candidate["branch"]
    registered = next((entry for entry in _worktree_records(product)
                       if entry["path"] == str(path)), None)
    if registered is None:
        if (not path.exists() and
                _git(product, "show-ref", "--verify", "--quiet",
                     f"refs/heads/{branch}", check=False).returncode != 0):
            return {"retired": True, "already": True,
                    "reason": "worktree y rama ya no existen"}
        _abstain("rama o ruta legacy existe sin worktree registrado")
    if registered.get("branch") != branch:
        raise ReconcileError(
            f"el worktree registrado apunta a {registered.get('branch')!r}, no a {branch!r}")
    head = candidate.get("head")
    if (not isinstance(head, str) or not _is_ancestor(product, head)):
        raise ReconcileError(
            f"{head} no está en la rama canónica; retirar el worktree perdería trabajo sin integrar")
    if registered.get("head") != head or _git(product, "rev-parse", f"refs/heads/{branch}").stdout.strip() != head:
        raise ReconcileError("la rama/worktree difiere de la cabeza registrada")
    if _git(product, "status", "--porcelain=v1", "--untracked-files=all").stdout:
        _abstain("producto canónico sucio")
    if _git(path, "status", "--porcelain=v1", "--untracked-files=all").stdout.strip():
        raise ReconcileError("el worktree tiene cambios sin integrar; no se retira nada")
    raise ReconcileError(
        "ABSTAINED: el worktree legacy y su metadata Git pueden contener "
        "archivos ignorados o privados que git status no inventaría; conservar "
        "worktree y rama para revisión y retirada manual del operador")
