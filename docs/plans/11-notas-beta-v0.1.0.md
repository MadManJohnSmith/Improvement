# 11 · v0.1.0-beta release notes

**English** | [Español](11-notas-beta-v0.1.0.es.md)

> **Published 2026-09-30** with the `v0.1.0-beta` tag, under the owner's authorization. G0 — the
> license — is closed: Apache-2.0, with `LICENSE` at the root.

## What it is

A framework that installs two modes generated specifically for your repository in it — an
auditor and a continuous repairer — with bounded on-disk memory, verification against the real
commands of your project and an integration boundary that cannot be jumped. One command
installs; two simple prompts operate.

## What has been proven

Four complete campaigns over real repositories, with the product intact until the operator made
the commit, the fast-forward and the push.

| Campaign | Stack | Findings | Verifications | Status |
|---|---|---|---|---|
| Syncify | Rust / Tauri / Vue | 77 (114 records) | 67 (61 PASS, 6 BLOCKED) | green CI in 3 jobs, 15 commits |
| RehabWeb | Django / Vue | 45, 6 CRITICAL | 4 | 108 real Django tests green |
| LoboApp | Flutter / Android | 14 (9 + 5 in the re-audit) | 14 PASS with `flutter test` | 166 Flutter tests and `flutter analyze` with no incidents |
| Improvement (self-test) | Python / unittest | 8 (7 + 1 in the re-audit) | 14 PASS with the project's own suite | 632 tests green |

## What you should know before using it

- **The modes do not commit or push.** Integrating is yours, always. It is the safety boundary,
  not a limitation.
- **The evidence is your project's entrypoint or nothing.** The Host resolves at install time
  which test and analysis command each technology of your repository uses, and that command is
  the only recordable result. A mock or a hand-written harness serves to investigate, not to
  verify. If a tool is missing, the record is `BLOCKED` naming what is missing: never an
  invented `PASS`.
- **A capability outside the default `PATH` is materialized in the workspace.** If your SDK
  rewrites itself on every run, the plan asks for a hard-linked local copy (0 bytes of disk)
  and points there.
- **Apache-2.0 license.** A repository that is public without an open license grants no
  rights; this one has it.

## Known limits

- `mode-state` carries a lease per file, so two sessions no longer step on each other when
  replacing the same file. What does **not** exist is batch atomicity: replacing five files is
  still five writes, and the framework declares it instead of pretending.
- The auditor's read-only boundary is contractual and enforced by the write tool, not by a
  kernel sandbox.
- Monorepo multi-stack: one technology per subdirectory is detected; a single tree with two
  different ecosystem manifests is not covered.
- In this environment DSH falls every few minutes. The turns are relaunched and the work
  recovered, but a long campaign costs more time than the framework assumes.

## What to look for in the beta

The three failures that only appeared with real stacks, and that no synthetic test would have
seen:

1. The plan emitted a verification command its own shell could not execute.
2. The sandbox left the SDK mounted read-only and the tool rewrote itself on every invocation.
3. A verification result did not identify the tree it verified, so a `PASS` could describe a
   revision prior to the fix.

If your project uses a technology that does not appear in the stack list, the plan will say so
with a `missing <capability>` instead of pretending. That is useful information too: say it.

## How to report

Your `mode-state` is the report. Share `findings.jsonl`, `handoffs.jsonl` and
`verification-results.jsonl` — without your product's code — plus the turns that ended
`RETAINED` and why. It is exactly the format the framework already produces.
