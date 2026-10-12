# DSH preparation: current state and the 3.0 target

**English** | [Español](setup-dsh.es.md)

## Final prerequisite

The user installs/configures DSH once and configures at least one provider/model. The framework:

- does not read/copy API keys;
- reuses DSH's effective configuration;
- uses the console's local token/cookie in memory only, for RPC;
- does not modify global routing/providers/credentials.

If Creator/provider/capacity is missing, bootstrap keeps `RETAINED` with a single action for the
owner.

## Tests against the installed runtime
Two regressions raise the real DSH runtime and **skip themselves if they cannot find
`DSH_MODULE_ROOT`**, so a green suite says nothing about them while the variable is unset:

```bash
DSH_MODULE_ROOT=/absolute/path/to/node_modules python3 -B -m unittest discover -s tests
```

`test_real_services_and_fail_closed` raises `ctx.fs`, `ctx.shell`, `ctx.subprocess` and
`ctx.sandboxPolicy` and checks the real denial: the product stays intact against a write attempt
and a descendant process is blocked too. `test_same_mode_escalation_writes_and_outside_denied`
mounts a per-agent preset and needs **`@deepseek-ai/dsh-agent-preset`, not published until
0.1.7-alpha.1**; with an older runtime it skips naming the missing version.

A default skip is not a test: if one of these stops running because the environment changed,
the failure disguises itself as a green skip. If you touch a live regression, run it with the
variable set before trusting it.

`tests/test_auditor_confinement.py` is the third, and the one that measures D2. It raises the
runtime with the policy pointing at the **workspace** and checks, in the same run, what decides
the design: the bash reads the product but cannot write it (a real `EROFS`, and descendants
inherit the boundary), `ctx.fs` cannot reach it either, and the auditor **can still write its
`mode-state`**. The regression includes the negative: with the policy at the session root, which
is what the current composition does, the product does get clobbered.

Two details only visible by running it. The session **must not live under `/tmp`**: `/tmp` is
the sandbox's writable root and gets remounted, so a product hosted there disappears instead of
becoming read-only —it reads as "file does not exist", not as denial—. And the runtime's
`writableRoots()` admits **one single** configurable root: that is why the auditor is confined
but the repairer is not, since it needs its candidate and its state at once.

## Checked current preparation

Standard keeps cwd at the parent with framework/product/workspace.
`onboard.py --prepare-skills --session-root` copies skills into the workspace and creates
managed links at `<parent>/.agents/skills`.

Dry-run first, then `--init`. Repetition is idempotent; foreign entries, altered links and
higher-precedence overrides block. `--update-skills` backs up complete folders before
replacing. `--remove-links` removes only owned links.

The links grant neither permissions nor sandbox. One workspace per parent; trusted parents; no
hostile concurrency.

## Checked loader mechanics

The checked runtime discovers skills from the cwd/project and follows directory links. Standard
mounts filesystem/tool-skill. The regressions verify:

- two parents;
- different bodies under the same name;
- logical source/real destination;
- exact body/hash;
- cross rejection;
- no cache leakage.

Run:

```bash
DSH_MODULE_ROOT=/absolute/node_modules node tests/test_dsh_skill_root.mjs
python3 -B -m unittest discover -s tests -v
```

### Description without quotes: silent discard

A `SKILL.md` with a plain `description` containing `: ` does not load. The YAML parser DSH uses
over the frontmatter body throws `Nested mappings are not allowed in compact mappings`,
`parseSkillFile` catches the error and returns `undefined`, so the skill does not enter the
catalogue and the `skill` tool answers `unknown or no longer available`: a session catalogues
zero skills without a visible failure. Measured with `@deepseek-ai/dsh` 0.2.0-rc.2.

The canonical correction is to quote `name` and `description` with double quotes; single
quotes and plain values without `: ` also load, so the regression does not retire older valid
generations. The Creator prompt quotes those quotes explicitly, the Host validation rejects
the plain form in `generated` bytes and in `packaged` before ACTIVE, and
`tests/test_dsh_frontmatter_shape.mjs` proves the behaviour against the real loader.

```bash
DSH_MODULE_ROOT=/absolute/node_modules node tests/test_dsh_frontmatter_shape.mjs
```

Without `DSH_MODULE_ROOT` that test leaves by the skip branch and proves nothing: a skip is
not a test, so touching the regression requires running it with the variable set.

## Current presets and plugin

The Syncify/RehabWeb presets and `workflow-write` proved composition/routing/subagents/writing.
They are MVP reference fixtures, neither a final distribution nor third-party defaults.
Automatic launch loads `workflow-write.mjs` as a `--patch` overlay
(`scripts/dsh-plugins/cordis-patch.yml`) over the owner's profile: no installation into the
DSH home and no dependencies; `DSH_PLUGIN_PATCH=0` omits it.

C4 must package generated plugins/modes without maintainer absolute paths and activate the set
via a manifest/managed pointer.

## Sandbox errors

`sandbox_permissions` is optional and only for strictly wider escalation; the current mode
must not be resent as an escalation. `workflow-write` corrects the observed case for writing.
A schema error or «strictly wider» does not authorize trying `danger-full-access`.

Auditor requires product/framework read and workspace-only write. Without granularity,
`RETAINED`, not total access.

## Current operational flow

```text
<common-parent>/
├── Improvement/
├── <Project>/
└── <Project>-workspace/
    ├── creator-runs/
    └── mode-state/
```

`bootstrap install --launch-dsh` reuses a healthy DSH Web instance or starts one with
`DSH_HOME` and the common parent as cwd. It creates a single Creator session; the Creator
preset must not delegate, open subagents or start workflows. The instance stays active on
completion.

Creator generates three selectable presets: `<project>-auditor`,
`<project>-continuous-repair` and `<project>-implementer` (the latter for requested changes,
not findings). Each mode contains `mode.json`, `preset.yml`, `agent.cordis.yml` and `SKILL.md`.
Its composition must mount persona, bash, fs, fs-search, skill-filesystem and tool-skill; the
Host retains an incomplete composition or one with subagent/delegation rows, workflow, web/
network or plugin-manager. Each mode or skill `SKILL.md` carries a `name` identical to the
directory and a non-empty `description`.

The Host materializes a bundle of `@deepseek-ai/dsh-agent-preset` declarations, copies all
generated skills and resources and each mode skill under `bundle/skills/<name>`, and
reconfigures each `dsh-skill-filesystem` with `includeDefaultRoots: false` and
`customSkillDirs` pointing at the bundle's absolute root. Collisions, symlinks and irregular
entries block the installation. It then installs via `pluginManager/installBundle`, queries
`agentPresets/list` and treats the installation as active only when every receipt preset ID
appears without a `broken` diagnostic. The current runtime no longer reads the legacy
`$DSH_HOME/.agent-presets` path.

The three modes share `<Project>-workspace/mode-state`; the Host preflights and initializes
strict schemas, file/record caps and the candidate slot. The persona forces loading the
eponymous skill first. Auditor only uses `workflow_write` for state. Repair does not use
write/edit; it changes code through bash with the candidate as workdir, derives identity from
full base+IDs, checks canonical invariants pre/post and does not commit from a simple prompt.
Replacements are per file, not a multi-file transaction; there is no CAS/lease nor mechanical
bash confinement, so the lifecycle is still IN PROGRESS until a real DSH pilot. Paths are
relative to the parent. The product receives no state from the flow. Acceptance is
deterministic and truthful: it validates package, plan, hashes and policy, but creates no
evaluator/reviewer sessions and does not assert dynamic holdouts. `READY_FOR_INSTALL`
authorizes publication; `ACTIVE` is written only after publication and a verified roster.
Tests and integration must always use a temporary `DSH_HOME`, never `~/.dsh`.

`scripts/bootstrap.py` currently implements the `install`, `accept`, `finalize`,
`verify-acceptance`, `update`, `uninstall` and `purge-data` subcommands the C0–C7 flow
describes.

## Final acceptance of a generation

It must verify:

- catalogue/load/source/body;
- capabilities and routing intact;
- Auditor without product writes;
- Repair in the candidate;
- red→green;
- QA;
- re-audit;
- checkpoint/reopening;
- rollback/uninstall;
- post-promotion smoke.

Creator only requests; the Host decides.
