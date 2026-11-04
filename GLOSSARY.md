# Improvement

Framework determinista de auditoría, reparación continua, implementación acotada y sincronización documental que opera sobre DeepSeek Harness (DSH) y el ejecutor de planes `workflow.py`.

## Language

### Roles y Fronteras de Confianza

**Host**:
El motor mecánico y determinista del framework (`scripts/`) que posee la autoridad exclusiva sobre validaciones, veredictos (`ACTIVE`, `RETAINED`), aprovisionamiento de candidatas sombra, cálculo de deriva y actualización de líneas base (`re-pin`).
_Avoid_: Orchestrator LLM, Agent Manager

**Harness**:
El runtime de ejecución subyacente (DeepSeek Harness `@deepseek-ai/dsh` montado con plugins Cordis en `scripts/dsh-plugins/`, o el ejecutor determinista `scripts/workflow.py`) que intercepta eventos de herramientas, aplica confinamiento de sandbox y dispara la verificación y sincronización documental sin depender de la iniciativa del agente.
_Avoid_: Wrapper, Prompt Runner

**Shadow Candidate**:
Repositorio Git autónomo aprovisionado por el Host dentro de `<workspace>/candidates/` donde un modo o tarea de sincronización documental realiza cambios aislados mientras el árbol del producto permanece en solo lectura (`EROFS`).
_Avoid_: Sibling Worktree, Direct Product Edit

### Detección de Deriva y Sincronización Documental (Doc Drift & Rot)

**Baseline Manifest**:
Artefacto gestionado por el Host en `<workspace>/drift/doc-baseline.json` que almacena el mapeo entre documentos y símbolos/archivos del producto junto con sus hashes de contrato (`contract_hash`), firmas estructurales de cuerpo (`body_lsh`), umbrales (`thresholds`) y revisión Git base.
_Avoid_: Inline Frontmatter State, Canonical Tree Manifest

**Contract Hash**:
Digest SHA-256 calculado exclusivamente sobre la secuencia normalizada de tokens de la firma pública exportada de un símbolo (nombre, parámetros, tipos, retorno y visibilidad), excluyendo comentarios, docstrings, espacios en blanco y cuerpos de implementación.
_Avoid_: File SHA-256, Raw Hash

**Body LSH**:
Firma determinista de similitud estructural (MinHash de 64 componentes sobre 3-shingles de tokens semánticos del cuerpo de una función o método) usada para cuantificar la proporción de cambio interno respecto a la versión documentada sin almacenar el código fuente completo.
_Avoid_: Line Diff Count, Git Numstat

**Contract Drift (`CONTRACT_DRIFT`)**:
Estado de invalidación inmediata en `drift/source-drift.json` que ocurre cuando el `Contract Hash` de un símbolo público vinculado difiere del registrado en el `Baseline Manifest` o cuando el símbolo exportado es eliminado.
_Avoid_: Stale Contract Broken

**Stale Reference (`STALE_REFERENCE`)**:
Estado de invalidación inmediata cuando un documento cita una ruta relativa de archivo, bloque de código anclado (`type-equiv` / `public-api`) o identificador de símbolo que ya no resuelve en el árbol del producto.
_Avoid_: Broken Link Warning

**Source Drift (`SOURCE_DRIFT`)**:
Estado de alerta conductual cuando el `Contract Hash` permanece intacto, pero el churn normalizado de tokens semánticos del cuerpo (`body_churn_ratio`), la divergencia de `Body LSH` o la entropía de Shannon (H(P)) entre archivos del subsistema superan los umbrales configurados.
_Avoid_: Possible Behavior Drift

**Non-Governing Change (`NON_GOVERNING_CHANGE`)**:
Modificación en el código fuente (como refactorizaciones en funciones privadas o ajustes internos de cuerpo por debajo de los umbrales de churn y entropía) que cambia el commit `HEAD` pero no invalida contratos ni requiere regenerar modos ni reescribir prosa documental; el Harness ejecuta un `re-pin` silencioso de la base.
_Avoid_: Ignored Commit

**Current (`CURRENT`)**:
Estado con delta semántico cero (cambios exclusivos de espacios en blanco, formateo de linter o corrección de comentarios/docstrings no gobernantes).
_Avoid_: Unchanged File

**Doc Drift Plugin (`doc-drift.mjs`)**:
Plugin Cordis de primer nivel montado en el Harness (`scripts/dsh-plugins/doc-drift.mjs` vía `cordis-patch.yml`) que observa mutaciones en la sesión, ejecuta `scripts/drift.py` al cierre del turno (`agent/turn-stopping` y gates de `workflow_write`), realiza `re-pin` silencioso ante `CURRENT`/`NON_GOVERNING_CHANGE` y, cuando detecta `CONTRACT_DRIFT`, `STALE_REFERENCE` o `SOURCE_DRIFT`, despacha una **propuesta** de sincronización documental acotada — una tarea en el workspace, nunca un reemplazo por sí solo: `sync` propone, `accept` evalúa y solo la instalación autorizada reemplaza.
