# Plan 08 — C7: promotion and distribution

**Outcome:** reproducible, documented, and legally distributable pilot version.
**Prerequisites:** C0–C6.

**English** | [Español](08-c7-promocion.es.md)

## Steps

1. Reconcile results, retentions, drift, rollback, and feedback.
2. Update architecture/index/status/guides only with facts.
3. Run suites and validators from a fresh clone.
4. Resolve the framework license.
5. Add `THIRD_PARTY_NOTICES.md` if MIT or other licensed code/text was reused.
6. Review provenance, private data, paths, and secrets.
7. Create the pilot tag.
8. Publish only to authorized destinations/within authorized scope.
9. Repeat the clean-room run from the tag.
10. Issue a report on limitations and feedback.

## Gate

- reproducible tag;
- clean clone + prepared DSH provider;
- bootstrap/Creator/accept/rollback demonstrated;
- coherent documents and license;
- no maintainer paths/identities;
- visible feedback and limitations;
- authorized publication or explicit retention.

The absence of public publication does not block the technical MVP if authorized private distribution is documented.

## Adaptation

The destination, license, notices, and scope of publication are decisions for the owner. Lack of authorization keeps C7 `BLOQUEADO`; local commits do not turn it into a success.
