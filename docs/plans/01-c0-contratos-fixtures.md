# Plan 01 — C0: contracts, schemas and fixtures

**English** | [Español](01-c0-contratos-fixtures.es.md)

**Output:** corpus of versioned contracts and valid/negative fixtures for validating C1–C5.
**Preconditions:** architecture 3.0, observed runtime and available MVP Host services.

## Artifacts

- schemas for `run`, `project-manifest`, `instructions-index`, `capabilities`, `generation-manifest`, `modes`, `skills`, `scenario`, `handoff`, `drift`, `backup`, `promotion`, `rollback`;
- schema for the immutable base library, pattern catalog, composition, limited override, transfer and extension;
- applicability, invariants, limits, provenance and scenarios for each catalog skill;
- Python/backend and multipart project fixtures;
- golden manifests;
- positive/negative corpus for paths, hashes, symlinks, collisions, capabilities, routing and licenses;
- `THIRD_PARTY_NOTICES.md` if MIT material is copied;
- `tests/test_generation_contracts.py` and stdlib validators.

## Steps

1. Derive fields from architecture v3.0 and `docs/creator-preset-spec.md`.
2. Define the version/schema and unknown-field policy.
3. Define ownership of each artifact and Host states.
4. Create external fixtures first; do not include real run results in the repository.
5. Implement parsing/validation without partial mutation.
6. Create negative cases: path traversal, symlink, stale hash, incomplete manifest, new routing, new provider, orphaned skill, load cycle, unresolved decision, free-form extension when a base applies, override outside slots, transfer without destination acceptance and duplicate skill with no material difference.
7. Run the corpus and review false positives.
8. Update `PLAN_IMPLEMENTACION.md` only if the gate passes.

## Gates

- every generated artifact has a schema and owner;
- the complete positive case is accepted without DSH;
- every negative case fails closed without writing;
- exhaustive manifest and verifiable hashes;
- fixtures contain no real paths, credentials or projects.

## Authorized adaptation

Record changes to fields, compatibility, fixtures or limits in the C0 run; a contract change requires changing the architecture first.
