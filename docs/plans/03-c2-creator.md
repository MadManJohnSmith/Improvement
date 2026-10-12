# Plan 03 — C2: DSH Creator automation

**English** | [Español](03-c2-creator.es.md)

**Output:** Creator generates a valid project-specific package from an automatic bootstrap request.
**Preconditions:** C0/C1; local RPC client and configured DSH provider.

## Steps

1. Implement a Host-side client without persisting a token/cookie.
2. Create a Creator session with the correct cwd/roots/inputs.
3. Send a versioned prompt invoking the internal scope/audit/architect/document/test/develop capabilities.
4. Resolve each need in the mandatory order: base inmutable (the immutable base) → catálogo especializado (the specialized pattern catalog) → composition → limited override → extension.
5. If an extension is generated, include a justification for why the preceding layers do not apply, and its own contract/scenarios.
6. Monitor requests, tokens, timeout, descendants and checkpoint.
7. Require `generation-manifest.json`, `finish.json`, contracts, modes, skills and acceptance-plan.
8. Verify that Creator writes only to staging.
9. Have Creator emit `bootstrap.accept.request` with the exact digest.
10. Retain on unresolved decisions, missing outputs or self-acceptance.

> **Bilingual terms.** `base inmutable` and `catálogo especializado` are kept verbatim: they are
> the Spanish terms the repository's tests assert on, and `docs/creator-preset-spec.md`
> defines the same order with their meanings.

## Gates

- Creator session is observable and authenticated locally;
- no credentials in artifacts;
- repeatable generation on a fixture;
- two project-specific modes and justified skills;
- no universal preset;
- finish/checkpoint can be recovered;
- Creator cannot mark ACTIVE.

## Negative cases

Prompt injection from the project, attempt to modify Host/validator, new provider/model, output outside staging, false manifest, prompt without source, unobserved capability, timeout and partial generation.

## Authorized adaptation

The DSH client and authentication method are adapted to the observed runtime. Do not add a general API or accept unrestricted shell access as a substitute.
