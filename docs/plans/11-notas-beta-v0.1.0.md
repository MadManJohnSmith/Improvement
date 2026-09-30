# v0.1.0-beta — notas de publicación

> **Borrador preparado, no publicado.** Publicar (tag `v0.1.0-beta` y push) requiere
> autorización del titular, y G0 —la licencia— sigue sin elegir: sin `LICENSE` el
> repositorio no debe anunciarse como instalable por terceros.

## Qué es

Un framework que instala en tu repositorio dos modos generados específicamente para tu
proyecto —un auditor y un reparador continuo— con memoria acotada en disco, verificación
contra los comandos reales de tu proyecto y una frontera de integración que no puede
saltarse. Un comando instala; dos prompts sencillos operan.

## Qué se ha probado

Cuatro campañas completas sobre repositorios reales, con el producto intacto hasta que el
operador hizo commit, fast-forward y push.

| Campaña | Stack | Hallazgos | Verificaciones | Estado |
|---|---|---|---|---|
| Syncify | Rust / Tauri / Vue | 77 (114 registros) | 67 (61 PASS, 6 BLOCKED) | CI verde en 3 jobs, 15 commits |
| RehabWeb | Django / Vue | 45, 6 CRITICAL | 4 | 108 pruebas Django reales en verde |
| LoboApp | Flutter / Android | 14 (9 + 5 en reauditoría) | 14 PASS con `flutter test` | 166 pruebas Flutter y `flutter analyze` sin incidencias |
| Improvement (self-test) | Python / unittest | 8 (7 + 1 en reauditoría) | 14 PASS con la suite del propio proyecto | 606 pruebas en verde |

## Lo que hay que saber antes de usarlo

- **Los modos no hacen commit ni push.** Integrar es tuyo, siempre. Es la frontera de
  seguridad, no una limitación.
- **La evidencia es el entrypoint de tu proyecto o nada.** El Host resuelve al instalar qué
  comando de test y de análisis usa cada tecnología de tu repo, y ese comando es el único
  resultado registrable. Un mock o un arnés escrito a mano sirven para investigar, no para
  verificar. Si falta una herramienta, el registro es `BLOCKED` nombrando qué falta: nunca
  un `PASS` inventado.
- **Una capacidad fuera del `PATH` por defecto se materializa en el workspace.** Si tu SDK se
  reescribe a sí mismo en cada ejecución, el plan pide una copia local con enlaces duros
  (0 bytes de disco) y apunta ahí.
- **Sin licencia no hay distribución.** G0 es la puerta.

## Límites conocidos

- No hay CAS ni lease multiarchivo: la actualización ordinaria de `mode-state` no es
  atómica ante escritura concurrente.
- La frontera de solo lectura del auditor es contractual y la impone la herramienta de
  escritura, no un sandbox de kernel.
- Multiarchivo monorepos: se detecta una tecnología por subdirectorio; un mismo árbol con
  dos manifiestos de ecosistema distinto no se cubre.
- En este entorno DSH se cae cada varios minutos. Los turnos se relanzan y el trabajo se
  recupera, pero una campaign larga cuesta más tiempo del que el framework asume.

## Qué buscar en la beta

Los tres fallos que solo aparecieron con stacks reales, y que ninguna prueba sintética
habría visto:

1. El plan emitía un comando de verificación que su propia shell no podía ejecutar.
2. El sandbox dejaba el SDK montado en solo lectura y la herramienta se reescribía en cada
   invocación.
3. Un resultado de verificación no identificaba el árbol que verificó, de modo que un `PASS`
   podía describir una revisión anterior al arreglo.

Si tu proyecto usa una tecnología que no aparece en la lista de stacks, el plan lo dirá con
un `falta <capacidad>` en lugar de fingir. Eso también es información útil: dilo.

## Cómo reportar

Tu `mode-state` es el informe. Comparte `findings.jsonl`, `handoffs.jsonl` y
`verification-results.jsonl` —sin código de tu producto— más los turnos que acabaron
`RETAINED` y por qué. Es exactamente el formato que el framework ya produce.