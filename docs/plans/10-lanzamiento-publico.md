# 10 · Public beta launch

**English** | [Español](10-lanzamiento-publico.es.md)

Status: **DONE**. The seven gates G0–G6 are closed; G6 was completed on 2026-09-30 with the
`v0.1.0-beta` tag published under the owner's authorization. The goal is met by its operational
definition: anyone with a repository and DSH configured installs Improvement with one command,
operates its two modes with simple prompts and reports results. What remains open — D2, D11 and
F5 — is hardening of the evidence and does not block this goal.
This plan succeeds the C0–C7 plans and the hardening campaign over real pilots (Syncify and
RehabWeb, both closed and documented in `CHANGELOG.md`).

Status vocabulary note: the Spanish status tokens of this plan (`HECHO`, `RETAINED`, `EN CURSO`)
are contract literals that the regression suite in `tests/` checks verbatim, and both the header
line and the gate table keep them. The canonical Spanish header line is: Estado: **HECHO**.

## Where we are

- **Proven:** end-to-end installation without operator intervention on a clean environment
  (new clone + new DSH home with credentials only, the initial roster of the four
  factory presets), with `Creator: GENERATED` and `Host: ACTIVE`; an audit with a simple prompt
  that persisted findings with evidence; a repair with a six-word prompt that fixed two
  security CRITICAL findings in a sister candidate.
- **Solid:** fail-closed core validated by two pilots (product intact until the operator
  integrates), startup with sentinel, mechanical anti-escalation, candidate reserved before
  editing, reconciliation without the operator, documented candidate withdrawal.
- **Declared debt:** non-conformant candidate record written by a generated mode; runtime
  compaction without receipt; orphaned `decisions.py` and `metrics.py`; no multi-file
  CAS/lease. The maintainer's complete report lives outside the canonical tree
  (`.zcode/workflow-drafts/informe-improvement-memoria.md`).

## Launch gates

| # | Gate | Content | Status |
|---|---|---|---|
| G0 | License | Choose and add `LICENSE` (recommendation: MIT or Apache-2.0; owner's decision) and reflect it in the README. Without this the repo must not be advertised as installable. | HECHO (DONE) 2026-09-30 (Apache-2.0) |
| G1 | Candidate contract | `recording_command` emits the exact JSON object to persist; the human forbids adding fields; the preflight reports what it discards (not just what it archives). Regression with the RehabWeb case (extra fields + absolute path). | HECHO (DONE) 2026-09-29 |
| G2 | decisions + metrics in the cycle | Call the metrics ledger and the decision store at turn close in `host_controller.py` (the hook already exists: transitions and UNIT_DONE/UNIT_RETAINED). Regression with the existing regression of both modules. | HECHO (DONE) 2026-09-29 |
| G3 | Compaction with receipt | Runtime overflow leaves a receipt (legacy file pattern, `dropped_records` included) instead of losing records without trace. Syncify case: 50/50 handoffs. | HECHO (DONE) 2026-09-29 |
| G4 | E2E from GitHub clone | Repeat the clean install cloning from `https://github.com/MadManJohnSmith/Improvement.git` (not local) over a demo repo, verifying roster, skills and an auditor→repairer cycle. | HECHO (DONE) 2026-09-29 |
| G5 | Public documentation | README (done), non-technical quickstart in `docs/usage.md`, feedback policy: what a tester shares (their `mode-state` is the evidence). | HECHO (DONE) 2026-09-30 |
| G6 | Tag and notes | Tag `v0.1.0-beta`, release notes with the real pilot metrics and the known limits. | HECHO (DONE) 2026-09-30 (published with the owner's authorization) |
| G7 | Verification against the real stack | The Host resolves a capability plan at install time (`scripts/stack.py`): the product's own entrypoint per stack (any technology, monorepos included), the real state of each capability and the exact provisioning step outside the product. Verification evidence is that entrypoint or `BLOCKED` naming what is missing; stubs are research material, never a result. Regression with the rehab case (Django missing) and with the real stacks of Syncify, RehabWeb and LoboApp. | HECHO (DONE) 2026-09-29 |

## Beta criteria

- A tester needs: Linux, `git`, DSH installed with a provider configured by them, and their own
  repository. The framework obtains no credentials.
- A tester's minimum success: `install` ends `ACTIVE`, the auditor persists findings with
  evidence, a repair prompt produces a candidate with verification, and the operator integrates
  with a commit.
- Feedback: the tester's `mode-state` IS the report. Sharing `findings.jsonl`, `handoffs.jsonl`
  and `verification-results.jsonl` (without product code) is requested, plus the turns that
  ended `RETAINED` and why.

## Declared risks

- DSH and the provider are the user's prerequisite; the framework neither installs nor
  configures providers, and without an authenticated session the run stays recoverable, not
  active.
- Multi-file `mode-state` updates have no CAS/lease: no isolation or concurrent atomicity is
  claimed.
- The modes never commit/push: the operator integrates. Publishing this as a feature (not as a
  gap) is part of the public message.
- Third-party dependencies are already attributed in `THIRD_PARTY_NOTICES.md`; any new skill
  entering `library/` requires its provenance entry.
- Mobile projects without a toolchain (LoboApp case: Flutter without the SDK on the machine):
  the candidate's verification stays `BLOCKED` for missing capability, never an invented PASS.
  With the SDK materialized outside the product, the same verification runs for real, and the
  plan names the entrypoint by its absolute path when the default `PATH` does not resolve it:
  a bare name the mode's own shell cannot invoke would turn a real suite into a `BLOCKED` the
  runtime has not earned (`scripts/stack.py::_runnable_entrypoint`).
  Candidate adapter for on-device Android evidence: `google/artemis` (Apache-2.0, UI automation
  with screenshots/logcat and an MCP server). It is not adopted as a dependency — it adds
  ADB/emulator/FFmpeg to the user's environment, covers only Android targets and does not emit
  static-analysis diagnostics; if a mobile-project tester integrates it, it requires a
  provenance entry and remains an external verifier, never a source of authority.

## Measurable pilot baseline (to compare during the beta)

| Metric | Syncify | RehabWeb | LoboApp |
|---|---|---|---|
| Install commands | 1 | 1 | 1 |
| Distinct findings persisted | 77 (114 records) | 45 | 9 + 5 in the re-audit |
| Maximum severity | HIGH | 6 CRITICAL | 1 CRITICAL |
| Verified work | 78 VERIFIED items | 2 CRITICAL repaired | 14 VERIFIED items |
| Persisted verifications | 67 (61 PASS / 6 BLOCKED) | 4 | 14 PASS (flutter test) |
| Commits from the modes, integrated | 15 | 1 | 4 |
| Outcome | green CI in 3 jobs | 220 lines of fix in 3 files | 14 findings closed; 166 Flutter tests and `flutter analyze` with no incidents |

LoboApp was installed from scratch from the framework's GitHub clone over a freshly cloned
Flutter product, and it is the campaign that closed G7: verification ran with real `flutter test`
from the workspace's local copy, not with a harness. It reached the end: the 9 findings of the
first audit were repaired and integrated in four turns, the re-audit confirmed them as
`RESOLVED` with evidence and found 5 more — one of them created by the previous fix, which left
an inherited backup unrestorable — and all were closed. Range `bb01cba..4c0bb30`.

Its time cost was high: DSH falls every few minutes in this environment and each turn is
relaunched until it finishes, with a Creator that had to be resumed three times. The framework
held throughout: product intact until integration, candidates recorded and reconciled, the
declared base re-anchored to HEAD with ancestry verified mechanically, and the operator
integrating only with commit, fast-forward and push.

Metric for the framework itself: 632 tests green **in the `v0.1.0-beta` tag** — since then the
suite is at 670 with runtime `0.1.7-rc.2` installed, whose count is updated here and not in the
tag notes, which describe what that tag contained; the units were born from the pilots; a silent
preflight loss detected and fixed with a regression.

## The framework over itself (self-test)

The framework installed from scratch over a clone of itself, with its declared entrypoint
(`python3 -B -m unittest discover -s tests`), did not only get audited: it was fixed. The auditor
persisted 7 findings (2 HIGH, 5 MEDIUM) and the repairer attended the first two with a six-word
prompt, verifying with the project's own real suite (606 tests at the time of that campaign; 632
when the beta was published):

- **IMP-AUD-001 (HIGH):** compaction by threshold discarded records without a receipt. G3 covered
  the drop by schema incompatibility, but what exceeded the ceiling was lost in silence. Now the
  drop by limit leaves a receipt and an archived copy.
- **IMP-AUD-002 (HIGH):** the write tool only bounded `verification-results.jsonl`; the rest of
  the managed state was left free. A managed session declares its root `<workspace>/mode-state`
  and every destination outside it is denied before the write-intent.

Both are integrated with a regression (`99a9f0e`). The product —the framework clone— was left
intact until integration, with the operator's commit and fast-forward.

G0 was closed on 2026-09-30: Apache-2.0 chosen by the owner, `LICENSE` at the root and the
reference in the README. Only G6 remains —the tag `v0.1.0-beta` and the publication—, which
requires authorization of the destination.
