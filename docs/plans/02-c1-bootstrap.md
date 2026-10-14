# Plan 02 — C1: deterministic bootstrap

**English** | [Español](02-c1-bootstrap.es.md)

**Output:** `scripts/bootstrap.py install` prepares a `creator-run` without touching the product or global configuration.
**Preconditions:** C0 approved; DSH and Creator installed; provider/model already configured by the user.

## Steps

1. Validate the project/framework/workspace, roots and overlaps.
2. Check DSH, Creator, the local channel and minimum capability without opening credentials.
3. Create the generation-id, `started.json`, budget and snapshot.
4. Inventory Git, manifests, instructions, areas and exclusions without executing the product.
5. Prepare general skills with ownership, idempotence and conflict handling.
6. Create initial `inputs/` and `discovery/`.
7. Prepare the Creator invocation package and the versioned prompt.
8. Checkpoint and return a compact reference.
9. Implement `update`, `uninstall` and `purge-data` only after the minimal install, with strict ownership.

## Negative cases

- missing provider;
- missing Creator;
- workspace inside the product/framework;
- symlinked/overlapping root;
- unavailable global configuration;
- foreign/conflicting skill;
- existing generation;
- secret detected in inputs;
- interruption before completing the snapshot.

## Gates

Clean clone + configured provider → one command creates a complete run; repetition is a no-op; product and global configuration remain unchanged; errors leave a RETAINED checkpoint.

## Authorized adaptation

The workspace convention, local DSH client, general skill names and data policy may be adjusted after a clean-room trial, preserving the contract and recording the reason.
