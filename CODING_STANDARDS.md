# Estándares de revisión

Lo lee el revisor, no el implementador. Cada regla nace de un fallo contado en el
historial local de ZCode (3.252 sesiones, 136.565 llamadas de herramienta,
2.720 errores): la evidencia manda, no la preferencia.

## Edición

- Leer el archivo inmediatamente antes de editarlo y re-leerlo si cambió desde la
  última lectura. (161 «File has not been read yet», 119 «modified since read».)
- No editar en lote varios archivos tras un cambio externo; cada ancla se
  verifica contra el texto actual.
- Un reemplazo que no cambia nada es un fallo: comprobar que `old_string` y
  `new_string` difieren. (87 «No changes to make».)
- `replace_all` solo cuando se quieren todas las ocurrencias. (17 «Found 2
  matches».)
- No usar herramientas de escritura en plan mode. (43 violaciones.)

## Rutas

- No adivinar rutas: verificar con `ls` o `test -e` antes de leer o escribir.
  (≈900 «File does not exist»; ≈136 en proyectos de código.)
- Preferir rutas relativas al cwd del repo. Para rutas externas, copiarlas de una
  salida previa en vez de reescribirlas.

## Herramientas

- Usar los nombres de parámetro exactos del esquema. Tras un fallo de validación,
  corregir el parámetro, no reescribir la intención. (610 «inputSchema
  validation».)

## Subagentes

- No lanzar más de 2-3 en paralelo: por encima fallan la concurrencia y la cuota.
- Un agente cancelado, inactivo o sin retorno no se reintenta a ciegas; primero se
  lee por qué. (149 errores de Agent: 44 cancelados, 22 inactivos, 11 de
  concurrencia.)

## Suite y commits

- Durante el ciclo, el módulo afectado; la suite completa una vez al cierre de la
  unidad. Un cambio solo de documentación no pide la suite completa.
- Antes de `reset`, `cherry-pick -i` o cualquier reescritura, mirar `git status`:
  el trabajo sin versionar no se descarta.
- Si falla el proyecto desechable, se corrige el proyecto, no el flujo.
- El estado remoto se comprueba con `gh` o `git ls-remote`; no se afirma de
  memoria.
