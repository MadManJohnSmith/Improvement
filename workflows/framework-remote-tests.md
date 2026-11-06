# Workflow: pruebas remotas del framework

**Estado:** especificado a partir del área E (2026-11-06). Cubre el repositorio
del framework, no los proyectos de los usuarios.

## Objetivo

Dejar las comprobaciones del framework corriendo en remoto: la suite
determinista en cada cambio y las evaluaciones de Creator cuando el mantenedor
las pide, con reportes y evidencia reproducibles.

## Disparo

- **Suite determinista:** `push` y `pull_request`.
- **Evaluación de Creator:** `workflow_dispatch` manual, con versión de prompt,
  modelo y presupuesto como entradas.
- Sin horario por defecto.

## Runner

GitHub Actions del repositorio. No hay runner propio ni infraestructura nueva.

## Job 1 — suite determinista

1. Checkout del repositorio.
2. Preparar Python y Node.
3. Ejecutar `python3 -B -m unittest discover -s tests`.
4. Ejecutar los verificadores de plugins
   (`scripts/dsh-plugins/verify-doc-drift.mjs` y
   `scripts/dsh-plugins/verify-workflow-write.mjs`).
5. Publicar el log y el resultado como artifacts del workflow.

Un fallo deja el commit rojo y el flujo publica la prueba que falló y su log. El
mantenedor decide si corrige o revierte; el flujo no repara el repositorio.

## Job 2 — evaluación de Creator

1. Entradas manuales: versión de prompt, modelo y presupuesto.
2. El perfil de DSH del entorno se rellena desde los secretos del repositorio.
   El flujo no fija un proveedor: usa el perfil de DSH disponible en el runner.
3. El producto de prueba es un fixture mínimo y sanitizado en `fixtures/`, con
   identidad y HEAD fijados. Ninguna ruta local del mantenedor entra al flujo.
4. Se ejecuta el caso pre-registrado con `scripts/creator_eval.py` y su conjunto
   cerrado de veredictos (`PASS`, `FAIL_MECHANISM`, `FAIL_COMPLETION`,
   `ABSTAIN`).
5. Se publican el reporte, el roster y los digests como artifacts.

## Checkpoints

- **Fallo de suite:** notificación con la prueba y el log; el mantenedor decide.
- **Reporte de evaluación:** el mantenedor lo revisa y decide el merge. El
  veredicto informa; no es una puerta mecánica. Un `ABSTAIN` por infraestructura
  no bloquea por sí solo.

## Evidencia y secretos

- La suite publica logs y resultados; la evaluación publica reporte, roster,
  journal comprimido y digests.
- El reporte y el roster se versionan solo cuando el mantenedor actualiza el
   roster; no se commitea cada corrida.
- Las claves del proveedor viven en secretos del CI y nunca se imprimen. El
  evaluador registra el modelo usado, no elige proveedor.

## Abierto

- Contenido exacto del fixture y su `root_identity` (hoy el caso usa un producto
  externo).
- Nombres de los archivos de workflow y plantilla del perfil DSH para el CI.
- Modelo y presupuesto por defecto de la evaluación manual.
