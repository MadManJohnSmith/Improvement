# Operational usage of the framework

> **English first.** A Spanish translation of this document is kept at
> [usage.es.md](usage.es.md).

The framework has two layers with distinct roles:

1. **Automatic flow (layer 3.0, implemented and verified):** one command coordinates Creator,
   Host validation, backups, acceptance, activation and rollback. This is the end-user
   experience. Verified state in [status.md](status.md).
2. **Maintenance tools (MVP base):** scripts the maintainer uses to prepare trials, audit
   coverage and verify missions. They are neither the final experience nor defaults for new
   projects.

## One-time prerequisite (the owner's)

DSH installed and configured with at least one provider/model. The framework never reads,
copies or asks for API keys: the provider gate verifies configuration structure and variable
names, never values. If no authentication path works, the run stays recoverable with the cause
and a concrete action.

## The automatic flow: `bootstrap.py`

Generates and installs project-specific modes and skills:

```bash
python3 -B scripts/bootstrap.py install \
  --project /path/to/project \
  --launch-dsh
```

What it does:

1. preflights project discovery and DSH/provider availability, and prepares a clean external workspace (`<Project>-workspace/`);
2. prepares the run (`creator-runs/<generation-id>/`) with a versioned prompt and a snapshot of the skill library;
3. dispatches Creator: with `--launch-dsh` it stops previous DSH instances, frees the port,
   starts `dsh web` with the framework's overlay and supervises the single Creator session
   (bound to the workspace, grouped in the UI, no delegation); without that flag it reuses an
   existing authenticated DSH instance;
4. Creator generates `<Project>-auditor`, `<Project>-continuous-repair` and justified
   specific skills, selecting base library and catalogue first;
5. Creator invokes `bootstrap accept`; the Host validates in 10 layers, backs up, installs to
   staging, runs the deterministic acceptance and publishes the modes as user presets in DSH,
   verified via `agentPresets/list` before `ACTIVE`;
6. activates the set, or rolls back / `RETAINED`. Only the Host emits `ACTIVE`.

The user never copies prompts, JSON, paths, receipts or acceptance scenarios.

Other subcommands: `accept` (only invoked by Creator), `verify-acceptance` and `finalize` (Host
acceptance stages), `update` (regeneration on a material change), `uninstall` and `purge-data`.
Repeating `install` on a resumable run resumes the dispatch; on a Host-owned run it reports it
without re-dispatching.

The command orchestrates generation (Creator), Host prevalidation, transactional activation
(bundle, presets, capability plan, campaign plan), acceptance, and — if any step fails —
restoring the previous generation. Nothing reaches your repository without a verified stage.

### Run states

```text
CREATED → GENERATING → GENERATED → VALIDATING → BACKED_UP → STAGED → ACCEPTING → ACTIVE
                                    └→ RETAINED (with cause and concrete action) → ROLLED_BACK → RECOVERY_REQUIRED
```

Without an authenticated DSH session the run remains recoverable in `CREATED`/`PREPARED`, never
silently stranded. A denied write or schema conflict during generation is a finding to report,
not a reason to escalate permissions: the run workspace is writable in the current mode, and
Creator never sends `sandbox_permissions` or `justification`.

### How the generated modes behave

With `<Project>-auditor` and `<Project>-continuous-repair` active, use brief messages in the project:

- Full audit: “Audit this project completely; do not modify or publish.”
- Area audit: “Audit this flow, feature or component.”
- Repair all recorded findings: “Repair the audit findings; do not publish.”
- Repair by IDs: “Repair A-01 and M-02; do not publish.”

When a preset is selected, its first action must load the exact skill with the same name.
Auditor persists a bounded handoff in `<Project>-workspace/mode-state`. Repair does not derive
any worktree from the product: the Host provisions a shadow at
`<workspace>/candidates/repair-<digest16>` with **its own `.git`** and a receipt the mode only
verifies, and it edits/tests only through bash with the candidate as workdir. A simple prompt
does not authorize commit, merge or push: the change stays in the shadow with
`candidate_commit: null` and the diff digest recorded by the Host. Drift of canonical
HEAD/status, a declared base that is not an ancestor, or an inherited shadow without a receipt
produces `RETAINED` with no further action. This is contractual enforcement with regressions,
not mechanical isolation; there is no multi-file CAS/lease.

### The capability plan and `stack`

Repair can only record as evidence the command the project itself declares, and the Host fixes
that command at install into `<Project>-workspace/.dsh-managed/capability-plan.json`:

```bash
python3 -B scripts/bootstrap.py stack --project /path/to/project --workspace /path/to/project-workspace
```

It prints one line per detected stack. The CLI says `listo` when the declared command is
ready to run as written, or `falta <capability>` when something specific is missing; the plan
names exactly how to provision it, always outside the product.

Two properties of that plan worth knowing:

- **The command is named the way it can actually be run.** If your toolchain is outside the
  default `PATH` (a Flutter SDK in `~/.local/share`, a JDK in `/opt`), the plan names it by
  absolute path or by the workspace-local copy. A bare name the repairer's shell cannot
  resolve would turn a working suite into an unfair `BLOCKED`.
- **The sandbox decides what can be written.** `workspace-write` only allows writes inside the
  session tree. An SDK that rewrites itself on every run (Flutter seals its engine version in
  `bin/cache` on each call) needs a local copy: that is why the plan asks for it to be
  materialized at `<workspace>/.stack/<stack>/` with hard links, which cost no space and do not
  touch your original installation.

When something cannot run, the record is `BLOCKED`, naming the capability and its provisioning
step. There is never an invented `PASS` nor a hand-written substitute: a mock or a copy of the
product's code serves to investigate, not to verify.

### What "verified" means here

Verification runs **the product's own commands** from the Host capability plan
(`.dsh-managed/capability-plan.json`): its test entrypoint and, when the plan lists one, its
lint entrypoint. A mock, a hand-written harness or a copy of the product's code is not
evidence: the verdicts allowed are `PASS`, `FAIL` and `BLOCKED`, never a partial value and
never an unearned pass.

### Integration and space recovery (operator)

A simple prompt does not authorize commit, merge or push: the operator decides whether to
integrate. The candidate is a **shadow**, not a product worktree; it shares the base content,
but not the Git history. A shadow branch or commit **cannot be merged** into the product.
Review process, not an automatic application command:

1. Identify the candidate in the Host receipt and `mode-state`; check the canonical base, clean
   product and verdicts of the tests run. If there was drift or `RETAINED`, do not treat the
   result as verified.
2. Obtain a complete diff between the product content at that base and the shadow, including
   additions, deletions, renames, uncommitted and committed changes; exclude `.git` directories
   and artifacts not proposed. Inspect paths, binaries and patch content before applying.
   `shadow_candidate.diff_command` expresses the comparison without ancestry
   (`git diff --no-index --binary`), but its raw output over the roots may include `.git`
   metadata and path prefixes from both copies: it is not an apply-ready patch without review
   and normalization.
3. Compare the path list and content digest from the `candidate_diff_command` contract with
   the candidate **as it is now** and the verification record; that line is a digest and a JSON
   path list, **not the patch**. Do not use `shadow_candidate.patch_digest` as the identity of
   pending changes either: it computes a diff from `shadow-base` to `HEAD` and omits uncommitted
   changes. If the entire patch cannot be attributed to the verified tree, stop and re-verify.
4. Only after that review, prove the patch applies cleanly to the product, apply it under
   operator control, run the project's checks there and inspect the result before committing.
   Remote publication also requires an operator decision; use the repository's configured
   identity, never one forced by the command.

None of this deletes the shadow. `bootstrap.py state --retire` checks evidence of a shadow's
integration but returns **ABSTAINED** instead of deleting it or its receipt: there is no
exclusive inventory of all its content (including `.git/`) proving it disposable. Keep the
candidate and its evidence; eventual removal requires the operator to list and manually review
content and space (for example with `find` and `du -sh`) and decide outside `--retire`. For
legacy worktrees recorded outside `<workspace>/candidates/`, `--retire` checks identity and
integration and likewise abstains before deletion: ignored files and Git metadata are not
inventoried by a clean `git status`. Their removal is also a manual decision.

Size matters: every candidate is a full copy of the product, and several can accumulate until
the disk is full. **Earlier pilots did use product worktrees**, where `state --retire` ran
`git worktree remove` and `git branch -D` after prior checks; those instructions and that space
recovery (Syncify pilot: four integrated candidates, about 320 GB, two crashed Repair turns)
are measured history, not the current procedure.

Operator rule when integrating: commit and push using the identity configured for the
repository. In two pilots, seven commits were attributed to a name other than the repository's
and history had to be rewritten with `rebase --exec`/`--force-with-lease`, checking identical
trees and manually updating the SHAs noted in artifacts. The framework does not commit, so
this is the operator's responsibility.

### Deciding whether a library skill change gets in

```bash
python3 -B scripts/bootstrap.py skill-gate --baseline baseline.json --candidate candidate.json
```

Provide a file of per-scenario observations, `{"scenarios": {"SC-107": "PASS", ...}}`,
produced by a real run; this command does not execute scenarios, because running them against
an agent needs the runtime. The gate accepts a candidate only when holdout improves
**strictly**, rejects it if the training partition regresses even when holdout improves, and
abstains — neither accepts nor rejects — if the validation slice is not disjoint or there are
no observations. Partitioning derives from the `scenario_id` digest, so it is identical on
every run and a change cannot choose which scenarios judge it.

### When a session splits in two: what is known at startup

`mode-state` consists of five files, and replacing them takes five writes. A crash between
writes used to leave `findings.jsonl` saying one thing and `work-items.json` another unnoticed.
The framework now writes a marker before the first write of a unit and reconciles it at startup,
so a half-written unit is named rather than believed:

```bash
python3 -B scripts/bootstrap.py state --project <product>
```

A `state_commit` with `TORN` means split state and identifies **which file** is missing or
altered; `COMPLETE_UNCLOSED` means the unit wrote everything and died before closing, so the
marker is cleared and there is nothing to repair. **This is not atomicity** — there are still
five writes — but detection and recovery without putting the entire log on every read's hot
path.

### What the framework already knows about your project

`mode-state/episodes.jsonl` stores one entry per closed unit, and `episodes-index.json`
answers “has this already been fixed?” in O(1). Two rules make it useful instead of duplicating
the ledger: the signature is the finding's **fingerprint**, not its wording, and **only a
verified fix is remembered**, since remembering a failed attempt teaches the next session to
repeat it. Only the Host writes the entry; **lookup does not depend on the mode doing it**:
`workflow_write` computes the fingerprint of the excerpt it will anchor, checks the index,
and, if present, stamps `evidence.prior_episode` with the unit that closed it and the fix that
worked. A mode writing that field is rejected, because the claim “my defect is already fixed”
cannot come from it. A missing index is empty memory; an existing unreadable one fails closed.
`bootstrap.py state` counts `OPEN` findings with `prior_episode` in `repeats`: that number is
not a ledger failure, but a prevention failure where a fix had worked.

### The candidate is a shadow repository, not a worktree

A `git worktree` keeps its index and HEAD in the `.git/worktrees/` of the **product**, so with
the product read-only —which is what the sandbox imposes— even `git add` fails inside the
candidate. That is why the candidate is created at `<workspace>/candidates/repair-<digest16>`
with **its own `.git`**: a single writable root covers candidate and state, and the product
stays truly read-only. Integration is **no longer a branch to merge**, because a shadow has no
ancestry with the product: what is produced is a diff/patch, and you decide whether to apply it.

This is the **current** state. In earlier pilots worktrees were used and integration there was
`git merge --ff-only` of the candidate branch and cleanup went through `state --retire`.

### Compiling the corpus and tying the gate to what was measured

The older `skill-gate` accepts a loose map: it does not know which corpus produced those
observations nor which candidate they belong to, so the same JSON serves two different runs.
For a publication decision use the bound path, which does check identities:

```bash
python3 -B scripts/bootstrap.py compile-corpus --output /external/path/corpus.json
python3 -B scripts/bootstrap.py bound-skill-gate --corpus /external/path/corpus.json \
  --baseline /external/path/baseline.json --candidate /external/path/candidate.json \
  --baseline-digest <sha256> --candidate-digest <sha256> --report /external/path/report.json
```

`compile-corpus` turns the 55 scenarios in `library/` into executable cases: `task`, fixture
and `evaluated_claim`, with `target` pointing at the skill. **The expected verdict does not
travel in the public case** —it is derived in the Host and used only when the recalculated
`corpus_digest` matches the declared one, so a corpus edited after compiling is rejected
instead of scored—. Every observation is bound to corpus, candidate and compiler version,
must be complete and unique, and an `unavailable` provider cannot declare them: here the gate
abstains. To tie this to a commit or a CI:
```bash
python3 -B scripts/bootstrap.py skill-gate-commit-check --changed-path library/base/... \
  --report /external/path/report.json --corpus-digest <sha256> --candidate-digest <sha256>
```
It fails closed if the change touches the corpus or the gate and the report does not accept it.
**An `abstain` blocks just like a `reject`**: an abstention is not permission. Changes that do
not touch the corpus are not blocked, because a gate that blocks everything stops being read.

### Running the corpus without repeating what was already rejected

```bash
python3 -B scripts/bootstrap.py skill-gate-run --corpus /external/path/corpus.json \
  --mode <project>-auditor --candidate-digest <sha256> --output /external/path/obs.json 2>/external/path/abstain.json
python3 -B scripts/bootstrap.py bound-skill-gate ... --buffer /external/path/reflection.jsonl
python3 -B scripts/bootstrap.py skill-gate-reflect --buffer /external/path/reflection.jsonl \
  --corpus-digest <sha256>
```

The sequence is `compile-corpus` → `skill-gate-run` (today: `ABSTAINED` with no exception,
see below) → `bound-skill-gate` **only if** a real verified Host evaluator produced complete
bound observations for baseline and candidate. Every path is external to the repository.

The contract `skill-gate-run` declares —and today cannot fulfil, see below— is to dispatch each
compiled case against a real mode and write observations bound to corpus, candidate and
compiler version; the evaluator prompt does not carry the expected verdict, a case that could
not run comes back `NOT_COVERED` with its reason, never an assumed `PASS`. And **the file is
written to `--output`**, not `--observations`: that flag does not exist in the CLI.

**Today the procedure ends in ABSTAIN before spending on a session.** The runner requires a
compatible Host evaluator adapter that, before creating any session, verifies two things the
CLI's operational preset cannot: the per-case compatible cwd (the corpus needs a fresh `cwd`
per case while an operational preset has a fixed session root) and the effective availability
of the target skill across the corpus's 25 targets (appearing in the roster proves the skill
exists, not that a live mode can invoke it). Without that adapter the command abstains naming
the missing piece and **does not create the session**; the reply is the same one the launcher
uses to say DSH is missing, so two different causes cannot hide behind the same silence.

With `--buffer`, a rejection is recorded with its holdout score before and after, and
**re-submitting an already rejected candidate against that same corpus is refused without
scoring it**: the same bytes over the same corpus cannot score differently, and doing so would
cost a full agent run to receive the same answer. `skill-gate-reflect` returns the summary the
next attempt must read. A rejection from another corpus does not apply: it answered a different
question.

### Seeing what a mission cost, and what was never recorded

```bash
python3 -B scripts/bootstrap.py metrics --mission /external/path/mission
```

Verifies the ledger chain (`events.jsonl` with a digest per event and a global one) and
aggregates what was recorded. What was never recorded is reported `NO_DISPONIBLE`, **never
zero**: zero would claim the mission cost nothing. A mission without a ledger returns
everything as `NO_DISPONIBLE` with `events: 0`. A tampered ledger returns no total at all.

### Service commands, off the user's path

These exist and have their own regression, but the normal flow does not call them:
`bootstrap.py` uses them as a library. They are documented so nobody discovers a second door
by accident.
- `missions.py reaudit` — re-runs the semantic audit of a closed unit (`verify` verifies the
  result; `reaudit` looks at the product again).
- `audit.py archive` — archives a finished cycle; `inventory` and `consolidate` live in
  [audit-contract.md](audit-contract.md).
- `transaction.py install|rollback|uninstall` — the transaction's low-level surface
  (verified backup, staging, swap and restore). The user's path is `bootstrap.py`.

### Running a deterministic workflow (the Host executor)

A workflow is a plan of steps the Host executes mechanically; no agent writes it and no prompt
improvises it:

```bash
python3 -B scripts/bootstrap.py workflow run /path/to/plan.json \
  --run-root /external/path/run
```

Each `ask` step gets its own DSH session with its own reasoning level, and every gate, verdict
and joint is decided by the Host from recorded evidence. A step whose evidence does not hold
stops the run with a cause instead of being assumed.

### When state and repository stop agreeing (operator)

The command without `--retire` or `--repoint` is a report and changes nothing:

```bash
python3 -B scripts/bootstrap.py state --project <product-path>
```

It names three discrepancies state alone cannot see:

- an integrated head that history rewriting (`commit --amend`, `rebase`, force push) removed
  from the canonical branch, with `integrated_head_rewritten` and the current revision; to
  correct the record manually, `--repoint <revision>` accepts only a revision Git proves is
  an ancestor of canonical HEAD with a clean product and leaves a receipt in `overflows.jsonl`;
- findings the ledger still calls `OPEN` while their work item is `VERIFIED`
  (`closed_findings`): a finding moves to `RESOLVED` when a later audit observes the fix, so
  in between the queue offers work already done;
- `OPEN` findings no handoff ever took (`uncovered_findings`).

It also reports `anchors`: how many findings have evidence anchored to a line the tool found
by citing a literal excerpt appearing exactly once in the file, and how many do not. A finding
without an anchor is not a defect: an architecture or a missing capability has no line. The
number honestly measures how much of the queue can be verified without opening the product.

## Maintenance tools (MVP layer)

For framework maintenance or controlled pilots supervised by the maintainer.

### Preparing a trial with `onboard.py`

Clone the framework alongside the project, never inside it:

```text
parent/
├── Improvement/            # framework (this repository)
├── project/
└── project-workspace/
```

```bash
python3 -B scripts/onboard.py \
  --project /path/project \
  --workspace /path/project-workspace \
  --name my-project \
  --prepare-skills \
  --session-root /path/parent

# review the dry-run, then repeat with --init
```

Identical repetition does not write. Conflicts block. `--update-skills` requires explicit
authorization and makes a complete external backup per skill before replacement; it neither
merges nor deletes foreign skills. This operational backup is not the layer 3.0 generational
transaction.

The parent root must not have an ambiguous Git ancestor or be mutable by third parties. Managed
links serve the skill loader; they grant no permissions and create no sandbox. One workspace
per parent.

### Audit coverage with `audit.py`

`inventory` and `consolidate` check inventory, partition and declared states; they are neither
a semantic auditor nor a permission control. Full contract in
[audit-contract.md](audit-contract.md).

### Verifying missions with `missions.py`

`task.json` v1 records mode/objective/authorization_ref, root/files/base/change_scope,
executor/criteria and commands/`timeout_seconds`/limits/exclusions; `result.json` v1 links the
task hash, candidate hashes, status/reason, findings and check/QA for repair. The limit field
is called **`timeout_seconds`**, not `timeout`: the mandate compares `--timeout` against
`task.timeout_seconds`, so a `task.json` with `timeout` is rejected with «Comando o timeout
fuera del mandato» even when the command itself is legitimate.

```bash
python3 -B scripts/missions.py run-check \
  --task /path/task.json --output /path/check-1 \
  --timeout 60 -- /path/python -B test.py

python3 -B scripts/missions.py verify \
  --task /path/task.json --result /path/result.json
```

`verify` proves documentary integrity, not authenticity, semantics or authority. QA and a later
audit are still necessary.

`missions.py` checks that a closed mission's evidence still holds against the repository it
claims to describe.

## What not to do

- Do not load or recreate generic presets/modes that were removed; they exist only in Git.
- Do not present Standard or the Syncify/RehabWeb presets as the final experience: they are
  fixtures.
- Do not use shell, cwd or links to circumvent permissions.
- Do not modify the framework during an operational mission; proposals are returned or applied
  in a separate maintenance mission.
- Do not publish or integrate without the owner's mandate.
- Do not run the framework's commands against a production repository without a backup.
- Do not import a real project's mode-state into this repository: it is evidence, not source,
  and it does not belong in the canonical tree.

## Security

- Product and framework are read-only during generation and audit; repair happens only in the
  authorized candidate/branch.
- No new providers, models or routing from artifacts; no secrets in prompts, argv or artifacts.
- No implicit remote publication; do not run scripts suggested by the product without
  authorization.
- A declared `AUTHORIZED` state does not grant permission. Lack of evidence is `UNVERIFIED`,
  not `PASS`.
- Configuring a provider in DSH does not authorize the framework to read its API key.

The framework never reads, copies or transmits API keys. The provider gate checks
configuration structure and variable names only. The sandbox channel forbids escalation and a
denial becomes `RETAINED` with no retry.

## References

- [status.md](status.md) — verified state
- [audit-contract.md](audit-contract.md) — local audit coverage contract
- [creator-preset-spec.md](creator-preset-spec.md) — generational Creator contract
- [setup-dsh.md](setup-dsh.md) — DSH preparation
- [progreso-agentico.md](progreso-agentico.md) — one-page milestone progress
- [../ARQUITECTURA_FLUJO_AGENTES.md](../ARQUITECTURA_FLUJO_AGENTES.md) — normative architecture
- [../CHANGELOG.md](../CHANGELOG.md) — changes
- Spanish version: [usage.es.md](usage.es.md)
