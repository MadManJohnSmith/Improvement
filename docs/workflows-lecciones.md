# Lessons from the workflow campaigns (ZCode) and the agentic flow

> **English (canonical).** A Spanish translation lives at [workflows-lecciones.es.md](workflows-lecciones.es.md).

**One-page view.** Each row is a **measured** failure or success, attributed to the evidence that produced it. It is not a campaign summary: it records what must be repeated and what must be prevented, plus the permanent test that backs it.

**What evidence exists and what does not.** This document was written **without access to
the runs' journals**. In that session `ListWorkflowRuns` and `GetWorkflowRun` were
unavailable; the answer was `workflow_introspection_unavailable`, a capability gap and not
an empty project. What persisted in `.zcode/workflow-runs/` and `~/.zcode/workflow-runs/`
was only the **lowered program** (`dwfrun-*.mjs`), not the journal or the artifacts: no
per-run verdict, no `log()` and no token usage. The later X1 evidence is attributed to its
own external trials, not inferred from those programs. Thus:

- “Run finished” is **not** “finding correct”. A run can close `COMPLETED` with the wrong
  finding inside.
- “Local gate green” is **not** “real DSH”. Repo tests inject a fake client; only some
  campaigns ran a real DSH session.
- Anything stated here as an *opposite success counterexample* comes from a `run.json`, an
  observation or a test that can be re-executed. The rest is marked `SIN PRUEBA`.

**Attribution rule.** Every row names a run id (`dwfrun-…`/`dwfeval-…`), a sha, an
executor `r-…` id or a path with line. Without one, the row is folklore and does not enter.

---

## 1. Attributable lesson matrix

`L<nn>` is the identifier. The *Test* column points at the permanent regression; `—` means the barrier is documentation or another existing test, which one is named.

### 1.1 Failures and how they were closed

| ID | Symptom | Verified cause | Preventive barrier | Test | Opposite success |
|---|---|---|---|---|---|
| L01 | A campaign gate was green without ever reading the suite | `unittest` writes its count and verdict to **stderr**; the gate parsed only stdout and never saw `Ran N tests` | The verdict parser merges both streams before extracting anything (see §3) | `tests/test_workflow_lessons.py` ([W01]) | `dwfrun-27cccb98` documented the defect in its own code comment |
| L02 | `MEMORY_RECONCILED {invalidated: 6, hits: 0}` was published anyway | Memory is measured against the workspace snapshot, not the product base | Reconciliation invalidates the whole group when the context differs and records it in the journal | `tests/test_workflow_lessons.py` ([W02]) | `docs/status.md:175` publishes the record with all six invalidations disclosed, not hidden |
| L03 | A memory index that survived a failed gate | Memory was published after `RUN_COMPLETED` alone, without looking at the gate verdict | Publish memory only after a terminal run; a `RETAINED` run does not publish | `tests/test_workflow_lessons.py` ([W03]) | `r-5d7d11…` stayed `RETAINED cause: gate-abort:gate-producto` and did not publish |
| L04 | Resuming re-executed everything and lost the run | `_run_id_for` was computed from mutable content instead of the plan sha | The run id comes from the plan sha: the same plan resumes the same run dir | `tests/test_workflow_lessons.py` ([W04]) | `r-7761c0…` resumed and reached `COMPLETED`, with 11→14 events |
| L05 | A `MEMORY_RECONCILED` with the run finished but no coherent PASS/FAIL | Memory publication was attempted outside terminal closure and could rewrite the verdict | Publication failure is recorded without turning the verdict into PASS or FAIL afterwards | `scripts/workflow.py:1796-1803` + `tests/test_workflow_memory.py` | Run recorded with `memory_error` logged and the verdict intact |
| L06 | Front pages claimed `848 tests in green` with 932 in the tree | The suite grew without a commit; the published figure described `HEAD` | The consistency test **discovers** the figure and demands an old one be declared old | `tests/test_architecture_consistency.py:352` | `README.md:290`/`README.es.md:289` publish 933, discovered rather than remembered |
| L07 | The suite dirtied its own output with `usage:` on stderr | CLIs that must exit with code 2 write on stderr, and the tests redirected only stdout | Subprocess output is captured in full in every regression | `tests/test_architecture_consistency.py:386` | The suite runs clean, with no `usage:` above the line of dots |
| L08 | Repeated “green” figures in two documents | Two hand-written counts sixteen lines apart | One figure per document, discovered, plus a test that cross-checks it | `tests/test_architecture_consistency.py:352` | A single place publishes the count, and the test verifies it |
| L09 | A real Creator did not persist `generated/generation-manifest.json` | The 29-tool-call headless turn went quiescent without an artefact; once measured, the cause was the session running without the `--patch` overlay, which made `write` fall into the upstream row the sandbox rejected | An accepted package must name who produced it; the headless argv goes through the official function that composes the overlay | `docs/status.md:205-212` (full pass section), external trial `ensayo-x3-actualizado.md:18-28` | The package from that pass was produced by deterministic tools, **not** by the model; afterwards X3 with the overlay did generate 19 artefacts and was ACTIVE, **before** the budget fix |
| L10 | Corpus gate without an evaluator endpoint or Host adapter | The startup diagnosis was **false**: `dsh web` did start; the copied home had `profiles/web/node_modules/` empty. What does **not** exist in `0.2.0-rc.2` is an `evaluator` endpoint, and what the CLI does not offer is the adapter that checks layout and effective skill before `session/create` | The gate abstains fail-closed, naming the missing piece, and invents neither endpoint nor verdict | `docs/status.md:187-215` (full pass section), `scripts/skill_gate_run.py:604-608`, `tests/test_skill_gate_run.py` | `action: reject` on the anti-fraud partition: the invented candidate lost 0.488 < 1.000 |
| L11 | Repair candidate without a product worktree | `git worktree add` was blocked by the sandbox: `Read-only file system` + `[sandbox: file access denied]` | The candidate is born as a shadow repository provisioned by the Host under the workspace (contract `Host-provision_repair-shadow-only`) | `docs/status.md:210-226` (full pass section), `tests/test_mode_lifecycle.py` | `x1-live/RESULTADO.md`: real headless DSH persisted `PROVISIONED → DIRTY` with a verified diff and 3/3 tests. Under the real preset, `x1-preset-real/RESULTADO.md` edited in 11 steps and 180,107 tokens (the 3/3 tests of that turn were run by the operator from outside); a later turn of the mode registered `DIRTY` with digest and paths, persisted `work-items.json` and ran the entrypoint (3/3). The full cycle under the real preset was therefore exercised across **two** turns, not one |
| L12 | Permission-escalation attempt | The mode attempted `danger-full-access` without an approval channel | Exact anti-escalation: `sandbox_permissions`/`justification` are forbidden at every value; denial or schema error → `RETAINED` without retry | `ARQUITECTURA_FLUJO_AGENTES.md:160` + `tests/test_mode_lifecycle.py` | `docs/status.md:180`: retry with `danger-full-access` rejected without a channel |
| L13 | The corpus evaluator received the expected answer | The evaluator prompt carried the marked expected verdict | The evaluation prompt never contains the expected answer | `tests/test_skill_gate_run.py:114` | A candidate without evidence stays uncovered: it was reported as it happened |
| L14 | A report file served as a path and publication failed | The reviewer returned prose with the path inside it, and that prose was used as the path | The canonical path is known outside the subagent's answer | `dwfrun-d8fb7dd5` (comment in its own script, fixed on resubmission) | The report ended up published as an artefact on the resubmission |
| L15 | A subagent read the maintainer's local paths into the report | The assignment included personal paths, expecting the archaeologist to use them | Assignments to subagents forbid local paths and third-party material | `tests/test_architecture_consistency.py:175-188` | `dwfrun-577fa719` used `git show <sha>:<path>`, with no live paths |
| L16 | Verified preset but undiscovered skill | An unquoted `description` containing `: ` broke the frontmatter (`Nested mappings are not allowed in compact mappings`) | `host_validator.skill_frontmatter_issue` rejects unparseable frontmatter before publishing | External trial `corpus-fixed/RESULTADO.md:5-9` (negative case with real DSH) | After quoting the frontmatter, `skills/list` returned 4 `modelInvocable` skills and the `skill` call returned content |
| L17 | A corpus case compiled a **skill** and dispatched to a **mode** | `SC-123` pointed at `source-driven-development`, but the gate dispatched to the `fixture-auditor` mode; the mode required the `<product>/<workspace>` layout, which the case directory did not have, and narrated `RETAINED` without `workflow_write` | Explicit targeting and layout before accepting a case as proof of a mode; the gate keeps reading `result.json`, never prose | External trial `corpus-fixed/RESULTADO.md:11-23` | `NOT_COVERED` with evidence, not an invented PASS |

### 1.2 Successes that must be preserved

| ID | What worked | Evidence | Test |
|---|---|---|---|
| L18 | Complete `FAIL → repair → PASS` in the executor with memory | `r-5d7d11…` retained by the gate; `r-7761c0…` completed, repaired | `tests/test_workflow_memory.py:360` |
| L19 | Incremental memory between campaigns using a synthetic git product | 22 tests: change/deletion/rename/base/config, symlink, malformed memory, two plans | `tests/test_workflow_memory.py:66-477` |
| L20 | Real headless preflight against DSH 0.2.0-rc.2 | `PING-OK`, `turn_end.reason.kind = completed`, `totalTokens = 6509` | `docs/status.md:174` (environment, not an automated test) |
| L21 | Skills loaded and invoked in a real DSH session | auditor 3, repairer 2, implementer 1; trivial turn → 0 tool calls | `docs/status.md:176` |
| L22 | Real abstention verified with a write-probe | `Decision: I abstain`; product intact after the attempt | `docs/status.md:177` |
| L23 | Host validator over a real package | `READY_FOR_ACCEPTANCE`, 10/10 layers PASS | `docs/status.md:178` |
| L24 | Anti-fraud corpus gate against an invented candidate | `action: reject`, 0.488 < 1.000 on the training partition | `docs/status.md:179` + `tests/test_corpus_gate.py` |
| L25 | Canonical confinement denying a write from the repo | Attempt denied; escalated retry rejected | `docs/status.md:180` |
| L26 | Real implementer with accepted external candidate | commit `95aa9b2`, 6/6 new tests, product intact, no implicit commit/merge/push | `docs/status.md:9` |
| L27 | External sources treated as untrusted and reproduced | Every claim that backed a code change was verified in the tree before changing code | `fuentes-memoria.md` (external evidence) and `dwfrun-0666568b`, whose lowered program repeats the order: the pass starts from inventory, not from the previous report |
| L28 | Identical reconciliation without rewriting | A different index is not overwritten; identical bytes reproduce the same index | `tests/test_workflow_lessons.py` ([W06]); `git show HEAD:scripts/workflow_evidence.py:276-309` |
| L29 | Campaign resubmission carries the fix from the previous attempt | `dwfrun-d8fb7dd5` fixed the `finalPath` lesson on its resubmission | `dwfrun-d8fb7dd5` |

---

## 2. Not proved: what these runs do not demonstrate

None of these rows is filled by supposition; current gaps are separated from superseded historical evidence. The actual **coverage** (*cobertura*) of the campaigns is this table, not the lesson count. “Not proved” is the original *No probado* evidence category, not a claim that every historical limitation still applies.

| Gap | Why it is not proved | Where stated |
|---|---|---|
| No journal access in the original writing session | `ListWorkflowRuns`/`GetWorkflowRun` returned `workflow_introspection_unavailable` | Opening evidence note of this document |
| “Run finished” ≠ “correct finding” | Without the journal there was no per-run verdict; `.mjs` files are programs, not results | Opening evidence note of this document |
| Creator end-to-end in a journal-verified pass | With the `--patch` overlay Creator persisted 19 artifacts and the session was `ACTIVE`, but that pass prepred dates the budget gate fix, so it does not validate the current gate | `docs/status.md:230-242`, `docs/progreso-agentico.md:215` |
| Discovery and design exercised with the overlay missing | The quiescent turn of L09 never persisted the manifest: `workspace write` fell in the upstream row the sandbox rejected | L09, `docs/status.md:205-212` |
| **SUPERSEDED (2026-10-11)** Full repair cycle under a real preset in a single turn | `x1-live` measured Host provisioning and mode behaviour headless; `x1-preset-real` resolved the preset and loaded its skill under a 120k cap, but the supervisor stopped **before editing** by projected token cost (104.372 measured, 129.898 projected; later batch 97.973/127.227). Superseded by the 200k-cap turn described below | `docs/progreso-agentico.md:215`, `x1-preset-real/RESULTADO.md`; kept as history |
| Full repair cycle under a real preset in a single turn | Under a 200k cap the mode reached the edit (11 steps, 180.107 billable tokens) but the turn stopped on projection before the second dirty claim and the `DIRTY` closure, and its 3/3 tests were run by the operator, not the mode. A **later** turn closed the remaining stretch: the mode recorded `DIRTY` with digest and paths, persisted `work-items.json` and ran the project entrypoint (3/3) | `x1-live/RESULTADO.md`, `x1-preset-real/RESULTADO.md`; `docs/progreso-agentico.md:215` |
| `git worktree add` real | Blocked by the session sandbox; the design no longer uses it, but a session acting with direct read-write on the canonical remains unproven | `docs/status.md:210-226` |
| `dsh web` / evaluator endpoint / Host adapter | `dsh web` **does** boot (empty home, real install): the false block was corrected. There is no `evaluator` endpoint in `0.2.0-rc.2`, and the CLI does not offer the adapter that checks layout and effective skill before `session/create`: the runner abstains without spending | `docs/status.md:187-215`, `scripts/skill_gate_run.py:604-608` |
| Full corpus against a real mode | One case of 55 failed with `NOT_COVERED`: it compiled a **skill** and dispatched to a **mode** that required another layout, and the mode did not write `result.json`. The 55 cases target 25 skills, not the modes: not a proof of the auditor mode | `corpus-fixed/RESULTADO.md`, `x3-corpus-live/RESULTADO.md` |
| `skill_router` against a real session | Still only an informative selector | `docs/status.md:9` |
| Mechanical bash confinement in a campaign | Not exercised | `docs/status.md:9` |

---

## 3. How this document is maintained

- **One lesson, one test.** A lesson that claims to have a permanent test points to `tests/test_workflow_lessons.py` with its identifier; if the test is not in the tree, `DocumentedLessonsMapTests` fails.
- **Mandatory attribution.** `test_lessons_map_at_least_a_run_id_or_a_commit_for_each_lesson` requires every row to name a run id, a sha, an `r-…` or a path. Without attribution, the row does not enter.
- **Nothing local or borrowed.** The campaigns ran on the maintainer's paths and some saved `.mjs` contain credentials literally. What is publishable is the lesson, not the trail: `test_no_local_paths_or_borrowed_identifiers_in_the_lessons_doc` rejects personal paths and third-party material in this file.
- **A lesson's code fixes live where the code lives.** This document documents and tests; it does not replace `X1` nor edit `scripts/`, `README*`, `docs/status.md`, `CHANGELOG.md` or `ARQUITECTURA_FLUJO_AGENTES.md`.
- **Historical claims are corrected, not erased.** When later evidence changes a claim (for example the DIRTY closure of X1), the old text is kept identified as superseded and the new evidence is dated (§2). This is also the L01 lesson applied to the document itself.
