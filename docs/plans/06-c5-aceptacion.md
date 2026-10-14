# Plan 06 — C5: automatic DSH acceptance

**Outcome:** `bootstrap accept` evaluates a candidate without Creator approving itself.
**Prerequisites:** C0–C4.

**English** | [Español](06-c5-aceptacion.es.md)

## Required scenarios

- discovery of both modes;
- exact native loading/origin/body;
- targeted reading;
- external evidence;
- Auditor without product write access;
- repair in a candidate;
- red→green;
- QA by an observable actor/session;
- semantic re-audit;
- reopening/checkpoint;
- rollback/uninstall;
- unchanged routing/global configuration.

## Controls

- public fixtures separate from Host holdouts;
- read-only tests/rubrics/thresholds;
- review separate from Creator;
- mechanical `verify` plus explicit semantic judgment;
- lack of isolation → `DEGRADED_REVIEW`, not independence;
- missing evidence → `UNVERIFIED/RETAINED`;
- repair always returns to Host evaluation;
- exact candidate/contract digest.

## Output

`host-verdict.json`, `evidence-ledger.jsonl`, `acceptance-record.json`, `retention-bundle` if applicable, `rollback-record` on failure.

## Gate

Only Host can issue `ACTIVE`. Every failure leaves an intact staged generation or rollback; no declarative acceptance by Creator changes state.

## Adaptation

The minimum scenario may grow per project, but immutable criteria must never be reduced. Holdouts are regenerated when a repair exposes them.
