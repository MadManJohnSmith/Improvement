# Estado comprobado del framework

**Actualización:** 2026-09-18
**Arquitectura vigente:** [v3.0](../ARQUITECTURA_FLUJO_AGENTES.md)
**Backlog único:** [C0–C7](../PLAN_IMPLEMENTACION.md)

Este documento registra únicamente el estado vigente. El detalle de iteraciones anteriores está en Git/`CHANGELOG.md`, no aquí.

## Base técnica comprobada

El repositorio conserva servicios Host y regresiones reutilizables:

- onboarding externo idempotente, manifest y enlaces gestionados;
- inventario/partición SHA-256 y cobertura fail-closed;
- contratos de misión, checks y verificación documental;
- publicador local idempotente y etapas de rol;
- presupuesto durable, decisiones y métricas append-only;
- controlador Host con locks/reconciliación/cancelación;
- launcher Linux aislado y canal de inferencia acotado;
- plugin de escritura con semántica de escalada corregida;
- QA, reauditoría semántica, archivo/restauración y crash de proceso/contenedor demostrados;
- distribución privada por red y clean-room del código base demostrada.

Estas capacidades constituyen la base MVP comprobada. No equivalen al flujo de incorporación 3.0 ni a modos finales para proyectos nuevos.

## Eliminaciones de vigencia

- No hay presets Auditor/Reparación genéricos en la distribución canónica.
- No hay skills operativas universales del MVP en el árbol actual.
- No hay planes P0–P9, M1–M8 ni diagramas v2.4 en la documentación vigente.
- Los nombres/configuraciones usados en proyectos de prueba no son defaults.
- El contrato Creator de dos archivos fue reemplazado por el paquete generacional completo.

El historial eliminado sigue disponible en Git y no debe reconstruirse como instrucciones actuales.

## Estrategia de skills aprobada

Creator selecciona primero la biblioteca base inmutable y el catálogo de patrones especializados; después compone o aplica overrides declarativos. Solo genera una extensión cuando demuestra que esas capas no aplican, con contrato, escenarios y aceptación específica. Una skill transferida no es válida automáticamente para otro proyecto. La regeneración no sustituye bases por conveniencia.

Las fuentes externas evaluadas quedan registradas con procedencia fijada en `library/source-registry.json` (esquema `source-registry.schema.json`): 43 fuentes — 20 repositorios de skills/índices/runtimes y 23 estándares o guías, con `fastapi-pydantic-docs` sustituida por `fastapi-framework` y `pydantic-framework` fijadas por observación directa — con URL canónica, commit, fecha, licencia, estado y decisión razonada. Una fuente sin revisión fijada o con licencia no resuelta no puede ser `CANDIDATE` ni `ACTIVE`; la adquisición es solo manual con pin, sin npx/marketplace/descargas, con staging fuera del árbol y validación Host previa. El inventario pormenorizado de 11.407 entradas que respalda las decisiones se mantiene en un espacio de auditoría externo; el registro solo conserva su digest SHA-256.

La biblioteca base está materializada en `library/library.json` con contenido y escenarios en `library/base/`. La conversión de la base está completa: 21 skills (reimplementación propia con atribución MIT de `obra-superpowers` y `addyosmani-agent-skills`) — brainstorming, writing-plans, executing-plans, systematic-debugging, test-driven-development, requesting-code-review, receiving-code-review, verification-before-completion, finishing-a-development-branch, spec-driven-development, constraint-driven-development, source-driven-development, security-and-hardening, context-engineering, api-and-interface-design, observability-and-instrumentation, documentation-and-adrs, performance-optimization, incremental-implementation, code-simplification y deprecation-and-migration. Cada skill base tiene un escenario positivo y al menos uno de veredicto FAIL/BLOCKED, y la cobertura es bidireccional y obligatoria en la suite. Se rechazaron como base idea-refine, interview-me y using-agent-skills por ser meta o interactivas sin valor universal.

El catálogo especializado contiene cuatro patrones activados por evidencia, con contenido en `library/catalog/` y escenarios propios: `fastapi-openapi-contract-check` (dominio `python-backend`, fuente `fastapi-framework` fijada por observación directa), `web-accessibility-wcag-audit` (dominio `web-frontend`, fuente `wcag-22` fijada por versión de especificación — 2.2, W3C Recommendation 2024-12-12 —), `http-security-headers-verifier` (dominio `web-platform`, fuente `mdn-web-docs` fijada por instantánea de mdn/content) y `aws-iam-policy-static-review` (dominio `aws-security`, fuente `aws-waf-apg` fijada por instantánea de awsdocs/iam-user-guide). Todos se activan solo ante señales observables declaradas en su contrato; los criterios de activación declarados deben aparecer verbatim en el contenido del patrón, y la regresión lo exige. Los estándares versionados se fijan mediante `spec_version` (esquema de registro y de biblioteca extendidos); el pin por commit queda reservado a repositorios. El catálogo no recibe más patrones sin evidencia de dominio y aceptación específica.

## Experiencia final objetivo

```text
usuario configura DSH/proveedor una vez
→ bootstrap install
→ Creator descubre/diseña/genera modos y skills específicos
→ Creator invoca accept
→ Host valida y respalda
→ aceptación automática
→ activación transaccional o rollback
→ usuario opera <Proyecto>-auditor y <Proyecto>-continuous-repair
```

## Límites vigentes

- C0–C7 completados con evidencia recuperable de DSH real (preset cordis) en dos proyectos piloto (Python y multiparte).
- `THIRD_PARTY_NOTICES.md` incorporado para atribución MIT de jsmastery-pro/skills.
- Publicación remota y release público requieren autorización del titular según la política de distribución.
- La pérdida física de energía y descendientes remotos hostiles no tienen garantía total.
- Configurar proveedor en DSH es responsabilidad previa del usuario; el framework no obtiene API keys.

## Pendiente vigente — C0–C7

| Etapa | Estado | Salida requerida |
|---|---|---|
| C0 | HECHO | schemas/fixtures/manifests/contracts/tests/handoffs/drift y procedencia |
| C1 | HECHO | `bootstrap install` determinista y reanudable |
| C2 | HECHO | sesión DSH Creator real (preset cordis) generó paquete específico y llamó accept |
| C3 | HECHO | validador Host fail-closed de 10 capas verificado sobre paquete real C2 (READY_FOR_ACCEPTANCE) |
| C4 | HECHO | backups verificados, staging, swap atómico y rollback comprobados sobre paquete real |
| C5 | HECHO | Creator invocó accept; Host ejecutó validación estática, ledger de evidencia y veredicto |
| C6 | HECHO | pilotos clean-room ejecutados en proyecto Python y proyecto multiparte con DSH real |
| C7 | HECHO | reconciliación de runs, THIRD_PARTY_NOTICES.md, 193 pruebas pasando y promoción verificada |
