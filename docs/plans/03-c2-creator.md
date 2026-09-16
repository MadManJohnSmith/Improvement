# Plan 03 — C2: automatización DSH Creator

**Salida:** Creator genera un paquete específico válido desde una petición automática del bootstrap.
**Precondiciones:** C0/C1; cliente RPC local y proveedor DSH configurado.

## Pasos

1. Implementar cliente Host-side sin persistir token/cookie.
2. Crear sesión Creator con cwd/roots/inputs correctos.
3. Enviar prompt versionado que invoque capacidades internas scope/audit/architect/document/test/develop.
4. Resolver cada necesidad en orden obligatorio: base inmutable → catálogo especializado → composición → override limitado → extensión.
5. Si se genera extensión, incluir justificación de por qué no aplican capas anteriores y su contrato/escenarios propios.
6. Supervisar requests, tokens, timeout, descendientes y checkpoint.
7. Exigir `generation-manifest.json`, `finish.json`, contracts, modes, skills y acceptance-plan.
8. Verificar que Creator solo escribe staging.
9. Hacer que Creator emita `bootstrap.accept.request` con digest exacto.
10. Retener ante unresolved decisions, outputs faltantes o self-acceptance.

## Gates

- sesión Creator observable y autenticada localmente;
- sin credenciales en artefactos;
- generación repeatable en fixture;
- dos modos específicos y skills justificadas;
- ningún preset universal;
- finish/checkpoint recuperables;
- Creator no puede marcar ACTIVE.

## Negativos

Prompt injection desde el proyecto, intento de modificar Host/validator, provider/model nuevo, output fuera de staging, manifest falso, prompt sin fuente, capacidad no observada, timeout y generación parcial.

## Adaptación autorizada

El cliente DSH y la forma de autenticar se adaptan al runtime observado. No añadir API general ni aceptar shell libre como sustituto.
