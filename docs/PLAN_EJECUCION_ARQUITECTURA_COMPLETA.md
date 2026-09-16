# Plan de ejecución de la arquitectura completa para otro agente

**Estado:** antecedente histórico ejecutado para el MVP v2.4; no es el backlog vigente de arquitectura 3.0. Consultar C0–C7 en `PLAN_IMPLEMENTACION.md`.
**Fecha de referencia:** 2026-09-13.
**Destinatario:** agente de mantenimiento encargado de ejecutar una misión posterior autorizada.
**Jerarquía:** subordinado a [arquitectura vigente](../ARQUITECTURA_FLUJO_AGENTES.md), [plan por etapas](../PLAN_IMPLEMENTACION.md), [estado comprobado](status.md) y [reglas del repositorio](../AGENTS.md).
**Nota sobre la redacción:** crear este plan no ejecutó su implementación. Esta nota no limita al agente que reciba el encargo de ejecutarlo: ese agente debe realizar las fases siguientes hasta su aceptación, dentro de la autoridad acordada.

## 1. Mandato de la futura ejecución y significado de completar

- Terminar el núcleo de TODA la arquitectura vigente, no otra demostración parcial de sus primitives.
- Implementar y verificar distribución, incorporación, dos modos DSH, Host, auditoría, reparación, QA, reauditoría, integración en copia, archivo y recuperación.
- Mantener `PLAN_IMPLEMENTACION.md` como único índice de progreso; este documento organiza trabajo y gates, no abre otro backlog.
- Reutilizar código, servicios DSH y contratos existentes; inspeccionarlos antes de decidir qué falta o dónde cambiarlo.
- Actualizar la arquitectura en su archivo vigente cuando una decisión autorizada cambie diseño; no convertir este plan en arquitectura competidora.
- No terminar voluntariamente la ejecución tras un hito cómodo mientras quede trabajo necesario, ejecutable y autorizado.
- Continuar internamente sin pedir al usuario el siguiente prompt ni aprobación para cada subpaso ya cubierto por la misión.
- La obligación de completar no permite ignorar límites del entorno, permisos, presupuesto, seguridad o duración de una sesión.
- Ante bloqueo real, preservar checkpoint, agotar trabajo independiente autorizado y entregar excepción concreta, sin declarar completitud.
- Un checkpoint para otro turno no es cierre de arquitectura; un gate necesario sin evidencia mantiene `PARCIAL`, `BLOQUEADO` o `RETENIDO`.
- Cerrar el núcleo no depende de adoptar productos terceros opcionales rechazados ni de demostrar prestaciones fuera de su alcance autorizado.
- Separar aceptación del framework, aceptación de cada candidato de producto y autorización de publicación: ninguna implica las otras.

## 2. Fuentes, línea base y hechos que no deben sobregeneralizarse

1. Leer `AGENTS.md`, arquitectura completa §§1–17 y `PLAN_IMPLEMENTACION.md` antes de intervenir.
2. Leer la síntesis de `docs/status.md` junto con sus últimos hitos, conservando el corte temporal de cada cifra.
3. Leer la [evaluación de incorporación F1–F5/D1–D5](EVALUACION_ORQUESTACION_EXTERNA.md). Consultar también `docs/external-orchestration-draft.md` si está disponible como antecedente; no es dependencia de instalación ni requisito para ejecutar este plan, que incluye las decisiones pertinentes. Las afirmaciones sobre terceros no fueron verificadas para este plan.
4. La propuesta externa titulada `DISENO_RSI_ACOTADO.md` fue leída para planificar; no copiar su historial privado ni convertirla en dependencia distribuible.
5. En ejecución, solicitar su acceso solo si hace falta detalle no contenido aquí y existe fuente autorizada; no inventar rutas o acceso entre sistemas.
6. Consultar `docs/usage.md`, `docs/setup-dsh.md`, `docs/audit-contract.md` y los contratos del código antes de diseñar cambios.
7. Las ocho skills, carga nativa, launcher, broker, recibos y ledger tienen evidencia acotada; no son piezas totalmente ausentes.
8. Todas las etapas globales siguen `PARCIAL`; un fixture del controlador no acredita el controlador Host de producción.
9. Los 48 tests de la síntesis son una selección con exclusiones explícitas, no prueba actual de discovery íntegro.
10. Syncify conserva cierres agrupados e incertidumbre semántica; número de fingerprints no equivale a reparaciones verificadas.
11. RehabWeb tiene un hito F6 posterior a la síntesis de seis reparaciones: reconciliar siete únicas y 43 ready declarados contra evidencia vigente.
12. No sumar cortes temporales, deducir reparaciones por resta ni interpretar asignación de 381 archivos como revisión efectiva de todos.
13. Reauditorías mecánicas `PENDING_SEMANTIC_REVIEW` requieren Auditor posterior real; QA previa no las sustituye.
14. El último hito registra runtime rc.2 y bash ordinario sin `sandbox_permissions` válido en hijo nativo: no reparar un esquema supuesto obligatorio; distinguir fallo conductual de restricción real. Presets visibles, sesiones vacías y carga sin modelos no acreditan conducta integral.
15. Los IDs DSH y ZCode no son intercambiables; usar fuentes disponibles y autorizadas, nunca supuesta recuperación entre plataformas.

## 3. Responsables, autoridad y organización del trabajo

| Responsable | Control o responsabilidad indelegable |
|---|---|
| Usuario/titular | Objetivo, alcance material, recursos, datos compartibles, presupuesto, integración y publicación cuando correspondan. |
| Mantenedor | Diseño vigente, cambios del flujo, revisión de distribución, staging selectivo y commits locales autorizados. |
| Host confiable | Identidad observada, capabilities, cuotas, locks, transiciones, cancelación, persistencia y reconciliación. |
| Coordinador DSH | Cola autorizada, encargos suficientes, dependencias, delegación, continuidad y excepciones compactas. |
| Ejecutor | Un candidato por unidad, escritor exclusivo, cambios dentro del alcance, autopruebas y evidencia íntegra. |
| QA independiente | Inspección del candidato real, criterios, regresiones, efectos relacionados y veredicto con límites explícitos. |
| Auditor | Cobertura, perspectivas, consolidación, prevención y reauditoría semántica posterior a QA. |
| Usuario-HUMANO evaluador | Observación perceptiva necesaria cuando las herramientas no pueden acreditar el criterio. |

- Standard es entorno de construcción; usuario final entra por Auditor o Reparación continua, sin tercer modo obligatorio.
- La incorporación es compartida; Ejecutor y QA son funciones internas, no sesiones que deba abrir rutinariamente el usuario.
- Autorizar una misión completa y finita; no exigir que el usuario elija N prompts, N agentes o cada paso técnico.
- Registrar duración, intentos, requests y límites de gasto aplicables antes del trabajo; acordar valores, no inferirlos del plan.
- Mantener el límite vigente de dos intentos de corrección por unidad salvo cambio material expresamente autorizado.
- No convertir autorización de mantenimiento en gasto nuevo, credenciales nuevas, escritura de producto real o publicación remota.
- Las aprobaciones nativas obligatorias siguen vigentes: agrupar permisos compatibles sin pedir acceso total para sortear granularidad insuficiente.
- Una declaración `AUTHORIZED` no autentica al usuario; Host debe enlazar mandato y permiso efectivo observado.

## 4. Evaluación de incorporación del borrador externo

### F1 — requisitos durables, con EARS opcional

- Incorporar trazabilidad de criterios al mandato; usar `requirements.md` solo cuando reduzca ambigüedad o facilite revisión.
- EARS es una forma opcional de redactar requisitos por criterio; no verifica semántica, suficiencia ni corrección del producto.
- Defaults: specs en workspace externo; `task.json` mantiene el contrato canónico ejecutable de unidad.
- La cola existente conserva selección/dependencias; `tasks.md`, si aporta valor, será una vista derivada, nunca segundo backlog editable.
- `design.md` solo si hay decisión técnica que conservar; enlazar versiones de requisitos y decisiones desde la tarea.
- Versionar specs de producto dentro de su Git requiere autorización específica; no introducirlas allí por conveniencia del agente.
- Gate de adopción: QA y Auditor resuelven el mismo criterio/versionado; cambios materiales invalidan aceptación previa.

### F2 — composición real Coding → QA → Auditor

- Es necesario cerrar la composición Host real, no asumir «nada estructural» porque existan funciones locales.
- Reutilizar `missions.py`, `publisher.py`, `budget.py` y servicios DSH; añadir únicamente enlaces y controles faltantes.
- La regresión sintética es gate mecánico inicial, nunca salida final del loop.
- Exigir sesiones/identidades observadas, candidato exacto, QA real, reauditoría semántica y continuación sin transporte humano de recibos.
- La separación de sesión con igual modelo no demuestra independencia estadística; tampoco cambiar etiquetas o proveedor.

### F3 — eventos locales antes de cualquier publicación remota

- Default: evento local de commit/delta autorizado → auditoría incremental → recibo local y notificación compacta.
- Definir identidad de evento, base/destino, alcance, autorización, deduplicación, orden, supersesión y cancelación.
- Exigir idempotencia al repetir entrega; un evento no autoriza reparar, integrar ni publicar por sí mismo.
- Publicación remota queda deshabilitada salvo destino y autoridad explícitos; no abrir un publicador paralelo ad hoc.
- PRs, CI o push remoto son adaptaciones opcionales; su falta no bloquea núcleo local, pero tampoco se declaran probados.
- Incorporar este disparador nuevo solo tras decisión arquitectónica explícita; el handoff local del núcleo sí es obligatorio.

### F4 — no dependencia obligatoria de Vibe Kanban ni Codex

- No adoptar Vibe Kanban, Codex ni otra plataforma como requisito de distribución o como sustituto de DSH.
- Puede evaluarse posteriormente una superficie visual si hay necesidad medible y autorización; no está en el camino crítico.
- Un worktree separa candidatos Git, no procesos, red, credenciales, cachés ni escrituras fuera del árbol: no es sandbox.
- Paralelismo del núcleo usa capacidades DSH/Host, recursos independientes y un escritor por entorno con enforcement real.
- La herramienta opcional no puede poseer autoridad adicional de merge, presupuesto o publicación.
- No comprobar ni repetir aquí afirmaciones comerciales o compatibilidad de terceros; no se realizó investigación web.

### F5 — índice gradual y memoria privada

- Separar decisiones normativas, localización de código y recuerdos episódicos; no dar autoridad a un resultado de búsqueda.
- Primero mapa local pequeño y símbolos con hashes; lectura pull y fuentes vigentes, sin cargar el repo map completo por defecto si excede presupuesto.
- Reindexar altas, bajas, renombres y cambios; rechazar resultados de proyecto/base distintos o con hashes obsoletos.
- Solo medir después si embeddings locales aportan calidad/coste frente a búsqueda convencional comparable.
- No instalar tree-sitter, motores vectoriales, modelos o bases nuevas sin necesidad medida y autorización de dependencias.
- Memoria episódica externa privada con TTL, cuotas y borrado; no archivar automáticamente en Git lo que salga de memoria caliente.
- Decisiones con vigencia contractual conservan su historial y reemplazos; no caducarlas por el TTL de recuerdos auxiliares.
- Índices locales evitan alojar ese índice en una nube; no garantizan privacidad completa si se usa inferencia remota.
- Los fragmentos enviados al proveedor se rigen por permiso de datos y política del proveedor; sin permiso, no enviarlos.
- Completar memoria de decisiones del núcleo; índice auxiliar y embeddings quedan condicionados a adopción, no bloquean por sí solos.

## 5. Contratos de implementación y evidencia compartidos

Los siguientes nombres de artefacto nuevos son propuestas de contrato, no APIs ni schemas ya existentes.
Reutilizar campos/esquemas actuales primero; versionar migraciones compatibles y sus negativos antes de emitir nuevos estados.
Todos los artefactos de misión viven fuera del repositorio distribuible; solo código y regresiones permanentes se versionan aquí.

| Contrato | Contenido mínimo y validador/control responsable |
|---|---|
| Perfil/incorporación | Identidad de proyecto, raíces lógicas, origen, base, exclusiones, comandos y datos; inicializador + permiso Host. |
| `task.json` | ID/revisión, proyecto, base, objetivo, criterios, scope, dependencias, límites y referencias; `missions` + Host. |
| Specs/decisiones | IDs estables, versión, motivo, alternativas, criterios/unidades afectadas y reemplazo; revisión semántica + resolución. |
| Inventario/cobertura | Archivos/hash, exclusiones y autorización, unidades, perspectivas y gaps; `audit` + Auditor. |
| Candidato/result/check | Snapshot íntegro, diff, altas/bajas, argv, entorno, salida/timeout/hash y resultado; runner confiable + `verify`. |
| QA/reauditoría | Actor/sesión observados, candidato/hash, criterios, método, evidencia, veredicto y pendientes; Host + evaluadores. |
| Verificación humana | ID, criterio, candidato/hash, entorno, procedimiento, evaluador, observación y estado; Host + humano real. |
| Entrega/eventos | ID opaco emitido, owner autenticado, capability, ciclo, base, payload limitado y secuencia; publicador Host. |
| Presupuesto | Límites inmutables, reserva previa, consumo observado, fuente/unidad e incertidumbre; ledger + broker Host. |
| Checkpoint/archivo | Intenciones, ack, ejecución activa, lock/fencing, siguiente acción, límites, referencias y manifiesto; reconciliador. |
| Sesión/versiones | Flujo/runtime/skills/configuración no secreta y hashes fijados por sesión; adaptador + distribución. |

- No atribuir a hashes autenticidad frente a quien controla todo el almacén; mantener ancla/identidad en plano Host confiable.
- `missions.verify` no cubre automáticamente archivos no enumerados: snapshot/diff íntegro debe detectar altas, bajas y cambios ocultos.
- Validar esquema y semántica mecánica en handler, no solo DSL; desconocidos/malformados fallan cerrados sin mutación parcial.
- Estado `COMPLETE` de entrega no significa QA, integración o completitud arquitectónica; cada aceptación conserva alcance propio.
- Cada fase conserva entrada/versiones, responsable, positivos, negativos, resultado, evidencia externa y limitaciones.
- Corregir los fallos del framework en mantenimiento separado de la misión operativa; prohibidos patches runtime ocultos para lograr verde.

## 6. Secuencia de fases y gates de salida

### P0 — reconciliar mandato, inventario de pendientes y baseline

- Responsable/control: mantenedor y usuario para decisiones materiales; Host comprueba permisos efectivos.
- Acciones: leer fuentes, inspeccionar código/tests, registrar trabajo ajeno y mapear cada pendiente a etapas 0–8 y §§1–17.
- Artefactos/schema: mandato versionado, manifiesto externo de baseline y matriz de gates con criterio necesario u opcional.
- Positivos: fuentes/versiones resolubles; autoridad cubre la misión normal y los ensayos en copias; presupuesto finito acordado.
- Negativos: estado declarativo como permiso, raíz ajena, presupuesto ausente, evidencia inaccesible presentada como verificada.
- Salida: alcance, fases, límites y criterios suficientes; bloqueos de autoridad concretos separados del trabajo ejecutable.

### P1 — descarga, preparación limpia y bootstrap del usuario

- Responsable/control: adaptador de distribución y mantenedor; adquisición solo desde origen/destino autorizado.
- Acciones: preparar padre externo nuevo, obtener código y runtime con versiones fijadas y registrar procedencia/hash.
- Si no hay autorización o acceso remoto, usar bundle local equivalente identificado; marcar `distribución remota no probada`.
- Si descarga remota es criterio necesario de la misión, el bundle no lo satisface y la aceptación global queda pendiente.
- Instalar/adquirir runtime y dependencias en fase host-side autorizada, separada de ejecutar código no confiable.
- Artefactos/schema: manifiesto de distribución, dependencias/lockfiles, bootstrap, perfil y manifiesto de enlaces propios.
- Positivos: incorporación desde cero, repetición idempotente, actualización respaldada, retirada solo de enlaces propios.
- Negativos: versiones incompatibles, conflictos, symlinks ajenos, árbol interno, ancestro Git inadecuado y sobrescritura silenciosa.
- Salida: dos proyectos incorporables con la misma distribución y sin configuración manual de producto fuera de pasos DSH autorizados.

### P2 — controles Host y composición nativa efectiva

- Responsable/control: Host/adaptador; skills orientan conducta pero no aplican aislamiento ni autenticación.
- Acciones: componer ambos modos con servicios reales, identidad/capabilities por misión y rutas de modelo autorizadas.
- Conectar un escritor durable, launcher, broker y ledger sin modificar routing global ni runtime instalado por detrás.
- Verificar herencia granular de capacidades y rechazo de rutas/modelos no autorizados; no conceder acceso total como arreglo.
- Artefactos/schema: registro de capacidades, composición versionada, sesiones observadas y política efectiva no secreta.
- Positivos: carga del cuerpo exacto de skills y aplicación conductual en turnos reales, delegación/QA nativas y herramientas útiles.
- Negativos: fixture que imita carga, habilidad ausente, caché cruzada, identidad falsificada, permiso revocado y escaladas repetidas.
- Salida: DSH real coordina el caso normal bajo controles probados; catálogo, preset visible o arranque sin modelos no bastan.

### P3 — auditoría completa, requisitos y cobertura semántica

- Responsable/control: Auditor real y `audit`; Host controla raíces, lectores y publicación, no decide semántica.
- Acciones: inventario determinista y barrido inicial propio antes de reconciliar informes previos; excluir solo con autoridad.
- Particionar, delegar unidades, aplicar dos perspectivas y contrastar productor/consumidor, incertidumbres y hallazgos relacionados.
- Artefactos/schema: snapshot, `coverage-matrix.json`, criterios/specs opcionales, entregas, cola existente y decisiones pertinentes.
- Positivos: informe completo recuperable, evidencia por perspectiva, prevención propuesta por hallazgo y cola deduplicada.
- Negativos: archivo omitido/ilegible, asignado sin revisar, mock/stub, prueba tautológica, base cambiada y exclusión para ocultar gap.
- Salida: cada criterio necesario tiene revisión suficiente; `PARTITION_VERIFIED` por sí solo nunca permite cierre semántico.

### P4 — reparación normal completa y QA independiente

- Responsable/control: coordinador y Ejecutor; Host autoriza lote y exclusión; QA independiente acepta el candidato real.
- Acciones: consumir cola autorizada sin prompts intermedios, crear candidatos externos y reproducir defecto en base separada.
- Probar rojo → cambio acotado → verde cuando aplique; si no existe reproducción automática pertinente, declarar evidencia alternativa necesaria.
- Artefactos/schema: task/result/check, snapshot completo, diff, QA original resoluble y referencias de criterios/decisiones.
- Positivos: QA inspecciona/ejecuta candidato, detecta un defecto real, corrige dentro del límite y revisa efectos relacionados.
- Negativos: mismo autor renombrado, QA de otro hash/proyecto, stdout alterado, scope incompleto, altas/bajas ocultas y prueba requerida omitida.
- Salida: cadena real aceptada o unidad honestamente retenida; consumir todo el lote no equivale a resolver todos sus criterios.

### P5 — circularidad cerrada, entrega y eventos consistentes

- Responsable/control: Host/publicador para transiciones; Auditor para reauditoría semántica, coordinador para siguiente unidad.
- Acciones: después de QA, volver a Auditor incremental, verificar prevención y reabrir defecto persistente sin duplicar causa.
- Continuar hasta cola autorizada resuelta o excepción; usar `cycle_id`, dependencias, base y límites persistentes.
- Artefactos/schema: lotes completos, estados por rol, secuencia de eventos, cola canónica y manifiesto de cierre de ciclo.
- Positivos: Auditor → Reparación autorizada → QA → Auditor → siguiente unidad/cierre sin usuario transportando recibos.
- Negativos: entrega PARTIAL consumida, replay conflictivo, evento duplicado/fuera de orden, presupuesto reiniciado y bucle sin progreso.
- Verificar consistencia entre eventos, backlog y commits de candidatos/integración en copias; commits sin Git usan revisión equivalente.
- Si se adopta F3, añadir commit local repetido, supersesión y cancelación; ningún evento concede autoridad remota.
- Salida: cierre semántico circular y estado reconstruible; cada commit y unidad conservan referencia a base/evidencia vigentes.

### P6 — integración conjunta en copia, archivo y restauración normal

- Responsable/control: integrador Host con autorización limitada a copia; QA valida conjunto, no suma aprobaciones aisladas.
- Acciones: integrar candidatos compatibles en copia externa limpia; resolver conflictos dentro del mandato o retenerlos.
- Reejecutar criterios afectados sobre el conjunto, detectar interacción entre cambios y reauditar el estado integrado.
- Artefactos/schema: manifiesto de integración, base/diff/hash final, autorizaciones, recibos y archivo externo indexado.
- Positivos: integración única, fuente original intacta, cierre compacto y restauración en proceso/sesión nueva sin historial completo.
- Negativos: base adelantada, conflicto, doble aplicación, archivo incompleto/corrupto y referencias rotas o de otro proyecto.
- Salida: conjunto aceptado en copia y archivo recuperable; esto no autoriza ni acredita integración en producto real o publicación.

### P7 — repetir el flujo real en Syncify y RehabWeb

- Responsable/control: coordinador y QA por proyecto; mantenedor compara misma versión de framework, no ramas de ensayo divergentes.
- Acciones: ejecutar P1–P6 de principio a fin por proyecto en copias externas, sin modificar fuentes ni reutilizar aceptaciones ciegamente.
- Syncify: seleccionar recorridos reales de UI/estado/API/persistencia según descubrimiento; cubrir IPC/build nativos cuando el criterio lo requiera.
- RehabWeb: seleccionar recorridos reales UI/servicio/autorización/persistencia según descubrimiento; no sustituirlos por tests estáticos de configuración.
- En ambos, auditar todo el inventario autorizado y consumir toda la cola reparable autorizada, no solo unidades fáciles ni todos los bugs imaginables.
- Mínimo por proyecto: dos vueltas reales reparación → QA → reauditoría con continuación interna; incluir al menos un rechazo QA por defecto concreto en el conjunto y su corrección/revisión. Si se siembra para control, declararlo; no suplanta el alcance real.
- Ninguna unidad necesaria queda sin evidencia al declarar aceptación integral; una excepción opcional no rebaja gates del núcleo. La caída/recuperación Host se ensaya separadamente en P8.
- Artefactos/schema: perfiles separados, escenarios funcionales, manifiestos antes/después y matriz requisito → evidencia por proyecto.
- Positivos: instalación/entrada simple, auditoría, reparación, QA, reauditoría, integración conjunta y recuperación normal reales en ambos.
- Negativos: intercambio de perfil/identidad/recibo/hash, contexto de skill cruzado, infraestructura ausente y resultados heredados obsoletos.
- Fallos sembrados sirven como escenarios controlados adicionales, rotulados como tales; no presentarlos como defectos originales descubiertos.
- Salida: dos ciclos integrales comparables; requisito funcional necesario sin entorno, hardware o QA adecuado mantiene el gate abierto.

### P8 — timeout, cancelación, caída y recuperación adversa

- Responsable/control: Host y reconciliador; evaluador independiente comprueba procesos, unicidad y estado preservado.
- Precondición: operación normal real P7 demostrada; no usar fallo complejo para eludir la primera misión normal completa.
- Acciones: cortar durante ejecución/QA, antes de publicar y después de publicar antes de ack; repetir con Host real, no solo fixture.
- Artefactos/schema: checkpoint con intent/ack, claves idempotentes, propietario/lease/fencing, ejecuciones inciertas y presupuesto acumulado.
- Positivos: reconciliar antes de relanzar, recuperar candidato/evidencia, no duplicar escritor, integración, entrega ni consumo aceptado.
- Negativos: ack perdido, lock obsoleto, publicación conflictiva, ledger alterado, agotamiento, worker huérfano y cancelación tardía.
- Verificar descendientes locales terminados; remotos solo se declaran controlados si existe protocolo real de consulta/cancelación/confirmación.
- Sin confirmación remota, marcar ejecución incierta y retener recursos incompatibles; no asumir que morir el Host canceló el remoto.
- Distinguir atomicidad visible, crash y pérdida de energía; demostrar esta última o mantener su gate de durabilidad explícitamente abierto.
- Salida: recuperación dentro del alcance contractual probada; límites remotos/hostiles no ensayados se publican como límites, no garantías.

### P9 — UX, métricas, distribución y cierre de mantenimiento

- Responsable/control: usuario-HUMANO para percepción; QA de distribución y mantenedor para evidencia/publicabilidad.
- Acciones: repetir bootstrap y uso desde entorno limpio con mensajes cortos; contar interacciones reales, comandos y decisiones excepcionales.
- Artefactos/schema: registro UX externo, métricas con fuente, matriz final de gates y manifiesto de distribución exacta.
- Positivos: el usuario elige modo/objetivo/límites; DSH resuelve lo técnico y devuelve cierre o excepción breve sin nuevos prompts rutinarios.
- Negativos: pedir JSON/receipts, transportar IDs, diagnosticar raíces, ocultar comandos de preparación y considerar datos no observables como cero.
- Ejecutar suites pertinentes completas con salidas externas; identificar omisiones y prerequisitos, sin renombrar una selección como suite íntegra.
- Revisar diff y artefactos publicables; actualizar arquitectura si cambió diseño, filas del plan, estado, guías afectadas y changelog.
- Commit local del flujo solo en mantenimiento autorizado, staging selectivo tras revisión; nunca producto real ni remoto por esta autorización.
- Preservar trabajo ajeno y declararlo; árbol limpio respecto al trabajo propio no exige borrar ni incorporar archivos ajenos.
- Salida: todos los gates necesarios del núcleo acreditados y distribución reproducible. Mientras falten gates ejecutables dentro del mandato, continuar trabajando: no usar un cierre parcial como salida rutinaria. Solo un bloqueo real de autoridad, recursos o entorno que no pueda resolver permite devolver excepción, con siguiente acción exacta y sin afirmar arquitectura terminada.

## 7. Seguridad del ensayo y separación adquisición/ejecución

- Crear áreas externas separadas para distribución, runtime/dependencias, copias de productos, candidatos, estado y evidencia.
- No instalar dependencias, crear worktrees, cachés, logs, bytecode ni resultados de ejecución dentro del repositorio canónico.
- Obtener código/runtime/dependencias mediante adquisición host-side autorizada; verificar origen/versiones, manifiestos y contenido relevante.
- Inspeccionar scripts de instalación, build hooks, `build.rs`, proc-macros y helpers antes de ejecutarlos; no confiar en lockfile como garantía de seguridad.
- Descargar paquetes sin ejecutar hooks cuando sea viable; evaluar hooks necesarios en sobre aislado con destinos externos explícitos.
- La ejecución de producto se hace sin red general, con inputs sanitizados en lectura y escritura solo en candidato/estado autorizados.
- La inferencia permitida usa canal Host acotado; no entregar credenciales al agente ni montar home, sockets o configuración privada.
- No instalar emuladores/audio/DBus/Xvfb preventivamente; decidir por criterio necesario y probar los límites de cualquier sustituto.
- Servicios GUI/DB y caches necesarios permanecen en el entorno de ensayo; no usar servicios reales como atajo para obtener verde.
- Verificar hashes/manifiestos de fuentes originales antes/después, incluidos archivos nuevos y borrados; no seguir enlaces para modificarlas.
- Si el sandbox bloquea una dependencia necesaria, corregir la preparación autorizada, no ejecutar libremente ni parchear el runtime en secreto.

## 8. Checklist de handoff/bootstrap para experiencia no técnica

- [ ] Entregar distribución y versión identificadas, requisitos mínimos y una entrada DSH documentada que realmente exista.
- [ ] Preparar lo automatizable desde un mandato; no exigir editar presets, JSON, variables técnicas o configuración del producto a mano.
- [ ] Gate UX de este plan: máximo dos comandos de bootstrap del framework además de los imprescindibles DSH; preferir instalador único. No relajar ese máximo sin decisión explícita del usuario. Registrar todos los comandos, incluidos los del mantenedor, sin ocultar preparación.
- [ ] Cero edición manual JSON/YAML, shell de producto o troubleshooting técnico en fase usuario; un fallo se corrige en mantenimiento y obliga a repetir clean-room desde cero, registrando la ayuda anterior.
- [ ] Separar instalación inicial, uso normal, decisiones materiales y recuperación excepcional al contar intervenciones.
- [ ] Objetivo UX: «Audita el alcance acordado» y «Repara la cola autorizada e integra solo en la copia» cuando falte esa autoridad; cero prompts de «siguiente unidad». No fijar cuentas, proveedores ni secretos por este plan.
- [ ] DSH descubre/reutiliza perfil y evidencia; cero transporte manual rutinario de receipts, IDs, backlogs o diagnósticos de raíces.
- [ ] Verificar desde ambos modos el caso de incorporación inicial, perfil existente, conflicto y capacidad ausente con explicación corta.
- [ ] No prometer cero configuración ambiental: credenciales/permisos que solo puede otorgar el titular son decisiones previas explícitas.
- [ ] Fuera de esos pasos DSH autorizados, cero configuración manual de producto para conseguir que la demostración funcione.
- [ ] Mostrar resultados compactos y evidencias accesibles por referencia; no inundar al usuario con logs o instrucciones para técnicos.
- [ ] Si un criterio exige percepción, pedir observación al usuario-HUMANO con candidato/hash y procedimiento, no inventar su respuesta.
- [ ] Verificación humana ausente, inconclusa u obsoleta conserva `UNVERIFIED`; aceptar riesgo no convierte el criterio en verificado.
- [ ] Separar al agente mantenedor del agente evaluador que representa al usuario: este último parte de un contexto nuevo y solo recibe guía pública, proyecto y mandato, sin rutas internas ni diagnósticos del implementador. Registrar toda ayuda extraordinaria como intervención. No inventar clicks, respuestas humanas o percepción.
- [ ] Probar el recorrido de arranque y configuración real del framework, incluyendo obtención de la distribución desde el origen autorizado y resolución de prerequisitos. Una imagen preconfigurada es útil para regresión, pero no sustituye la prueba limpia desde descarga.
- [ ] Mantener un registro externo por interacción: actor, comando o mensaje visible, motivo, resultado y si fue imprescindible, decisión material o troubleshooting. Reproducir el mismo camino sin conocimiento privado del mantenedor en ambos proyectos.

## 9. Métricas, reservas y aceptación sin bucles

- Medir tiempo transcurrido, tokens de entrada/caché/salida por rol, requests, denegaciones, reintentos, rondas y tamaños de encargos/retornos.
- Registrar fuente, unidad y alcance; request no equivale a token ni coste, caracteres no equivalen a ahorro medido.
- El ledger reserva conservadoramente antes de inferir/ejecutar, reconcilia consumo observado y conserva incertidumbre sin subcontar al reiniciar.
- Conectar cuotas del broker por lanzamiento con presupuesto durable de misión; reiniciar proceso no renueva autoridad ni gasto disponible.
- Sin coste monetario observable, indicarlo y aplicar topes autorizados disponibles; no afirmar respeto a un tope monetario imposible de medir/acotar.
- Comparar misma base, alcance, aceptación y entorno, incluyendo fallos/retenciones; medir F5 o delegación contra baseline comparable.
- Calidad, seguridad, cobertura y evidencia humana necesaria son gates, no puntos compensables por ahorrar tokens.
- Consolidar revisión inicial; revisar luego correcciones y efectos nuevos, deduplicando causa/criterio/evidencia sin ocultar amenazas materiales.
- Presupuesto agotado, defecto repetido sin progreso o criterio indispensable ausente retienen la unidad; no ampliar límites ni forzar aprobación.

## 10. RSI acotada: EXTENSIÓN propuesta y condicionada

- RSI no está adoptada por este plan: requiere decisión explícita y actualización de arquitectura antes de incorporarse como requisito ejecutable.
- Cerrar primero el núcleo de misión normal; no sustituirlo por construir un motor recursivo de mejora.
- Default recomendado: mejora empírica en mantenimiento acotado; no reentrenamiento de pesos ni autorreescritura libre de objetivos/permisos.
- Responsable/control: mantenedor autoriza clase de cambio; evaluador confiable independiente fija gates; Host mantiene aislamiento y presupuesto.
- Artefactos/schema: observación mínima saneada → hipótesis por causa/ámbito → candidato externo versionado → comparación → decisión de promoción.
- Operación solo devuelve observaciones; no edita framework canónico ni skills activas para adaptar sus propias instrucciones.
- El candidato no puede modificar sus propios controles, evaluador, holdouts, criterios, permisos, presupuesto o mecanismo de promoción.
- Runner/evaluador provienen de versión confiable fijada; revisar aparte regresiones nuevas del autor, sin reemplazar la aceptación congelada.
- Positivos: comparar baseline/candidato en casos emparejados, defectos conocidos, casos sanos y transferencia a otro proyecto con QA real.
- Reservar holdouts fuera del acceso del generador; conservar repeticiones, resultados negativos e incertidumbre, no seleccionar solo ganadores.
- Negativos: frecuencia tratada como calidad, éxito de invocación sin resultado, contaminación de holdouts, fuga entre proyectos y cambios fuera del diff permitido.
- Gate: mejora observable con calidad/seguridad necesarias intactas, snapshot íntegro y QA/promoción autorizada; inconcluso queda retenido.
- Fijar versiones por sesión; promover solo para sesiones futuras, con actualización explícita/idempotente y rollback probado.
- Memoria externa privada con TTL y aplicabilidad; no ingestión automática de chats, secretos o código privado ni Git automático.
- ECC u otro tercero no es dependencia necesaria; las observaciones de la propuesta externa no constituyen auditoría propia ni benchmark reproducido aquí.
- Si no se adopta RSI, registrar decisión y cerrar el núcleo sin ella; si se adopta como requisito, sus gates faltantes impiden declarar completa esa extensión.

## 11. Matriz de trazabilidad de la arquitectura §§1–17

| Sección normativa | Fases | Evidencia/gate que debe quedar cerrado |
|---|---|---|
| §1 Consulta y mantenimiento | P0, P9 | Diseño único vigente, decisiones autorizadas y estado distinto de propuesta/implementación/verificación. |
| §2 Objetivo y límites | P0, P7, P9 | Dos proyectos, resultado aceptado, continuidad finita y ausencia de plataforma opcional obligatoria. |
| §3 Responsabilidades | P2, P4, P5 | Dos modos DSH reales, Host con autoridad, escritor único y revisión observable. |
| §4 Capas | P1, P2 | Método/perfil/skills/adaptador/Host separados; ninguna instrucción presentada como enforcement. |
| §5 Incorporación | P1, P7 | Descubrimiento, perfil privado mínimo, repetición segura y rechazo de conflictos. |
| §6 Mandato y autoridad | P0, P2, P9 | Capability ligada a permiso real, presupuesto finito y decisiones materiales no inferidas. |
| §7 Ciclo y persistencia | P4–P8 | Cola continuada, memoria de decisiones, versiones, ledger, checkpoint y reconciliación. |
| §8 Publicador/evidencia | P2, P5, P6, P8 | Identidad, autorización, resolución, límites, idempotencia y durabilidad contractual comprobada. |
| §9 Aceptación sin bucles | P3–P9 | Criterios fijados, QA/observación humana vigentes, negativos y retención por ausencia. |
| §10 Incidentes/regresiones | P3–P5, P9 | Causa deduplicada, corrección del responsable y prevención ejecutada sin autodebilitar controles. |
| §11 Seguridad | P1, P2, P7, P8 | Adquisición separada, sandbox efectivo, datos permitidos y fuentes conservadas. |
| §12 Intervención/recuperación | P7–P9 | Normal primero, excepciones breves, cancelación y ejecución incierta reconciliada. |
| §13 Cobertura/contratos | P3, P4, P7 | Inventario vigente, asignado distinto de revisado, perspectivas y contratos funcionales reales. |
| §14 Distribución/perfil | P1, P7, P9 | Bootstrap externo limpio, privacidad, actualización respaldada y límites de publicación. |
| §15 Adaptador/evolución | P2, P7–P9 | Composición Host sin patches ocultos, métricas finas y capacidades fallando cerradas. |
| §16 Hoja de ruta | P0, P9 | Etapas 0–8 reconciliadas por evidencia, no por cantidad de actividad ni éxito de fixtures. |
| §17 Aceptación distribución | P1, P7, P9 | Descubrimiento/cuerpo/conducta nativos y distribución exacta reproducible desde inicio. |

## 12. Entrega final del ejecutor y prompt listo para pegar

Entregar un resumen corto con estado del núcleo y de extensiones, gates aprobados/faltantes, evidencia externa recuperable, versiones y límites.
Informar comandos/intervenciones reales, coste observable, pruebas omitidas, fuentes preservadas y cambios/commits locales del flujo.
Si falta autoridad o entorno, indicar bloqueo, evidencia, decisión mínima, candidato/checkpoint preservado y trabajo independiente completado.
No publicar historiales privados en documentación; actualizar solo hechos publicables, sin rutas personales, secretos ni resultados privados.

> Ejecuta el plan de `docs/PLAN_EJECUCION_ARQUITECTURA_COMPLETA.md` subordinado a la arquitectura, al plan por etapas y al estado vigentes. Termina todo el núcleo con DSH real y pruebas end-to-end aisladas en copias externas de Syncify y RehabWeb, desde distribución/bootstrap hasta QA, circularidad, integración en copia, archivo y recuperación. Continúa sin pedirme prompts por subpaso dentro del mandato; usa mensajes cortos. Respeta autoridad y presupuesto finitos: este encargo no concede credenciales, gasto nuevo, cambios de producto real ni publicación remota. Si falta una autorización o capacidad necesaria, conserva evidencia/checkpoint, completa lo independiente y pide solo la decisión indispensable; no declares completo un gate sin probar. Evalúa las propuestas con los defaults del plan; RSI exige adopción arquitectónica explícita. No uses fixtures o patches runtime ocultos como sustituto de operación real.
