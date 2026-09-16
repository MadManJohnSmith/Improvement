# Arquitectura del flujo de trabajo con agentes

**Versión:** 3.0
**Actualización:** 2026-09-16
**Estado:** arquitectura normativa objetivo para la siguiente etapa del framework. El MVP operativo anterior permanece comprobado según `docs/status.md`; la capa nueva de bootstrap, generación Creator específica por proyecto y activación transaccional sigue pendiente de implementación por etapas C0–C7.
**Responsable de alcance y autorización:** usuario/titular.
**Propósito:** definir el flujo final distribuible en el que un usuario configura DSH una vez, clona el framework y ejecuta un bootstrap único que coordina Creator, validación Host, backups, aceptación automática, activación y rollback de modos y skills específicos del proyecto.
**Jerarquía:** subordinada a `AGENTS.md`; `PLAN_IMPLEMENTACION.md` registra el progreso comprobado y `docs/status.md` separa hechos de destino.
**Antecedentes:** la arquitectura v2.4 y los planes de cierre permanecen en Git; los presets operativos de Syncify/RehabWeb son fixtures de referencia, no defaults distribuibles. Se adaptan patrones del repositorio público `jsmastery-pro/skills` en el commit observado `43b69e44c9ca905fe3a3418ccdf4102255e20d40` (MIT, 2026-08-07).

---

## 1. Corrección fundamental del diseño

El framework no debe distribuir presets finales universales de Auditoría y Reparación continua. Los presets externos usados durante el desarrollo demostraron routing, skills, subagentes, QA, reauditoría y el plugin `workflow-write`, pero son **rigs de referencia**, no la experiencia final del usuario.

El producto distribuible será:

```text
método + skills generales + plantillas normativas + schemas + validadores
+ controles Host + bootstrap + prompts de Creator + fixtures saneados
```

El resultado de la incorporación será:

```text
<Proyecto>-auditor
<Proyecto>-continuous-repair
+ skills específicas justificadas por el proyecto
```

La especialización sucede una vez durante la incorporación o regeneración. En el uso normal el usuario elige uno de los dos modos y escribe objetivos breves; no vuelve a Creator por cada auditoría o reparación.

### 1.1 Qué se conserva de la arquitectura vigente

- dos modos finales: Auditoría y Reparación continua;
- incorporación compartida;
- Host como dueño de autoridad, persistencia, presupuesto, locks y transiciones;
- Auditor sin escritura de producto;
- candidato externo o rama autorizada para Reparación;
- un escritor por entorno;
- QA independiente y reauditoría semántica posterior;
- evidencia ligada a base/candidato/hash;
- máximo dos intentos de corrección por unidad;
- publicación remota deshabilitada salvo autorización;
- estados fail-closed (`RETAINED`, `UNVERIFIED`);
- separación producto/framework/workspace;
- skills no equivalen a enforcement;
- Creator propone, pero no concede autoridad ni se autoaprueba.

### 1.2 Qué se corrige

- Los modos no son presets genéricos preparados por el mantenedor; son composiciones generadas por proyecto.
- Creator no produce únicamente `preset.yml` y `agent.cordis.yml`; produce un paquete generacional completo.
- El usuario no debe copiar el prompt a Creator ni ejecutar manualmente `bootstrap accept` en el caso normal.
- El bootstrap debe autenticarse contra DSH local y enviar automáticamente la petición a Creator.
- Creator ejecuta `bootstrap.py accept`; el Host valida y decide la aceptación mecánica.
- Las skills específicas pueden generarse o mejorarse, pero siempre con backup íntegro antes de sustitución.
- La instalación/actualización es transaccional como conjunto de modos y skills, no archivo por archivo.
- La aceptación funcional pequeña se ejecuta automáticamente mediante sesiones DSH; el usuario no diseña el escenario.
- Los patrones de progressive disclosure y presupuestos de hot paths se incorporan a las skills generadas.

---

## 2. Experiencia objetivo del usuario

### 2.1 Prerrequisitos

El usuario debe configurar una sola vez:

1. DSH instalado en una versión compatible.
2. Al menos un proveedor/modelo utilizable dentro de DSH.
3. Credenciales gestionadas por DSH, no por el framework.
4. Creator disponible en la instancia.
5. Permisos nativos mínimos para leer proyecto/framework y escribir el workspace externo.

El bootstrap no lee ni copia la API key del proveedor. Reutiliza el Host DSH y obtiene únicamente el token/cookie local de consola necesario para la API local. Ese secreto se mantiene en memoria y nunca entra en prompts, argv, entorno del agente ni artefactos.

Si falta proveedor, Creator o capacidad:

```text
RETAINED: <capacidad ausente>
Siguiente acción: <una única decisión o preparación del titular>
```

### 2.2 Un único comando normal

```bash
python3 -B scripts/bootstrap.py install \
  --project /ruta/proyecto
```

Opcional avanzado:

```bash
  --workspace /ruta/workspace
```

El comando realiza:

```text
descubrimiento inicial
→ workspace externo
→ skills generales
→ creator-run
→ petición automática a Creator por DSH local
→ generación específica
→ Creator invoca accept
→ Host valida, respalda e instala en staging
→ aceptación funcional automática
→ activación o rollback
→ cierre compacto
```

El usuario no copia prompts, rutas, JSON, IDs, receipts, plugins o modelos; tampoco ejecuta `accept` manualmente en el caso normal.

### 2.3 Uso posterior

Auditoría completa:

> Audita completamente este proyecto.

Auditoría dirigida:

> Audita el flujo de pagos.

> Audita este componente.

Reparación completa:

> Repara la cola autorizada en la rama de prueba.

Reparación dirigida:

> Repara este hallazgo.

> Repara solo el flujo de pagos.

El Host gestiona internamente unidades, escritor, candidatos, QA, reauditoría, commits, archivo y continuidad.

---

## 3. Responsabilidades y fronteras de confianza

| Actor/componente | Puede | No puede |
|---|---|---|
| Usuario | Configurar DSH/proveedor; iniciar install/update/uninstall; conceder permisos materiales; definir rama/publicación | Transportar recibos rutinariamente; diseñar la aceptación técnica |
| Bootstrap | Descubrir; preparar workspace; llamar DSH/Creator; validar; respaldar; staging; instalar; activar/rollback | Inventar autorización; leer credenciales de proveedor; modificar producto |
| Creator | Analizar proyecto; generar paquete candidato; crear skills específicas; invocar `bootstrap accept`; corregir errores mecánicos dentro de límites | Instalar directamente; modificar validadores; rebajar controles; declararse ACCEPTED |
| Host | Validar schema/capabilities/hashes; presupuesto; backup; instalación transaccional; aceptación; activación/rollback | Delegar autoridad al modelo; aceptar manifiestos declarativos como permiso |
| Auditor generado | Leer alcance; inventariar; delegar revisión; emitir cola/evidencia | Modificar producto; publicar; ampliar roots |
| Reparación generada | Trabajar en candidato/rama autorizada; ejecutar pruebas permitidas; coordinar QA | Escribir fuera del cambio autorizado; publicar sin mandato |
| QA | Revisar candidato exacto; ejecutar criterios; aceptar/rechazar | Ser el mismo autor presentado con otra etiqueta |
| Auditor posterior | Reauditar semánticamente candidato aceptado | Sustituirse por la QA previa |

La frontera principal es:

```text
Creator genera y solicita aceptación
Host valida, instala y decide estado mecánico
```

---

## 4. Contenido distribuible del repositorio

### 4.1 Skills generales del framework

- incorporación/onboarding;
- aceptación acotada;
- gestión de evidencia;
- validación segura;
- creación controlada de skills;
- entrega proporcional y recuperación;
- utilidades generales que no codifiquen un proyecto.

Las skills operativas actuales de Auditor/Reparación pueden servir como fuentes normativas y fixtures, pero no se instalan como modos finales universales.

### 4.2 Plantillas de composición

- contrato obligatorio de `<Proyecto>-auditor`;
- contrato obligatorio de `<Proyecto>-continuous-repair`;
- campos variables que Creator debe completar;
- restricciones inmutables;
- contratos de plugins, herramientas, routing y modelos;
- escenarios de aceptación mínimos.

### 4.3 Schemas y validadores

- perfil/manifiesto de proyecto;
- `generation-manifest.json`;
- modos generados;
- capabilities;
- roots/exclusiones;
- comandos autorizables;
- modelos y proveedores permitidos;
- presupuesto/timeout/intentos;
- identidad de roles;
- skills generadas;
- grafo de progressive disclosure;
- backup/install/rollback receipts.

### 4.4 Bootstrap y desinstalador

Comandos objetivo:

```bash
bootstrap.py install
bootstrap.py accept          # lo invoca Creator en operación normal
bootstrap.py verify-acceptance
bootstrap.py update
bootstrap.py uninstall
bootstrap.py purge-data      # destructivo, separado y con confirmación
```

### 4.5 Prompts versionados para Creator

- incorporación inicial;
- regeneración por cambio material;
- actualización de framework/DSH;
- corrección de generación `RETAINED`;
- creación/mejora de skills específicas.

### 4.6 Ejemplos/fixtures

- Syncify y RehabWeb saneados;
- sin rutas locales, credenciales, sesiones, candidatos ni datos privados;
- marcados explícitamente como fixtures;
- nunca se instalan como defaults;
- golden manifests para pruebas del generador/validador.

### 4.7 Plantillas de skills específicas

- frontmatter permitido;
- router de entrada;
- `modes/`, `internal/`, `references/`, `templates/`;
- criterios de activación;
- capacidades requeridas/prohibidas;
- pruebas mínimas;
- reglas para scripts/helpers;
- límites de contexto y hot paths;
- procedencia/licencias.

### 4.8 Controles Host

- onboarding/manifest;
- budget y métricas;
- memoria de decisiones;
- publisher y missions verify;
- controller;
- launcher/canal de inferencia;
- plugin `workflow-write`;
- validador de generación;
- instalador transaccional.

---

## 5. Layout de una generación

Cada incorporación/regeneración crea un ID opaco y un directorio exclusivo:

```text
workspace/
└── creator-runs/
    └── <generation-id>/
        ├── started.json
        ├── generation-request.json
        ├── creator-prompt.md
        ├── discovery/
        │   ├── project-inventory.json
        │   ├── instructions-index.json
        │   ├── effective-capabilities.json
        │   ├── effective-routing.json
        │   └── evidence-index.json
        ├── design/
        │   ├── mode-map.json
        │   ├── skill-plan.json
        │   ├── policy-decisions.json
        │   └── provenance.json
        ├── generated/
        │   ├── generation-manifest.json
        │   ├── project-manifest.json
        │   ├── capabilities.json
        │   ├── modes/
        │   │   ├── <Proyecto>-auditor/
        │   │   └── <Proyecto>-continuous-repair/
        │   ├── skills/
        │   │   ├── <Proyecto>-auditor/
        │   │   ├── <Proyecto>-continuous-repair/
        │   │   └── <skills-específicas>/
        │   ├── templates/
        │   ├── adapters/
        │   ├── acceptance-plan.json
        │   └── generation-report.md
        ├── validation/
        │   ├── schema-report.json
        │   ├── portability-report.json
        │   ├── context-budget-report.json
        │   ├── security-report.json
        │   ├── graph-report.json
        │   └── collision-report.json
        ├── accept/
        │   ├── host-preflight.json
        │   ├── backup-manifest.json
        │   ├── backup-verification.json
        │   ├── staging-manifest.json
        │   ├── install-receipt.json
        │   ├── acceptance-report.json
        │   └── rollback-receipt.json
        ├── checkpoint.json
        ├── report.md
        └── finish.json
```

Reglas:

- directorio nuevo, nunca sobrescrito;
- Creator escribe solo dentro de su generación;
- `generated/` queda inmutable durante `accept`;
- Host revalida todos los hashes justo antes de instalar;
- logs extensos por referencia;
- secretos nunca se escriben.

---

## 6. Contrato de `generation-manifest.json`

Campos mínimos:

```json
{
  "schema_version": 1,
  "generation_id": "opaque-id",
  "status": "GENERATED",
  "project": {
    "name": "MiProyecto",
    "root_identity": "sha256",
    "base_revision": "git-or-content-id"
  },
  "creator": {
    "session_ref": "observed-session",
    "runtime_version": "observed-version"
  },
  "framework": {
    "revision": "commit",
    "templates_revision": "commit"
  },
  "artifacts": [
    {
      "path": "skills/MiProyecto-auditor/SKILL.md",
      "type": "skill-entrypoint",
      "sha256": "digest"
    }
  ],
  "required_capabilities": [],
  "forbidden_capabilities": [],
  "effective_routing_digest": "digest",
  "context_policy": {
    "skill_entrypoint_max_bytes": 32768,
    "support_file_max_bytes": 24576,
    "warning_ratio": 0.9,
    "hot_paths": {}
  },
  "license_provenance": []
}
```

Creator solo puede emitir `GENERATED`. `ACCEPTED`, `RETAINED`, `ACTIVE` y `ROLLED_BACK` los emite el Host.

El manifest cubre todos los archivos. Archivo no manifestado, hash incorrecto, symlink, path traversal o tipo especial causan rechazo antes de cualquier backup/instalación.

---

## 7. Flujo detallado del bootstrap

### B0 — preflight local

- validar argumentos/rutas;
- comprobar que proyecto/framework/workspace no se solapan;
- comprobar DSH y Creator;
- obtener versión/capabilities/routing efectivos;
- comprobar proveedor/modelo utilizable sin abrir credenciales;
- verificar canal local de autenticación DSH;
- fijar presupuesto, timeout y datos permitidos;
- crear `started.json` y reservar presupuesto.

### B1 — descubrimiento mecánico

- Git/identidad/revisión;
- instrucciones y manifiestos;
- lenguajes/toolchains;
- roots/exclusiones preliminares;
- tests/builds detectables, no ejecutados;
- configuración/skills/modes existentes;
- conflicts y precedencia del loader;
- perfil mínimo.

### B2 — skills generales

- copiar/enlazar skills generales al workspace con manifest gestionado;
- idénticas: idempotentes;
- conflicto ajeno: `RETAINED`;
- no instalar modos finales;
- verificar carga nativa de las skills generales necesarias para Creator.

### B3 — paquete y llamada a Creator

- crear `generation-request.json` y prompt versionado;
- abrir/reutilizar Host DSH autorizado;
- derivar cookie/token local en memoria;
- crear sesión Creator con cwd correcto;
- enviar prompt automáticamente;
- supervisar turno, presupuesto y timeout;
- exigir `generation-manifest.json` y `finish.json`;
- Creator ejecuta `bootstrap.py accept` al terminar.

### B4 — `accept` invocado por Creator

El comando recibe workspace + generated o generation-id. No recibe autoridad desde el manifest.

Creator puede corregir errores mecánicos dentro del límite de intentos, pero no puede:

- modificar `bootstrap.py`/validadores;
- instalar directamente;
- cambiar capabilities/routing;
- escribir en destinos activos;
- marcarse aceptado.

### B5 — validación Host

1. Schema/versiones.
2. Identidad proyecto/base/framework.
3. Manifest exhaustivo, hashes y archivos regulares.
4. Rutas contenidas en `generated/`.
5. Plugins/tools/modelos dentro de allowlist efectiva.
6. Routing idéntico al snapshot permitido.
7. Roots mínimos; Auditor sin escritura de producto.
8. Reparación solo en candidato/rama.
9. Roles/sesiones observables.
10. Presupuesto, timeout, dos intentos.
11. Skills/frontmatter/referencias/grafo/hot paths.
12. Portabilidad y ausencia de rutas del mantenedor.
13. Scripts/helpers: imports, red, subprocess, writes, instalación.
14. Colisiones/precedencia y ownership.
15. Licencias/procedencia.

Todo rechazo ocurre antes de tocar destinos activos.

---

## 8. Progressive disclosure y estructura de skills

Se adopta de `jsmastery-pro/skills` el patrón, no su flujo ni sus nueve skills:

```text
<Project>-auditor/
├── SKILL.md
├── modes/
│   ├── full.md
│   ├── area.md
│   └── follow-up.md
├── internal/
│   ├── evidence-policy.md
│   ├── completion.md
│   └── recovery.md
├── references/
│   ├── project-context.md
│   ├── acceptance-contract.md
│   └── domain-contracts.md
├── templates/
└── adapters/
```

`SKILL.md` es un router pequeño. Carga únicamente la rama pertinente. El manifest declara el grafo y hot paths. El Host valida:

- referencias existentes;
- cero archivos huérfanos salvo declarados `asset`;
- no ciclos de carga;
- presupuesto por archivo;
- presupuesto agregado por hot path;
- contratos duplicados idénticos o generados desde fuente canónica;
- adapters opcionales y no autoritativos.

Valores iniciales propuestos (configurables): 32 KiB entrypoint, 24 KiB soporte, warning 90%. Deben medirse y ajustarse; no son garantía de calidad.

No se adopta:

- `/scope→/audit→/architect→...`;
- `npx skills@latest`;
- obligación universal de `agents/openai.yaml`;
- reglas editoriales ajenas sin relación funcional;
- herramientas/nombres de proveedor como contrato universal;
- score único basado en tokens.

---

## 9. Creación y mejora de skills específicas

Creator solo crea/mejora una skill si el perfil no basta y existe necesidad recurrente observada.

Cada propuesta declara:

- motivo y evidencia;
- dominio/unidades donde aplica;
- entradas/salidas;
- capabilities mínimas;
- herramientas prohibidas;
- archivos y hot paths;
- prueba de carga;
- prueba de conducta;
- procedencia/licencia;
- relación con skill previa si es reemplazo.

### 9.1 Backup obligatorio

Antes de sustituir una skill gestionada:

```text
detectar cambio
→ backup completo externo
→ hashes del backup
→ backup-verification.json
→ staging del conjunto nuevo
→ smoke + aceptación
→ activar o rollback
```

Reglas:

- idéntica: no escribir ni backup innecesario;
- nueva: creación exclusiva;
- gestionada y modificada: backup obligatorio antes de tocar destino;
- ajena/no gestionada: conflicto `RETAINED`;
- fallo de backup: no instalar;
- fallo posterior: restaurar backup y verificar;
- rollback no verificable: `RECOVERY_REQUIRED`;
- nunca borrar backup durante el mismo paso de instalación;
- política de retención/limpieza separada.

El backup cubre la carpeta completa y archivos auxiliares, no solo `SKILL.md`.

---

## 10. Instalación transaccional

La unidad de activación es el conjunto de dos modos + skills específicas + adapters + manifest. No se activan componentes por separado.

Secuencia:

1. Validación completa en staging inmutable.
2. Plan de cambios y collisions.
3. Backup y verificación.
4. Construcción de árbol candidato hermano.
5. Descubrimiento/carga contra el árbol candidato.
6. Smoke mecánico.
7. Aceptación funcional.
8. Swap atómico del puntero/directorio gestionado.
9. Revalidación desde sesión nueva.
10. Manifest activo + install receipt.
11. Si falla: rollback conjunto y verificación.

Nunca debe quedar Auditor nuevo con Reparación anterior o skills mezcladas.

---

## 11. Aceptación automática generada, no diseñada por el usuario

Creator produce `acceptance-plan.json`, pero el framework impone criterios mínimos congelados. `accept` valida que existan y ejecuta automáticamente vía DSH local:

1. Descubrimiento de ambos modos.
2. Carga exacta de skills y origen esperado.
3. Lectura dirigida de unidad fixture.
4. Evidencia fuera del producto.
5. Auditor bloqueado para modificar producto.
6. Reparación en candidato controlado.
7. Rojo→verde real.
8. QA por sesión/actor observable.
9. Reauditoría semántica posterior.
10. Presupuesto/checkpoint/reapertura.
11. Instalación/rollback/desinstalación controlada.
12. Ausencia de cambios en producto/routing/config global.

Creator invoca `accept`, pero el Host ejecuta/verifica el plan. Creator no escribe los resultados. Si falta aprobación nativa que solo puede dar el titular, el bootstrap pausa con una instrucción compacta, preserva checkpoint y reanuda tras la decisión; no elude la UI.

Estados:

```text
GENERATED → VALIDATING → BACKED_UP → STAGED
→ ACCEPTING → ACTIVE
                  └→ RETAINED → ROLLED_BACK
                                 └→ RECOVERY_REQUIRED (si rollback no verificable)
```

---

## 12. Actualización/regeneración

```bash
python3 -B scripts/bootstrap.py update --project /ruta/proyecto
```

Disparadores:

- cambio material de arquitectura/lenguaje/repos;
- nuevas fronteras de datos/hardware;
- actualización de framework/DSH;
- modo/skill obsoleto;
- generación rechazada.

La generación activa permanece en servicio mientras se crea/valida la nueva. Solo se conmuta tras aceptación. Las decisiones materiales conservan historial y reemplazos mediante `decisions.py`.

---

## 13. Desinstalación y datos

```bash
bootstrap.py uninstall --project /ruta/proyecto
```

Retira únicamente:

- modos gestionados;
- skills/enlaces gestionados;
- plugin bindings gestionados;
- manifest activo e instalación;
- referencias propias.

Conserva producto, configuración ajena, recibos, candidatos, informes, archivos y backups.

```bash
bootstrap.py purge-data --project /ruta/proyecto
```

Es destructivo, requiere confirmación explícita, muestra rutas exactas y nunca sigue enlaces.

---

## 14. Seguridad y supply chain

- No usar `npx ...@latest` ni ejecutar instaladores remotos durante `accept`.
- Versiones/orígenes/digests fijados.
- Adquisición host-side separada de ejecución no confiable.
- Rechazar symlinks, hardlinks inesperados, dispositivos y sockets.
- Protección TOCTOU: hashes justo antes del swap, fuente inmutable, revalidación.
- Scripts generados no se ejecutan por existir; requieren allowlist y revisión.
- `allowed-tools`/frontmatter no concede herramientas; Host aplica capabilities.
- Snapshot routing antes/después; nuevos providers/modelos/aliases se rechazan.
- Proyecto privado: fragmentos enviados a inferencia se rigen por permiso de datos.
- Inputs/outputs del modelo son datos no confiables.
- Límites de archivos, manifest, requests, tokens, tiempo e intentos.

---

## 15. Licencias y procedencia

El repositorio `jsmastery-pro/skills` observado es MIT. Si se copia/adapta código o texto sustancial:

- conservar aviso MIT en `THIRD_PARTY_NOTICES.md`;
- indicar archivos derivados;
- cabecera de procedencia cuando aplique;
- registrar commit fuente en `license_provenance`.

Si solo se adoptan ideas/patrones, documentar inspiración y mantener implementación propia. Antes de publicación pública debe decidirse la licencia del framework y comprobar compatibilidad.

---

## 16. Plan de implementación de la candidata

### C0 — contratos y fixtures

- schema generation/project/capabilities/modes/skills;
- fixture mínimo válido/inválido;
- Syncify/RehabWeb saneados;
- golden manifest;
- tests de paths/hashes/capabilities/licencia.

**Gate:** validar un paquete fixture completo sin tocar DSH ni destinos activos.

### C1 — `bootstrap install`

- preflight DSH/proveedor/Creator;
- workspace/generation-id;
- skills generales;
- perfil/discovery mecánico;
- paquete/prompt Creator;
- checkpoint/reanudación.

**Gate:** desde clone limpio, preparar una generación sin modificar producto/config global.

### C2 — automatización DSH Creator

- cliente local autenticado;
- sesión Creator;
- prompt automático;
- streaming/timeout/presupuesto;
- manifest/finish obligatorio;
- cero secretos persistidos.

**Gate:** Creator fixture genera paquete válido desde un comando.

### C3 — validador generado

Adaptar patrones de `check-portability.mjs`:

- frontmatter/nombres/descripciones;
- tamaños/hot paths;
- referencias/grafo;
- portabilidad;
- contracts;
- capabilities/routing;
- scripts/seguridad;
- manifest exhaustivo;
- procedencia/licencia.

**Gate:** corpus positivo/negativo, fail-closed sin escrituras.

### C4 — backups y transacción

- ownership manifest;
- backup completo/verificado;
- staging del conjunto;
- swap/rollback;
- fallos inyectados en cada transición;
- uninstall conservador.

**Gate:** crash/errores no dejan conjunto mixto; estado anterior restaurable.

### C5 — aceptación DSH automática

- acceptance plan schema;
- dos modos específicos fixture;
- carga/lectura/escritura externa;
- repair/QA/reaudit;
- plugin/capabilities/routing;
- reanudación;
- rollback.

**Gate:** `install` de un comando produce modos ACTIVE o RETAINED con rollback íntegro.

### C6 — piloto clean-room

Proyectos nuevos no usados durante implementación:

- uno Python/backend;
- uno JS/Rust/UI o equivalente multiparte;
- usuario sin contexto privado;
- proveedor DSH ya configurado;
- contar intervenciones y troubleshooting;
- update y uninstall completos.

**Gate:** usuario ejecuta un comando, recibe modos específicos útiles y opera con mensajes cortos.

### C7 — promoción

- reconciliar resultados;
- corregir arquitectura vigente en su mismo archivo;
- reemplazar `creator-preset-spec.md` por contrato generacional;
- actualizar START/README/usage/setup/status/plan/changelog;
- tag de piloto;
- conservar esta candidata como antecedente o eliminarla tras promoción (historial queda en Git).

---

## 17. Matriz de aceptación de la candidata

| Gate | Evidencia necesaria |
|---|---|
| Un comando | clone + provider preconfigurado + `bootstrap install` |
| Creator automático | sesión/turno observado sin prompt manual |
| Específico del proyecto | modos/nombres/skills/criterios derivados del proyecto |
| No autoaprobación | Creator solo GENERATED; Host emite estados |
| Backup | cada reemplazo tiene backup completo verificado previo |
| Transacción | conjunto viejo o nuevo, nunca mezcla |
| Progressive disclosure | grafo/hot paths válidos y presupuestados |
| Seguridad | capabilities/routing/roots fail-closed |
| Aceptación | read/evidence/repair/QA/reaudit/reopen reales |
| Rollback | fallo inyectado restaura estado anterior |
| Idempotencia | reinstall/update/uninstall repetibles |
| Portabilidad | cero rutas/identidades del mantenedor |
| Datos | permisos/proveedor/sensibilidad registrados |
| UX | usuario no copia prompts, JSON, recibos ni diseña pruebas |

---

## 18. Transición desde el MVP anterior

Durante la implementación C0–C7:

- Este archivo es la referencia normativa única.
- `docs/creator-preset-spec.md` sigue describiendo el experimento anterior de un preset neutral, no el contrato final propuesto.
- `START.md`/`usage.md` siguen operando el MVP actual mediante skills y modos ya preparados.
- El diseño no acredita que bootstrap, Creator o instalación ya estén implementados.
- Las discrepancias son deliberadas y forman parte de la prueba de la candidata.

Al completar C0–C7:

1. actualizar la arquitectura vigente, no mantener dos normas;
2. convertir este plan en antecedente histórico;
3. actualizar el índice de implementación con etapas C0–C7;
4. retirar la noción de presets genéricos operativos del flujo final;
5. conservar los presets actuales solo como fixtures de regresión.

---

## 19. Preguntas que la implementación debe resolver antes del piloto

1. ¿Creator puede invocar `accept` y recibir errores estructurados sin necesitar shell libre?
2. ¿La API local DSH permite todo el ciclo sin token manual y sin filtrar secretos?
3. ¿Cuál es la unidad de swap más portable para modos+skills (directorio, manifest/puntero o user preset root)?
4. ¿Cómo se representa un fork QA recuperable cuando el runtime no expone session ID?
5. ¿Los límites iniciales 32/24 KiB y hot paths predicen realmente el coste en DSH?
6. ¿Qué adapters requiere DSH y cuáles son opcionales para otros hosts?
7. ¿Qué campos de proyecto deben ser decisiones humanas, no inferidas?
8. ¿Qué aprobación nativa mínima puede quedar en un flujo de «un comando»?
9. ¿Cómo se distribuye el plugin `workflow-write` de forma portable sin rutas absolutas?
10. ¿Qué licencia tendrá el framework antes del piloto público?

---

## 20. Resultado esperado de la arquitectura

```text
usuario configura DSH/proveedor una vez
→ clona framework
→ ejecuta bootstrap install
→ bootstrap prepara workspace y llama Creator
→ Creator analiza proyecto y genera candidato específico
→ Creator invoca accept
→ Host valida schema/capabilities/routing/skills
→ backup obligatorio de lo reemplazado
→ instalación transaccional en staging
→ aceptación automática DSH (repair+QA+reaudit)
→ ACTIVE o rollback/RETAINED
→ usuario opera con mensajes cortos
```

Este es el flujo que C0–C7 debe implementar y validar antes del piloto con usuarios reales.

---

## 21. Sistema interno de construcción de Creator inspirado en `jsmastery-pro/skills`

La evaluación profunda del repositorio externo corrige una lectura insuficiente: su valor no se limita a carpetas, progressive disclosure y validación de portabilidad. Las nueve skills forman una cadena de producción de artefactos y gates que puede adaptarse como **sistema interno de construcción de Creator**.

No se instalarán como modos finales ni se expondrán al usuario. Se transformarán en capacidades privadas de la sesión Creator:

```text
scope      → particionar capacidades y decidir qué debe existir
audit      → descubrir la realidad del proyecto
architect  → convertir evidencia en contratos de modos/skills
test       → derivar escenarios públicos y familias de holdouts
develop    → generar el candidato desde contratos completos
check      → verificar conducta y revisar independientemente
debug      → reparar una generación RETAINED sin tocar controles
document   → producir contexto durable y contratos trazables
sync       → detectar drift y proponer regeneración conservadora
```

Capacidades internas propuestas:

```text
creator-project-discovery
creator-project-documenter
creator-contract-and-risk-mapper
creator-capability-partitioner
creator-capability-designer
creator-scenario-author
creator-skill-generator
creator-generation-repair
creator-drift-analyzer
```

Estas capacidades componen una sola ejecución Creator. El usuario no las invoca ni las ve como presets.

### 21.1 Procedencia y límites de reutilización

Fuente observada:

```text
https://github.com/jsmastery-pro/skills
commit 43b69e44c9ca905fe3a3418ccdf4102255e20d40
licencia MIT
```

Se adoptan mecanismos y se reimplementan de forma neutral. Si se copia o traduce texto/código sustancial, se añade `THIRD_PARTY_NOTICES.md`, aviso MIT, archivos derivados y commit fuente. No se importan supuestos Claude/web/Node como contratos universales.

---

## 22. `scope` como particionador de capacidades

`scope` se adapta para responder qué debe generar Creator, no qué features debe construir el producto.

### 22.1 Mecanismos adoptados

- clasificación greenfield/brownfield/monorepo;
- separación entre inventario, unidad coherente, decisión y tarea;
- **invent test**: si una capacidad obligaría a inventar una decisión, se bloquea hasta diseño/decisión;
- mapa compacto con detalle por referencia;
- deduplicación y replanificación incremental;
- orden/dependencias;
- enfoques de corte:
  - Tracer Bullet como camino completo inicial;
  - Skateboard como conjunto mínimo utilizable;
  - Journey como experiencia Auditor→Repair completa;
  - Facade solo `PREVIEW_ONLY`, nunca activable.

### 22.2 Salida

```text
design/capability-plan.json
design/generation-strategy.json
design/rejected-candidates.json
```

`capability-plan.json` contiene dos modos obligatorios, skills compartidas/específicas, dependencias, orden de generación, nivel de riesgo y decisiones bloqueantes.

No se adoptan literalmente features, go-to-market, SEO ni tiers Prototype/Alpha/Beta/GA. Se sustituyen por impacto, profundidad, QA, evidencia, datos, escritura y publicación.

---

## 23. `audit` como motor de discovery de Creator

Se adaptan casi directamente `audit/modes/whole-repo.md`, `area.md`, `gapfill.md` y su disciplina de preflight/scouts compactos.

### 23.1 Principios

- primer barrido independiente antes de reconciliar documentación;
- separar global de área/workspace;
- no sobrescribir conocimiento humano;
- distinguir:
  - `OBSERVED`;
  - `DECLARED`;
  - `INFERRED`;
  - `PROPOSED`;
  - `UNVERIFIED`;
- taxonomía `GAPS`, `PROPOSED_ADDITIONS`, `CONTRADICTIONS`, `UNKNOWNS`, `EXCLUSIONS`;
- subagentes read-only por área, devolución estructurada y compacta;
- rutas/símbolos como localizadores, no prueba semántica.

### 23.2 Salidas

```text
discovery/project-classification.json
discovery/repository-map.json
discovery/workspaces.json
discovery/instructions-index.json
discovery/commands.json
discovery/data-boundaries.json
discovery/observed-capabilities.json
discovery/contract-map.json
discovery/authority-map.json
discovery/risk-map.json
discovery/coverage-plan.json
discovery/contradictions.json
discovery/unknowns.json
discovery/exclusions.json
discovery/evidence-index.json
discovery/areas/<area>.json
```

Cada claim conserva fuente, hash, ubicación, estado, confianza y limitaciones.

### 23.3 Tool/skill discovery

`audit/modes/tool-skills.md` se usa solo como patrón para inventariar:

- skills instaladas;
- procedimientos cubiertos;
- procedimientos recurrentes faltantes;
- candidatos a skill específica;
- candidatos rechazados;
- sugerencias externas opcionales.

Quedan prohibidos en bootstrap base: `npx skills find/add`, instalación automática, búsqueda web/MCP y conexión de servicios. Cualquier adquisición externa necesita misión y autorización separadas.

Los presets Clean/DDD/Functional/SOLID solo sirven como clasificadores si el proyecto los evidencia; nunca como opciones impuestas.

---

## 24. `architect` como diseñador de contratos

Se adaptan `internal/design-conversation.md`, `spec-template.md` y los modos architecture/feature/enhancement/cross-cutting.

### 24.1 Ledger de decisiones

Toda dimensión se clasifica:

```text
INFER      — fuente observada suficiente
ASK        — decisión exclusiva del titular
RECOMMEND  — Creator recomienda, titular/contrato decide
NOT_APPLICABLE — con motivo
UNRESOLVED — bloquea la generación afectada
```

Salida:

```text
discovery/question-ledger.json
design/decision-ledger.json
```

### 24.2 Contrato por modo/skill

Cada capacidad define:

- propósito y triggers positivos/negativos;
- inputs y fuentes;
- reads/writes;
- capabilities mínimas/prohibidas;
- invariantes y anti-goals;
- estados/transiciones;
- handoffs;
- fallos/concurrencia/retries/timeouts;
- migración/rollback;
- criterios `SR-N`;
- escenarios y stop conditions;
- evidencia;
- procedencia/licencia.

### 24.3 Value sourcing

Toda decisión/valor operativo debe nombrar fuente válida. Si falta raíz, comando, criterio, base, autorización o actor QA: `RETAINED`/`UNVERIFIED`, nunca inferencia silenciosa.

### 24.4 Modos architect adaptados

- architecture: fronteras bootstrap/Creator/Host/modos;
- feature: contrato de skill específica;
- enhancement: regeneración, migración y rollback de skill existente;
- cross-cutting: evidencia, errores, permisos, naming y contratos transversales.

El Host, no Creator, ratifica decisiones y estados.

---

## 25. `document` como productor de contexto durable

No se adopta como generador de changelogs. Se usa para normalizar evidencia en:

```text
project-manifest.json
instructions-index.json
references/
contracts/<skill-id>.contract.json
unknowns.json
conflicts.json
```

Reglas adoptadas:

- hechos reales/diff/código prevalecen sobre narración;
- no inventar resultados/causas/pruebas;
- afirmación trazable;
- repetición idempotente;
- no filtrar secretos;
- respetar formatos canónicos existentes;
- desconocido permanece desconocido.

`project-manifest` fija identidad/base/inventario/hashes/capabilities/autoridad. `instructions-index` indexa ruta, scope, precedencia, secciones, hashes, facts, constraints, unknowns y conflicts; no copia todo el contenido al hot path.

Templates externos inspiran forma, no prosa final. Se crean templates propios para contracts, references, acceptance y drift.

---

## 26. `test` como autor de escenarios y holdouts

Se adapta la trazabilidad `AC-N` a requisitos `SR-N`.

Creator genera escenarios públicos antes del candidato:

- positivos;
- negativos;
- límites;
- tool/capability denial;
- missing capability;
- prompt injection;
- ciclos;
- handoff inválido;
- base/candidato obsoleto;
- idempotencia;
- scope/write violations.

Salida:

```text
tests/public/scenarios.jsonl
tests/public/coverage-matrix.json
tests/holdout-spec.json
tests/immutable-digests.json
harness-profile.json
```

Creator solo diseña familias de holdout. El Host/evaluador independiente materializa casos concretos y oculta oráculos al generador/reparador. Un caso visto por Creator es fixture público, no holdout.

Los tests/rúbricas/thresholds/allowlists se montan read-only. El reparador no puede editarlos ni rebajar expectations/severity/coverage.

`NOT_COVERED` es estado explícito; no se fuerza automatización de criterios no observables.

---

## 27. `develop` como generador contractual

Se adapta el input/spec coverage gate:

Antes de escribir, para cada salida/decisión de la skill el contrato debe nombrar su fuente. Si falta: volver a discovery, pedir decisión o retener.

### 27.1 Ownership

Creator escribe solo en staging. No puede:

- promover;
- modificar aceptación/holdouts/Host/backups;
- escribir skills activas;
- cambiar routing/capabilities;
- marcar `ACCEPTED`.

### 27.2 Orden de generación

```text
contratos/protocolos/estados compartidos
→ routers y modos
→ skills específicas
→ references/templates
→ adapters
→ manifest/hashes
```

Se preservan versiones activas hasta promoción. Reanudación por hashes/estado; no regenerar artefactos aceptados; no eliminar versión anterior durante el build.

### 27.3 Salida staged

```text
generated/modes/
generated/skills/
generated/contracts/
generated/references/
generated/templates/
generated/adapters/
generated/generation-manifest.json
```

Self-check = `preflight`, nunca aceptación.

---

## 28. `check` como verificación y revisión independiente

Se separa:

```text
verify — ejecutar/observar con evidence ledger
review — inspección independiente read-only
```

### 28.1 Verify

Sin evidencia no hay PASS. Cada `SR-N` enlaza scenario/input/expected/evidence/verdict. Estados: PASS, FAIL, BLOCKED, NOT_COVERED, UNVERIFIED, IMPLEMENTED_NOT_APPLIED.

El evaluador no modifica contrato ni expectativas. Resultados append-only.

### 28.2 Review

Revisor distinto, read-only, prompt/corpus separados, sin self-assessment de Creator, sin outputs de holdout. Idealmente modelo/proveedor distinto cuando está autorizado. Si no hay aislamiento real: `DEGRADED_REVIEW`, no “independiente”.

Rúbrica adaptada:

- fidelidad contrato;
- trigger/routing;
- confinamiento;
- terminación;
- handoff;
- prompt injection;
- capability missing;
- aislamiento;
- evidencia;
- portabilidad;
- escritura;
- anti-autoaprobación.

El Host calcula veredicto; el revisor no acepta/promueve.

---

## 29. `debug` como reparador de una generación RETAINED

Ciclo adoptado:

```text
síntoma → reproducción → localización → hipótesis falsable
→ experimento mínimo → fix mínimo → revalidación → siblings
```

Input: `retention-bundle` inmutable con candidate digest, failing scenario IDs, observations, violated policies, evidence refs, allowed edit paths, immutable controls, attempt y budget.

El reparador solo modifica candidato staged/instrumentación scratch. No modifica tests/holdouts/rúbrica/thresholds/capabilities/allowlists/Host/acceptance. Máximo de intentos, archivos y diff; repetición sin progreso retiene. Holdout expuesto deja de ser secreto y Host genera otro.

Transición prohibida:

```text
REPAIRING → ACCEPTED
```

Debe volver siempre a evaluación Host.

---

## 30. `sync` como detector de drift/regeneración conservadora

Compara:

1. base del proyecto usada;
2. contrato normalizado;
3. generación aceptada;
4. skill/modo instalado actual;
5. proyecto actual.

Estados:

```text
CURRENT
SOURCE_DRIFT
NON_GOVERNING_CHANGE
LOCAL_SKILL_EDIT
CONTRACT_DRIFT
ORPHANED
AMBIGUOUS_SCOPE
STALE_REFERENCE
UNVERIFIED
```

Default: no hacer nada. Solo cambios en procedimiento durable, comando, restricción, interfaz o contrato justifican regeneración.

Reglas:

- fuentes declaradas por skill;
- candidato nuevo, nunca overwrite activo;
- local edit bloquea reemplazo automático;
- sin merge heurístico de instrucciones;
- removals más estrictos;
- conflictos como artefactos;
- segunda ejecución misma base = no-op;
- cambio de base invalida aceptación salvo irrelevancia demostrada.

Salida:

```text
drift/source-drift.json
drift/installed-drift.json
drift/update-plan.json
```

`sync` propone; `accept` evalúa; instalación autorizada reemplaza.

---

## 31. Pipeline Creator definitivo ampliado

```text
Host bootstrap/snapshot/authority
→ creator-project-discovery (audit)
→ creator-project-documenter (document)
→ creator-contract-and-risk-mapper (audit+architect)
→ creator-capability-partitioner (scope)
→ creator-capability-designer (architect)
→ creator-scenario-author (test)
→ Host materializa/sella holdouts
→ creator-skill-generator (develop)
→ Creator preflight/self-review
→ Creator invoca bootstrap accept
→ Host static/schema/graph/portability checks
→ Host check verify (public + holdouts)
→ Host check review (independiente)
→ ACCEPTED o RETAINED
→ creator-generation-repair (debug) si RETAINED
→ backup verificado
→ promoción transaccional
→ post-promotion smoke
→ creator-drift-analyzer (sync) en updates
```

Creator genera y solicita aceptación; Host decide/promueve.

---

## 32. `creator-runs` ampliado

```text
creator-runs/<generation-id>/
├── run.json
├── inputs/
│   ├── bootstrap-request.json
│   ├── snapshot.json
│   ├── inventory.json
│   ├── authority.json
│   ├── host-policy.json
│   ├── runtime-capabilities.json
│   └── effective-routing.json
├── discovery/
│   ├── project-manifest.json
│   ├── instructions-index.json
│   ├── repository-map.json
│   ├── workspaces.json
│   ├── contract-map.json
│   ├── authority-map.json
│   ├── risk-map.json
│   ├── coverage-plan.json
│   ├── contradictions.json
│   ├── unknowns.json
│   ├── exclusions.json
│   ├── decision-gaps.json
│   └── areas/
├── design/
│   ├── generation-strategy.json
│   ├── capability-plan.json
│   ├── decision-ledger.json
│   ├── skill-contracts/
│   ├── mode-contracts/
│   ├── handoff-schemas/
│   ├── reuse-map.json
│   └── rejected-candidates.json
├── tests/
│   ├── public/scenarios.jsonl
│   ├── public/coverage-matrix.json
│   ├── holdout-spec.json
│   ├── immutable-digests.json
│   └── harness-profile.json
├── generated/
│   ├── generation-manifest.json
│   ├── candidate-manifest.json
│   ├── modes/
│   ├── skills/
│   ├── contracts/
│   ├── references/
│   ├── templates/
│   └── adapters/
├── validation/
│   ├── schema.json
│   ├── graph.json
│   ├── portability.json
│   ├── context-budget.json
│   └── creator-self-review.json
├── acceptance/
│   ├── request.json
│   ├── host-static-results.json
│   ├── public-results.json
│   ├── holdout-results.json
│   ├── independent-review.json
│   ├── evidence-ledger.jsonl
│   └── host-verdict.json
├── retained/attempt-N/
│   ├── retention-bundle.json
│   ├── root-cause.json
│   ├── repair-diff.patch
│   └── rerun-results.json
├── backup/
│   ├── previous-manifest.json
│   ├── previous-skills/
│   ├── hashes.json
│   └── restore-plan.json
├── promotion/
│   ├── promotion-plan.json
│   ├── acceptance-record.json
│   ├── post-promotion-smoke.json
│   └── rollback-record.json
├── checkpoint.json
├── report.md
└── finish.json
```

---

## 33. Handoffs y prevención de ciclos

Cada handoff contiene type, schemaVersion, runId, candidateDigest, sourceActor, targetActor, reason, evidenceRefs, allowedNextActions, attempt y parentEventId.

Tipos:

```text
creator.generation.complete
bootstrap.accept.request
host.accepted
host.retained
repair.complete
repair.blocked
host.rejected
```

Controles:

- máquina de estados Host;
- transiciones allowlisted;
- actor no se invoca a sí mismo;
- accept una vez por digest;
- reparación exige digest nuevo;
- límites de intentos/tiempo/tokens/diff;
- findings repetidos sin progreso → retained;
- idempotency key;
- terminal no reabre sin run nuevo;
- repair nunca acepta;
- pruebas de no ciclo y privilegios.

---

## 34. Contexto, hot paths y métricas

Principios adoptados de conventions/check-portability/analyze-token-usage:

- cada línea cargada debe cambiar conducta;
- contenido largo/raro fuera de entrypoint;
- referencia lazy con trigger explícito;
- instrucciones comunes, seguridad y acceptance inline;
- grafo de carga validado;
- presupuestos por archivo y hot path;
- warnings 90%; presupuestos ratchet, no subir automáticamente;
- medir fresh input, cache write/read y output por hilo/subagente;
- optimizar primero output/input fresco, no cache barata;
- retornos de scouts compactos, no dumps.

`context-budget-report.json` registra always-loaded, hot paths, bytes/tokens, observed runs y recomendaciones. Métricas no equivalen a calidad.

---

## 35. Controles Host anti-autoaprobación

1. Identidades separadas Creator/evaluator/reviewer/repairer/Host.
2. Staging aislado; Creator no escribe activo.
3. Contratos/tests sellados por hash.
4. Holdouts ocultos y frescos tras exposición.
5. Evaluadores read-only con salida append-only.
6. Veredicto mecánico Host.
7. Self-assessment solo informativo.
8. Reparador sin acceso de escritura a controles.
9. Comparar escenarios/expectativas/severity/permissions antes/después.
10. Presupuesto de ciclos/diff/findings.
11. Backup previo y promoción transaccional.
12. Acceptance ligada a digest exacto.
13. Capability missing → BLOCKED/DEGRADED, no PASS.
14. Registro append-only.
15. Pruebas no-cycle/self-invocation.
16. Pruebas de privilegios/paths/tools.
17. Prompt-injection fixtures del proyecto.
18. Post-promotion smoke en ubicación real.
19. No instalación/adquisición externa durante evaluación.
20. Creator no puede modificar validator/Host/routing.

---

## 36. Qué se adopta, adapta y rechaza del repositorio externo

### Adoptar casi directamente

- scope invent test;
- audit whole-repo/area scan;
- gaps/proposed/contradictions;
- INFER/ASK/RECOMMEND;
- completeness gate/value sourcing;
- state models;
- producer/consumer tracing;
- migration/rollback;
- requisito→escenario→evidencia;
- independent read-only critique;
- progressive disclosure de un modo;
- durable artifacts;
- spec/input coverage gate;
- artifact ownership;
- no evidence/no PASS;
- NOT_COVERED;
- root-cause loop con una hipótesis;
- idempotencia y update quirúrgico;
- hot-path budgets y métricas fresh/cache/output.

### Adaptar

- feature specs → skill/mode contracts;
- AC-N → SR-N;
- verify.md → scenario manifest;
- test-preferences → harness profile;
- Git diff → candidate manifest;
- workflow tiers → riesgo/gates;
- AGENTS context → project-manifest/instructions-index;
- other model → reviewer realmente aislado;
- sync edits → drift plan/candidate regeneration;
- Assumed → RETAINED_NEEDS_RATIFICATION;
- adapters OpenAI → renderers desde modelo neutral.

### Rechazar

- las nueve skills como modos finales;
- slash workflow literal;
- npx skills/MCP auto-install;
- CLAUDE.md/AskUserQuestion/modelos Claude;
- web/UI dimensions universales;
- presets Clean/DDD/SOLID sin evidencia;
- Git obligatorio/push desde Creator;
- self-check como aceptación;
- evaluator que modifica criterios;
- repair que modifica tests/holdouts;
- auto-promoción/done por generador;
- adapters como lógica canónica;
- score único de tokens;
- reglas editoriales sin función;
- copiar material MIT sin atribución.

---

## 37. Riesgos adicionales de generar skills desde auditorías

- autojustificación: separar OBSERVED/INFERRED/DECIDED/PROPOSED;
- anclaje en docs: barrido independiente primero;
- cobertura falsa: inventario/partición Host;
- rutas frágiles: perfil para datos variables;
- skills genéricas renombradas: prueba de especialización;
- bugs como convenciones: frecuencia no es validez;
- mismo modelo autor/revisor: no alegar independencia;
- permisos por texto: solo capabilities Host;
- supply-chain: sin búsquedas/instalación automática;
- optimizar para validador: anti-placeholders + negativos;
- regeneración borra edits humanos: diff/ownership/backup;
- drift falso: default no-op, solo cambio durable;
- acceptance base obsoleta: ligar project/candidate digest;
- calidad ≠ autorización/instalación;
- no determinismo: misma base con output distinto → CONTRACT_DRIFT.

---

## 38. Modificación de las fases C0–C7

Las fases de §16 se amplían obligatoriamente:

- C0: schemas también para discovery/design/tests/handoffs/drift.
- C1: bootstrap instala capacidades internas Creator y genera run.
- C2: Creator ejecuta pipeline §31, no un único prompt monolítico.
- C3: validador incluye contracts, graph, hot paths, anti-autoaprobación y procedencia.
- C4: backup/transacción preserva edición local y estado generacional completo.
- C5: acceptance separa public fixtures, holdouts Host y review independiente; debug RETAINED.
- C6: pilotos prueban generación inicial, RETAINED+repair, update por drift, local skill edit, rollback y uninstall.
- C7: promoción reemplaza arquitectura/creator spec y añade THIRD_PARTY_NOTICES si aplica.

Ninguna fase puede declararse completa solo por schema o archivos generados; debe demostrar conducta y fronteras Host.

---

## 39. Resultado de arquitectura candidata revisada

La candidata completa deberá expresar:

```text
usuario configura DSH/proveedor
→ bootstrap crea run/snapshot/authority
→ audit descubre realidad
→ document normaliza contexto/contratos
→ scope particiona capacidades
→ architect diseña modos/skills
→ test deriva escenarios; Host sella holdouts
→ develop genera candidato staged
→ Creator preflight e invoca accept
→ Host check verify + review
→ ACCEPTED o RETAINED
→ debug repara RETAINED dentro de límites
→ backup y promoción transaccional
→ sync detecta drift y prepara regeneración futura
→ usuario opera modos específicos con mensajes cortos
```

Este sistema usa la profundidad real de las nueve skills como maquinaria interna de Creator sin convertirlas en presets genéricos, sin entregarles autoridad Host y sin adoptar sus dependencias de Claude/web/Git.
