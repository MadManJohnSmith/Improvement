# Cambios

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
