# Plan 07 — C6: clean-room pilot

**Outcome:** validate the end-user experience in projects not used during development.
**Prerequisites:** C0–C5 and DSH/provider configured by the participant.

**English** | [Español](07-c6-piloto.es.md)

## Pilots

1. Python/backend project.
2. Multipart JS/Rust/UI project or equivalent.

Neither shares a generation, profile, candidates, holdouts, or private diagnostics with the implementation.

## Walkthrough

- clone the pilot tag;
- one-command `bootstrap install`;
- automatic Creator;
- automatic acceptance;
- visible project-specific modes;
- full and targeted audit;
- targeted and queue repair;
- QA/re-audit;
- update after material change/drift;
- local skill edit and conservative resolution;
- rollback/uninstall;
- feedback without secrets.

## Metrics

- visible commands/messages;
- human decisions;
- troubleshooting;
- time;
- requests/tokens by role;
- failures/retentions;
- context switches;
- perceived clarity.

## Gate

A user without insider knowledge gets useful modes, does not edit JSON/prompts/receipts, does not transport IDs, and can leave/resume. Any extraordinary intervention is recorded and prevents declaring a clean UX if it was necessary.

## Adaptation

Do not relax controls because of convenience feedback. Classify each comment as a bug, ambiguity, environmental capability, optional improvement, or scope change.
