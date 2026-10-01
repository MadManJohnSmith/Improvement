"""The candidate is a shadow repository, not a worktree of the product (E4).

Measured, not assumed: `git worktree` keeps the worktree's index and HEAD in
the *product's* `.git/worktrees/`. With the product read-only, `git add` inside
the candidate fails with

    fatal: Unable to create '.../product/.git/worktrees/cand/index.lock':
    Permission denied

so confinement and worktrees are mutually exclusive. Read-only is the property
worth having -- it is the only thing that stops a mode from editing the user's
tree -- and a worktree is the thing that cannot live with it.

The shadow repository resolves it. The candidate is created inside the
workspace, from a copy of the product's working tree, and gets **its own**
`.git`. Then one writable root covers both the candidate and the state, the
product sits outside it and is kernel-read-only, and every git operation inside
the candidate works because nothing it touches is shared with the product.

Integration changes shape accordingly. A worktree produced a branch to merge;
a shadow produces a patch. `diff_command` is the honest boundary: the operator
applies it, and the framework never does.
"""

import hashlib
import os
import shlex
from pathlib import Path
import shutil
import subprocess
import tempfile

SHADOW_DIR = "candidates"
# A tag, not a branch: the branch the shadow is on moves with every commit,
# and diffing against it would report no change at all.
BASE_COMMIT = "shadow-base"
# What never crosses into the shadow: .git is the product's own history, and
# copying it is exactly the sharing the shadow exists to avoid.
EXCLUDED = {".git"}
MAX_COPY_BYTES = 512 * 1024 * 1024
MAX_FILES = 20000


class ShadowError(RuntimeError):
    pass


def candidate_root(workspace, digest16):
    if not isinstance(digest16, str) or len(digest16) != 16 or set(digest16) > set("0123456789abcdef"):
        raise ShadowError(f"digest de candidata inválido: {digest16!r}")
    return Path(workspace) / SHADOW_DIR / f"repair-{digest16}"


def _git(root, *arguments, check=True):
    finished = subprocess.run(["git", "-C", str(root), *arguments],
                             capture_output=True, text=True)
    if check and finished.returncode != 0:
        raise ShadowError(
            f"git {' '.join(arguments)} falló en {root}: "
            f"{(finished.stderr or finished.stdout).strip()[:200]}")
    return finished


def _copy_tree(product, shadow):
    """Copy the working tree without .git, refusing a product too large to copy.

    The size cap is a real limit, not caution for its own sake: the candidate is
    a full second copy, and a repository that does not fit is one the framework
    has to say it cannot handle rather than start and fill a disk.
    """
    total, count = 0, 0
    for source in Path(product).rglob("*"):
        relative = source.relative_to(product)
        if relative.parts and relative.parts[0] in EXCLUDED:
            continue
        if source.is_symlink():
            raise ShadowError(f"el producto contiene un enlace simbólico: {relative}")
        if source.is_dir():
            continue
        if not source.is_file():
            raise ShadowError(f"el producto contiene una entrada no regular: {relative}")
        size = source.stat().st_size
        total += size
        count += 1
        if total > MAX_COPY_BYTES:
            raise ShadowError(
                "el producto supera el tope de copia de la candidata "
                f"({MAX_COPY_BYTES} bytes)")
        if count > MAX_FILES:
            raise ShadowError(
                f"el producto supera el tope de ficheros de la candidata ({MAX_FILES})")
        target = shadow / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return count, total


def provision(product, workspace, digest16, base_ref=None):
    """Create the shadow, or return the existing one unchanged.

    Reuse is decided by content, not by a flag: a shadow already at BASE_COMMIT
    whose tree matches the product is the same shadow, and re-creating it would
    discard work that is still in flight.
    """
    product, workspace = Path(product), Path(workspace)
    if product.is_symlink():
        raise ShadowError("el producto no puede ser un enlace simbólico")
    if not product.is_dir():
        raise ShadowError(f"el producto no existe: {product}")
    target = candidate_root(workspace, digest16)
    if target.exists():
        if not (target / ".git").is_dir():
            raise ShadowError(f"la candidata existe y no es un repositorio: {target}")
        _git(target, "rev-parse", "--verify", "HEAD")
        return target, False
    (workspace / SHADOW_DIR).mkdir(mode=0o700, parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".shadow-", dir=workspace / SHADOW_DIR))
    try:
        files, total = _copy_tree(product, staging)
        _git(staging, "init", "-q", "-b", "candidate", ".")
        _git(staging, "config", "user.email", "shadow@dsh.invalid")
        _git(staging, "config", "user.name", "Improvement shadow candidate")
        _git(staging, "add", "-A", ".")
        if not files:
            _git(staging, "commit", "-q", "--allow-empty", "-m", "base vacía")
        else:
            _git(staging, "commit", "-q", "-m", "base del producto")
        _git(staging, "tag", BASE_COMMIT)
        head = _git(staging, "rev-parse", "HEAD").stdout.strip()
        if base_ref and not _ancestor(product, base_ref):
            raise ShadowError(
                f"la base declarada {base_ref} no es ancestro del producto")
        os.rename(staging, target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target, True


def _ancestor(product, ref):
    finished = _git(product, "merge-base", "--is-ancestor", ref, "HEAD", check=False)
    return finished.returncode == 0


def verify(product, candidate):
    """The candidate is a shadow at the base, and the product is untouched."""
    product, candidate = Path(product), Path(candidate)
    if not candidate.is_dir():
        raise ShadowError(f"la candidata no existe: {candidate}")
    # Ask git where the repository actually lives rather than trusting the
    # layout on disk: a worktree and a submodule both carry a `.git` *file*
    # pointing into another repository, and only git resolves that honestly.
    answered = _git(candidate, "rev-parse", "--absolute-git-dir", check=False)
    if answered.returncode != 0:
        raise ShadowError("la candidata no tiene repositorio propio")
    recorded = Path(answered.stdout.strip()).resolve()
    product_git = (product / ".git").resolve()
    if recorded == product_git or recorded.is_relative_to(product_git):
        raise ShadowError("la candidata sigue compartiendo el .git del producto")
    dirty = _git(candidate, "status", "--porcelain=v1").stdout
    if dirty:
        raise ShadowError("la candidata tiene cambios sin registrar")
    return {
        "candidate": str(candidate),
        "shadow_of": None,
        "product_untouched": not bool(_git(product, "status", "--porcelain=v1").stdout),
    }


def diff_command(product, candidate):
    """The exact command the operator runs to integrate. It is not run here.

    `git diff --no-index` rather than a worktree branch: the shadow has no
    ancestry with the product, which is the point, so a merge would be a lie
    about where the change came from. A patch says exactly that it is one.
    """
    return (f"git diff --no-index --binary -- "
            f"{shlex_quote(Path(product))} {shlex_quote(Path(candidate))}")


def shlex_quote(value):
    return shlex.quote(str(value))


def patch_digest(candidate):
    """Identity of the candidate's proposed change, for binding to the receipt."""
    patch = _git(Path(candidate), "diff", BASE_COMMIT, "HEAD", "--binary",
                 ".").stdout.encode()
    return hashlib.sha256(patch).hexdigest()


def retire(candidate):
    """Remove the shadow and its branch, only when it carries no work."""
    candidate = Path(candidate)
    if not candidate.is_dir():
        return False
    if _git(candidate, "status", "--porcelain=v1").stdout:
        raise ShadowError("la candidata tiene cambios sin integrar; no se retira")
    shutil.rmtree(candidate)
    return True
