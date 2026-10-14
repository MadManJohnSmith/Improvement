# Plan 05 — C4: backup, transactional installation, and uninstallation

**Outcome:** activate/deactivate a complete generation without a mixed set and with verifiable rollback.
**Prerequisites:** C0–C3; valid staged package.

**English** | [Español](05-c4-transaccion.es.md)

## Sequence

1. Resolve ownership and collisions.
2. Create a complete backup of every managed resource (directory, auxiliary files, links/manifest).
3. Verify the backup with hashes.
4. Build a sibling candidate tree.
5. Validate loading/origin/body from the candidate.
6. Run mechanical smoke tests.
7. Switch one managed generational pointer/directory.
8. Revalidate from a new session.
9. Write an install/promotion receipt.
10. Retain the backup until acceptance is closed and the retention policy permits its removal.

## Injected negative cases

Backup failure, copy failure, hash failure, process termination during staging/swap, third-party symlink, local edit, name conflict, rename/copy rollback, failed post-promotion smoke test, partial uninstall, and concurrent old/active generations.

## Gates

- complete prior backup;
- complete candidate;
- modes+skills activated as a set;
- rollback restores previous hashes;
- uninstall removes only self-owned resources;
- does not modify the product or third-party global configuration;
- a crash leaves neither a mixed set nor a destroyed backup without recovery.

## Adaptation

The swap unit may be a directory, pointer, or user preset root depending on the actual DSH behavior, but it must demonstrate the same negative cases; do not claim portable atomicity without a test.
