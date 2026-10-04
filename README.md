# Improvement

**English** | [Español](README.es.md)

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE) [![Status: beta](https://img.shields.io/badge/status-beta-orange)](docs/plans/10-lanzamiento-publico.md) [![tests](https://img.shields.io/github/actions/workflow/status/MadManJohnSmith/Improvement/ci.yml?label=tests)](https://github.com/MadManJohnSmith/Improvement/actions/workflows/ci.yml) [![version](https://img.shields.io/github/v/release/MadManJohnSmith/Improvement?include_prereleases&sort=semver&label=version)](https://github.com/MadManJohnSmith/Improvement/releases)

**An auditor and a repairer that live next to your repository: they find the real
defects, fix them verified against your own tests, and leave the commit and the push in
your hands.**

If you maintain a live project, this sounds familiar: the same class of bug comes back
every few weeks, a deep audit is always left for tomorrow, and the why behind each fix
lives in the head of whoever made it. Improvement turns that routine into a cycle with
memory: you talk to it in one-line prompts, the framework does the heavy lifting, and you
decide what gets integrated.

On install, it generates **two modes tailored to your project**. The **auditor** examines
the code and records every finding with its evidence (`file:line`) and its severity. The
**repairer** fixes things in an isolated worktree, verifies every fix against your
project's real commands, and leaves your tree intact. Nothing reaches your branch without
going through you.

It is a framework proven in three full campaigns on real repositories: Syncify (a music
app in Rust/Tauri/Vue), RehabWeb (a clinical app in Django/Vue), and LoboApp (a Flutter
app, with the framework installed from a GitHub clone). The metrics below come from those
campaigns, not promises.

## Quick start

### What is DSH?

Improvement does not bring its own AI: it works on top of **DSH (DeepSeek Harness)**,
DeepSeek's open source agent runtime (MIT license, more than 240,000 stars on GitHub).
Its architecture is *everything is a plugin*: models, tools, skills, sessions, and the
sandbox compose as plugins. It runs on your machine and opens a local web app in the
browser (`npx @deepseek-ai/dsh web`); its
[documentation](https://deepseek-harness.github.io/deepseek-harness/) tells the rest. It
is in *developer preview* and iterates fast.

Improvement installs into DSH the two modes generated for your project, as agent presets:
it is the app where you talk to them. Your provider credentials live in DSH; Improvement
never reads them or asks for them, it only checks that the provider you configured
exists.

### Requirements

Linux, `git`, and Python 3, plus [DSH](docs/setup-dsh.md) already configured with at
least one provider/model of your own. Nothing else.

Clone the framework **next to your project, never inside it**, and run one command:

```bash
git clone https://github.com/MadManJohnSmith/Improvement.git
cd Improvement
python3 -B scripts/bootstrap.py install \
  --project /path/to/your/project \
  --launch-dsh
```

That discovers your project, generates `<YourProject>-auditor` and
`<YourProject>-continuous-repair` with their skills, validates the package in 10 layers,
backs up, installs, and activates; if anything fails, it rolls back leaving a recoverable
state. Your product is not touched during installation.

## The problem it solves

In long-lived projects, auditing and repair become hard for three reasons: context fills
up, errors happen again because nobody remembers the previous one, and every fix is done
with different criteria. Improvement puts that into a structure that survives the cycles:

- an **auditor** that examines your project and persists findings with evidence
  (`file:line`), severity, and deduplication by `(finding, revision)`;
- a **repairer** that takes the findings, claims an isolated work candidate in a sibling
  worktree, fixes it, verifies it, and **leaves your product's tree intact**;
- a **memory on disk** (`<project>-workspace/mode-state`) with strict caps per file and
  per record: it grows up to its limit and compacts, it does not saturate;
- a **clear integration boundary**: the mode leaves the verified candidate and you make
  the commit and the push. Nothing reaches your branch without going through you.

## Where the modes come from

The two modes do not come out of an empty template: on every install they are composed
from a **skills library** with recorded provenance. The base is 21 immutable skills —
test-driven development, systematic debugging, security hardening, code review, writing
plans…— reimplemented with MIT attribution. On top, 4 specialized catalog patterns that
activate only on signals observed in your project: static review of IAM policies,
security HTTP headers verification, FastAPI OpenAPI contract checks, and WCAG 2.2
accessibility. Behind them stand 45 pinned external sources — skill repositories, W3C
standards, AWS and MDN guides — with URL, revision, and license recorded for each one.

Creator selects following a mandatory order: first a base skill; then a catalog pattern,
only if its signal really appears in your repo; then compositions; and only as a last
resort a brand-new extension, which has to demonstrate the previous layers do not apply.
Every reuse is declared, and the Host verifies it against the library snapshot frozen
with its digest at install time: what your mode reuses is exactly what the digest signed,
not a version that drifted afterwards. This is the flow that generated the modes of
RehabWeb, LoboApp, and the framework itself.

**The library improves on evidence, not on opinions.** Its 55 scenarios compile into
executable cases whose expected verdict only the Host knows. No base-skill change gets in
without scoring on a gate that only accepts strict improvement: rejected attempts are
kept with their before/after scores, and the reason for the rejection feeds the next
attempt, so the framework never pays twice for the same correction. The executor is
`bootstrap.py skill-gate-run`: against a DSH session with your project, the full loop is
in your hands — use the modes, produce observations, the gate scores, the library can
only get better.

## How to use it

### Simple prompts

With the two presets active in DSH, you operate with short messages:

| You want… | You write |
|---|---|
| Audit everything | «Audita completamente este proyecto; no modifiques ni publiques.» |
| Audit one area | «Audita este flujo, característica o componente.» |
| Repair what was audited | «Repara los hallazgos de la auditoría; no publiques.» |
| Repair specific findings | «Repara A-SEC-01 y A-SEC-02; no publiques.» |

Every audit leaves a handoff with the next prompt ready to copy. When the repairer
finishes, you integrate with a normal `git merge --ff-only`: the commit and the push are
still yours.

![The operating cycle: audit, repair, integrate](docs/diagrams/ciclo-operativo.png)

*The full cycle, including the learning close-out: each campaign's observations score the
library at the holdout gate. It is an explorable diagram: every relationship can be
traced, and the theme switches light/dark, in the [interactive version](https://madmanjohnsmith.github.io/Improvement/diagrams/ciclo-operativo.html).*

## Terms you will see

| Term | What it is |
|---|---|
| DSH (DeepSeek Harness) | DeepSeek's open source agent runtime, where the two modes and your provider credentials live. |
| Mode | Each of the two agents generated for your project: the auditor and the repairer. |
| Finding | A defect recorded with evidence (`file:line`), severity, cause, and prevention. |
| Handoff | The record every audit leaves behind, with the next prompt ready to copy. |
| Candidate | The isolated sibling worktree where the repairer changes code. |
| `mode-state` | The workspace's on-disk memory: findings, handoffs, verifications, and receipts. |
| Capability plan | The inventory of your project's real test and analysis commands, signed at install. |
| RETAINED | A retained turn: it ended with a readable result and without stepping outside the contract. |
| VERIFIED / RESOLVED | The verified work and the closed defects, each with its evidence. |
| Skills library | The 21 immutable base skills the modes are composed from, with executable scenarios and recorded sources. |
| Evidence anchor | The literal code snippet that pins where a finding lives; the tool computes the location and rejects what it cannot place. |
| Holdout gate | The lock that scores any library change against executable cases and only accepts strict improvement. |

## Verification against your real project, never with stubs

On install, Improvement reads your project and writes a **capability plan** to
`<project>-workspace/.dsh-managed/capability-plan.json`: which technologies make up your
project (monorepos included), which **test and analysis commands belong to each one**,
and whether this machine already has what it takes to run them.

That plan is the only evidence the repairer can record. An invented command, a mock, or a
copy of the product's code is investigation material, never a result. If the command
cannot run because a tool is missing, the record is `BLOCKED`, naming exactly what is
missing and how to install it; never an invented `PASS`.

```
stacks:
  dart-flutter  listo  (/home/your-user/.local/share/flutter/bin/flutter test)
  java-gradle   falta java   (instalar un JDK 17+ fuera del producto y anteponerlo al PATH)
```

The plan's own output is Spanish, like the rest of the framework: `ready` is
`listo`, and a missing tool is reported as `falta <capability>` — never an invented
`PASS`.

A detail the beta uncovered the hard way: if the tool is installed but outside the
default `PATH`, the plan names it **by its absolute path**. A bare name that the mode's
shell cannot invoke turns a working suite into a false `BLOCKED`.

A finding's evidence is verifiable, not prose. A finding can anchor its location with a
**literal code snippet** (`path` + `excerpt`): it is the write tool that locates the
snippet and computes the line, and if the snippet is absent, or appears more than once,
the write **is rejected** instead of guessing — an anchor that cannot be placed is an
anchor pointing at the wrong line. `bootstrap.py state` reports how many findings are
anchored and how many are not.

Memory consults memory: when a finding is persisted, the episode index is checked, and if
that exact signature was closed before, the record carries `prior_episode` with the unit
that closed it and the fix that worked. `bootstrap.py state` counts the **repeats**: a
prevention that failed is a different defect from the first one.

### Stacks proven and stacks declared

| Stack | Verification | Status |
|---|---|---|
| Rust | `cargo test`, `cargo clippy` | **proven** — Syncify, CI green in 3 jobs |
| Django | `python manage.py test`, `django check` | **proven** — RehabWeb, 108 real tests |
| Flutter | `flutter test`, `flutter analyze` | **proven** — LoboApp, 166 real tests |
| Python | `pytest -q`, `compileall` | **proven** — the framework on itself |
| Node · Bun · Deno | `npm test` · `bun test` · `deno test` | declared |
| Go | `go test ./...`, `go vet ./...` | declared |
| Java · Scala: Maven · Gradle · Android · sbt | `mvn test` · `./gradlew test` · `./gradlew testDebugUnitTest` · `sbt test` | declared |
| .NET · PHP · Ruby | `dotnet test` · `vendor/bin/phpunit` · `bundle exec rspec` | declared |
| Swift · C/C++ (CMake) · Meson | `swift test` · `ctest` · `meson test` | declared |
| Elixir · Erlang · Clojure · Perl | `mix test` · `rebar3 eunit` · `clojure -M:test` · `prove` | declared |
| Zig · Crystal · Nim · Julia · R | `zig build test` · `crystal spec` · `nimble test` · `Pkg.test()` · `R CMD check` | declared |
| Haskell (Cabal · Stack) · OCaml (Dune) | `cabal test` · `stack test` · `dune runtest` | declared |

The twenty-six declared ones are the beta's real gap: the plan resolves their command just the
same, and if a tool is missing the result is `BLOCKED` naming it — never an invented
`PASS`. Exercising them on real repositories is exactly what the beta exists for. The
complete table, one row per stack, is in the [verified status](docs/status.md).

## Real-world cases

### Syncify: from red CI to green CI

A music app (Rust/Tauri/Vue) with a failing suite. Over the campaign, the modes found and
fixed real defects, not only test ones: a WebP validator that rejected legal files, an
album count that tagged a 10-track disc as a 1-track one, a SQLite deadlock that hung the
CI at 0% CPU, a download bridge that signed requests with an empty secret.

| Metric | Result |
|---|---|
| Distinct findings persisted | 77 (114 records with their history) |
| Verified work | 78 VERIFIED items |
| Verifications persisted | 67 (61 PASS, 6 declared BLOCKED) |
| Commits generated by the modes and integrated | 15 |
| Result | CI green in all 3 jobs (Rust, frontend, Python) |

### RehabWeb: 45 security findings, a six-word prompt

A clean install from start to finish with a single command. The first audit found
**45 findings (6 CRITICAL, 16 HIGH, 23 MEDIUM)**, among them: any authenticated user
could read the clinical history of the entire population, and one patient could rewrite
another's diagnosis. The prompt «Repara A-SEC-01 y A-SEC-02; no publiques.» produced the
fix for both, with its regression test (3 files, 220 lines), without touching the
product's tree until integration.

### LoboApp: the campaign that actually found the limits

A Flutter app (Android) installed **from a GitHub clone of the framework**, on a freshly
cloned product with no prior contamination: exactly the scenario a tester walks into. The
audit with a simple prompt persisted 9 findings (1 CRITICAL, 2 HIGH, 4 MEDIUM, 2 LOW).

The CRITICAL was a broken promise: the privacy notice said that logging out erases from
the device what you saved, but the code only removed one key; progress and notes were
still there and reappeared when you logged back in. «Repara F-01 y F-02; no
publiques.» produced the fix with its regression tests in 7 files and 353 lines,
verified with **a real `flutter test`** (125 tests green) and `flutter analyze` with no
issues, and integrated with `bb01cba..eb25ec3`: commit, fast-forward, and push by the
operator.

This campaign found the two failures no synthetic test would have seen: the framework
emitted a verification command its own shell could not execute, and the sandbox left the
SDK mounted read-only while the tool rewrites itself on every run. Both are fixed, with
regression tests, and they are the reason verification is real instead of declarative.

The campaign ran to the end. The 9 findings were fixed and integrated across four turns,
each one verified with a real `flutter test`; the follow-up re-audit confirmed the 9 as
**RESOLVED** with evidence and found 5 more, which were also fixed. At the end:
**14 findings, 166 Flutter tests green**, and four commits integrated with
`bb01cba..4c0bb30`. Among them, a finding the previous fix had created: when comparing
namespaces, a legacy backup without a namespace stopped being restored.

### The framework itself

Installed on a clone of itself, the auditor found 7 real framework defects (2 HIGH,
5 MEDIUM) and the repairer fixed all of them with their tests: limit-based compaction
discarded records **without a receipt** (the silent loss G3 was supposed to have closed
and only half covered); the write tool did not confine managed state to its root, leaving
the auditor's read-only boundary resting only on a later `git status`; the validator's
`graph` layer checked nothing; the `lifecycle` layer skipped the per-role contract; the
G7 gate read the capability plan without checking its signature; and `install` only
linked the Host verdict to the candidate when it received a path.

The framework's re-audit confirmed the seven as **RESOLVED** and found the most
uncomfortable one of all: **a verification result did not identify the tree it
verified**. The contract forbids committing a candidate, so the verified tree is a dirty
worktree whose HEAD is still its base and the fix lives in the uncommitted diff;
`candidate_head` does not distinguish it from the revision before the fix. Measured on
the real state, the seven records carried two heads, both older than the changes they
claimed to verify. Now every record carries the digest of the verified diff and three
places check it.
The framework's own suite at that point: **743 tests green**.

The memory applies to itself too: the hardening units were born from the pilots'
failures (claiming a candidate before editing, reconciliation without an operator,
mechanical anti-escalation, documented candidate retirement, a stale base that re-anchors
by testing kinship…), and an audit of the memory itself discovered a silent loss of
records in the preflight, fixed with a regression test. The memory's second audit found
that the register of already-closed defects **was written and nobody read it**: the
documentation said the auditor consulted it and no product path did, so the same defect
came back every session. Now the consultation is mechanical and `bootstrap.py state`
counts the repeats.
Framework suite: **777 tests green**.

## What you get in your repo

![What Improvement installs on your machine](docs/diagrams/arquitectura-instalacion.png)

*The provenance-tracked library feeding generation, the anti-escalation guard, the two
generated modes, the bounded memory, and the integration boundary. Also
explorable: [interactive version](https://madmanjohnsmith.github.io/Improvement/diagrams/arquitectura-instalacion.html).*

```
your-project/
your-project-workspace/
├── mode-state/
│   ├── findings.jsonl            # findings with evidence and state
│   ├── handoffs.jsonl            # one record per audit, with the next prompt
│   ├── verification-results.jsonl  # how each fix was verified
│   ├── overflows.jsonl           # what compaction discarded, and why
│   └── work-items.json           # work queue and active candidate
├── .dsh-managed/
│   └── capability-plan.json      # your project's real commands and what is missing
└── creator-runs/                 # what Creator generated, with its validations
```

All of it with caps per file and per record, and compaction when they are reached: the
memory can grow a lot, but not without limit. What compaction discards does not disappear
silently: a receipt is left in `overflows.jsonl` saying what was lost and why.

## What it does NOT do (on purpose)

- **It does not commit or push.** The repairer leaves the verified candidate and your
  product's tree clean; integrating is on you. That is the security boundary, and it is
  tested.
- **It is not autonomous in the shadows.** Every turn ends with a readable result; what
  is retained is said, and why.
- **It does not install providers or credentials.** DSH and your provider are
  prerequisites.
- **The repairer does not run inside a kernel sandbox.** The write boundary is
  contractual and tested; mechanical confinement exists today for the auditor (see
  below), not for the repairer: it needs two writable roots and the runtime only accepts
  one.

## What is hardened

- **Escalation is truly forbidden.** The modes never send `sandbox_permissions` or
  `justification` — with any value — and a first-party guard intercepts those arguments
  in bash before approval. There is a regression against the real runtime that mounts the
  exact composition and blocks `workspace-write` and `danger-full-access` flat.
- **The auditor can be confined in the kernel.** With the policy pointing at the
  workspace, your product sits outside the writable roots: bash gets a real `EROFS` when
  it tries to write it, and the auditor can still persist its findings. Measured against
  the runtime, with a regression.
- **The count is not the mode's claim.** A central command recomputes the persisted
  findings from the files and requires the handoff to cover them exactly; a partial or
  contradictory result is never written.

## Status: public beta

This ships for testing. What is already proven: end-to-end installation with no
intervention, from a GitHub clone and with no prior contamination; the
auditor→repairer→integration cycle in three real campaigns; verification executed
against the product's real entrypoint (Flutter and Django, no stubs) with the evidence
persisted and mechanically validated; and the memory reaching its caps with compaction
and a receipt. The Apache-2.0 license and the `v0.1.0-beta` tag are already published.
What is left for the stable release is in the
[launch plan](docs/plans/10-lanzamiento-publico.md).

If the session dies mid-turn — and in a developer preview it does — the work is not lost:
an interrupted candidate resumes by verifying the exact recorded identity (same worktree,
same base, same findings digest) without discarding the diff, and `bootstrap.py state`
reconciles the state with your repository when something moved outside it, with receipts
instead of silences.

## Want to try it?

The command from the [quick start](#quick-start) is all it takes. To report your
experience, share your `mode-state` (`findings.jsonl`, `handoffs.jsonl`,
`verification-results.jsonl`, without your product's code), the turns that ended up
retained and why: [open an issue](https://github.com/MadManJohnSmith/Improvement/issues).
That is the most useful report possible, and it is exactly the format the framework
already produces.

## Documentation

- [Operational usage](docs/usage.md) — the full cycle, integration, and space recovery
- [Interactive diagrams](https://madmanjohnsmith.github.io/Improvement/diagrams/ciclo-operativo.html) — the operating cycle and the [installed architecture](https://madmanjohnsmith.github.io/Improvement/diagrams/arquitectura-instalacion.html), as explorable HTML
- [DSH setup](docs/setup-dsh.md)
- [Verified status](docs/status.md)
- [Normative architecture](ARQUITECTURA_FLUJO_AGENTES.md)
- [Implementation plans](docs/plans/README.md) · [Launch plan](docs/plans/10-lanzamiento-publico.md)
- [Changes](CHANGELOG.md) · [Third-party attributions](THIRD_PARTY_NOTICES.md)
- [v0.1.0 beta notes](docs/plans/11-notas-beta-v0.1.0.md) (published 2026-09-30)

## License

Apache-2.0 ([LICENSE](LICENSE)). Third-party skills and their attributions are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
