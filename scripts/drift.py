"""The deterministic doc-drift engine: documents and code, compared by math.

`evaluate(config, base_rev, target_rev)` is the single public seam. The CLI
commands, `bootstrap.py`, the `workflow.py` gates and the DSH plugin all
consume the same boundary, so a verdict is never a matter of who asked.

Purity contract (ADR 0001): no `mtime`, no commit dates, no wall clock. Every
verdict is a pure function of the normalized syntax trees and the change
topology between `base_rev` and `target_rev`. Running the same pair twice
produces byte-identical JSON — the suite proves it, not the docstring.

Filter 1 pins public contracts. For each symbol a document claims, the engine
hashes the normalized signature — name, parameters, annotations, return,
visibility — with every comment, docstring and body stripped. Python goes
through `ast`; TypeScript, JavaScript, Rust and Go go through a lexical
extractor with a string/comment state machine and brace balancing. Reference
checking is baseline-independent: a path or pinned block a document cites must
resolve in the target tree, whatever the baseline says (ADR 0002).

Filter 2 judges behaviour beneath an unchanged signature. Semantic body
tokens — whitespace-insensitive by construction, so a mass re-indent scores
zero — feed the normalized churn ratio (`difflib`, rounded to 4 decimals), a
64-component MinHash over 3-shingles, and the Shannon entropy of the change
dispersion across the subsystem a document tracks. Over a threshold or
dispersed wide enough, that is `SOURCE_DRIFT`; beneath them but nonzero,
`NON_GOVERNING_CHANGE`; silent, `CURRENT`.

State lives in `<workspace>/drift/`, never inside the product tree and never
inside this canonical tree (`tests/test_canonical_tree_holds_no_run_artifacts.py`
enforces the latter by name). `doc-baseline.json` is written only through
`pin_baseline`, atomically; `repin` is Host/Harness authority, not an agent's.
The baseline stores each tracked symbol's body tokens so churn works against a
pinned baseline without re-reading the base revision.

The lexical extractors are deliberately best-effort (ADR 0001): a declaration
shape they do not model is skipped, never guessed. Missing a symbol delays a
verdict; inventing one fabricates it.
"""

import argparse
import ast
import difflib
import hashlib
import io
import json
import math
import os
import posixpath
import re
import subprocess
import sys
import tokenize
from pathlib import Path

SCHEMA_VERSION = 1

DEFAULT_THRESHOLDS = {
    "body_churn_ratio": 0.35,
    "entropy_limit": 2.5,
    "min_entropy_tokens": 20,
}

LSH_COMPONENTS = 64

# Directories that are never product content: framework infrastructure or
# run-artifact homes the canonical-tree guard names. Mirrors the product's
# own vocabulary so a candidate or a run directory inside the evaluated tree
# is never read as source.
SKIP_DIRS = {
    ".git", ".zcode", "__pycache__", "node_modules", ".dsh", ".dsh-managed",
    "candidates", "runs", "reports", "mode-state", "metrics", "decisions",
    "evidence", "observations", "screenshots", "campaign",
}

# Extensions a document reference may point at and be worth checking. A
# reference to anything else (binaries, images) is not this engine's claim.
REF_EXTENSIONS = {
    ".md", ".py", ".ts", ".tsx", ".js", ".mjs", ".rs", ".go",
    ".json", ".yml", ".yaml", ".sh", ".toml", ".txt",
}

CONFIG_KEYS = {
    "repo_root", "workspace", "docs", "thresholds", "rules",
    "generation_id", "accepted_generation",
}


class DriftError(ValueError):
    """Raised for a configuration or input the engine refuses to guess about."""


# --------------------------------------------------------------------------
# Git trees: one read-only view over either a revision or the working tree.
# --------------------------------------------------------------------------


def _git(repo_root, *args):
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True, check=False)
    if result.returncode != 0:
        raise DriftError(
            "git %s failed in %s: %s"
            % (" ".join(args), repo_root,
               result.stderr.decode("utf-8", "replace").strip()))
    return result.stdout


def _resolve_rev(repo_root, rev):
    return _git(repo_root, "rev-parse", rev).decode("utf-8").strip()


class _Tree:
    """A read-only file view: a git revision or the working tree."""

    def __init__(self, files):
        # path -> text, decoded with errors='replace' so a stray byte in the
        # product can change a hash's input but never crash a verdict.
        self._files = files

    def read(self, path):
        return self._files.get(path)

    def has(self, path):
        return path in self._files

    def paths(self):
        return set(self._files)


def _revision_tree(repo_root, rev):
    names = _git(repo_root, "ls-tree", "-r", "--name-only", "-z", rev)
    files = {}
    for name in names.decode("utf-8", "replace").split("\0"):
        if not name:
            continue
        raw = subprocess.run(
            ["git", "-C", str(repo_root), "show", "%s:%s" % (rev, name)],
            capture_output=True, check=False)
        # A path that ls-tree listed but show cannot return is a submodule or
        # a race; an unreadable entry is absent, never a guessed empty file.
        if raw.returncode == 0:
            files[name] = raw.stdout.decode("utf-8", "replace")
    return _Tree(files)


def _worktree_tree(repo_root):
    files = {}
    root = Path(repo_root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for filename in sorted(filenames):
            path = (Path(dirpath) / filename).relative_to(root).as_posix()
            try:
                files[path] = (Path(dirpath) / filename).read_bytes().decode(
                    "utf-8", "replace")
            except OSError:
                continue
    return _Tree(files)


def _target_tree(repo_root, target_rev):
    if target_rev is None or target_rev == "WORKTREE":
        return _worktree_tree(repo_root)
    return _revision_tree(repo_root, target_rev)


# --------------------------------------------------------------------------
# Normalization primitives: everything hashes normalized text, never bytes.
# --------------------------------------------------------------------------


def _normalize_ws(text):
    return re.sub(r"\s+", " ", text).strip()


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Python extractor: `ast`, public names, bodies and docstrings discarded.
# --------------------------------------------------------------------------


def _python_param(arg, default):
    piece = arg.arg
    if arg.annotation is not None:
        piece += ": " + ast.unparse(arg.annotation)
    if default is not None:
        piece += " = " + ast.unparse(default)
    return piece


def _python_params(args):
    parts = []
    pos_defaults = list(args.defaults)
    pos_args = list(args.posonlyargs) + list(args.args)
    first_default = len(pos_args) - len(pos_defaults)

    for index, arg in enumerate(pos_args):
        default = pos_defaults[index - first_default] \
            if index >= first_default else None
        parts.append(_python_param(arg, default))
    if args.posonlyargs:
        parts.append("/")
    if args.vararg or args.kwonlyargs:
        parts.append("*")
    if args.vararg:
        parts.append(_python_param(args.vararg, None))
    for index, arg in enumerate(args.kwonlyargs):
        parts.append(_python_param(arg, args.kw_defaults[index]))
    if args.kwarg is not None:
        keyword = "**" + args.kwarg.arg
        if args.kwarg.annotation is not None:
            keyword += ": " + ast.unparse(args.kwarg.annotation)
        parts.append(keyword)
    return ", ".join(parts)


def _python_function_signature(node, name):
    lines = []
    for decorator in node.decorator_list:
        lines.append("@" + ast.unparse(decorator))
    keyword = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    signature = "%s %s(%s)" % (keyword, name, _python_params(node.args))
    if node.returns is not None:
        signature += " -> " + ast.unparse(node.returns)
    lines.append(signature)
    return "\n".join(lines)


def _python_all_names(tree):
    names = set()
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if (isinstance(target, ast.Name) and target.id == "__all__"
                    and isinstance(node.value, (ast.List, ast.Tuple))):
                for element in node.value.elts:
                    if (isinstance(element, ast.Constant)
                            and isinstance(element.value, str)):
                        names.add(element.value)
    return names


def _python_symbols(source):
    """symbol_id -> normalized signature for one Python module."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return {}
    exported = _python_all_names(tree)

    def public(name):
        return not name.startswith("_") or name in exported

    symbols = {}

    def collect_function(node, qualified):
        if public(node.name):
            symbols[qualified] = _python_function_signature(node, qualified)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            collect_function(node, node.name)
        elif isinstance(node, ast.ClassDef):
            if public(node.name):
                bases = ", ".join(
                    [ast.unparse(base) for base in node.bases]
                    + ["%s=%s" % (kw.arg, ast.unparse(kw.value))
                       for kw in node.keywords if kw.arg is not None])
                symbols[node.name] = (
                    "class %s(%s)" % (node.name, bases)
                    if bases else "class %s" % node.name)
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        collect_function(child, "%s.%s" % (node.name, child.name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if public(node.target.id):
                symbols[node.target.id] = "%s: %s" % (
                    node.target.id, ast.unparse(node.annotation))
    return symbols


# --------------------------------------------------------------------------
# Filter 2 tokenization: semantic body tokens, immune to re-indentation.
# --------------------------------------------------------------------------


_DROP_TOKEN_TYPES = frozenset({
    tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
    tokenize.DEDENT, tokenize.ENDMARKER,
})
_FSTRING_TOKEN_TYPES = frozenset({
    getattr(tokenize, "FSTRING_START", -1),
    getattr(tokenize, "FSTRING_MIDDLE", -2),
    getattr(tokenize, "FSTRING_END", -3),
})


def _string_bucket(text):
    body = text
    if len(body) >= 2 and body[0] == body[-1] and body[0] in "'\"":
        body = body[1:-1]
    return "s" if len(body) <= 24 else "S"


def _python_body_tokens(text):
    """Semantic tokens of a function segment: comments, whitespace,
    docstrings and trivial literals collapsed; everything else literal."""
    try:
        stripped = "\n".join(line.strip() for line in text.split("\n"))
        tokens = []
        for token in tokenize.generate_tokens(io.StringIO(stripped).readline):
            if token.type in _DROP_TOKEN_TYPES:
                continue
            if token.type == tokenize.STRING:
                tokens.append(_string_bucket(token.string))
            elif token.type == tokenize.NUMBER:
                tokens.append("n")
            elif token.type in _FSTRING_TOKEN_TYPES:
                tokens.append("s")
            else:
                tokens.append(token.string)
        return tokens
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        return []


def _python_docstring_range(node):
    first = node.body[0] if node.body else None
    if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)):
        return first.lineno, first.end_lineno
    return None


def _python_semantic_tokens(source):
    """symbol_id -> {"public": bool, "tokens": [...]} for functions/methods."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return {}
    exported = _python_all_names(tree)
    lines = source.split("\n")

    def body_tokens(node):
        start = node.lineno - 1
        end = node.end_lineno
        docstring = _python_docstring_range(node)
        segments = []
        if docstring:
            if docstring[0] - 1 > start:
                segments.append((start, docstring[0] - 1))
            if end > docstring[1]:
                segments.append((docstring[1], end))
        else:
            segments.append((start, end))
        text = "\n".join(
            "\n".join(lines[a:b]) for a, b in segments if b > a)
        return _python_body_tokens(text)

    def public(name):
        return not name.startswith("_") or name in exported

    units = {}

    def collect(node, qualified, is_public):
        units[qualified] = {
            "public": is_public,
            "tokens": body_tokens(node),
        }

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            collect(node, node.name, public(node.name))
        elif isinstance(node, ast.ClassDef):
            class_public = public(node.name)
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    collect(child, "%s.%s" % (node.name, child.name),
                            class_public and public(child.name))
    return units


# --------------------------------------------------------------------------
# Lexical extractor: comment/string state machine plus brace balancing for
# TypeScript, JavaScript, Rust and Go. Best-effort by design (ADR 0001).
# --------------------------------------------------------------------------


def _rust_raw_at(text, index):
    """True when text[index:] starts a Rust raw (or byte-raw) string literal."""
    if text[index] == "b":
        index += 1
        if index >= len(text) or text[index] != "r":
            return False
    if text[index] != "r":
        return False
    index += 1
    if index >= len(text):
        return False
    if text[index] == '"':
        return True
    return text[index] == "#" and index + 1 < len(text) \
        and text[index + 1] == '"'


def _rust_raw_end(text, index):
    start = index
    if text[start] == "b":
        start += 1
    start += 1  # the r
    hashes = 0
    while start + hashes < len(text) and text[start + hashes] == "#":
        hashes += 1
    closing = '"%s' % ("#" * hashes)
    end = text.find(closing, start + hashes + 1)
    return len(text) if end == -1 else end + len(closing)


def _strip_lexical(text, ext):
    """Comment-free source with every string literal replaced by "S"."""
    if ext in ("ts", "tsx", "js", "mjs"):
        quotes = {'"': True, "'": True, "`": False}
    elif ext == "go":
        quotes = {'"': True, "`": False, "'": True}
    else:  # rust
        quotes = {'"': True, "'": True}

    out = []
    index, size = 0, len(text)
    while index < size:
        char = text[index]
        two = text[index:index + 2]
        if ext == "rs" and char in "rb" and _rust_raw_at(text, index):
            out.append('"S"')
            index = _rust_raw_end(text, index)
            continue
        if two == "//":
            end = text.find("\n", index)
            index = size if end == -1 else end  # keep the newline
            continue
        if two == "/*":
            end = text.find("*/", index + 2)
            index = size if end == -1 else end + 2
            out.append(" ")
            continue
        if char in quotes:
            allow_escape = quotes[char]
            index += 1
            while index < size:
                if text[index] == "\\" and allow_escape:
                    index += 2
                    continue
                if text[index] == char:
                    index += 1
                    break
                # A newline inside a "..." is a syntax error we normalize
                # away rather than swallow the rest of the file.
                if text[index] == "\n" and char != "`":
                    break
                index += 1
            out.append('"S"')
            continue
        # A Rust apostrophe is usually a lifetime, not a char literal; only
        # a well-formed 'c' or '\\n' is a literal, anything else is code.
        if ext == "rs" and char == "'":
            match = _CHAR_LITERAL.match(text, index)
            if match:
                out.append('"S"')
                index = match.end()
                continue
            out.append(char)
            index += 1
            continue
        out.append(char)
        index += 1
    return "".join(out)


_CHAR_LITERAL = re.compile(r"'([^'\\\n]|\\.)'")


def _find_body(text, start):
    """Index of the declaration's `{` at parenthesis depth zero, or None when
    a `;` ends the declaration first."""
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "{" and depth == 0:
            return index
        elif char == ";" and depth == 0:
            return None
    return None


def _match_balanced(text, start):
    """Index of the `}` matching the `{` at start, or None."""
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _statement_end(text, start):
    candidates = [index for index in (text.find(";", start),
                                      text.find("\n", start)) if index != -1]
    return min(candidates) if candidates else len(text)


_DECL_EXPORT = r"(export\s+)?(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?"
_DECL_RE = {
    "ts": re.compile(
        r"(?m)^[ \t]*%s(?:function\s*\*?\s*([A-Za-z_$][\w$]*)"
        r"|(class|interface|enum)\s+([A-Za-z_$][\w$]*)"
        r"|type\s+([A-Za-z_$][\w$]*)\s*[={;]"
        r"|const\s+([A-Za-z_$][\w$]*))" % _DECL_EXPORT),
    "rs": re.compile(
        r"(?m)^[ \t]*(pub\s+)?(?:\([^)]*\)\s+)?"
        r"(?:(?:async\s+)?fn\s+([A-Za-z_][\w]*)"
        r"|(struct|enum|trait|type|union)\s+([A-Za-z_][\w]*))"),
    "go": re.compile(
        r"(?m)^[ \t]*(?:func\s+(?:\([^)]*\)\s*)?([A-Za-z_][\w]*)"
        r"|type\s+([A-Za-z_][\w]*)\s+(struct|interface)\b)"),
}
_DECL_RE["tsx"] = _DECL_RE["ts"]
_DECL_RE["js"] = _DECL_RE["ts"]
_DECL_RE["mjs"] = _DECL_RE["ts"]
_TS_EXTS = ("ts", "tsx", "js", "mjs")

_SNIPPET_LANGS = {
    "python": "py", "py": "py", "typescript": "ts", "ts": "ts",
    "tsx": "tsx", "javascript": "js", "js": "js", "mjs": "mjs",
    "rust": "rs", "rs": "rs", "go": "go",
}


def _lexical_scan(source, ext):
    """(public signatures, semantic units) over comment-free text.

    `units` maps symbol_id -> (body_text, is_public) and covers private
    declarations too: Filter 2 needs their churn even though Filter 1 never
    pins them.
    """
    stripped = _strip_lexical(source, ext)
    pattern = _DECL_RE[ext]
    symbols = {}
    units = {}
    for match in pattern.finditer(stripped):
        if ext in _TS_EXTS:
            _ts_symbol(stripped, match, symbols, units)
        elif ext == "rs":
            _rust_symbol(stripped, match, symbols, units)
        else:
            _go_symbol(stripped, match, symbols, units)
    return symbols, units


def _ts_symbol(stripped, match, symbols, units):
    is_public = bool(match.group(1))
    fn_name, type_kw, type_name = match.group(2), match.group(3), match.group(4)
    alias_name, const_name = match.group(5), match.group(6)
    if fn_name or type_kw == "class":
        body_open = _find_body(stripped, match.end())
        if body_open is None:
            return
        close = _match_balanced(stripped, body_open)
        if close is None:
            return
        signature = _normalize_ws(stripped[match.start():body_open]) + " {}"
        # A class's methods carry their own units; the stripped shell is not
        # a body. An interface's or enum's body is its contract.
        body = "" if type_kw == "class" else stripped[body_open + 1:close]
        name = fn_name or type_name
        if is_public:
            symbols[name] = signature
        units[name] = (body, is_public)
    elif type_kw in ("interface", "enum"):
        body_open = _find_body(stripped, match.end())
        if body_open is None:
            return
        close = _match_balanced(stripped, body_open)
        if close is None:
            return
        if is_public:
            symbols[type_name] = _normalize_ws(
                stripped[match.start():close + 1])
        units[type_name] = (stripped[body_open + 1:close], is_public)
    elif alias_name:
        body_open = _find_body(stripped, match.end())
        if body_open is None:
            end = _statement_end(stripped, match.end())
            if is_public:
                symbols[alias_name] = _normalize_ws(
                    stripped[match.start():end])
            units[alias_name] = ("", is_public)
            return
        close = _match_balanced(stripped, body_open)
        if close is None:
            return
        if is_public:
            symbols[alias_name] = _normalize_ws(
                stripped[match.start():close + 1])
        units[alias_name] = (stripped[body_open + 1:close], is_public)
    elif const_name:
        # The binding name is the contract; the initializer is implementation.
        if is_public:
            symbols[const_name] = "export const %s" % const_name
        units[const_name] = ("", is_public)


def _rust_symbol(stripped, match, symbols, units):
    is_public = bool(match.group(1))
    fn_name, type_kw, type_name = match.group(2), match.group(3), match.group(4)
    if fn_name:
        body_open = _find_body(stripped, match.end())
        if body_open is None:
            return
        close = _match_balanced(stripped, body_open)
        if close is None:
            return
        if is_public:
            symbols[fn_name] = _normalize_ws(
                stripped[match.start():body_open]) + " {}"
        units[fn_name] = (stripped[body_open + 1:close], is_public)
    else:
        body_open = _find_body(stripped, match.end())
        if body_open is None:
            end = _statement_end(stripped, match.end())
            if is_public:
                symbols[type_name] = _normalize_ws(
                    stripped[match.start():end])
            units[type_name] = ("", is_public)
            return
        close = _match_balanced(stripped, body_open)
        if close is None:
            return
        if is_public:
            symbols[type_name] = _normalize_ws(
                stripped[match.start():close + 1])
        units[type_name] = (stripped[body_open + 1:close], is_public)


def _go_symbol(stripped, match, symbols, units):
    func_name, type_name, type_kw = match.group(1), match.group(2), match.group(3)
    if func_name:
        is_public = func_name[:1].isupper()
        body_open = _find_body(stripped, match.end())
        if body_open is None:
            return
        close = _match_balanced(stripped, body_open)
        if close is None:
            return
        header = _normalize_ws(stripped[match.start():body_open])
        if is_public:
            receiver = re.search(
                r"func\s+\([^)]*?([A-Za-z_][\w]*)\s*\)", header)
            symbol_id = ("%s.%s" % (receiver.group(1), func_name)
                         if receiver else func_name)
            symbols[symbol_id] = header + " {}"
        units[func_name] = (stripped[body_open + 1:close], is_public)
        return
    is_public = type_name[:1].isupper()
    body_open = _find_body(stripped, match.end())
    if body_open is None:
        return
    close = _match_balanced(stripped, body_open)
    if close is None:
        return
    if is_public:
        symbols[type_name] = _normalize_ws(stripped[match.start():close + 1])
    units[type_name] = (stripped[body_open + 1:close], is_public)


def _lexical_symbols(source, ext):
    """symbol_id -> normalized signature; public declarations only."""
    symbols, _ = _lexical_scan(source, ext)
    return symbols


def _lexical_body_tokens(body):
    return re.findall(r"\w+|[^\w\s]", body)


def extract_symbols(path, source):
    """Dispatch on extension; unknown extensions yield no symbols."""
    ext = os.path.splitext(path)[1].lstrip(".")
    if ext == "py":
        return _python_symbols(source)
    if ext in _DECL_RE:
        return _lexical_symbols(source, ext)
    return {}


def extract_semantic_tokens(path, source):
    """symbol_id -> {"public": bool, "tokens": [...]} for one source file."""
    ext = os.path.splitext(path)[1].lstrip(".")
    if ext == "py":
        return _python_semantic_tokens(source)
    if ext in _DECL_RE:
        _, units = _lexical_scan(source, ext)
        return {
            name: {"public": is_public, "tokens": _lexical_body_tokens(body)}
            for name, (body, is_public) in units.items()}
    return {}


# --------------------------------------------------------------------------
# Filter 2 math: churn, MinHash and Shannon entropy.
# --------------------------------------------------------------------------


def _token_delta(base_tokens, target_tokens):
    """Count of changed semantic token positions between two bodies."""
    matcher = difflib.SequenceMatcher(
        None, base_tokens, target_tokens, autojunk=False)
    return sum(max(a2 - a1, b2 - b1)
               for tag, a1, a2, b1, b2 in matcher.get_opcodes()
               if tag != "equal")


def _minhash(tokens):
    """64-component MinHash over 3-shingles, or None below three tokens."""
    shingles = {" ".join(tokens[index:index + 3])
                for index in range(len(tokens) - 2)}
    if not shingles:
        return None
    return [
        min(int.from_bytes(
            hashlib.sha256(("%d:%s" % (k, shingle)).encode("utf-8"))
            .digest()[:8], "big")
            for shingle in shingles)
        for k in range(LSH_COMPONENTS)
    ]


def _lsh_hex(signature):
    return "".join("%016x" % value for value in signature)


def _lsh_divergence(base_signature, target_signature):
    if base_signature is None or target_signature is None:
        return 0.0
    matches = sum(1 for base, target in zip(base_signature, target_signature)
                  if base == target)
    return round(1.0 - matches / float(LSH_COMPONENTS), 4)


def _entropy(deltas):
    """Shannon entropy H(P) over the per-element changed-token counts."""
    positive = [delta for delta in deltas if delta > 0]
    total = sum(positive)
    if total == 0:
        return 0.0
    return round(-sum((delta / total) * math.log2(delta / total)
                      for delta in positive), 4)


# --------------------------------------------------------------------------
# Document parsing: directives, frontmatter, pinned blocks, references.
# --------------------------------------------------------------------------


_DIRECTIVE_RE = re.compile(r"<!--\s*drift:track\s+(.*?)-->", re.DOTALL)
_ATTR_RE = re.compile(r'([a-zA-Z_]+)\s*=\s*"([^"]*)"')
_FRONTMATTER_RE = re.compile(r"(?m)^\s*drift-track:\s*(.+)$")
_LINK_RE = re.compile(r"!?\[[^\]]*\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
_CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
_PATH_LIKE_RE = re.compile(
    r"^(?:[\w.-]+/)+[\w.-]+\.(?:py|ts|tsx|js|mjs|rs|go|md|json|ya?ml|sh|toml|txt)$")
_FENCE_OPEN_RE = re.compile(r"^(`{3,})(.*)$")
_FENCE_CLOSE_RE = re.compile(r"^`{3,}\s*$")


def _parse_attrs(text):
    return dict(_ATTR_RE.findall(text))


def _parse_directive(text):
    attrs = _parse_attrs(text)
    path = attrs.get("path")
    if not path:
        return None
    symbols = [s.strip() for s in attrs.get("symbols", "").split(",") if s.strip()]
    return {"path": path, "symbols": symbols}


def _parse_doc(text):
    """Extract everything a document claims about the code, deterministically."""
    directives = []
    for match in _DIRECTIVE_RE.finditer(text):
        parsed = _parse_directive(match.group(1))
        if parsed:
            directives.append(parsed)

    if text.startswith("---\n"):
        closing = text.find("\n---", 4)
        if closing != -1:
            for match in _FRONTMATTER_RE.finditer(text[:closing]):
                parsed = _parse_directive(match.group(1))
                if parsed:
                    directives.append(parsed)

    pinned = []
    lines = text.split("\n")
    index = 0
    while index < len(lines):
        opened = _FENCE_OPEN_RE.match(lines[index])
        if not opened:
            index += 1
            continue
        info = opened.group(2)
        end = index + 1
        while end < len(lines) and not _FENCE_CLOSE_RE.match(lines[end]):
            end += 1
        if "type-equiv" in info or "public-api" in info:
            pinned.append({
                "info": info.strip(),
                "attrs": _parse_attrs(info),
                "content": "\n".join(lines[index + 1:end]),
            })
        index = end + 1

    links = []
    for match in _LINK_RE.finditer(text):
        target = match.group(1)
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        links.append(target)

    governed = bool(directives or pinned)
    inline_paths = []
    if governed:
        for match in _CODE_SPAN_RE.finditer(text):
            candidate = match.group(1).strip()
            if _PATH_LIKE_RE.match(candidate):
                inline_paths.append(candidate)

    return {
        "directives": directives,
        "pinned": pinned,
        "links": links,
        "inline_paths": sorted(set(inline_paths)),
        "governed": governed,
    }


def _resolve_ref(doc_path, ref, tree):
    ref = ref.split("#", 1)[0].strip()
    if not ref:
        return False
    if ref.endswith("/"):
        prefix = ref.lstrip("/")
        return any(path.startswith(prefix) for path in tree.paths())
    if ref.startswith("/"):
        return tree.has(ref.lstrip("/"))
    resolved = posixpath.normpath(
        posixpath.join(posixpath.dirname(doc_path), ref))
    return tree.has(resolved)


# --------------------------------------------------------------------------
# Baseline I/O: <workspace>/drift/, atomic writes, Host authority.
# --------------------------------------------------------------------------


def drift_dir(workspace):
    return Path(workspace) / "drift"


def baseline_path(workspace):
    return drift_dir(workspace) / "doc-baseline.json"


def report_path(workspace):
    return drift_dir(workspace) / "source-drift.json"


def _atomic_write_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(_dumps(document), encoding="utf-8")
    os.replace(tmp, path)


def load_baseline(workspace):
    path = baseline_path(workspace)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def pin_baseline(workspace, baseline):
    """Atomic; called by the Host/Harness after verification, never by an agent."""
    _atomic_write_json(baseline_path(workspace), baseline)


def write_report(workspace, report):
    _atomic_write_json(report_path(workspace), report)


def collect_baseline(config, *, target_rev="HEAD"):
    """Freeze the per-symbol contract hashes, signatures and body tokens."""
    config = _prepare_config(config)
    tree = _target_tree(config["repo_root"], target_rev)
    thresholds = _thresholds(config)
    rules_by_doc = {}
    for rule in config.get("rules", []):
        rules_by_doc.setdefault(rule["doc"], []).append(rule)
    documents = {}
    for doc in sorted(_governed_docs(config, tree)):
        parsed = _parse_doc(tree.read(doc))
        symbols = []
        for tracked in _tracked_paths(config, parsed, rules_by_doc.get(doc, [])):
            path = tracked["path"]
            source = tree.read(path)
            if source is None:
                continue
            signatures = extract_symbols(path, source)
            units = extract_semantic_tokens(path, source)
            for name, signature in sorted(signatures.items()):
                tokens = units.get(name, {}).get("tokens", [])
                entry = {
                    "symbol_id": "%s::%s" % (path, name),
                    "contract_hash": _sha256(signature),
                    "signature": signature,
                    "tokens": tokens,
                }
                lsh = _minhash(tokens)
                if lsh is not None:
                    entry["body_lsh"] = _lsh_hex(lsh)
                symbols.append(entry)
        if symbols:
            documents[doc] = {"thresholds": thresholds, "symbols": symbols}
    return {
        "schema": "doc-baseline@%d" % SCHEMA_VERSION,
        "base_rev": _resolve_rev(config["repo_root"], target_rev)
        if target_rev not in (None, "WORKTREE") else "WORKTREE",
        "documents": documents,
    }


# --------------------------------------------------------------------------
# Config plumbing
# --------------------------------------------------------------------------


def _prepare_config(config):
    if not isinstance(config, dict):
        raise DriftError("config must be a dict")
    unknown = sorted(set(config) - CONFIG_KEYS)
    if unknown:
        raise DriftError("config has unknown keys: %s" % ", ".join(unknown))
    if "repo_root" not in config:
        raise DriftError("config requires repo_root")
    repo_root = Path(config["repo_root"]).resolve()
    if not repo_root.is_dir():
        raise DriftError("repo_root is not a directory: %s" % repo_root)
    prepared = dict(config)
    prepared["repo_root"] = str(repo_root)
    return prepared


def _thresholds(config):
    merged = dict(DEFAULT_THRESHOLDS)
    for key, value in (config.get("thresholds") or {}).items():
        if key not in merged or not isinstance(value, (int, float)):
            raise DriftError("thresholds: unknown key or non-numeric %s" % key)
        merged[key] = value
    return merged


def _scoped_docs(config, tree):
    doc_filter = config.get("docs")
    docs = [path for path in tree.paths() if path.endswith(".md")]
    if doc_filter:
        docs = [doc for doc in docs if doc in set(doc_filter)]
    return sorted(docs)


def _governed_docs(config, tree):
    """Docs that claim something about the code: directives, pins or rules."""
    ruled = {rule["doc"] for rule in config.get("rules", [])}
    governed = []
    for doc in _scoped_docs(config, tree):
        if doc in ruled:
            governed.append(doc)
            continue
        parsed = _parse_doc(tree.read(doc))
        if parsed["directives"] or parsed["pinned"]:
            governed.append(doc)
    return sorted(set(governed))


def _tracked_paths(config, parsed, doc_rules):
    """The union of paths this document claims, in first-seen order."""
    paths = []
    seen = set()

    def add(path, symbols):
        if path not in seen:
            seen.add(path)
            paths.append({"path": path, "symbols": list(symbols)})
            return
        for entry in paths:
            if entry["path"] == path:
                for symbol in symbols:
                    if symbol not in entry["symbols"]:
                        entry["symbols"].append(symbol)

    for directive in parsed["directives"]:
        add(directive["path"], directive["symbols"])
    for rule in doc_rules:
        add(rule["path"], rule.get("symbols", []))
    return paths


# --------------------------------------------------------------------------
# The seam
# --------------------------------------------------------------------------


def evaluate(config, *, base_rev=None, target_rev="HEAD", dry_run=False):
    """The single deterministic evaluation boundary.

    Returns the drift report document. When `base_rev` is None and a pinned
    baseline exists in the workspace, the baseline is the base; when neither
    exists there is nothing to compare contracts against, so only reference
    validity is judged. `target_rev=None` or `"WORKTREE"` reads the working
    tree; any other value is a git revision.
    """
    config = _prepare_config(config)
    repo_root = config["repo_root"]
    tree = _target_tree(repo_root, target_rev)
    thresholds = _thresholds(config)
    rules_by_doc = {}
    for rule in config.get("rules", []):
        rules_by_doc.setdefault(rule["doc"], []).append(rule)

    base_symbols = _base_symbols(config, base_rev, tree)

    entries = []
    for doc in _scoped_docs(config, tree):
        parsed = _parse_doc(tree.read(doc))
        tracked = _tracked_paths(config, parsed, rules_by_doc.get(doc, []))
        claims_code = bool(tracked or parsed["pinned"])
        if not claims_code and not parsed["links"] and not parsed["inline_paths"]:
            continue

        problems = {"contract": [], "stale": []}
        symbol_records = []
        public_stats = []
        private_changed = []

        for tracked_entry in tracked:
            path = tracked_entry["path"]
            if not tree.has(path):
                problems["stale"].append(path)
                continue
            source = tree.read(path)
            live = extract_symbols(path, source)
            live_units = extract_semantic_tokens(path, source)
            previous = base_symbols.get(doc, {}).get(path)
            previous_public = previous["public"] if previous else {}
            # A file absent from the base (or a baseline, which stores public
            # symbols only) has no private ground to diff against: its
            # private symbols are newly discovered, not changed.
            previous_private = previous["private"] if previous else None

            for name, signature in sorted(live.items()):
                digest = _sha256(signature)
                record = {
                    "symbol_id": "%s::%s" % (path, name),
                    "contract_hash": digest,
                }
                if name in previous_public:
                    old_hash, old_signature, old_tokens = \
                        previous_public[name]
                    if old_hash != digest:
                        problems["contract"].append({
                            "symbol": record["symbol_id"],
                            "before": old_signature,
                            "after": signature,
                        })
                        record["symbol_diff"] = {
                            "before": old_signature, "after": signature}
                    elif old_tokens is not None:
                        live_tokens = live_units.get(name, {}).get(
                            "tokens", [])
                        churn = round(
                            1.0 - difflib.SequenceMatcher(
                                None, old_tokens, live_tokens,
                                autojunk=False).ratio(), 4)
                        delta = _token_delta(old_tokens, live_tokens)
                        divergence = _lsh_divergence(
                            _minhash(old_tokens), _minhash(live_tokens))
                        record["body_churn_ratio"] = churn
                        live_lsh = _minhash(live_tokens)
                        if live_lsh is not None:
                            record["body_lsh"] = _lsh_hex(live_lsh)
                        public_stats.append((churn, divergence, delta))
                symbol_records.append(record)
            for name in sorted(set(previous_public) - set(live)):
                old_hash, old_signature, _ = previous_public[name]
                problems["contract"].append({
                    "symbol": "%s::%s" % (path, name),
                    "before": old_signature,
                    "after": None,
                })

            # Private bodies are nobody's contract, but their churn is the
            # difference between CURRENT and NON_GOVERNING_CHANGE. The
            # baseline stores none, so a pinned baseline cannot see it; a
            # base revision can.
            if previous_private is not None:
                for name, unit in sorted(live_units.items()):
                    if unit["public"]:
                        continue
                    old_tokens = previous_private.get(name)
                    if old_tokens is None:
                        if unit["tokens"]:
                            private_changed.append("%s::%s" % (path, name))
                    elif _token_delta(old_tokens, unit["tokens"]) > 0:
                        private_changed.append("%s::%s" % (path, name))

        for block in parsed["pinned"]:
            _check_pinned_block(block, tree, problems)

        for ref in parsed["links"]:
            # A link to a binary or an extensionless target is not a claim
            # this engine can verify; the inline path scan is scoped tighter.
            if os.path.splitext(ref)[1] not in REF_EXTENSIONS:
                continue
            if not _resolve_ref(doc, ref, tree):
                problems["stale"].append(ref)
        for ref in parsed["inline_paths"]:
            if not _resolve_ref(doc, ref, tree):
                problems["stale"].append(ref)

        entry = {"path": doc, "source": "doc-drift"}
        if problems["contract"]:
            entry["status"] = "CONTRACT_DRIFT"
            entry["action"] = "update"
        elif problems["stale"]:
            entry["status"] = "STALE_REFERENCE"
            entry["action"] = "update"
        else:
            entry["status"] = _behaviour_verdict(
                public_stats, private_changed, thresholds)
            if entry["status"] == "SOURCE_DRIFT":
                entry["action"] = "update"
            entry["metrics"] = _metrics(public_stats)
        detail = _detail(problems)
        if detail:
            entry["detail"] = detail
        if symbol_records:
            entry["tracked_symbols"] = sorted(
                symbol_records, key=lambda record: record["symbol_id"])
        entry["thresholds"] = dict(thresholds)
        entries.append(entry)

    report = {
        "schema_version": SCHEMA_VERSION,
        "generation_id": config.get("generation_id", "drift-evaluate"),
        "comparison_points": {
            "project_base": _base_label(config, base_rev, repo_root),
            "accepted_generation": config.get("accepted_generation", ""),
            "current_project": "WORKTREE"
            if target_rev in (None, "WORKTREE")
            else _resolve_rev(repo_root, target_rev),
        },
        "entries": entries,
    }
    if not dry_run and config.get("workspace"):
        write_report(config["workspace"], report)
    return report


def _behaviour_verdict(public_stats, private_changed, thresholds):
    """The disjunctive SOURCE_DRIFT rule with its minimum-token floor."""
    limit = thresholds["body_churn_ratio"]
    over_threshold = any(
        churn > limit or divergence > limit
        for churn, divergence, _ in public_stats)
    deltas = [delta for _, _, delta in public_stats]
    total_delta = sum(deltas)
    entropy = _entropy(deltas)
    if over_threshold or (total_delta >= thresholds["min_entropy_tokens"]
                          and entropy > thresholds["entropy_limit"]):
        return "SOURCE_DRIFT"
    if total_delta > 0 or private_changed:
        return "NON_GOVERNING_CHANGE"
    return "CURRENT"


def _metrics(public_stats):
    return {
        "max_body_churn_ratio": round(
            max([churn for churn, _, _ in public_stats], default=0.0), 4),
        "shannon_entropy": _entropy(
            [delta for _, _, delta in public_stats]),
        "total_semantic_delta_tokens": sum(
            delta for _, _, delta in public_stats),
    }


def _check_pinned_block(block, tree, problems):
    path = block["attrs"].get("path")
    if path is None or not tree.has(path):
        problems["stale"].append(path or "pinned-block")
        return
    wanted = None
    if block["attrs"].get("symbol"):
        wanted = [block["attrs"]["symbol"]]
    elif block["attrs"].get("symbols"):
        wanted = [s.strip() for s in block["attrs"]["symbols"].split(",")
                  if s.strip()]
    live = extract_symbols(path, tree.read(path))
    snippet_ext = os.path.splitext(path)[1].lstrip(".")
    if not snippet_ext:
        language = block["info"].split()[0] if block["info"] else ""
        snippet_ext = _SNIPPET_LANGS.get(language, "ts")
    pinned = extract_symbols("snippet." + snippet_ext, block["content"])
    for name, signature in sorted(pinned.items()):
        if wanted is not None and name not in wanted:
            continue
        if name not in live:
            problems["contract"].append({
                "symbol": "%s::%s" % (path, name),
                "before": signature, "after": None})
        elif _sha256(signature) != _sha256(live[name]):
            problems["contract"].append({
                "symbol": "%s::%s" % (path, name),
                "before": signature, "after": live[name]})


def _base_symbols(config, base_rev, target_tree):
    """doc -> path -> {"public": {...}, "private": {...}} from the base.

    `public` maps name -> (contract_hash, signature, body tokens or None);
    `private` maps name -> body tokens, or is None when the base is a pinned
    baseline, which stores public symbols only.
    """
    base = {}
    repo_root = config["repo_root"]
    if base_rev is not None:
        base_tree = _target_tree(repo_root, base_rev)
        rules_by_doc = {}
        for rule in config.get("rules", []):
            rules_by_doc.setdefault(rule["doc"], []).append(rule)
        for doc in _scoped_docs(config, target_tree):
            parsed = _parse_doc(target_tree.read(doc))
            for tracked in _tracked_paths(
                    config, parsed, rules_by_doc.get(doc, [])):
                path = tracked["path"]
                source = base_tree.read(path)
                if source is None:
                    continue
                signatures = extract_symbols(path, source)
                units = extract_semantic_tokens(path, source)
                base.setdefault(doc, {})[path] = {
                    "public": {
                        name: (_sha256(signatures[name]), signatures[name],
                               units.get(name, {}).get("tokens", []))
                        for name in signatures},
                    "private": {
                        name: unit["tokens"]
                        for name, unit in units.items()
                        if not unit["public"]},
                }
        return base
    baseline = None
    if config.get("workspace"):
        baseline = load_baseline(config["workspace"])
    if baseline:
        for doc, document in baseline.get("documents", {}).items():
            base[doc] = {}
            for symbol in document.get("symbols", []):
                path, _, name = symbol["symbol_id"].partition("::")
                base[doc].setdefault(path, {"public": {}, "private": None})
                base[doc][path]["public"][name] = (
                    symbol["contract_hash"], symbol.get("signature", ""),
                    symbol.get("tokens"))
    return base


def _base_label(config, base_rev, repo_root):
    if base_rev is not None:
        return "WORKTREE" if base_rev == "WORKTREE" \
            else _resolve_rev(repo_root, base_rev)
    if config.get("workspace") and load_baseline(config["workspace"]):
        return "baseline-manifest"
    return ""


def _detail(problems):
    parts = []
    if problems["contract"]:
        parts.append("changed: %s" % ", ".join(
            sorted({problem["symbol"] for problem in problems["contract"]})))
    if problems["stale"]:
        parts.append("unresolved: %s" % ", ".join(
            sorted(set(problems["stale"]))))
    return "; ".join(parts)


def _dumps(document):
    return json.dumps(document, sort_keys=True, indent=2,
                      ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# CLI: the same seam, invocable. A workflow gate step can run `check` as its
# deterministic verdict: exit 0 = clean (only CURRENT/NON_GOVERNING_CHANGE),
# exit 1 = drift found, exit 2 = refused input. No network, no LLM, ever.
# ---------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Motor determinista de deriva documental (ADR 0001/0002)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser(
        "check", help="Evaluar la deriva documental entre dos revisiones")
    p_check.add_argument("--project", required=True,
                         help="Ruta al repositorio del producto evaluado")
    p_check.add_argument("--workspace", default=None,
                         help="Workspace externo que contiene drift/ "
                              "(default: sin estado en disco)")
    p_check.add_argument("--from", dest="from_rev", default=None,
                         help="Revisión base (default: la línea base anclada; "
                              "sin base solo se verifican referencias)")
    p_check.add_argument("--to", default="HEAD",
                         help="Revisión objetivo (default: HEAD; 'WORKTREE' "
                              "lee el árbol de trabajo)")
    p_check.add_argument("--dry-run", action="store_true",
                         help="No escribir source-drift.json")
    p_check.add_argument("--json", action="store_true",
                         help="Imprimir el reporte completo en JSON")

    for name, help_text in (
            ("init-baseline",
             "Anclar la primera línea base de contratos del proyecto"),
            ("repin",
             "Re-anclar doc-baseline.json tras verificación del Host")):
        p_pin = sub.add_parser(name, help=help_text)
        p_pin.add_argument("--project", required=True,
                           help="Ruta al repositorio del producto evaluado")
        p_pin.add_argument("--workspace", required=True,
                           help="Workspace externo donde vive drift/")
        p_pin.add_argument("--to", default="HEAD",
                           help="Revisión a anclar (default: HEAD)")

    args = parser.parse_args(argv)
    config = {"repo_root": str(Path(args.project).resolve())}
    workspace = getattr(args, "workspace", None)
    if workspace:
        config["workspace"] = str(Path(workspace).resolve())

    try:
        if args.command == "check":
            report = evaluate(config, base_rev=args.from_rev,
                              target_rev=args.to, dry_run=args.dry_run)
            found = any(entry["status"] not in ("CURRENT", "NON_GOVERNING_CHANGE")
                        for entry in report["entries"])
            if args.json:
                print(_dumps(report), end="")
            else:
                for entry in report["entries"]:
                    print("%s %s" % (entry["status"], entry["path"]))
                print("verdict: %s" % ("DRIFT" if found else "CLEAN"))
            return 1 if found else 0

        baseline = collect_baseline(config, target_rev=args.to)
        if args.command == "init-baseline" \
                and load_baseline(config["workspace"]) is not None:
            print("doc-baseline.json ya existe; repin es la re-ancla",
                  file=sys.stderr)
            return 2
        pin_baseline(config["workspace"], baseline)
        print("%s %s (base %s, %d símbolos en %d documentos)" % (
            "anclada" if args.command == "init-baseline" else "re-anclada",
            baseline_path(config["workspace"]), baseline["base_rev"],
            sum(len(doc["symbols"]) for doc in baseline["documents"].values()),
            len(baseline["documents"])))
        return 0
    except DriftError as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
