"""The doc-drift engine is judged only through its seam.

Every test drives `drift.evaluate(...)` over synthetic git repositories built
in a temporary directory, exactly as the spec's testing decision requires: no
parser internals, no extractor calls — verdicts, diffs and JSON only. The CLI
surface is exercised later, at the bootstrap integration round.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import drift  # noqa: E402
import generation_contracts as gc  # noqa: E402


TOOL_V1 = '''\
"""A tool module with a documented public contract."""


def public_fn(a: int, b: str = "x") -> bool:
    """Decide something important.

    The prose here is deliberately long: reformatting it must never
    change the verdict, because docstrings are not contract.
    """
    _helper(a)
    return a > 0 and b == "x"


def _helper(value: int) -> None:
    # Private implementation detail; rewriting it entirely must not
    # invalidate anything public above.
    total = 0
    for step in range(value):
        total += step * 3 - 1
    print("helper did", total)


def other_public() -> str:
    return "stable"
'''

TOOL_WHITESPACE = '''\
"""A tool module with a documented public contract.

Reformatted: more blank lines, a rewritten docstring, inline comments and
cosmetic signature spacing. Zero contract delta is expected.
"""


def public_fn( a : int , b : str = "x" ) -> bool :   # signature spacing only
    # a comment where none was
    """Decide something important -- now with different wrapping and

    totally different prose, because docstrings are not contract.
    """
    _helper(a)
    return a > 0 and b == "x"      # an aligned comment


def _helper(value: int) -> None:
    total = 0
    for step in range(value):
        total += step * 3 - 1
    print("helper did", total)


def other_public() -> str:
    # touched comment only
    return "stable"
'''

TOOL_PARAM_DRIFT = TOOL_V1.replace(
    'def public_fn(a: int, b: str = "x") -> bool:',
    'def public_fn(a: int, b: str = "x", *, today=None) -> bool:')

TOOL_REMOVED = TOOL_V1.replace(
    'def other_public() -> str:\n    return "stable"\n', '')

TOOL_NEW_SYMBOL = TOOL_V1 + '\n\ndef third_public(n: int) -> int:\n    return n\n'

TOOL_PRIVATE_REWRITE = TOOL_V1.replace(
    '''def _helper(value: int) -> None:
    # Private implementation detail; rewriting it entirely must not
    # invalidate anything public above.
    total = 0
    for step in range(value):
        total += step * 3 - 1
    print("helper did", total)''',
    '''def _helper(value: int) -> None:
    # Completely rewritten implementation, same private name.
    scaled = value * 7919 - 13
    pieces = [scaled % (step + 2) for step in range(9)]
    pieces.sort(reverse=True)
    print("rewrote", pieces[:3])''')

TOOL_HEAVY_BODY = TOOL_V1.replace(
    '''def public_fn(a: int, b: str = "x") -> bool:
    """Decide something important.

    The prose here is deliberately long: reformatting it must never
    change the verdict, because docstrings are not contract.
    """
    _helper(a)
    return a > 0 and b == "x"''',
    '''def public_fn(a: int, b: str = "x") -> bool:
    """Decide something important; prose rewritten freely."""
    matrix = [[value * step for step in range(6)] for value in range(a + 3)]
    folded = sum(sum(row) for row in matrix) % 977
    levels = {folded << shift: shift for shift in range(5)}
    return bool(levels) and folded > 0 and b == "x"''')

TOOL_SMALL_CHANGE = TOOL_V1.replace(
    '    _helper(a)\n    return a > 0 and b == "x"',
    '    _helper(a)\n    a = a + 0\n    return a > 0 and b == "x"')

RUN_V1 = (
    "def run(value):\n"
    "    total = value\n"
    "    tmp = total * 2\n"
    "    other = tmp + 1\n"
    "    third = tmp + 2\n"
    "    fourth = tmp + 3\n"
    "    fifth = tmp + 4\n"
    "    sixth = tmp + 5\n"
    "    return tmp + other + third + fourth + fifth + sixth\n")

# Three inserted tokens: far under every threshold in isolation, visible in
# aggregate once enough files contribute.
RUN_V2 = RUN_V1.replace(
    "    return tmp + other",
    "    marker = tmp\n    return tmp + other")

# Ten scattered single-token renames: churn stays under 0.35 but the
# 3-shingle damage pushes the MinHash divergence well past it, so the
# disjunction's second branch fires on its own.
RUN_SCATTER = (RUN_V1.replace("tmp", "val").replace("total", "tot")
               .replace("other", "sec").replace("third", "thd"))

SUB_DOC = "# Subsystem contract\n\n" + "".join(
    '<!-- drift:track path="src/m%d.py" -->\n' % index
    for index in range(1, 9))

API_DOC = '''# API contract

<!-- drift:track path="src/tool.py" symbols="public_fn,other_public" -->

The entry point is `public_fn`; the second export is `other_public`.
'''

API_DOC_WITH_LINK = API_DOC + '\nSee [the guide](guide.md).\n'

PINNED_DOC = '''# Pinned contract

<!-- drift:track path="src/tool.py" -->

```python type-equiv path="src/tool.py" symbol="public_fn"
def public_fn(a: int, b: str = "x") -> bool:
```
'''

TS_V1 = '''\
// Greeting helpers.
export function greet(name: string): string {
  /* implementation detail, never pinned */
  return "hi " + name;
}

export interface Greeting {
  formal: boolean;
}

const hidden = 1;

function privateish(): number {
  return 2;
}
'''

TS_PARAM_DRIFT = TS_V1.replace(
    'export function greet(name: string): string {',
    'export function greet(name: string, punct: string): string {')

RS_V1 = '''\
/// Compute doubling.
pub fn compute(value: i32) -> i32 {
    // internal detail
    value * 2
}

fn private_one() -> i32 {
    3
}

pub struct Config {
    pub retries: u8,
}
'''

RS_PARAM_DRIFT = RS_V1.replace(
    'pub fn compute(value: i32) -> i32 {',
    'pub fn compute(value: i32, scale: i32) -> i32 {')

GO_V1 = '''\
package main

// Exported adds one.
func Exported(n int) int {
	return n + 1
}

func hidden(n int) int {
	return n
}

// Limits bounds a run.
type Limits struct {
	Max int
}
'''

GO_PARAM_DRIFT = GO_V1.replace(
    'func Exported(n int) int {',
    'func Exported(n int, scale int) int {')

GO_TYPE_DRIFT = GO_V1.replace(
    'type Limits struct {\n\tMax int\n}',
    'type Limits struct {\n\tMax int\n\tMin int\n}')


class DriftEngineTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name) / "product"
        self.workspace = Path(tmp.name) / "workspace"
        self.repo.mkdir()
        self._git("init", "-q")
        self._write("src/tool.py", TOOL_V1)
        self._write("docs/api.md", API_DOC_WITH_LINK)
        self._write("docs/guide.md", "# Guide\n")
        self._commit("base")
        self.base_rev = self._git("rev-parse", "HEAD").strip()

    # -- helpers ------------------------------------------------------------

    def _git(self, *args):
        result = subprocess.run(
            ["git", "-C", str(self.repo), *args],
            capture_output=True, text=True, check=True)
        return result.stdout

    def _write(self, relative, text):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _commit(self, message):
        self._git("add", "-A")
        self._git("-c", "user.name=Tester", "-c", "user.email=t@example.test",
                  "commit", "-q", "-m", message)

    def _evaluate(self, *, base_rev="unset", target_rev="WORKTREE", **kwargs):
        config = {"repo_root": str(self.repo)}
        return drift.evaluate(
            config,
            base_rev=self.base_rev if base_rev == "unset" else base_rev,
            target_rev=target_rev, dry_run=True, **kwargs)

    def _entry(self, report, doc="docs/api.md"):
        return next(e for e in report["entries"] if e["path"] == doc)

    # -- Filter 1: the five critical cases ----------------------------------

    def test_formatting_and_comment_edits_report_current(self):
        self._write("src/tool.py", TOOL_WHITESPACE)
        entry = self._entry(self._evaluate())
        self.assertEqual(entry["status"], "CURRENT")
        self.assertEqual(entry["metrics"], {
            "max_body_churn_ratio": 0.0,
            "shannon_entropy": 0.0,
            "total_semantic_delta_tokens": 0,
        })
        for symbol in entry["tracked_symbols"]:
            self.assertNotIn("symbol_diff", symbol)
            self.assertIn("body_lsh", symbol)

    def test_parameter_change_reports_contract_drift_with_exact_symbol_diff(self):
        self._write("src/tool.py", TOOL_PARAM_DRIFT)
        entry = self._entry(self._evaluate())
        self.assertEqual(entry["status"], "CONTRACT_DRIFT")
        self.assertEqual(entry["action"], "update")
        drifted = next(s for s in entry["tracked_symbols"]
                       if "symbol_diff" in s)
        self.assertEqual(drifted["symbol_id"], "src/tool.py::public_fn")
        self.assertEqual(
            drifted["symbol_diff"]["before"],
            "def public_fn(a: int, b: str = 'x') -> bool")
        self.assertEqual(
            drifted["symbol_diff"]["after"],
            "def public_fn(a: int, b: str = 'x', *, today = None) -> bool")
        # The untouched sibling keeps its hash and gains no diff.
        stable = next(s for s in entry["tracked_symbols"]
                      if s["symbol_id"].endswith("other_public"))
        self.assertNotIn("symbol_diff", stable)

    def test_removed_symbol_reports_contract_drift(self):
        self._write("src/tool.py", TOOL_REMOVED)
        entry = self._entry(self._evaluate())
        self.assertEqual(entry["status"], "CONTRACT_DRIFT")
        self.assertIn("src/tool.py::other_public", entry["detail"])

    def test_new_public_symbol_is_current(self):
        self._write("src/tool.py", TOOL_NEW_SYMBOL)
        self.assertEqual(self._entry(self._evaluate())["status"], "CURRENT")

    def test_private_rewrite_does_not_break_contracts(self):
        self._write("src/tool.py", TOOL_PRIVATE_REWRITE)
        entry = self._entry(self._evaluate())
        self.assertEqual(entry["status"], "NON_GOVERNING_CHANGE")
        self.assertNotIn("symbol_diff", entry.get("tracked_symbols", [{}])[0])

    def test_public_body_rewrite_over_threshold_reports_source_drift(self):
        self._write("src/tool.py", TOOL_HEAVY_BODY)
        entry = self._entry(self._evaluate())
        self.assertEqual(entry["status"], "SOURCE_DRIFT")
        self.assertEqual(entry["action"], "update")
        # A single-file rewrite is maximally concentrated: H(P) == 0 while
        # the churn branch alone fires.
        self.assertEqual(entry["metrics"]["shannon_entropy"], 0.0)
        self.assertGreater(entry["metrics"]["max_body_churn_ratio"], 0.35)

    def test_public_body_change_under_threshold_is_non_governing(self):
        self._write("src/tool.py", TOOL_SMALL_CHANGE)
        entry = self._entry(self._evaluate())
        self.assertEqual(entry["status"], "NON_GOVERNING_CHANGE")
        self.assertLess(entry["metrics"]["max_body_churn_ratio"], 0.35)
        self.assertLess(entry["metrics"]["total_semantic_delta_tokens"], 20)

    def test_lsh_divergence_fires_when_churn_is_below_threshold(self):
        self._write("src/tool.py", RUN_V1)
        self._write("docs/api.md",
                    '<!-- drift:track path="src/tool.py" symbols="run" -->\n')
        (self.repo / "docs" / "guide.md").unlink()
        self._commit("scatter base")
        self.base_rev = self._git("rev-parse", "HEAD").strip()
        self._write("src/tool.py", RUN_SCATTER)
        entry = self._entry(self._evaluate())
        self.assertEqual(entry["status"], "SOURCE_DRIFT")
        self.assertLess(entry["metrics"]["max_body_churn_ratio"], 0.35,
                        "el caso prueba la rama disyuntiva del Body LSH")

    def test_dispersed_changes_across_subsystem_report_source_drift(self):
        for index in range(1, 9):
            self._write("src/m%d.py" % index, RUN_V1)
        self._write("docs/sub.md", SUB_DOC)
        self._commit("subsystem base")
        self.base_rev = self._git("rev-parse", "HEAD").strip()

        # Four files with three inserted tokens each: 12 < 20, far below
        # churn and MinHash thresholds per symbol.
        for index in range(1, 5):
            self._write("src/m%d.py" % index, RUN_V2)
        entry = self._entry(self._evaluate(), "docs/sub.md")
        self.assertEqual(entry["status"], "NON_GOVERNING_CHANGE")
        self.assertEqual(entry["metrics"]["total_semantic_delta_tokens"], 12)

        # Eight files dispersing the same kind of edit: 24 >= 20 tokens and
        # H(P) = log2(8) = 3.0 > 2.5, so the entropy branch fires.
        for index in range(5, 9):
            self._write("src/m%d.py" % index, RUN_V2)
        entry = self._entry(self._evaluate(), "docs/sub.md")
        self.assertEqual(entry["status"], "SOURCE_DRIFT")
        self.assertEqual(entry["metrics"]["total_semantic_delta_tokens"], 24)
        self.assertEqual(entry["metrics"]["shannon_entropy"], 3.0)

    def test_broken_cited_path_reports_stale_reference(self):
        entry = self._entry(self._evaluate())
        self.assertEqual(entry["status"], "CURRENT")
        (self.repo / "docs" / "guide.md").unlink()
        entry = self._entry(self._evaluate())
        self.assertEqual(entry["status"], "STALE_REFERENCE")
        self.assertEqual(entry["action"], "update")
        self.assertIn("unresolved: guide.md", entry["detail"])

    def test_pinned_block_tracks_the_documented_signature(self):
        self._write("docs/api.md", PINNED_DOC)
        (self.repo / "docs" / "guide.md").unlink()
        entry = self._entry(self._evaluate())
        self.assertEqual(entry["status"], "CURRENT")
        # The block normalizes before hashing: the same signature written
        # with different quoting is still the same contract.
        self._write("src/tool.py", TOOL_PARAM_DRIFT)
        entry = self._entry(self._evaluate())
        self.assertEqual(entry["status"], "CONTRACT_DRIFT")
        drifted = next(s for s in entry["tracked_symbols"]
                       if "symbol_diff" in s)
        self.assertEqual(
            drifted["symbol_diff"]["before"],
            "def public_fn(a: int, b: str = 'x') -> bool")

    # -- Polyglot extractors, still through the seam ------------------------

    def test_lexical_extractors_detect_contract_changes_across_languages(self):
        self._write("docs/api.md", "# API\n")
        self._write("docs/guide.md", "# Guide\n")
        self._write("src/api.ts", TS_V1)
        self._write("docs/ts.md",
                    '<!-- drift:track path="src/api.ts" symbols="greet,Greeting" -->\n')
        self._write("src/util.rs", RS_V1)
        self._write("docs/rs.md",
                    '<!-- drift:track path="src/util.rs" symbols="compute,Config" -->\n')
        self._write("src/main.go", GO_V1)
        self._write("docs/go.md",
                    '<!-- drift:track path="src/main.go" symbols="Exported,Limits" -->\n')
        self._commit("polyglot base")
        self.base_rev = self._git("rev-parse", "HEAD").strip()

        def statuses():
            report = self._evaluate()
            return {e["path"]: e["status"] for e in report["entries"]}

        current = statuses()
        self.assertEqual(current["docs/ts.md"], "CURRENT")
        self.assertEqual(current["docs/rs.md"], "CURRENT")
        self.assertEqual(current["docs/go.md"], "CURRENT")

        self._write("src/api.ts", TS_PARAM_DRIFT)
        drifted = statuses()
        self.assertEqual(drifted["docs/ts.md"], "CONTRACT_DRIFT")
        self.assertEqual(drifted["docs/rs.md"], "CURRENT")
        self.assertEqual(drifted["docs/go.md"], "CURRENT")

        self._write("src/api.ts", TS_V1)
        self._write("src/util.rs", RS_PARAM_DRIFT)
        drifted = statuses()
        self.assertEqual(drifted["docs/rs.md"], "CONTRACT_DRIFT")
        self.assertEqual(drifted["docs/ts.md"], "CURRENT")

        self._write("src/util.rs", RS_V1)
        self._write("src/main.go", GO_PARAM_DRIFT)
        drifted = statuses()
        self.assertEqual(drifted["docs/go.md"], "CONTRACT_DRIFT")
        self.assertEqual(drifted["docs/rs.md"], "CURRENT")

        self._write("src/main.go", GO_TYPE_DRIFT)
        drifted = statuses()
        self.assertEqual(drifted["docs/go.md"], "CONTRACT_DRIFT")

    # -- Modes, determinism, state location ---------------------------------

    def test_worktree_and_revision_evaluation_agree_on_entries(self):
        self._write("src/tool.py", TOOL_PARAM_DRIFT)
        self._commit("drift the signature")
        from_revision = self._evaluate(
            base_rev=self.base_rev, target_rev="HEAD")
        from_worktree = self._evaluate(
            base_rev=self.base_rev, target_rev="WORKTREE")
        self.assertEqual(from_revision["entries"], from_worktree["entries"])

    def test_same_pair_produces_bit_identical_reports(self):
        self._write("src/tool.py", TOOL_PARAM_DRIFT)
        config = {"repo_root": str(self.repo), "workspace": str(self.workspace)}
        first = drift.evaluate(config, base_rev=self.base_rev,
                               target_rev="WORKTREE")
        digest_first = hashlib_sha(drift.report_path(str(self.workspace)))
        second = drift.evaluate(config, base_rev=self.base_rev,
                                target_rev="WORKTREE")
        self.assertEqual(
            hashlib_sha(drift.report_path(str(self.workspace))), digest_first)
        self.assertEqual(first, second)

    def test_baseline_roundtrip_governs_evaluation_without_base_rev(self):
        config = {"repo_root": str(self.repo), "workspace": str(self.workspace)}
        baseline = drift.collect_baseline(config, target_rev="HEAD")
        drift.pin_baseline(str(self.workspace), baseline)
        self.assertTrue(
            drift.baseline_path(str(self.workspace)).is_file())
        self.assertEqual(self._entry(drift.evaluate(
            config, base_rev=None, target_rev="WORKTREE",
            dry_run=True))["status"], "CURRENT")
        self._write("src/tool.py", TOOL_PARAM_DRIFT)
        report = drift.evaluate(config, base_rev=None,
                                target_rev="WORKTREE", dry_run=True)
        entry = self._entry(report)
        self.assertEqual(entry["status"], "CONTRACT_DRIFT")
        self.assertEqual(
            report["comparison_points"]["project_base"], "baseline-manifest")
        # The pinned baseline carries body tokens, so churn works without
        # re-reading a base revision: same signature, rewritten body.
        self._write("src/tool.py", TOOL_HEAVY_BODY)
        report = drift.evaluate(config, base_rev=None,
                                target_rev="WORKTREE", dry_run=True)
        self.assertEqual(self._entry(report)["status"], "SOURCE_DRIFT")

    def test_report_writing_respects_dry_run(self):
        config = {"repo_root": str(self.repo), "workspace": str(self.workspace)}
        report_path = drift.report_path(str(self.workspace))
        self.assertFalse(report_path.exists())
        drift.evaluate(config, base_rev=self.base_rev, target_rev="WORKTREE")
        self.assertTrue(report_path.is_file())
        written = report_path.read_bytes()
        drift.evaluate(config, base_rev=self.base_rev,
                       target_rev="WORKTREE", dry_run=True)
        self.assertEqual(report_path.read_bytes(), written)

    def test_engine_report_validates_against_the_drift_contract(self):
        self._write("src/tool.py", TOOL_PARAM_DRIFT)
        report = self._evaluate()
        gc.validate("drift", report)
        with_report = drift.evaluate(
            {"repo_root": str(self.repo), "workspace": str(self.workspace)},
            base_rev=self.base_rev, target_rev="WORKTREE")
        gc.validate("drift", with_report)

    def test_state_never_lands_inside_the_product(self):
        config = {"repo_root": str(self.repo), "workspace": str(self.workspace)}
        baseline = drift.collect_baseline(config, target_rev="HEAD")
        drift.pin_baseline(str(self.workspace), baseline)
        drift.evaluate(config, base_rev=None, target_rev="WORKTREE")
        self.assertFalse((self.repo / "drift").exists())
        self.assertTrue((self.workspace / "drift" / "doc-baseline.json").is_file())
        self.assertTrue((self.workspace / "drift" / "source-drift.json").is_file())

    def test_unknown_config_key_is_refused(self):
        with self.assertRaises(drift.DriftError):
            drift.evaluate({"repo_root": str(self.repo), "bogus": 1})


def hashlib_sha(path):
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
