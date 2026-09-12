# Arquitectura del flujo de trabajo con agentes

**Versión:** 2.3
**Actualización:** 2026-09-12
**Estado:** arquitectura objetivo completa; implementación comprobada limitada a v0.1 acotada mediante skills Standard, recibos locales y controles mecánicos. Consultar [PLAN_IMPLEMENTACION.md](PLAN_IMPLEMENTACION.md) para el progreso por etapas.
**Responsable de las decisiones de alcance y autorización:** usuario.
**Propósito de este archivo:** ser la referencia vigente del diseño, sin depender de la memoria de una conversación.

## 1. Cómo consultar y mantener este documento

Leer este archivo al retomar el trabajo y antes de proponer cambios arquitectónicos. Consultar después solo los artefactos relevantes enlazados. Este documento describe la arquitectura; no acredita por sí mismo ejecución, permisos ni resultados actuales del entorno.

Cuando se acuerde una modificación:
1. Leer la sección vigente y actualizarla en este mismo archivo, sin crear otro plan competidor.
2. Registrar decisiones y cambios en CHANGELOG.md y Git; mantener esta arquitectura libre de historial.
3. Distinguir propuesta, decisión aceptada, implementación y verificación. No convertir una conversación favorable ni un estado JSON en una prueba de ejecución.
4. Mantener los pendientes y criterios de salida coherentes con el cambio. Preservar antecedentes fuera de la distribución y cambios futuros en Git.
5. Cambios de alcance, permisos, presupuesto o contrato material requieren autorización pertinente; no inferirla de este documento.

Si aparece un conflicto entre este archivo y una instrucción posterior explícita del usuario, aplicar la instrucción autorizada y actualizar el documento. Si solo cambia un hecho del entorno, registrar su procedencia y verificar lo necesario sin rediseñar el flujo.


## 2. Objetivo y límites

Permitir que el usuario autorice una misión acotada y deje a los agentes investigar, implementar, verificar, corregir y continuar con intervención mínima. El usuario no debe redactar una nueva orden al terminar cada turno.

El flujo es multiproyecto. Cada proyecto aporta sus especializaciones; ninguno define las tecnologías, rutas o artefactos obligatorios para los demás. Se admiten trabajos de software, investigación, documentación y operaciones, incluso sin Git.

El éxito se mide por resultados aceptados con evidencia, calidad, seguridad y coste, no por cantidad de agentes, documentos o actividad. Una tarea pequeña puede resolverse directamente. Los controles necesarios de seguridad y protección de datos no se omiten por simplicidad.

**No objetivos iniciales:** construir una plataforma universal nueva, producir dashboards/backlogs vacíos, rediseñar todo proyecto al incorporarlo, ni prometer recuperación ante cualquier caída antes de probarla.

## 3. Distribución de responsabilidades

### Usuario

Define objetivo y decisiones propias: alcance material, recursos permitidos, presupuesto cuando corresponda, datos compartibles y autorización de publicación/integración. Autoriza una misión completa con límites, no cada subpaso mecánico. Recibe cierre o excepción concreta.

### Arquitectura y mejora del sistema — fuera del flujo de usuario

El diseño, mantenimiento y mejora del propio flujo se realizan aparte de su operación. ZCode puede asumir actualmente ese trabajo, consultando y actualizando este documento. Perplexity Search queda como herramienta externa opcional de investigación o segunda opinión, **no como componente, requisito ni paso inicial/final del flujo**. No es necesario mantenerlo activo para desarrollar u operar el sistema; sus paquetes se conservan como antecedentes. Tampoco ZCode será una dependencia del usuario final.

La función original de Search era ayudar a mejorar la arquitectura, no redactar las misiones rutinarias del usuario ni aprobar cada resultado. Ningún asesor externo obtiene autoridad de ejecución por sus recomendaciones. Mantener separados el plano de mantenimiento del sistema y las misiones de los proyectos.

### DSH — dos modos de entrada para el usuario final

El usuario interactúa directamente con **Auditor** y **Reparación continua**. El plan original archivado usaba «Auditor de Completitud y Calidad» y «Syncify Lead Architect & Orquestador»; esos nombres quedan como antecedentes del diseño, no como modos adicionales ni presets actuales. Esta decisión no acredita que los modos objetivo ya estén implementados completamente.

- **Auditoría completa:** incorpora o reconoce el proyecto mediante skills compartidas, descubre superficies, particiona el alcance en unidades funcionales, delega revisiones reales cuando DSH lo permita, consolida hallazgos y publica una cola externa. No modifica producto; la reauditoría incremental reutiliza este rol.
- **Auditor unitario:** inspecciona una unidad autorizada y publica una entrega recuperable. Sigue siendo el worker interno de Auditoría completa y una entrada válida para encargos pequeños.
- **Reparación continua:** evolución del Orquestador. Recibe una misión o lote suficiente, comprueba base, alcance y autorización, coordina un ejecutor y QA independiente, gestiona correcciones, solicita reauditoría y continúa con las unidades autorizadas. Conserva candidatos y evidencia, integra solo si está autorizado y devuelve cierre o excepción. «Continua» significa continuidad dentro de límites, no ejecución infinita ni ampliación automática de alcance.
- **Ejecutor y QA:** funciones internas; un escritor por entorno y revisión independiente cuando la aceptación o el impacto lo requieran. El usuario no tiene que abrir sus sesiones ni redactar sus encargos rutinariamente.
- **Host/coordinador:** mantiene misión, autorización, entrega, estado, exclusión de escritores y límites. Realiza las transiciones internas cuando estén autorizadas; un hallazgo del Auditor no autoriza por sí solo repararlo.

La autorización de una misión debe poder reutilizarse como capability nativa durante sus unidades compatibles: lectura de producto, ejecución limitada del framework y escritura externa. Si el Host no demuestra esa persistencia y granularidad, el modo retiene la unidad en vez de repetir escalaciones o pedir acceso total.


La incorporación es una capacidad compartida disponible desde ambos modos, no un tercer modo obligatorio. Reparación continua puede reutilizar una auditoría válida; si falta diagnóstico suficiente, lo solicita internamente o pide únicamente la decisión humana indispensable. El objetivo es que el usuario elija modo y alcance, no transporte manualmente recibos entre sesiones.

**Standard y Creator/Cordis son herramientas de desarrollo/transición**, no modos adicionales exigidos al usuario final. Standard puede alojar ensayos de skills y ejecución; Creator se usa solo para necesidades reales de composición. No cambian presets, permisos ni instalaciones automáticamente por esta actualización documental.

Una sesión separada con el mismo modelo puede proporcionar separación autor/revisor, pero no independencia estadística garantizada. Cambiar de proveedor o renombrar el mismo autor no acredita una revisión independiente. QA debe inspeccionar el candidato real y tener acceso suficiente a la evidencia.

### Alcance operativo v0.1

Standard aloja `workflow-auditor` y `workflow-continuous-repair` como entradas conductuales nativas de una unidad supervisada, no presets ni enforcement Host. START despacha el pedido ordinario; docs/usage.md define bootstrap, permisos efectivos y protocolo. Auditor termina en informe/propuesta sin modificar producto. Reparación requiere encargo separado, candidato externo, un escritor, autoprueba registrada y QA de subagente nativo disponible o revisor humano; sin QA se retiene, no se simula. Máximo dos intentos de corrección, sin goals ni siguiente objetivo automático. No integra producto por defecto.

Dos archivos centrales task/result referencian evidencia externa. `scripts/missions.py` ejecuta argv explícito autorizado con shell=false, timeout POSIX y stdout/stderr con hashes; verify rechaza aceptación documental sin prueba vigente o referencia QA correspondiente en reparación. `reaudit` liga una reauditoría mecánica incremental al resultado y candidato vigentes, dejando la revisión semántica explícitamente pendiente para Auditor/QA. No autentica autorización, independencia ni semántica y no es sandbox. El publicador histórico no se adapta mientras este alcance local no lo necesite. Permisos del producto hermano se comprueban por lectura mínima; si faltan, se detiene para decisión nativa del usuario sin eludir límites.

Las skills se copian recursivamente al workspace, idénticas son idempotentes; actualización conflictiva exige autorización explícita y respaldo externo completo. No hay actualización operativa del framework ni cambios globales. La carga con servicios DSH y el ciclo sintético prueban mecanismos locales; operación LLM, QA nativa real y recuperación se acreditan por separado.

## 4. Capas de la solución

| Capa | Contenido | No debe confundirse con |
|---|---|---|
| Método general | Alcance, aceptación, roles, evidencia, paradas y medición | Un procedimiento pesado obligatorio para toda tarea |
| Perfil del proyecto | Fuentes, repositorios, rutas, comandos, restricciones, canónicos y datos sensibles | Una skill ni permisos efectivos |
| Skills generales de DSH | Incorporación, ejecución, pruebas seguras, evidencia, revisión y reauditoría | Código que hace cumplir restricciones |
| Skills específicas | Procedimientos particulares recurrentes y comprobados | Una copia de rutas o instrucciones generadas por tecnología |
| Adaptador del entorno | Versión, loader, herramientas, API y capacidades comprobadas | Suposiciones transferidas desde otro runtime |
| Servicios y controles Host | Persistencia, autorización, límites, publicación y coordinación | Un modelo que decide por sí solo la corrección semántica |

Las skills explican cómo trabajar. El perfil aporta datos. El Host aplica las propiedades mecánicas. Ninguna skill puede ampliar la autorización o reducir la aceptación para obtener un resultado verde.

## 5. Incorporación de proyectos: descubrir antes de crear

La incorporación usa una skill compartida y un inicializador externo. Su disponibilidad y verificación actual se documentan en docs/status.md; no implican autonomía DSH.

Debe:
1. Identificar fuentes y origen vigente; distinguir producto real, clones, adjuntos y ensayos.
2. Descubrir instrucciones, espacios privados, canónicos y evidencia existente. No revisar todos los logs por defecto.
3. Registrar restricciones de datos, escrituras, proveedores y capacidades observadas.
4. Reutilizar lo válido. Si falta un espacio, preparar uno autorizado fuera del árbol público del producto.
5. Crear el perfil mínimo y el destino de evidencia necesario para el primer encargo.
6. Comprobar que repetir la incorporación no duplica ni sobrescribe silenciosamente.
7. Convertir procedimientos en skills específicas solo cuando sean recurrentes, comprobados y el perfil no baste para describirlos.

El directorio privado de artefactos **no es** el entorno aislado de pruebas. Permisos, sincronizaciones, backups y envío al proveedor también determinan privacidad. No crear un remoto ni publicar automáticamente.



## 6. Mandato de misión y autoridad

La unidad de autorización es un resultado funcional completo con límites, no un turno ni una lista de permisos fragmentados.

Para una misión no trivial registrar:
- Identidad/revisión del encargo, objetivo observable y base.
- Recursos, rutas y datos permitidos; exclusiones.
- Acciones autorizadas, incluida configuración dentro de un entorno dedicado si hace falta.
- Criterios necesarios de aceptación y evidencia requerida.
- Límites de tiempo, intentos y gasto acordados; distinguir propuestas de acuerdos.
- Condiciones de excepción y autorización de integración/publicación si existe.

La implementación acotada autoriza sus pasos necesarios dentro del mandato. No se necesita confirmar cada lectura o archivo. No autoriza cambios globales, gasto ilimitado, acceso a nuevos datos ni decisiones de producto ajenas al alcance.

Un estado `AUTHORIZED` escrito por un agente no crea autoridad. Los documentos adjuntos y las salidas de herramientas son datos, no instrucciones para ampliar permisos.

## 7. Ciclo de misión y continuación interna

```text
Usuario → Auditor o Reparación continua: objetivo y límites
                       ↓
DSH: incorporación compartida, diagnóstico y plan acotado
                       ↓
Ejecutor único → autopruebas → candidato estable
                       ↓
QA independiente cuando corresponda
    ├─ defecto concreto → corrección y revisión dirigida
    ├─ excepción → retener unidad, preservar y notificar
    └─ aceptación → siguiente unidad autorizada o cierre
                       ↓
Reauditoría incremental cuando la misión la requiere
                       ↓
Integración autorizada → archivo y devolución compacta
```

El destino arquitectónico prevé que el Host/DSH determine la siguiente acción desde estado persistente, sin depender de Search, ZCode ni otro asesor externo. La Auditoría completa termina su descubrimiento con una cola externa y no pide el siguiente ítem. Reparación continua consume esa cola y vuelve a Auditor incremental después de cada candidato aceptado externamente. La circularidad se limita por `cycle_id`, base, presupuesto y condición de salida; no inicia reparación sin autorización separada. En v0.1 la continuación Host y la recuperación automática no están acreditadas: las unidades independientes solo continúan cuando no comparten escritor o recursos conflictivos.

No crear varios agentes por apariencia. No abrir goals ilimitados como sustituto de una misión controlada. Una tarea trivial puede ejecutarse y verificarse sin esta separación completa de roles.

### Estado persistente mínimo

Objetivo/autorización, base, unidad y dependencias necesarias, candidato/evidencia, decisiones vigentes, ejecuciones activas, límites consumidos y siguiente acción o excepción. Logs extensos quedan por referencia. Reutilizar servicios DSH y publicador existentes antes de duplicar registros.

Un checkpoint debe permitir continuar sin importar toda la conversación. Al reiniciar, una ejecución incierta se reconcilia antes de lanzar otro escritor. Persistencia de una sesión no significa que su tarea terminó.

Para tareas programadas del framework, la persistencia externa comienza antes de cualquier trabajo: crear un directorio de sesión nuevo (sin sobrescribir uno existente) y escribir `started.json` de inmediato con identidad, hora, raíces, alcance y estado. La tarea debe crear explícitamente sus fixtures y prerequisitos, registrar sus rutas absolutas y no depender de cwd, scheduler o contexto de otra sesión. Cada salida termina con `checkpoint.json`, `report.md` y `finish.json`; si falta un prerequisito o la ejecución queda bloqueada, checkpoint e informe deben conservar `RETAINED` con causa, evidencia, límites y siguiente acción. `finish.json` referencia los tres artefactos y el estado final. Esta garantía de protocolo no acredita durabilidad ante crash o pérdida de energía ni sustituye controles Host.

## 8. Publicador, entrega y evidencia

Reutilizar el publicador de referencia al preparar el adaptador; generalizar bindings y alcance antes de distribuirlo como operativo. El archivo histórico no es una dependencia de instalación.

Propiedades necesarias: identidad real del llamante más autorización; entradas y tamaño limitados; destinos determinados por Host; registros incrementales; reintentos idempotentes; conflictos rechazados; evidencia ligada a la base; entrega parcial distinta de completa; recuperación verificable de contenido.

El ID es opaco y realmente emitido. No imponer convenciones ficticias como `receipt_TASK_timestamp.json`.

`INICIO_LOTE: {"receipt_id":"..."}` es suficiente **solo entre consumidores con resolución real y acceso autorizado al contenido**. En el flujo final, entrega y resolución pertenecen a DSH/Host; copiar ese mensaje manualmente es un recurso de ensayo o recuperación, no un requisito rutinario del usuario. El paso Auditor→Reparación requiere autorización de reparación vigente. Exportar evidencia a un asesor externo es opcional, previa revisión de sensibilidad; no forma parte del protocolo obligatorio.

`ACCEPTED`/`VERIFIED` son estados con alcance definido, no prueba automática de QA ni integración. Registrar quién evaluó qué candidato, evidencia y limitaciones. Los hashes detectan identidad/corrupción; no acreditan por sí solos autenticidad contra quien controla todo el almacén.

Distinguir visibilidad atómica, no sobrescritura, persistencia tras proceso, crash y pérdida de energía. Un rename o un reinicio normal no prueba todas esas propiedades. Multiarchivo necesita mecanismo propio; edición manual no aporta atomicidad por sí misma.

El publicador local entrega únicamente cierres `COMPLETE`; Auditoría completa añade un ciclo externo versionado con manifiesto, matriz de cobertura, cola de reparación y resumen compacto. Los logs y cierres extensos pasan a un archivo indexado y no se cargan automáticamente en el estado activo. El consumidor valida apertura, propietario, hashes, ausencia de gaps y tareas enlazadas a evidencia del mismo lote. Rechaza JSON no objeto, `OPEN` y escrituras de lote tras cierre; reserva sufijos de ciclo y limita IDs de lote a 53 caracteres para admitir registros generados y etapas. Las etapas positivas reciben como `evidence` el ID de evidencia incluida y enlazada por una tarea del lote: su payload contiene `task_ref`, `task_sha256`, `result_ref` y `result_sha256`. Revalida recibos, hashes y `missions.verify` en cada transición; executor/QA/auditor comparten esa referencia y declaran actores distintos. `CANDIDATE` significa aquí una misión ya aceptada documentalmente, no un candidato previo a QA. `reaudit` reutiliza todos los prerrequisitos de `verify`; audit no requiere prueba, pero valida cualquier `check_ref` aportado. Esto no autentica actores ni revisión semántica; almacén local confiable, sin garantía de concurrencia hostil.

El namespace local conserva IDs con guiones: los registros ordinarios no pueden terminar en el componente `open`, `close`, `executor`, `qa` o `auditor`, tampoco con prefijos como `x-close`. Así no ocupan IDs de ciclo de otros lotes; cualquier colisión ordinaria se rechaza sin sobrescribir. La cuota sigue siendo de 16 archivos JSON por almacén: toda publicación, incluida la genérica, computa registros existentes más reservas reconstruidas desde aperturas/cierres. Abrir reserva un cierre y tres etapas; un lote `COMPLETE` conserva las etapas pendientes, y `PARTIAL` libera esas tres plazas. Cada escritura terminal consume su propia reserva; reintentos idénticos no consumen cuota. Política conservadora acotada: un lote abierto aislado admite como máximo 11 registros ordinarios, y no se liberan etapas por estados fallidos; otro almacén externo es necesario cuando se agota la capacidad. La reserva garantiza espacio, no la validez semántica de una transición, ni concurrencia o reparación de almacenes previos ya saturados. IDs anidados y enlaces `evidence_id` malformados se rechazan con `ValueError` antes de operaciones de conjuntos/mapas. Antes de persistir `COMPLETE`, el productor exige payloads objeto tanto en evidencia como en tareas, incluidas publicaciones genéricas, igual que el consumidor; el rechazo no escribe cierre ni impide publicar registros corregidos o cerrar `PARTIAL` con gaps.

## 9. Aceptación sin bucles

- Fijar alcance y criterios antes de implementar. Un cambio material versiona el contrato con autorización pertinente.
- Consolidar una revisión inicial y revisar después correcciones, efectos relacionados y evidencia material nueva.
- Bloquear por incumplimiento de un criterio necesario o un problema concreto de seguridad/datos. Evidencia necesaria ausente permanece `UNVERIFIED`.
- Preferencias y mejoras futuras no son nuevos requisitos de aceptación.
- Deduplicar por causa, criterio y evidencia. No repetir una objeción resuelta sin evidencia nueva.
- Si la causa se repite sin progreso o se consume el presupuesto, retener y preservar esa unidad. No forzar aprobación ni continuar rondas indefinidas.
- Una nueva amenaza material no se ignora para satisfacer un contador de revisiones; se atiende dentro de alcance o se escala.

Una revisión documental externa no sustituye QA que necesita inspeccionar/ejecutar el candidato en el entorno adecuado. La aceptación operativa no depende de un veredicto de Search.

## 10. Convertir incidentes en regresiones del flujo

Por cada fallo relevante: identificar causa → corregir la pieza responsable → añadir comprobación pequeña → verificar casos relevantes sin degradar garantías.

| Incidente observado | Tratamiento correcto |
|---|---|
| Preguntar otra vez dónde van artefactos | Guardar y reutilizar decisión del perfil |
| Confundir persona.prefix con loader de skills | Separar esquema de preset, descubrimiento y carga de skill |
| Repetir argumentos inválidos | Control Host con diagnóstico y suspensión comprobable |
| Terminar con una skill no utilizable | Aceptación funcional de descubrimiento, carga y prueba |
| Quitar symlink y declarar aislamiento | Comprobar destinos de escritura y límites efectivos |
| Hallazgo antiguo con hashes del candidato corregido | Vincular diagnóstico a su base y distinguir reproducción histórica |
| Pedir al usuario el siguiente prompt | Estado y continuación internos dentro de la misión |
| Autorizar cada subpaso documental | Mandato de resultado con límites suficientes |

No crear una skill ni añadir otra prohibición global por cada incidente. Las regresiones de conducta pueden ser escenarios; las garantías mecánicas necesitan pruebas y controles ejecutables. El flujo no puede automejorarse rebajando sus propios criterios o permisos.

## 11. Seguridad de pruebas y protección del producto

Inspeccionar manifiestos, scripts, build.rs, proc-macros, helpers y rutas antes de ejecutar. Clasificar pruebas según dependencias: unitarias aislables, integración local, GUI/servicios, audio/hardware, red y datos personales. No instalar DBus/Xvfb/audio simulado de forma preventiva.

El launcher externo `scripts/host_launcher.py` aplica una envolvente Linux/bubblewrap fail-closed a un argv explícito. Monta plataforma `/usr` y compatibilidad bin/lib en lectura, entradas autorizadas con nombres bajo `/inputs` y solo un estado externo recién creado 0700 bajo `/state`; proc/dev y namespaces de red/PID/IPC son privados, el entorno se reconstruye sin configuración ni credenciales heredadas. No monta la raíz del Host ni su home/run/tmp. Rechaza sockets en las entradas y raíces ambiguas/solapadas; el caller debe suministrar árboles estables sin secretos: lectura explícita no equivale a sanitización de su contenido, ni se acreditan carreras hostiles. No instala runtime ni configura modelos, no reutiliza estado y no ofrece fallback sin aislamiento. El estado externo preserva logs incluso ante fallo/timeout. El cwd debe ser la ruta original de una entrada autorizada: se monta adicionalmente en lectura en esa ruta, creando solo padres vacíos y rechazando colisiones con raíces reservadas. `/tmp` usa un bind privado para no cambiar el cwd mediante resolución de symlinks. Esta primitive no integra el Host activo ni acredita subagentes, continuación o QA; el alcance comprobado de servicios, arranque autenticado y carga nativa de ambos modos en sesión Host sin modelos se registra en docs/status.md.

Clones, worktrees y HOME/XDG/TMPDIR no son sandbox OS. Enlaces de node_modules pueden escribir caché fuera del ensayo. No copiar datos personales ni credenciales para lograr tests verdes. Toolchains y cachés requieren rutas explícitas si cambia el entorno.

Un escritor por entorno. Preservar diff, archivos nuevos, hashes y diagnóstico antes de descartar un candidato. No usar stash/pop como mecanismo rutinario para demostrar rojo sobre trabajo activo; reproducir base en copia desechable. Verificar terminación antes de recuperar.

Una suite con fallos preexistentes puede demostrar ausencia de regresiones dentro de una comparación pertinente, no una suite limpia. Informar fallos exactos y pruebas omitidas.


## 12. Intervención humana y recuperación

Intervenir por: cambio material de alcance/contrato, acceso a recursos o credenciales no autorizados, gasto fuera de límites, integración/publicación no autorizada o ejecución incierta no reconciliable.

Formato breve de excepción: bloqueo concreto; evidencia; recomendación y decisión necesaria; candidato preservado; trabajo independiente que puede continuar. No pedir al usuario nombres/rutas ya acordados ni que diagnostique errores mecánicos por el agente.

Primero demostrar autonomía durante operación normal. Después probar timeout, cancelación, caída del Host y recuperación. Ante estado incierto, no reenviar escrituras ni crear escritores duplicados a ciegas. La suspensión durable y la reconciliación requieren pruebas específicas antes de declararse disponibles.


## 13. Cobertura y contratos

Inventariar unidades y dependencias relevantes sin equiparar leído con revisado. Separar hallazgos, hipótesis, exclusiones y cobertura desconocida. Revisar conjuntamente dos o más problemas relacionados, y también un único problema de alto impacto. No certificar completitud con conteos.

Seguir contratos desde productor real hasta consumidor, incluidos serialización, null, opcionales, números y persistencia. Compilar no demuestra equivalencia funcional. Los mocks deben corresponder al productor y las regresiones quedar ejecutables. QA revisa también cambios en expectativas y configuración. Una excepción aceptada no se renombra VERIFIED.

## 14. Distribución y perfil privado

Clonar agent-workflow junto al proyecto, nunca dentro de su árbol. El repositorio contiene método, skills, inicializador y pruebas sintéticas. El workspace externo contiene PROJECT.md, identidad mínima y evidencia necesaria; no se versiona aquí. Producto, framework y workspace son ámbitos distintos. El inicializador no instala runtime, no autoriza ejecución y no descubre automáticamente todos los canónicos. La sesión Standard conserva el padre de framework/producto/workspace como raíz. La preparación autorizada copia skills completas al workspace y expone enlaces individuales en `.agents/skills` del padre, gestionados por manifiesto externo; no modifica destinos a través de enlaces. Sin ancestro Git, el loader nativo usa ese cwd y sigue esos enlaces, sin buscar hijos arbitrarios. Un workspace gestionado por padre; conflictos, overrides locales y cambios de conjunto de nombres bloquean hasta reconciliación explícita. Repetición idempotente, actualización de copias con respaldo y retirada solo de enlaces propios. No requiere overlay ni cambios globales. Descubrimiento por proyecto no es aislamiento de archivos: lectura de producto/framework y escritura de workspace requieren autoridad efectiva separada. Framework de solo lectura es procedimental salvo enforcement externo demostrado; sin granularidad necesaria Auditor retiene, no solicita acceso total.

La incorporación exige rutas explícitas, evita enlaces y sobrescrituras, conserva el perfil existente y falla ante conflictos. No crear dashboards ni backlogs vacíos. Configuración, credenciales, fuentes privadas, logs, clones y candidatos quedan fuera de la distribución. La publicación requiere revisión explícita y licencia decidida por el titular.

## 15. Adaptador, controles y evolución incremental

DSH/Cordis reutiliza sus registros de sesiones, persistencia y herramientas; un preset no duplica servicios globales. Los plugins dinámicos son ensayos, deben liberar efectos al detenerse y no acreditan instalación persistente. No modificar presets distribuidos ni routing, modelos, alias, fallback o proveedores sin autorización.

Comprobar el DSL y validar dentro del handler, además del esquema. El Host detecta argumentos inválidos repetidos, limita intentos y conserva un diagnóstico antes de suspender. Suspensión, timeout, cancelación, reinicio y recuperación se verifican por separado. RTK o compresión no prueban ahorro global; separar salida íntegra y truncada.

Avanzar por incorporación local, carga real de skills, misión normal completa, coordinación de los dos modos, excepciones/recuperación y transferencia a un segundo proyecto. Reutilizar el código existente cuando sus límites encajen, sin desarrollar un motor universal por adelantado. Medir base fija, resultados aceptados, intervenciones, coste disponible y regresiones; no actividad ni número de agentes.

## 16. Hoja de ruta y estado de implementación

El plan original archivado en `PLAN_ARQUITECTURA_ORIGINAL.md` se conserva como arquitectura de destino completa: publicador Host, handoff determinista, coordinación persistente, QA independiente, reauditoría, integración autorizada, archivo y recuperación. No se considera que esas capacidades existan por estar descritas aquí.

La implementación actual es una reordenación acotada y comprobada parcialmente: onboarding, distribución/carga nativa de skills, recibos locales, ejecución argv controlada, snapshots/hash, límites de `change_scope`, ciclo sintético rojo→verde, retención por evidencia ausente y reauditoría mecánica. Los ensayos históricos de publicador, lector, handoff y piloto Syncify permanecen como evidencia externa supervisada; no equivalen a un Host operativo, autonomía LLM, IPC Tauri nativo, integración del producto ni recuperación ante crash.

La matriz breve y vigente de etapas está en [PLAN_IMPLEMENTACION.md](PLAN_IMPLEMENTACION.md). Los diagramas interactivos del sistema están en [docs/diagrams/README.md](docs/diagrams/README.md). `docs/status.md` conserva el estado comprobado; `CHANGELOG.md` conserva decisiones históricas. No se importan logs, candidatos, rutas privadas ni resultados de ejecución al repositorio.

El criterio final de éxito sigue siendo el flujo de destino:

```text
diagnóstico sustentado → solución revisada → encargo suficiente
→ implementación acotada → QA independiente → reauditoría incremental
→ integración autorizada → archivo recuperable
```

Hasta que la matriz y la evidencia indiquen lo contrario, el framework debe describirse como operación v0.1 acotada, no como autonomía completa.

## 17. Aceptación de la distribución y fuentes vigentes

El inicializador debe funcionar en directorios desechables, no modificar producto ni framework, rechazar conflictos y permitir repetición sin pérdida. La carga DSH exige comprobar descubrimiento, cuerpo y ejecución real con presupuesto autorizado. Una prueba Python no acredita estas propiedades del runtime.

Guía de entrada: [README.md](README.md). Instalación acotada: [docs/setup-dsh.md](docs/setup-dsh.md). Evidencia y pendientes: [docs/status.md](docs/status.md). Historial: [CHANGELOG.md](CHANGELOG.md) y Git. Este documento es el diseño normativo completo; el estado implementado se consulta por separado.
