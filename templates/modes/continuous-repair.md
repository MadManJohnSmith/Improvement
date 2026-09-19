# {{PROJECT_NAME}}-continuous-repair

Mode: `{{PROJECT_NAME}}-continuous-repair`
Purpose: Minimal bounded repair on candidate branches for `{{PROJECT_NAME}}`.

## Boundaries and Immutable Invariants

1. Operates only on designated candidate worktrees or authorized branches.
2. Modifies only files within the authorized finding change scope.
3. Every repair must be proven green by existing automated tests.
4. Maximum two repair attempts per finding before retaining.
5. Emits candidate patches for independent Host QA; never self-approves.

## Triggers

- Explicit command: "Repara la cola autorizada", "Repara este hallazgo"
- Finding queue handoff from `{{PROJECT_NAME}}-auditor`
- Reaudit regression repair loop

## Inputs and Sources

- Finding specification from external `repair-queue.json`
- Source code in candidate worktree
- Documented test commands from `AGENTS.md`

## Procedure

1. Isolate the candidate finding and reproduce failure (red state).
2. Apply the smallest verifiable change to address root cause.
3. Rerun the documented test command to verify green state.
4. If green, commit candidate receipt and request independent QA review.
5. If failure persists after second attempt, mark finding `RETAINED`.
