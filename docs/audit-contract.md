# Local audit coverage contract

**English** | [Español](audit-contract.es.md)

The full mode preserves the authorized scope and its review dimensions under
[architecture §13](../ARQUITECTURA_FLUJO_AGENTES.md#13-cobertura-y-contratos).
`scripts/audit.py` only checks inventory, partition and declared states; it is neither a
semantic auditor nor a permission control.

## Preparing the inventory

Run against a stable, previously authorized, secret-free root:

```sh
python3 -B /path/framework/scripts/audit.py inventory \
  --product /path/product --exclusions /path/workspace/exclusions.json \
  > /path/workspace/inventory.json
```

`--exclusions` is optional. Its file is an object mapping exact relative paths to reasons,
for example `{ ".git": "Git metadata outside the authorized code review" }`. There are no
globs, implicit dependency exclusions, or instruction-file reads by the script. The operator
determines scope and authorizes exclusions; a reason written in JSON does not create that
authority. Auditing Git history requires a separate explicit scope, not treating an excluded
`.git` as reviewed.

The inventory enumerates directories with visible errors, orders files and calculates SHA-256
in chunks. An excluded file or directory records its kind and reason without reading its
content; an excluded directory is a boundary, not a count of its files. Encountered symlinks
(including an exclusion target), special files, absolute/traversal paths and missing/nested
exclusions are rejected. Descendants of an excluded boundary are not inspected. It does not
guarantee stability against hostile concurrent writers; use a stable or read-only mounted
copy where appropriate.

## Manifest and consolidation

The v1 manifest preserves its fields and adds `inventory`, exactly as emitted above:

```json
{
  "version": 1,
  "root": "/path/product",
  "inventory": {
    "version": 1,
    "files": {"src/example.py": "<real sha256>"},
    "exclusions": {".git": {"kind": "directory", "reason": "Metadata excluded by authorized scope"}}
  },
  "units": [
    {"unit_id": "core", "files": ["src/example.py"], "depends_on": [], "status": "ACCEPTED"}
  ]
}
```

`ACCEPTED` for a unit is a declaration that review finished, not proof of depth. Perspective
references, decisions and semantic evidence stay in that unit's review artifacts.

```sh
python3 -B /path/framework/scripts/audit.py consolidate \
  --root /path/workspace --manifest /path/workspace/manifest.json \
  --findings /path/workspace/findings.json --cycle-id audit-001 \
  --base-revision observed-revision
```

`findings.json` keeps the shape `{"findings": [...]}`. Every JSON input to the CLI, including
the full manifest with inventory and units, is bounded at 2 MiB. The emitted inventory does not
reserve space for the wrapper: check manifest size before consolidating; an oversized one is
rejected without emitting a cycle. Unlimited manifests and automatic partition into fragments
are not supported; expanding that contract needs its own work and regressions, not omitting
files to fit.

The workspace must be external and not overlap the product. A cycle ID is one segment of up to
64 alphanumeric, hyphen or underscore characters, starting with alphanumeric. Existing cycles
or active files are not overwritten: preserve and reconcile them before another publication;
this command does not implement the automatic transition between cycles.

On consolidation it:

- Re-enumerates the same root and compares hashes/exclusions with the snapshot. New, deleted or
  changed files invalidate the base; it fails before writing the cycle.
- Rejects duplicate files within a unit, overlapping owners, unknown/cyclic dependencies and
  files assigned inside exclusions.
- Returns `coverage.status: PARTITION_VERIFIED` only when every included file is assigned.
  Omissions become `coverage_gaps`; a missing snapshot yields `INVENTORY_MISSING`.
- Emits `UNVERIFIED` when the partition is incomplete/unverified or any unit is not `ACCEPTED`.
  It does not invent findings merely because gaps exist.
- With a verified partition and all units accepted, preserves `AUDIT_COMPLETE` or
  `AUDIT_COMPLETE_WITH_RETAINED_ITEMS` depending on finding states. A complete close may still
  have retained findings; it does not mean a repaired or defect-free product.
- Preserves the declared repair queue even with incomplete coverage, to allow authorized
  independent units. Its `READY_FOR_REPAIR` state does not certify semantic evidence or grant
  repair authority.

It also emits `coverage-matrix.json` with counts of included/assigned files, excluded entries,
gaps and pending units. It is not a matrix certifying reading or double review of each file.
The existing fingerprint deduplication does not validate cause or authenticity of findings
either; the coordinator preserves their original evidence.

## Compatibility and limits

The API `consolidate(root, cycle_id, base_revision, units, findings, snapshot=None)` supports
older consumers. Without a snapshot it certifies no coverage: it returns `UNVERIFIED` and
preserves findings/queue. Historical evidence files are neither migrated nor requalified
automatically. `write_consolidated` takes the snapshot from `manifest.inventory`.

Double perspective, recurrence prevention, human verification, decision memory and current
source counts apply in skills/Host/review. This validator neither authenticates nor proves
their execution. `audit.py consolidate` does not require or validate decision memory or metrics,
because it does not write them: since G2 the Host controller's turn close
(`scripts/host_controller.py`) writes the event in `metrics/` and ratifies the decision in
`decisions/`, fail-closed with a reconcilable unit. Human evidence and its specific mechanical
validation remain outside this contract. Changing a prompt does not implement enforcement.
