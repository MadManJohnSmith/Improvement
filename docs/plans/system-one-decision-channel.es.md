# Diseño: canal System 1 (modelo de decisión) como propuesta advisory

**English:** [system-one-decision-channel.md](system-one-decision-channel.md) | **Español**


**Estado:** diseño aprobado para implementación por fases. Ninguna fase está
implementada todavía salvo la Fase 0, que ya está en el árbol.

**Qué es y qué no es.** Un *modelo de decisión* (System 1) no es un LLM barato ni
un modo rápido del que ya usamos: es otra arquitectura. No genera texto. Recibe
un `state` (texto o JSON), una lista de opciones permitidas y una rúbrica, y
devuelve una distribución de probabilidad sobre esas opciones. El caso que
motoriza la categoría es **Jev** de TypeSafe AI (anuncio 2026-09-16,
https://typesafe.ai/blog/introducing-system-one-models-and-jev), entrenado con
*RL for Calibrated Decisions*. El patrón arquitectónico de referencia es
Talker-Reasoner (arXiv 2410.08328): el System 1 **propone** y el System 2
**endorsa o veta**.

## La regla que gobierna todo el diseño

> Un System 1 en este framework **amplía cobertura y nunca otorga autoridad**.

Esto no es una preferencia: es la misma regla que ya gobierna `skill_router`
(`authorizes_execution: false` siempre, `scripts/skill_router.py:192`) y el
módulo de razonamiento (el nivel nunca da veredicto ni capacidad). Un modelo de
decisión produce una **propuesta con digest de rúbrica**; el Host la verifica,
registra y puede revocar. Si la propuesta no se puede verificar, se descarta.

## Evidencia que motiva el canal (medida, no del vendor)

| Fuente | Resultado |
|---|---|
| Vals AI (independiente, https://www.vals.ai/blogs/independent-evaluation-of-jev) | Verificación de claims **0.975**, empatando con GPT-6 Astra a **1/498 del coste** ($0.02 vs $12 por 1.000 casos); latencia 194× menor en lotes de 32. **Calibración ECE 0.011**, la mejor de 12 sistemas. |
| arXiv 2610.11978 (13 benchmarks, 19 LLMs) | Gana en conocimiento (MMLU-Redux, ARC-Challenge) pero en **matemática queda 17.7 puntos bajo la mediana** y por debajo de los 19 modelos comparados. |
| Vals AI, LegalBench | **Último de 12** (0.730) y su calibración en esa tarea es **0.108**, la peor del conjunto. |
| Vendor, https://docs.typesafe.ai/model-jaggedness/jev-1.13 | «Si le das un objetivo difícil, comprimirá la ambigüedad en una elección, aunque sea errónea»; «no puede razonar sobre cadenas largas»; contexto 16k; «no debe usarse para decisiones que requieran supervisión humana». |

**La conclusión que decide el diseño:** la calibración medida en una tarea
**no se traslada** a otra (0.011 en claims, 0.108 en legal). El modo de fallo
peligroso no es el error visible sino **el acierto con confianza alta**. Por eso
el canal se diseña para que un fallo del System 1 sea **barato y detectable**,
nunca silencioso.

## Fases

**Fase 0 — desbloqueo del transporte (implementada, commit `4352a55`).**
`DshLocalClient` envuelve `session/selectModel` y `session/projections`
(`scripts/creator_client.py`). Sin esto ni el System 2 aplicaba nivel por paso,
así que un System 1 estaría integrado a un cliente que no puede seleccionar
sesión. El nivel se valida antes del wire y una respuesta cuyo `applied` no
coincide lanza en vez de dejar creer que se aplicó.

**Fase 1 — rúbrica versionada (prerequisito, sin ella no hay canal).**
El resultado depende de la rúbrica, luego la rúbrica es un **insumo versionado
con digest**, no un string en el código. Se valida como cualquier otro artefacto
del framework. Sin digest de rúbrica, una propuesta no es auditable: no se puede
demostrar qué criterio la produjo.

**Fase 2 — el canal advisory (piloto: deduplicación de hallazgos).**
`episodes.signature` (`scripts/episodes.py:51`) identifica un defecto por
`(path, excerpt)` o por fingerprint. La clave exacta deja fuera los duplicados
descritos con otras palabras. El canal añade: dado un hallazgo nuevo y los
existentes, un `choice` sobre «¿mismo defecto?» con umbral de confianza.
Debajo del umbral → **abstención nombrada**, no adivinanza. El digest de
evidencia ya existente fuerza la revisión humana del auditor, así que un
duplicado mal clasificado se ve.

**Fase 3 — hechos candidatos para el router.**
`skill_router` aborta con `ambiguous_observations` cuando dos observaciones del
mismo hecho discrepan (`scripts/skill_router.py:118-121`). El canal puede
proponer hechos desde texto libre; el Host **sigue exigiendo** el
`evidence_sha256` de cada uno. Acota cobertura; no sustituye la validación.

**Fase 4 — clasificación de fallos del ciclo (diagnóstico).**
Caso real de esta sesión: un turno murió con `zlib.error: incorrect data check`
de causa no evidente. Un `choice` sobre «¿error de decodificación, de identidad
o de layout?» acelera el diagnóstico. Solo etiqueta el fallo: no lo corrige ni
lo evalúa.

## Orquestar pruebas y compilaciones: proponer, no ejecutar

Un modelo de decisión System 1 no ejecuta `npm test`, `cargo check`, builds, compiladores ni
otras herramientas: devuelve una opción o probabilidad, no el resultado de un proceso. Su papel
útil sería **ordenar** comprobaciones ya autorizadas, por ejemplo «unit tests rápidos primero,
luego la suite completa obligatoria» o «compilar TypeScript antes de las pruebas de navegador»,
a partir de un estado acotado (`changed_paths`, plan de capacidades/stack, duraciones previas).
El Host proporciona las opciones permitidas, aplica el plan y ejecuta comandos; código de
salida, cobertura, stdout/stderr y digest de candidata siguen siendo la evidencia. Ante baja
confianza o distribución no reconocida se abstiene y se sigue el plan determinista. Nunca puede
omitir un check obligatorio, convertir una compilación fallida en `PASS`, inventar un entrypoint
ni tomar su confianza como prueba de que se ejecutó algo. **No está medido** si esto reduce
latencia/coste medio sin perder detección de defectos: comparar sobre cambios reales y contar
escaladas.

Es una línea de investigación, **no un modo nuevo** ni compromiso de implementación.

## Dónde NO entra, y por qué

Veredictos, aceptación, verificación de diff, reconciliación y adopción de
candidata. Ahí la «ambigüedad comprimida en una elección errónea» es un fallo
silencioso, no un error visible. Son exactamente los puntos donde el framework
falla-cerrado a propósito hoy.

## Patrón de cascada que se traslada literal

Medido por Vals AI: reenviar el 1 % de casos a un modelo frontera cuesta 27
centavos por mil. La traducción es: **umbral declarado como política, reenvío
como ejecución**. El System 1 clasifica; por debajo del umbral escala al modelo
caro o al operador. El umbral es un dato del plan, no una constante escondida.

## Verificación obligatoria antes de afirmar nada

1. Medir precisión y calibración **sobre nuestra distribución**, no benchmarks
   públicos. Si la calibración no se mantiene, la respuesta es no.
2. Ninguna prueba puede afirmar que el modelo decidió: solo que propuso y con
   qué digest de rúbrica.
3. El piloto (Fase 2) se ejecuta con cliente/servidor falso inyectado, como el
   resto del árbol; la corrida real contra Jev es un paso aparte y se documenta
   como no ejercitado hasta que ocurra.

## Ideas que el canal abre (no comprometidas)

- **Reenvío con presupuesto**: cuántos casos se reenvían es una política de
  coste medible, no un juicio.
- **Dos tamaños (`min`/`pro`) por etapa de campaña**, igual que hoy se declara
  esfuerzo por etapa.
- **Detección de bucles**: si el mismo defecto vuelve tras N enfoques, el canal
  ya no clasifica: el ledger lo marca (`MAX_PER_SIGNATURE = 3`,
  `scripts/episodes.py`).

## Anexo de contrato (2026-11-05): qué deben declarar las Fases 1-2 (diseño, sin construir)

Ratificado en la minería del 2026-11-04/05 (70 fichas; ver el espacio externo de
conciliación). Solo detalles de contrato: este anexo no implementa ninguna fase.

- **Gate de tres estados con eco del umbral.** Toda propuesta con gate reporta `passed`,
  `abstained` o `unevaluated` y repite el umbral aplicado. Un booleano no puede expresar
  «el gate corrió y no había número usable».
- **Umbrales por bucket con validación de alcanzabilidad.** El umbral es un mapa por forma
  de pregunta (`tipo:nº_opciones`) con `default`; la validación rechaza claves que ninguna
  respuesta puede producir — un bucket que el llamante cree gateado y no lo está.
- **La procedencia de la probabilidad es obligatoria.** Todo valor de confianza declara su
  origen: `logits` (lectura directa) o `declared` (el modelo reportó un número como
  texto/JSON). Solo `logits` puede calibrar; `declared` jamás autoriza nada. Un transporte
  compatible puede entregar números que parecen probabilidades y no lo son.
- **Sin reparación de JSON ni bucle de decodificación.** La Fase 1 solo admite números
  leídos directamente por opción; un transporte que parsea texto o repara JSON es
  `declared` por definición y no gatea nada.
- **Umbral por elección calibrado sobre trayectorias propias; barra en bucle.** Los
  umbrales se ajustan por elección sobre las trayectorias del propio framework, nunca con
  benchmarks públicos. La barra es éxito en bucle, no precisión en preguntas aisladas: el
  modelo más preciso en aislado resolvió solo el 69,5 % de las tareas de agente, y delegar
  elecciones de herramienta sin calibrar costó -19,0 puntos de éxito (JevAgentHarness). El
  ajuste conservador del corte (+1 pseudo-error; fallback a «abstenerse siempre») es el
  algoritmo por defecto hasta que se mida otra cosa.
- **Pre-registro y coverage-at-error.** La barra de aceptación se compromete antes de
  medir; los informes llevan `coverage-at-error` con política de métrica versionada y la
  advertencia in-sample; los gates retirados permanecen en el ledger con su motivo y sus
  veredictos pasados intactos.
- **Familias de contraste y splits conscientes de grupos.** El authoring añade cinco
  variantes de contraste por escenario (sin evidencia, contrafáctico que invierte el
  veredicto, paráfrasis, distractor), el holdout se agrupa por `group_id` (no por
  escenario), el oráculo se verifica a ciegas con ids de orden opaco, y el corpus declara
  su plan de cobertura con veto de casi-duplicados que cruzan splits.
- **Vocabulario de evidencia.** Un recibo no es un estado post: un éxito reportado nunca es
  una verificación. La evidencia de calibración se reporta como
  PRESENT/MISSING/INSUFFICIENT/UNKNOWN/INCOMPARABLE, con INCOMPARABLE solo ante conflicto de
  digest.
- **Certificados de decisión resuelta (nota de diseño para el ejecutor, sin construir).**
  Reutilizar una decisión con argumentos cerrados exige guardas sobre recibos observados y
  emite un certificado que liga el hash del plan/journal, el id de paso, el recibo del
  predecesor, los argumentos exactos, el recibo de la herramienta y el id del despacho
  omitido. El certificado prueba ejecución y ausencia de la llamada, nunca corrección ni
  coste contrafactual; los negativos de la fuente (AIME +28 % de coste, 5/10 regresiones)
  son parte de la evidencia.

La regla gobernante no cambia: el canal propone; el Host verifica y puede revocar.
