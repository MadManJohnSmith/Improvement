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
| G0 | Licencia | Elegir y añadir `LICENSE` (recomendación: MIT o Apache-2.0; decisión del titular) y reflejarla en el README. Sin esto el repo no debe anunciarse como instalable. | PENDIENTE |
| G1 | Contrato de candidata | El `recording_command` emite el objeto JSON exacto a persistir; la persona prohíbe añadir campos; el preflight informa de lo que descarta (no solo lo archiva). Regresión con el caso RehabWeb (campos extra + ruta absoluta). | HECHO 2026-09-29 |
| G2 | decisions + metrics al ciclo | Llamar al ledger de métricas y al almacén de decisiones al cierre de turno en `host_controller.py` (el hook ya existe: transiciones y UNIT_DONE/UNIT_RETAINED). Regresión con la regresión existente de ambos módulos. | HECHO 2026-09-29 |
| G3 | Compactación con recibo | El desbordamiento de runtime deja recibo (patrón del archivo legacy, `dropped_records` incluido) en lugar de perder registros sin traza. Caso Syncify: 50/50 handoffs. | HECHO 2026-09-29 |
| G4 | E2E desde clon de GitHub | Repetir la instalación limpia clonando desde `https://github.com/MadManJohnSmith/Improvement.git` (no local) sobre un repo demo, verificando roster, skills y un ciclo auditor→reparador. | PENDIENTE |
| G5 | Documentación pública | README (hecho), quickstart no técnico en `docs/usage.md`, política de feedback: qué comparte un tester (su `mode-state` es la evidencia). | EN CURSO |
| G6 | Etiqueta y notas | Tag `v0.1.0-beta`, release notes con las métricas reales del piloto y los límites conocidos. | PENDIENTE |

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

## Línea base medible del piloto (para comparar durante la beta)

| Métrica | Syncify | RehabWeb |
|---|---|---|
| Comandos de instalación | 1 | 1 |
| Hallazgos distintos persistidos | 77 (114 registros) | 45 |
| Severidad máxima | HIGH | 6 CRITICAL |
| Trabajo verificado | 78 items VERIFIED | 2 CRITICAL reparados |
| Verificaciones persistidas | 67 (61 PASS / 6 BLOCKED) | 4 |
| Commits de los modos integrados | 15 | 1 |
| Resultado | CI verde en 3 jobs | 220 líneas de arreglo en 3 ficheros |

Métrica del propio framework: 556 pruebas en verde; 7 unidades de endurecimiento nacidas
de los pilotos; una pérdida silenciosa del preflight detectada y corregida con regresión.
