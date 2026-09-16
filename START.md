# Entrada del framework

## Estado de esta entrada

El flujo final 3.0 (`bootstrap install` que llama Creator y activa modos específicos por proyecto) todavía no está implementado. Este archivo conserva la entrada operativa comprobada del MVP para mantenedores y pilotos controlados.

No uses START como evidencia de C0–C7. El progreso está en `PLAN_IMPLEMENTACION.md`.

## Incorporación actual

Ante «incorpora/prepara»:

1. Lee `AGENTS.md`, `docs/usage.md`, `docs/setup-dsh.md` y `skills/project-onboarding/SKILL.md`.
2. Identifica framework, producto y workspace externo; nunca pongas workspace dentro de producto/framework.
3. Registra revisiones/estado Git sin limpiar trabajo ajeno.
4. Descubre instrucciones/canónicos existentes y evita un segundo backlog.
5. Ejecuta `scripts/onboard.py` primero dry-run y luego `--init` si no hay conflicto.
6. Si se autoriza preparar skills, usa `--prepare-skills --session-root <padre>`; no modifica configuración global ni concede permisos.
7. Verifica catálogo/carga nativa según `docs/setup-dsh.md`.
8. Devuelve incorporación mínima preparada o `RETAINED` con bloqueo exacto.

Ejemplo actual:

```bash
python3 -B /ruta/framework/scripts/onboard.py \
  --project /ruta/producto \
  --workspace /ruta/workspace \
  --name proyecto \
  --prepare-skills \
  --session-root /ruta/padre

# repetir con --init después de revisar
```

## Despacho actual

- Auditoría completa: carga `workflow-complete-auditor`.
- Auditoría unitaria: carga `workflow-auditor`.
- Reparación acotada: carga `workflow-continuous-repair`.
- Ejecutor/QA son funciones internas cuando la composición comprobada los ofrece.

Mensajes breves:

> Audita completamente este proyecto; no modifiques ni publiques.

> Audita este flujo o componente.

> Repara la cola autorizada en la rama o copia de prueba.

> Repara solo este hallazgo.

## Límites actuales

- No instalar presets genéricos como resultado final para terceros.
- Presets Syncify/RehabWeb son fixtures de regresión.
- No inventar que Creator/accept automático existen.
- No usar shell/cwd/enlaces para eludir permisos.
- No modificar framework durante misión operativa.
- No publicar/integrar sin mandato.
- `RETAINED` es correcto cuando falta capacidad/evidencia.

## Destino 3.0

C0–C7 reemplazarán esta preparación por:

```text
bootstrap install
→ DSH Creator automático
→ modos/skills específicos
→ Creator invoca accept
→ Host valida/backup/staging/aceptación
→ ACTIVE o rollback
```

Cuando C0–C7 pasen clean-room, START cambiará a la interfaz de un comando.
