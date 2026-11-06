# Workflow: diseño de un workflow de usuario

**Estado:** especificado a partir de las áreas A, C y E (2026-11-06).

## Objetivo

Convertir un loop recurrente que el usuario describe en un spec revisable y
aprobado, y dejarlo corriendo bajo el disparo que el propio spec declare.

## Disparo

- El usuario pide automatizar un loop en la interfaz.
- Una vez aprobado el spec, corre por evento —commit nuevo o prueba fallida— o
  a mano. Sin horario por defecto.

## Pasos

1. **Entrevista.** El framework pregunta por rondas, como en una sesión de
   `loop-me`: qué dispara el loop, qué produce, dónde está el checkpoint, qué
   brief necesita el usuario. Cada pregunta lleva una respuesta recomendada.
2. **Spec.** El framework escribe `workflows/<nombre>.md` con trigger, pasos,
   checkpoint, brief y criterio de éxito. La ubicación es configurable: por
   defecto en el producto, para que viaje con su Git; también puede quedar en el
   workspace del framework.
3. **Aprobación del spec.** El usuario revisa el spec y lo aprueba antes de que
   se ejecute. La escritura en el producto queda autorizada por esa aprobación,
   no por un modo.
4. **Armado.** El framework registra el disparo: evento (commit o prueba
   fallida) o manual. El runner local de DSH queda a la escucha.
5. **Ejecución.** Cada corrida produce el brief que el spec define y, si hay
   checkpoint, espera la decisión del usuario. Si no hay checkpoint, corre hasta
   el final y entrega el brief.
6. **Cambios.** Toda modificación del spec crea una versión nueva, muestra su
   brief y requiere aprobación antes de la siguiente corrida. Las corridas
   registran la versión del spec que las produjo.

## Checkpoints

- Aprobación del spec inicial.
- Los checkpoints internos que el spec declare; ninguno por defecto si el loop
  es solo informativo.

## Briefs

- El brief de cada corrida lo define el spec: qué produjo, qué decidió, qué
  evidencia lo respalda y el enlace al artefacto.
- El brief nunca es la salida cruda: es la decisión lista para el usuario.

### Evidencia

- Spec versionado, journal de la corrida y brief quedan enlazados.
- Los journals y la evidencia no se borran al cerrar la corrida.

## Abierto

- Plantilla exacta de los campos del spec (`trigger`, `brief`, `checkpoint`,
  `success`).
- Vigilante local de eventos: cómo detecta commits y pruebas fallidas con la
  aplicación cerrada.
- Versión remota del runner: opción posterior, fuera de este loop.
