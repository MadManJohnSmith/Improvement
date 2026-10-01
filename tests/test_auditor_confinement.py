"""The auditor's read-only frontier, measured against the real DSH runtime.

D2 asked for kernel enforcement instead of a contractual rule, and the
recorded blocker said it was impossible: `read-only` denies every `ctx.fs`
mutation, and the auditor persists its findings through the write tool, so it
would audit and never record. That premise was wrong, and this module is the
evidence.

The runtime's `writableRoots()` carries exactly one configurable root. Root
that root at the *workspace* instead of the session root and the product, which
is a sibling of the session cwd, falls outside it: bash and `ctx.fs` both get
a real EROFS, while the state the auditor must write stays writable. The
regression that matters is therefore not "the policy is read-only" but "the
product is unwritable and the state is writable, in the same run".

These cases skip without a runtime, and a skip is the absence of proof: the
number of live cases is asserted by the suite so a silent skip cannot pass as
green.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

JS = r'''
import {existsSync, readFileSync, writeFileSync, mkdirSync} from 'node:fs';
const load = name => import(`${process.argv[2]}/@deepseek-ai/${name}/lib/index.js`);
const {Context} = await load('cordis');
const SESSION = process.argv[3];
const WORKSPACE = `${SESSION}/workspace`;
const PRODUCT = `${SESSION}/product`;
const CANDIDATE = process.argv[4];

const ctx = new Context();
for (const [name, config] of [
  ['dsh-session-projection', {}],
  ['dsh-sandbox-policy', {mode: 'workspace-write', workspaceRoot: WORKSPACE}],
  ['dsh-sandbox-local', {}], ['dsh-subprocess-local', {}],
  ['dsh-fs-sandbox', {cwd: SESSION}],
  ['dsh-bash-sandbox', {cwd: SESSION, timeoutMs: 5000}],
]) await ctx.plugin((await load(name)).default, config);

const {writableRoots} = await load('dsh-sandbox');
const policy = ctx.sandboxPolicy.resolve({});
const out = {policy, writableRoots: writableRoots(policy)};
const run = async command => {
  const request = ctx.shell.resolve({command, sandboxPolicy: policy});
  return typeof ctx.shell.run === 'function'
    ? await ctx.shell.run(request)
    : await (await ctx.shell.execute(request)).result();
};

// An auditor that cannot read the product is not an auditor.
const read = await run(`cat ${PRODUCT}/source.txt`);
out.readProduct = {exitCode: read.exitCode, text: (read.stdout.text || '').trim(),
                   stderr: (read.stderr.text || '').trim()};

// Writing the product must fail at the kernel, not at a rule in a prompt.
const write = await run(`printf CLOBBERED > ${PRODUCT}/source.txt`);
out.writeProduct = {exitCode: write.exitCode, stderr: (write.stderr.text || '').trim()};
out.productContent = readFileSync(`${PRODUCT}/source.txt`, 'utf8');

// The state the auditor must persist has to stay writable.
const state = await run(`printf '{"finding":1}\\n' > ${WORKSPACE}/mode-state/findings.jsonl`);
out.writeState = {exitCode: state.exitCode, stderr: (state.stderr.text || '').trim()};
let fsState = null;
try {
  await ctx.fs.writeText(await ctx.fs.resolve(`${WORKSPACE}/mode-state/fs-findings.jsonl`),
                         '{"f":1}\n', undefined, undefined, policy);
  fsState = {allowed: true};
} catch (error) { fsState = {allowed: false, error: String(error).slice(0, 200)}; }
out.fsWriteState = fsState;
let fsProduct = null;
try {
  await ctx.fs.writeText(await ctx.fs.resolve(`${PRODUCT}/fs-clobber.txt`),
                         'x', undefined, undefined, policy);
  fsProduct = {allowed: true};
} catch (error) { fsProduct = {allowed: false, error: String(error).slice(0, 200)}; }
out.fsWriteProduct = fsProduct;

// Descendants inherit the frontier; a subshell is not an escape hatch.
const descendant = await run(`/bin/sh -c "printf CLOBBERED > ${PRODUCT}/source.txt"`);
out.writeProductDescendant = {exitCode: descendant.exitCode,
                              stderr: (descendant.stderr.text || '').trim()};
out.productContentAfterDescendant = readFileSync(`${PRODUCT}/source.txt`, 'utf8');

// Candidate provisioning writes into the product's .git, which is now read-only.
// git's own status, not a pipeline's: `| tail` would report tail's exit code.
const worktree = await run(
  `git -C ${PRODUCT} worktree add ${CANDIDATE} -b probe; echo "git_exit=$?"`);
out.worktreeAdd = {exitCode: worktree.exitCode,
                    text: ((worktree.stdout.text || '') + (worktree.stderr.text || '')).trim()};

writeFileSync(process.argv[5], JSON.stringify(out));
'''


def _runtime():
    return os.environ.get("DSH_MODULE_ROOT") or ""


def _node_modules(root):
    # DSH_MODULE_ROOT already points at the node_modules directory itself, the
    # same convention the rest of the suite uses to resolve @deepseek-ai/*.
    return Path(root)


@unittest.skipUnless(_runtime() and _node_modules(_runtime()).is_dir(),
                     "needs DSH_MODULE_ROOT with an installed runtime")
class AuditorConfinementTest(unittest.TestCase):
    """What the kernel does to the product, with the policy rooted at the workspace."""

    def setUp(self):
        # Not /tmp: the sandbox remounts every writable root, and /tmp is one of
        # them, so a session living there is invisible from inside the sandbox.
        # That is a property of the deployment, not of the test, so the test
        # reproduces a deployment instead of an accident.
        base = Path(os.environ.get("DSH_CONFINEMENT_BASE")
                    or Path.home() / ".dsh-confinement")
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(prefix="session-", dir=base))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.session = self.tmp / "session"
        self.product = self.session / "product"
        self.state = self.session / "workspace" / "mode-state"
        self.product.mkdir(parents=True)
        self.state.mkdir(parents=True)
        (self.product / "source.txt").write_text("product sentinel\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", "."], cwd=self.product, check=True)
        subprocess.run(["git", "add", "-A"], cwd=self.product, check=True)
        subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c",
                        "user.name=t", "commit", "-qm", "init"],
                       cwd=self.product, check=True)
        self.out = self.tmp / "out.json"
        script = self.tmp / "probe.mjs"
        script.write_text(JS, encoding="utf-8")
        finished = subprocess.run(
            ["node", str(script), str(_node_modules(_runtime())), str(self.session),
             str(self.tmp / "candidate"), str(self.out)],
            capture_output=True, text=True, timeout=300)
        self.assertEqual(finished.returncode, 0, finished.stderr[-3000:])
        self.report = json.loads(self.out.read_text(encoding="utf-8"))

    def test_the_policy_admits_exactly_one_configurable_root(self):
        # This is the constraint the whole design turns on: root it at the
        # workspace and the product is outside; the runtime offers no way to
        # admit a second root, which is what leaves the repairer unresolved.
        roots = self.report["writableRoots"]
        self.assertEqual(self.report["policy"]["mode"], "workspace-write")
        self.assertEqual(self.report["policy"]["workspaceRoot"],
                         str(self.session / "workspace"))
        self.assertIn(str(self.session / "workspace"), roots)
        self.assertNotIn(str(self.product), roots)
        self.assertEqual([r for r in roots if r not in ("/tmp",)], roots[:1])

    def test_the_auditor_can_still_read_the_product(self):
        self.assertEqual(self.report["readProduct"]["exitCode"], 0,
                         self.report["readProduct"])
        self.assertEqual(self.report["readProduct"]["text"], "product sentinel")

    def test_bash_cannot_write_the_product_and_the_kernel_says_so(self):
        self.assertNotEqual(self.report["writeProduct"]["exitCode"], 0)
        self.assertRegex(self.report["writeProduct"]["stderr"],
                         r"(?i)read-only file system|EROFS|permission denied")
        self.assertEqual(self.report["productContent"], "product sentinel\n")

    def test_a_descendant_process_inherits_the_frontier(self):
        self.assertNotEqual(self.report["writeProductDescendant"]["exitCode"], 0)
        self.assertRegex(self.report["writeProductDescendant"]["stderr"],
                         r"(?i)read-only file system|EROFS|permission denied")
        self.assertEqual(self.report["productContentAfterDescendant"],
                         "product sentinel\n")

    def test_the_write_tool_cannot_reach_the_product_either(self):
        self.assertFalse(self.report["fsWriteProduct"]["allowed"],
                         self.report["fsWriteProduct"])
        self.assertFalse((self.product / "fs-clobber.txt").exists())

    def test_the_auditor_can_still_persist_its_findings(self):
        # The premise that blocked D2: confining the product also denies the
        # state write, and the auditor would audit and never record. Measured.
        self.assertEqual(self.report["writeState"]["exitCode"], 0,
                         self.report["writeState"])
        self.assertTrue(self.report["fsWriteState"]["allowed"],
                        self.report["fsWriteState"])
        self.assertTrue((self.state / "findings.jsonl").is_file())
        self.assertTrue((self.state / "fs-findings.jsonl").is_file())

    def test_candidate_provisioning_is_what_this_prices_out(self):
        # `git worktree add` registers the worktree in the product's .git, so a
        # confined session cannot provision its own candidate. Recorded as the
        # measured reason the repairer stays contractual, not as a guess.
        self.assertIn("git_exit=255", self.report["worktreeAdd"]["text"],
                      self.report["worktreeAdd"])
        self.assertRegex(self.report["worktreeAdd"]["text"],
                         r"(?i)read-only file system")


if __name__ == "__main__":
    unittest.main()
