# Domain Docs

Maintained with `/setup-matt-pocock-skills` (manual invocation). To choose the skill or flow that consumes this configuration, use `/ask-matt`.

How the engineering skills consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`GLOSSARY.md`** at the repo root.
- **`docs/adr/`**: read ADRs that touch the area you're about to work in.
- **`ARQUITECTURA_FLUJO_AGENTES.md`**: normative v3.0 architecture of Improvement.

## File structure

Single-context repo:

- `GLOSSARY.md`
- `docs/adr/0001-stdlib-first-ast-signature-pinning.md`
- `docs/adr/0002-harness-driven-doc-sync-via-dsh-plugins.md`

## Use the glossary's vocabulary

When your output names a domain concept, use the exact term defined in `GLOSSARY.md` and `schemas/drift.schema.json`. Do not invent parallel status enums.
