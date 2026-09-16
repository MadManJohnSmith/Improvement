# Entrada de preparación del framework

## Estado

La arquitectura vigente es 3.0. El flujo final de usuario (`bootstrap install` → Creator automático → modos/skills específicos → Host accept/backup/activación) está pendiente de C0–C7.

Este archivo no despacha modos genéricos ni procedimientos del MVP anterior. Esos artefactos fueron eliminados del árbol actual y permanecen en Git.

## Preparación disponible hoy

Ante «incorpora/prepara»:

1. Lee `AGENTS.md`, `ARQUITECTURA_FLUJO_AGENTES.md`, `PLAN_IMPLEMENTACION.md`, `docs/usage.md`, `docs/setup-dsh.md` y `skills/project-onboarding/SKILL.md`.
2. Identifica framework, producto y workspace externo; no los solapes.
3. Registra revisión/estado Git sin limpiar trabajo ajeno.
4. Descubre instrucciones/canónicos existentes y evita un segundo backlog.
5. Ejecuta `scripts/onboard.py` primero dry-run y luego `--init` si no hay conflicto.
6. Si se autoriza preparar las skills generales actuales, usa `--prepare-skills --session-root <padre>`; no modifica configuración global ni concede permisos.
7. Verifica catálogo/carga nativa según `docs/setup-dsh.md`.
8. Devuelve `incorporación mínima preparada` o `RETAINED` con bloqueo exacto.

```bash
python3 -B /ruta/framework/scripts/onboard.py \
  --project /ruta/producto \
  --workspace /ruta/workspace \
  --name proyecto \
  --prepare-skills \
  --session-root /ruta/padre

# revisar y repetir con --init
```

Esto prepara perfil y skills generales. **No crea todavía modos Auditor/Reparación específicos ni autoriza una misión de producto.**

## Qué no hacer

- No cargar ni recrear presets/modos genéricos eliminados.
- No copiar procedimientos del MVP desde Git histórico.
- No presentar Standard como experiencia final.
- No inventar `bootstrap.py`/Creator/accept antes de C0–C7.
- No usar shell/cwd/enlaces para eludir permisos.
- No modificar el framework durante misión operativa.
- No publicar/integrar sin mandato.

## Destino C0–C7

```text
bootstrap install
→ DSH Creator automático
→ discovery/design/scenarios/generation específicos
→ Creator invoca accept
→ Host valida/backup/staging/aceptación
→ <Proyecto>-auditor + <Proyecto>-continuous-repair ACTIVE
→ rollback/RETAINED si falla
```

Hasta completar C7, este repositorio es para desarrollo/mantenimiento de la arquitectura 3.0, no para entregar una experiencia final de auditoría genérica.
