# 10 · Lanzamiento público beta

Estado: **EN CURSO**. Meta: que cualquier persona con un repo y DSH configurado instale
Improvement con un comando, opere sus dos modos con prompts simples y reporte resultados.
Este plan sucede a los planes C0–C7 y a la campaña de endurecimiento sobre pilotos reales
(Syncify y RehabWeb, ambas cerradas y documentadas en `CHANGELOG.md`).

## Dónde estamos

- **Probado:** instalación de principio a fin sin intervención del operador sobre un
  entorno limpio (clon nuevo + home DSH nuevo con solo credenciales, roster inicial de
  los cuatro presets de fábrica), con `Creator: GENERATED` y `Host: ACTIVE`; auditoría
  con un prompt simple que persistió hallazgos con evidencia; reparación con un prompt
  de seis palabras que arregló dos CRITICAL de seguridad en candidata hermana.
- **Sólido:** núcleo fail-closed validado por dos pilotos (producto intacto hasta que el
  operador integra), startup con sentinel, anti-escalada mecánica, reserva de candidata
  antes de editar, reconciliación sin operador, retirada de candidatas documentada.
- **Deuda declarada:** registro de candidata no conforme escrito por un modo generado;
  compactación de runtime sin recibo; `decisions.py` y `metrics.py` huérfanos; sin
  CAS/lease multiarchivo. El informe completo del mantenedor vive fuera del árbol
  canónico (`.zcode/workflow-drafts/informe-improvement-memoria.md`).

## Puertas de lanzamiento

| # | Puerta | Contenido | Estado |
|---|---|---|---|
| G0 | Licencia | Elegir y añadir `LICENSE` (recomendación: MIT o Apache-2.0; decisión del titular) y reflejarla en el README. Sin esto el repo no debe anunciarse como instalable. | HECHO 2026-09-30 (Apache-2.0) |
| G1 | Contrato de candidata | El `recording_command` emite el objeto JSON exacto a persistir; la persona prohíbe añadir campos; el preflight informa de lo que descarta (no solo lo archiva). Regresión con el caso RehabWeb (campos extra + ruta absoluta). | HECHO 2026-09-29 |
| G2 | decisions + metrics al ciclo | Llamar al ledger de métricas y al almacén de decisiones al cierre de turno en `host_controller.py` (el hook ya existe: transiciones y UNIT_DONE/UNIT_RETAINED). Regresión con la regresión existente de ambos módulos. | HECHO 2026-09-29 |
| G3 | Compactación con recibo | El desbordamiento de runtime deja recibo (patrón del archivo legacy, `dropped_records` incluido) en lugar de perder registros sin traza. Caso Syncify: 50/50 handoffs. | HECHO 2026-09-29 |
| G4 | E2E desde clon de GitHub | Repetir la instalación limpia clonando desde `https://github.com/MadManJohnSmith/Improvement.git` (no local) sobre un repo demo, verificando roster, skills y un ciclo auditor→reparador. | HECHO 2026-09-29 |
| G5 | Documentación pública | README (hecho), quickstart no técnico en `docs/usage.md`, política de feedback: qué comparte un tester (su `mode-state` es la evidencia). | HECHO 2026-09-30 |
| G6 | Etiqueta y notas | Tag `v0.1.0-beta`, release notes con las métricas reales del piloto y los límites conocidos. | HECHO 2026-09-30 (publicada con autorización del titular) |
| G7 | Verificación contra el stack real | El Host resuelve un plan de capacidades al instalar (`scripts/stack.py`): entrypoint propio del producto por stack (cualquier tecnología, monorepos incluidos), estado real de cada capacidad y paso exacto de provisión fuera del producto. La evidencia de verificación es ese entrypoint o `BLOCKED` nombrando lo que falta; los stubs son material de investigación, nunca resultado. Regresión con el caso rehab (Django ausente) y con los stacks reales de Syncify, RehabWeb y LoboApp. | HECHO 2026-09-29 |

## Criterios de la beta

- Un tester necesita: Linux, `git`, DSH instalado con un proveedor configurado por él,
  y su propio repositorio. El framework no obtiene credenciales.
- Éxito mínimo de un tester: `install` termina `ACTIVE`, el auditor persiste hallazgos
  con evidencia, un prompt de reparación produce una candidata con verificación, y el
  operador integra con commit.
- Feedback: el `mode-state` del tester ES el informe. Se pide compartir
  `findings.jsonl`, `handoffs.jsonl` y `verification-results.jsonl` (sin código del
  producto), más los turnos que acabaron en `RETAINED` y por qué.

## Riesgos declarados

- DSH y el proveedor son prerrequisito del usuario; el framework no instala ni configura
  proveedores, y sin sesión autenticada el run queda recuperable, no activo.
- La actualización multiarchivo de `mode-state` no tiene CAS/lease: no se afirma
  aislamiento ni atomicidad concurrente.
- Los modos nunca hacen commit/push: el operador integra. Publicar esto como
  característica (no como falta) es parte del mensaje público.
- Dependencias de terceros ya atribuidas en `THIRD_PARTY_NOTICES.md`; cualquier skill
  nueva que entre a `library/` exige su entrada de procedencia.
- Proyectos móviles sin toolchain (caso LoboApp: Flutter sin SDK en la máquina): la
  verificación del candidato queda `BLOCKED` por falta de capacidad, nunca PASS inventado.
  Con el SDK materializado fuera del producto la misma verificación corre de verdad, y el
  plan nombra el entrypoint por su ruta absoluta cuando el PATH por defecto no lo resuelve:
  un nombre suelto que la shell del modo no puede invocar convertiría una suite real en un
  `BLOCKED` que el runtime no se ha ganado (`scripts/stack.py::_runnable_entrypoint`).
  Adaptador candidato para evidencia en dispositivo Android: `google/artemis` (Apache-2.0,
  automatización de UI con capturas/logcat y servidor MCP). No se adopta como dependencia —
  añade ADB/emulador/FFmpeg al entorno del usuario, solo cubre objetivos Android y no emite
  diagnósticos de análisis estático; si un tester de proyecto móvil lo integra, exige entrada
  de procedencia y queda como verificador externo, nunca como fuente de autoridad.

## Línea base medible del piloto (para comparar durante la beta)

| Métrica | Syncify | RehabWeb | LoboApp |
|---|---|---|---|
| Comandos de instalación | 1 | 1 | 1 |
| Hallazgos distintos persistidos | 77 (114 registros) | 45 | 9 + 5 en la reauditoría |
| Severidad máxima | HIGH | 6 CRITICAL | 1 CRITICAL |
| Trabajo verificado | 78 items VERIFIED | 2 CRITICAL reparados | 14 items VERIFIED |
| Verificaciones persistidas | 67 (61 PASS / 6 BLOCKED) | 4 | 14 PASS (flutter test) |
| Commits de los modos integrados | 15 | 1 | 4 |
| Resultado | CI verde en 3 jobs | 220 líneas de arreglo en 3 ficheros | 14 hallazgos cerrados; 166 pruebas Flutter y `flutter analyze` sin incidencias |

LoboApp se instaló de cero desde el clon de GitHub del framework sobre un producto Flutter
recién clonado, y es la campaña que cerró G7: la verificación se ejecutó con
`flutter test` real desde la copia local del workspace, no con un arnés. Se llega al final:
los 9 hallazgos de la primera auditoría se repararon e integraron en cuatro turnos, la
reauditoría los confirmó como `RESOLVED` con evidencia y encontró 5 más —uno de ellos creado
por el arreglo anterior, que dejó sin poder restaurar un respaldo heredado— y todos se
cerraron. Total `bb01cba..4c0bb30`.

Su coste en tiempo fue alto: DSH se cae cada varios minutos en este entorno y cada turno se
relanza hasta que termina, con un Creator que hubo que reanudar tres veces. El marco aguantó
todo: producto intacto hasta la integración, candidatas registradas y reconciliadas, base
declarada re-anclada al HEAD con la ascendencia comprobada mecánicamente, y el operador
integrando solo con commit, fast-forward y push.

Métrica del propio framework: 632 pruebas en verde; las unidades de endurecimiento nacen
de los pilotos; una pérdida silenciosa del preflight detectada y corregida con regresión.

## El framework sobre sí mismo (self-test)

El framework instalado de cero sobre un clon de sí mismo, con su entrypoint declarado
(`python3 -B -m unittest discover -s tests`), no solo se auditó: se corrigió. El auditor
persistió 7 hallazgos (2 HIGH, 5 MEDIUM) y el reparador atendió los dos primeros con un
prompt de seis palabras, verificando con la suite real del proyecto (606 pruebas en el
momento de aquella campaña; 632 al publicar la beta):

- **IMP-AUD-001 (HIGH):** la compactación por límite descartaba registros sin recibo. G3
  cubría el descarte por incompatibilidad de esquema, pero lo que excedía el tope se perdía
  en silencio. Ahora el descarte por límite deja recibo y copia archivada.
- **IMP-AUD-002 (HIGH):** la herramienta de escritura solo acotaba
  `verification-results.jsonl`; el resto del estado gestionado quedaba libre. Una sesión
  gestionada declara su raíz `<workspace>/mode-state` y todo destino fuera de ella se
  deniega antes del write-intent.

Ambos están integrados con regresión (`99a9f0e`). El producto —el clon del framework—
quedó intacto hasta la integración, con commit y fast-forward del operador.

G0 quedó cerrada el 2026-09-30: Apache-2.0 elegida por el titular, `LICENSE` en la raíz y
referencia en el README. Queda solo G6 —el tag `v0.1.0-beta` y la publicación—, que requiere
autorización de destino.
