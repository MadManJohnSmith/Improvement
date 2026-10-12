# Modos del ciclo de vida de un proyecto: dominios, límites y secuencia

**Estado:** inventario de diseño; no afirma modos implementados. [English](project-lifecycle-modes.md).

Improvement aspira a servir todo el ciclo de vida de un proyecto. Una skill es un procedimiento
reutilizable; un **modo** es un rol operativo específico del proyecto, publicado por el Host,
con techo de capacidades, contrato de estado y pruebas de aceptación explícitos. El Host
conserva autorización, evidencia, publicación y veredictos. Varias skills no implican
necesariamente varios modos: crear otro solo cuando su frontera de autoridad, entrega o
handoff difiera materialmente.

## Lo que existe hoy

| Rol | Límite | Estado comprobado |
|---|---|---|
| Auditor | Lee el producto y escribe hallazgos con evidencia y handoff. | Publicado en sesiones DSH reales; el gate del corpus completo aún se abstiene sin adaptador evaluador Host compatible. |
| Reparador continuo | Repara hallazgos registrados en sombra provisionada por el Host, verifica con el entrypoint del producto, nunca fusiona/publica. | La edición X1 bajo preset web real y el cierre `DIRTY` ocurrieron en turnos separados; no prueba una campaña autónoma única. |
| Implementador | Implementa una **petición nueva y autorizada**, no un hallazgo existente, en sombra aislada y con prueba del comportamiento pedido. | Contrato y transacción de tres presets existentes; un caso DSH real produjo candidata con 6/6 tests, pero Creator `ACTIVE` post-budget y paquete generado íntegro aceptado por Host **no están probados**. `verify_implementation` tampoco exige aún el entrypoint del plan Host. No marcar el rol completo. |

Las capacidades internas de Creator (`capability-designer`, `skill-generator`, gestión de
contexto) son maquinaria de generación, **no** modos publicados del proyecto. Skills base como
`brainstorming`, `writing-plans`, `executing-plans`, `test-driven-development` y documentación de
ADRs son procedimientos para el modo autorizado; ninguna por sí misma autoriza escritura ni
crea un rol.

## Dominios candidatos y entregas no solapadas

| Dominio / modo candidato | Entrada y salida | Límite de autoridad y handoff | Prioridad |
|---|---|---|---|
| Descubrimiento / analista | Pregunta autorizada y hechos observados → restricciones, incógnitas y requisitos citados. | Solo lectura; marca hipótesis, no emite veredictos ni edita producto. Alimenta ideación o plan. | Alta, solo diseño |
| Ideación / alternativas | Restricciones observadas → al menos dos opciones viables, costes, criterios de descarte y recomendación. | Solo lectura; procedimiento `brainstorming`; no ejecuta plan ni adopta diseño sin checkpoint de titular/Host. Puede combinarse con descubrimiento mientras no haya evidencia de frontera distinta. | Alta, solo diseño |
| Planificador | Objetivo y restricciones elegidas → unidades, dependencias, presupuestos, tests y paradas. | Escribe propuesta en estado de workspace, no en producto. Operador/Host aprueba plan antes de ejecutar. | Alta, solo diseño |
| Arquitecto / diseñador | Requisitos aprobados → interfaces, ADRs, migración/rollback y restricciones transversales. | Propone diseño técnico pero no amplía alcance ni se autoaprueba. Un modo aparte se justifica si ADR/interfaz requieren gate distinto. | Alta, solo diseño |
| Implementador | Plan/petición aprobados → diff de sombra y evidencia de comportamiento. | Escritura de candidata y ejecución de tests solo en sombra; no reescribe plan ni fusiona. **Terminar antes este modo existente.** | Alta, parcial |
| Revisor / verificador | Diff y plan → evidencia independiente de tests/build/seguridad y hallazgos de revisión. | Solo lee producto; puede ejecutar checks autorizados en entorno aislado. El Host juzga códigos de salida/digests y emite veredicto. Puede ser fase de workflow en vez de preset permanente. | Media |
| Release / operaciones | Cambio aceptado por Host y plan de despliegue → checklist, migración y evidencia de monitorización. | Publicación, push, despliegue y rollback son acciones explícitas del operador/Host; no modo autónomo de release por defecto. | Posterior |

Auditor y reparador conservan sus fronteras. Un modelo de decisión (System 1) **no es un
modo**: puede proponer una elección tipada pequeña a un rol o al Host, pero nunca ejecuta
herramientas ni concede autoridad. Véase [diseño System 1](system-one-decision-channel.es.md).

## Ciclo propuesto y gates de aceptación

```text
petición → descubrimiento → alternativas (si existen de verdad) → plan / ADR aprobado
         → sombra implementador → checks / revisión independiente → veredicto Host
         → integración / release por operador → feedback operativo → nueva petición
```

1. Terminar primero el implementador: paquete Creator post-budget `ACTIVE`, preset específico
   cargado en sesión DSH real, entrypoint del plan Host usado en aceptación, producto limpio y
   diff acotado en sombra. Hasta entonces el caso real existente sigue siendo parcial.
2. Pilotar descubrimiento+ideación como un modo de solo lectura o fase de workflow acotada.
   Separarlos solo si se miden permisos/handoffs distintos; evitar un preset por skill.
3. Pilotar planificación+arquitectura como gates distintos si el plan y ADR/interfaz aprobados
   tienen propietarios o evidencia diferente. Ninguno se autoaprueba por su prosa.
4. Añadir verificación independiente antes de un modo de release. Comandos test/build viven en
   el plan de capacidades Host; código de salida y captura son evidencia, no un dicho del modelo.
5. Medir cobertura de proyectos reales (lenguajes, stacks, funciones nuevas, bugs, upgrades,
   despliegue) antes de afirmar «cualquier proyecto» o ciclo de vida completo.

**Decisión abierta:** el número final de presets depende de evidencia. La tabla identifica
*dominios*, no promete siete modos. Creator solo debería generar roles con ámbitos,
capacidades aplicables y handoffs probados para ese proyecto.
