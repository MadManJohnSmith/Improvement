# Cambios

## Separación H1-only de QueueItem — 2026-09-10

- Preparar fuera del repositorio una unidad nueva que retira únicamente `service`, `quality`, `effective_service`, `original_service` y `allow_fallback` en `ui/src/api/types.ts`; no aceptar la expansión completa previa.
- Conservar reproducción roja y prueba verde, `change_scope` explícito de un archivo y reauditoría mecánica de hashes/alcance.
- Mantener `RETAINED`/`UNVERIFIED` por falta de QA independiente real observable; no modificar ni integrar Syncify.

## Cierre honesto del contrato v0.1 — 2026-09-10

- Añadir `missions.py reaudit` para ligar mecánicamente candidato, prueba y resultado antes de la revisión semántica.
- Extender el ciclo sintético con la reauditoría incremental; se conserva explícitamente la revisión semántica para Auditor/QA.
- v0.1 se declara operativa acotada, no autonomía ni piloto real de producto.

## Alcance de Reparación continua verificado — 2026-09-10

- Trayectoria Standard sintética cargó `workflow-continuous-repair` y `workflow-bounded-acceptance`.
- Una prueba verde con archivo fuera de `change_scope` fue rechazada por `missions.py verify`; `RETAINED` se conservó.
- No se modificó producto/framework y no se afirma QA semántica multimodelo.

## Alcance explícito de reparación — 2026-09-10

- Exigir `change_scope` en tareas repair y rechazar aceptación si cualquier archivo fuera de ese subconjunto difiere de `base`, aunque la prueba pase.
- Añadir regresiones para alcance ausente y archivo inspeccionado modificado fuera de permiso.


## Descubrimiento nativo desde el padre — 2026-09-10

- Conservar cwd padre en Standard mediante enlaces individuales gestionados a las copias externas; manifiesto, dry-run, conflictos sin sobrescritura y retirada solo de entradas propias. Sin configuración global ni edición del consumidor/producto.
- Regresión DSH instalada: dos padres, un scope compartido con las filas reales de skills de Standard, cuerpos y destinos exactos, rechazo cruzado y retorno al primer agente. No Host completo, modelos ni garantía de sandbox.
- Separar errores de argumentos bash de denegaciones; no escalada automática a acceso total. Validación nativa de emparejamiento/rechazo y escenarios conductuales documentados, no enforcement nuevo.
- Siete tests Python aprobados; guía de preparación integrada y límites de permisos explícitos.

## Operación acotada v0.1 — 2026-09-10

- Añadir entradas Auditor y Reparación continua en Standard, despacho START y guía con permisos efectivos del producto hermano; sin producto vivo, presets nuevos ni autonomía Host.
- Añadir recibos task/result, runner argv explícito con timeout/salidas/digests y verificación documental de candidato/prueba/referencia QA; no autentica revisión semántica ni autoridad.
- Copiar skills completas recursivamente; repetición idéntica y actualización explícita respaldada, conservando conflictos y ediciones locales.
- Seis regresiones Python aprobadas, incluido ciclo sintético rojo/verde y rechazos negativos; QA fixture declaradamente simulada. Carga nativa determinista de siete skills con DSH instalado, sin modelos. Piloto real pendiente.

## Aceptación acotada en Standard — 2026-09-10

- Registrar carga nativa y aplicación observadas en tres turnos de un caso sintético: ACCEPTABLE → RETAINED → ACCEPTABLE, sin ampliar requisitos ni escribir archivos.
- Comprobar un cuarto turno con evidencia necesaria ausente: UNVERIFIED, solicitud ligada al candidato, sin ejecución ni ampliación de alcance.
- No modificar la skill: no se observó un defecto en este recorrido. Conservar límites de validación y trayectoria privada externa.

## Corrección de descubrimiento DSH

- Entrada por raíz del workspace externo; retirada plantilla inefectiva sobre proveedor global desactivado por Web. Sin overlay ni cambios globales.
- Regresión contra servicios instalados: alcance de agente, padre frente a workspace, carga nativa de cinco cuerpos y hashes sin modelos.
- Preparación rechaza enlaces en destino `.agents/skills` y manifiestos de origen; pruebas de no escritura fuera del workspace.

## Overlay portable para skills por proyecto — 2026-09-10

- Añadir `docs/dsh-project-profile.patch.yml` como plantilla de override con `customSkillDirs` y placeholder explícito.
- Mantener la ruta real fuera del repositorio; no aplicar ni modificar perfiles globales.
- Documentar que el override debe probarse en un perfil dedicado y que el preset efectivo puede montar el proveedor en alcance propio.

## Skills por proyecto: adaptador de loader documentado — 2026-09-10

- Documentar que la copia en `.agents/skills` no activa el proveedor en DSH.
- Registrar el fragmento conceptual `customSkillDirs`/`includeDefaultRoots` para un Host/preset dedicado, sin aplicarlo globalmente ni presentarlo como configuración universal.
- Mantener la activación efectiva pendiente de una sesión DSH reiniciada con overlay comprobado.

## Frontera canónica durante misiones — 2026-09-10

- Corregir START.md: una misión operativa no edita el framework canónico para adaptar su procedimiento ni pide hacerlo durante la misma misión.
- Añadir `framework_clean()` y regresión permanente para detectar cambios inesperados en la raíz Git del framework.
- Mantener las propuestas de evolución fuera del árbol hasta una misión de mantenimiento autorizada.

## START.md — punto de entrada legible por agentes — 2026-09-10

- Crear START.md: procedimiento de incorporación de proyecto con alcance, límites y retorno, todo consultable sin exigir al usuario un prompt largo.
- Actualizar README: instrucción breve de arranque DSH Standard y modelo de publicación commit→push→pull.
- Publicación por commit con push autorizado; el usuario jala cambios con pull en su clon de Syncify.

## Repositorio canónico — 2026-09-10

- Establecer reglas persistentes en AGENTS.md: solo archivos distribuibles y regresiones permanentes en Git; datos y resultados de ensayos fuera del árbol.
- Adoptar evaluación incremental de sesiones DSH Standard para mejorar el flujo; no cambia los dos modos finales.
- Configurar identidad Git autorizada para commits locales; sin publicación remota.

## Distribución inicial — 2026-09-09

- Separar framework reusable de archivos privados, clones, runtime y antecedentes; preservar originales en archivo hermano no publicable.
- Conservar arquitectura y sus invariantes, generalizar perfiles y mantener dos modos objetivo: Auditor y Reparación continua. Search no es dependencia.
- Añadir onboarding Python explícito, comprobación local y cinco skills portables; separar estado real de arquitectura.
- Preservar publicador experimental en archivo externo por sus restricciones de ensayo, sin anunciar adaptación universal ni autonomía completa.
- Preparar Git local sin remoto; commit pendiente de identidad configurada. No elegir licencia en nombre del titular.

Cambios futuros se registran aquí de forma breve y en commits; antecedentes privados no se importan al historial público.
