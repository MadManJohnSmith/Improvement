# Plan 04 — C3: Host generation validator

**English** | [Español](04-c3-validador-host.es.md)

**Output:** independent, fail-closed validator of Creator packages, without active writes.
**Preconditions:** C0 schemas/corpus; C2 generates at least one fixture.

## Layers

1. schema/version/unknown fields;
2. exhaustive manifest, hashes, file types, paths and symlinks;
3. reference graph, cycles and hot paths;
4. contracts/requirements/source provenance;
5. capabilities, roots, tools, models and routing;
6. portability, scripts, subprocesses, network and data;
7. context budgets;
8. collision/ownership/precedence;
9. license/THIRD_PARTY_NOTICES;
10. anti-self-approval and lifecycle.

## Steps

- reuse existing validators only where the contract matches;
- create a pure CLI/API without mutation;
- produce separate reports for each layer;
- create a negative corpus for each rule;
- link each rejection to a path/field/claim;
- distinguish `RETAINED`, `REJECTED`, `BLOCKED`, `UNVERIFIED`.

## Gate

Every negative case fails closed before backup/install; the complete positive case produces `READY_FOR_ACCEPTANCE`; reports are reproducible from bytes/manifests.

## Adaptation

Byte/hot-path thresholds and allowlists are set after measuring C2; they are never raised just to make a candidate pass.
