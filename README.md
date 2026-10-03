# Improvement

[![Licencia: Apache-2.0](https://img.shields.io/badge/licencia-Apache--2.0-blue)](LICENSE) [![Estado: beta](https://img.shields.io/badge/estado-beta-orange)](docs/plans/10-lanzamiento-publico.md)

**Un auditor y un reparador que viven junto a tu repositorio: encuentran los defectos
reales, los arreglan verificándolo con tus propias pruebas y dejan el commit y el push en
tus manos.**

Si mantienes un proyecto vivo, esto te suena: la misma clase de bug vuelve cada pocas
semanas, auditar a fondo se queda siempre para mañana y el porqué de cada arreglo vive en
la cabeza de quien lo hizo. Improvement convierte esa rutina en un ciclo con memoria: le
hablas con prompts de una línea, el framework hace el trabajo pesado y tú decides qué se
integra.

Al instalarlo, genera **dos modos hechos a la medida de tu proyecto**. El **auditor**
examina el código y registra cada hallazgo con su evidencia (`archivo:línea`) y su
severidad. El **reparador** corrige en un worktree aislado, verifica cada arreglo contra
los comandos reales de tu proyecto y deja tu árbol intacto. Nada llega a tu rama sin pasar
por ti.

Es un framework probado en tres campañas completas sobre repositorios reales: Syncify
(una app de música en Rust/Tauri/Vue), RehabWeb (una app clínica en Django/Vue) y LoboApp
(una app Flutter, con el framework instalado desde un clon de GitHub). Las métricas de
abajo son de esas campañas, no promesas.

## Inicio rápido

### ¿Qué es DSH?

Improvement no trae su propia IA: trabaja sobre **DSH (DeepSeek Harness)**, un runtime
local de agentes que instalas y configuras **una sola vez**. DSH es la aplicación donde
viven los dos modos generados, donde hablas con ellos y donde están tus credenciales de
proveedor. Improvement nunca lee ni pide tus API keys: solo comprueba que el proveedor
que configuraste existe.

### Requisitos

Linux, `git` y Python 3, y [DSH](docs/setup-dsh.md) ya configurado con al menos un
proveedor/modelo tuyo. Nada más.

Clona el framework **junto a tu proyecto, nunca dentro**, y ejecuta un comando:

```bash
git clone https://github.com/MadManJohnSmith/Improvement.git
cd Improvement
python3 -B scripts/bootstrap.py install \
  --project /ruta/a/tu/proyecto \
  --launch-dsh
```

Eso descubre tu proyecto, genera `<TuProyecto>-auditor` y `<TuProyecto>-continuous-repair`
con sus skills, valida el paquete en 10 capas, hace backup, instala y activa; si algo
falla, hace rollback dejando el estado recuperable. Tu producto no se toca durante la
instalación.

## El problema que resuelve

En proyectos de larga vida, la auditoría y la reparación se vuelven difíciles por tres
motivos: el contexto se llena, los errores vuelven a ocurrir porque nadie recuerda el
anterior, y cada arreglo se hace con criterio distinto. Improvement pone eso en una
estructura que sobrevive a los ciclos:

- un **auditor** que examina tu proyecto y persiste hallazgos con evidencia
  (`archivo:línea`), severidad y deduplicación por `(hallazgo, revisión)`;
- un **reparador** que toma los hallazgos, reclama una candidata de trabajo aislada en un
  worktree hermano, la corrige, verifica y **te deja el árbol de tu producto intacto**;
- una **memoria en disco** (`<proyecto>-workspace/mode-state`) con topes estrictos por
  fichero y por registro: crece hasta su límite y se compacta, no se satura;
- una **frontera de integración clara**: el modo deja el candidato verificado y tú haces
  el commit y el push. Nada llega a tu rama sin pasar por ti.

## Cómo se usa

### Prompts simples

Con los dos presets activos en DSH, operas con mensajes cortos:

| Quieres… | Escribes |
|---|---|
| Auditar todo | «Audita completamente este proyecto; no modifiques ni publiques.» |
| Auditar un área | «Audita este flujo, característica o componente.» |
| Reparar lo auditado | «Repara los hallazgos de la auditoría; no publiques.» |
| Reparar hallazgos concretos | «Repara A-SEC-01 y A-SEC-02; no publiques.» |

Cada auditoría deja un handoff con el siguiente prompt listo para copiar. Cuando el
reparador termina, integras con un `git merge --ff-only` normal: el commit y el push
siguen siendo tuyos.

![El ciclo operativo: auditar, reparar, integrar](docs/diagrams/ciclo-operativo.png)

*El ciclo completo. Es un diagrama explorable: cada relación se puede trazar y el tema
cambia claro/oscuro en la [versión interactiva](https://madmanjohnsmith.github.io/Improvement/diagrams/ciclo-operativo.html).*

## Los términos que verás

| Término | Qué es |
|---|---|
| DSH (DeepSeek Harness) | El runtime local de agentes donde viven los dos modos y tus credenciales de proveedor. |
| Modo | Cada uno de los dos agentes generados para tu proyecto: el auditor y el reparador. |
| Hallazgo | Un defecto registrado con evidencia (`archivo:línea`), severidad, causa y prevención. |
| Handoff | El registro que deja cada auditoría, con el siguiente prompt listo para copiar. |
| Candidata | El worktree hermano y aislado donde el reparador cambia código. |
| `mode-state` | La memoria en disco del workspace: hallazgos, handoffs, verificaciones y recibos. |
| Plan de capacidades | El inventario de los comandos reales de test y análisis de tu proyecto, firmado al instalar. |
| RETAINED | Un turno retenido: terminó con un resultado legible y sin salirse del contrato. |
| VERIFIED / RESOLVED | El trabajo verificado y los defectos cerrados, cada uno con su evidencia. |

## Verificación contra tu proyecto real, nunca con stubs

Al instalar, Improvement lee tu proyecto y escribe un **plan de capacidades** en
`<proyecto>-workspace/.dsh-managed/capability-plan.json`: qué tecnologías componen tu
proyecto (incluidos monorepos), cuál es **el comando de test y el de análisis propios de
cada una**, y si esta máquina tiene ya lo necesario para ejecutarlos.

Ese plan es la única evidencia que el reparador puede registrar. Un comando inventado, un
mock o una copia del código del producto son material de investigación, nunca un
resultado. Si el comando no puede ejecutarse porque falta una herramienta, el registro es
`BLOCKED` nombrando exactamente qué falta y cómo se instala; nunca un `PASS` inventado.

```
stacks:
  dart-flutter  listo  (/home/tu/usuario/.local/share/flutter/bin/flutter test)
  java-gradle   falta java   (instalar un JDK 17+ fuera del producto y anteponerlo al PATH)
```

Un detalle que la beta destapó por las malas: si la herramienta está instalada pero fuera
del `PATH` por defecto, el plan la nombra **por su ruta absoluta**. Un nombre suelto que
la shell del modo no puede invocar convierte una suite que funciona en un `BLOCKED` falso.

## Casos reales

### Syncify: de la CI en rojo a la CI verde

App de música (Rust/Tauri/Vue) con la suite fallando. A lo largo de la campaña, los modos
encontraron y repararon defectos reales, no solo de pruebas: un validador de WebP que
rechazaba archivos legales, un recuento de álbumes que etiquetaba un disco de 10 pistas
como de 1, un deadlock de SQLite que colgaba la CI con 0 % de CPU, un puente de descargas
que firmaba peticiones con un secreto vacío.

| Métrica | Resultado |
|---|---|
| Hallazgos distintos persistidos | 77 (114 registros con su historial) |
| Trabajo verificado | 78 ítems VERIFIED |
| Verificaciones persistidas | 67 (61 PASS, 6 BLOCKED declarados) |
| Commits generados por los modos e integrados | 15 |
| Resultado | CI verde en los 3 jobs (Rust, frontend, Python) |

### RehabWeb: 45 hallazgos de seguridad, un prompt de seis palabras

Instalación limpia de principio a fin con un solo comando. La primera auditoría encontró
**45 hallazgos (6 CRITICAL, 16 HIGH, 23 MEDIUM)**, entre ellos: cualquier usuario
autenticado podía leer el historial clínico de toda la población, y un paciente podía
reescribir el diagnóstico de otro. El prompt «Repara A-SEC-01 y A-SEC-02; no publiques.»
produjo la corrección de ambos con su prueba de regresión (3 ficheros, 220 líneas), sin
tocar el árbol del producto hasta la integración.

### LoboApp: la campaña que encontró los límites de verdad

App Flutter (Android) instalada **desde un clon de GitHub del framework**, sobre un
producto recién clonado y sin contaminación previa: exactamente el escenario que se
encuentra un tester. La auditoría con un prompt simple persistió 9 hallazgos (1 CRITICAL,
2 HIGH, 4 MEDIUM, 2 LOW).

El CRITICAL era una promesa incumplida: el aviso de privacidad decía que cerrar sesión
borra del dispositivo lo que guardaste, pero el código solo quitaba una clave; el avance y
las notas seguían ahí y reaparecían al volver a entrar. «Repara F-01 y F-02; no
publiques.» produjo el arreglo con sus pruebas de regresión en 7 ficheros y 353 líneas,
verificado con **`flutter test` real** (125 pruebas en verde) y `flutter analyze` sin
incidencias, e integrado con `bb01cba..eb25ec3`: commit, fast-forward y push del operador.

Esta campaña encontró los dos fallos que ninguna prueba sintética habría visto: el
framework emitía un comando de verificación que su propia shell no podía ejecutar, y el
sandbox dejaba el SDK montado en solo lectura mientras la herramienta se reescribe a sí
misma en cada ejecución. Los dos están corregidos, con regresión, y son la razón de que la
verificación sea real y no declarativa.

La campaña siguió hasta el final. Los 9 hallazgos se repararon y se integraron en cuatro
turnos, cada uno verificado con `flutter test` real; la reauditoría posterior confirmó los
9 como **RESOLVED** con evidencia y encontró 5 más, que también se repararon. Al terminar:
**14 hallazgos, 166 pruebas Flutter en verde**, y cuatro commits integrados con
`bb01cba..4c0bb30`. Entre ellos, un hallazgo que el arreglo anterior había creado: al
comparar espacios de nombres, un respaldo heredado sin namespace dejó de restaurarse.

### El propio framework

Instalado sobre un clon de sí mismo, el auditor encontró 7 defectos reales del framework
(2 HIGH, 5 MEDIUM) y el reparador los arregló todos con sus pruebas: la compactación por
límite descartaba registros **sin recibo** (la pérdida silenciosa que G3 debía haber
cerrado y solo cubrió a medias); la herramienta de escritura no confinaba el estado
gestionado a su raíz, dejando la frontera de solo lectura del auditor apoyada únicamente
en un `git status` posterior; la capa `graph` del validador no comprobaba nada; la capa
`lifecycle` se saltaba el contrato por rol; el control G7 leía el plan de capacidades sin
comprobar su firma; y `install` solo vinculaba el veredicto Host al candidato cuando
recibía una ruta.

La reauditoría del framework confirmó los siete como **RESOLVED** y encontró el más
incómodo de todos: **un resultado de verificación no identificaba el árbol que verificó**.
El contrato prohíbe hacer commit de una candidata, así que el árbol verificado es un
worktree sucio cuyo HEAD sigue siendo su base y el arreglo vive en el diff sin commitear;
`candidate_head` no lo distingue de la revisión anterior al arreglo. Medido sobre el
estado real, los siete registros llevaban dos cabezas, ambas anteriores a los cambios que
decían verificar. Ahora cada registro lleva el digest del diff verificado y tres sitios lo
comprueban. Suite del propio framework en ese punto: **743 pruebas en verde**.

La memoria se aplica también a sí misma: las unidades de endurecimiento nacieron de los
fallos de los pilotos (reserva de candidata antes de editar, reconciliación sin operador,
anti-escalada mecánica, retirada de candidatas documentada, base obsoleta que se re-ancla
probando el parentesco…), y una auditoría de la propia memoria descubrió una pérdida
silenciosa de registros en el preflight, corregida con regresión. La segunda auditoría de
la memoria encontró que el registro de defectos ya cerrados **se escribía y nadie lo
leía**: la documentación decía que el auditor lo consultaba y ningún camino del producto
lo hacía, así que el mismo defecto volvía cada sesión. Ahora la consulta es mecánica y
`bootstrap.py state` cuenta las repeticiones. Suite del framework: **774 pruebas en
verde**.

## Qué obtienes en tu repo

![Qué instala Improvement en tu máquina](docs/diagrams/arquitectura-instalacion.png)

*Los dos modos generados, la memoria acotada y la frontera de integración. También
explorable: [versión interactiva](https://madmanjohnsmith.github.io/Improvement/diagrams/arquitectura-instalacion.html).*

```
tu-proyecto/
tu-proyecto-workspace/
├── mode-state/
│   ├── findings.jsonl            # hallazgos con evidencia y estado
│   ├── handoffs.jsonl            # un registro por auditoría, con el siguiente prompt
│   ├── verification-results.jsonl  # cómo se verificó cada arreglo
│   ├── overflows.jsonl           # qué se descartó al compactar, y por qué
│   └── work-items.json           # cola de trabajo y candidata activa
├── .dsh-managed/
│   └── capability-plan.json      # los comandos reales de tu proyecto y qué falta
└── creator-runs/                 # qué generó Creator, con sus validaciones
```

Todo con topes por fichero y por registro, y compactación cuando se alcanzan: la memoria
puede crecer mucho, pero no sin límite. Lo que la compactación descarta no desaparece en
silencio: queda un recibo en `overflows.jsonl` diciendo qué se perdió y por qué.

## Qué NO hace (a propósito)

- **No hace commit ni push.** El reparador deja el candidato verificado y el árbol de tu
  producto limpio; integrar es tuyo. Es la frontera de seguridad, y está probada.
- **No es autónomo en la sombra.** Cada turno termina con un resultado legible; lo que se
  retiene se dice y por qué.
- **No instala proveedores ni credenciales.** DSH y tu proveedor son prerrequisitos.
- **No promete aislamiento mecánico del sistema de ficheros.** La frontera es contractual
  y está probada; no hay sandbox de kernel.

## Estado: beta pública

Esto se lanza para testeo. Lo que ya está probado: instalación de principio a fin sin
intervención, desde un clon de GitHub y sin contaminación previa; el ciclo
auditor→reparador→integración en tres campañas reales; verificación ejecutada contra el
entrypoint real del producto (Flutter y Django, sin stubs) con la evidencia persistida y
validada mecánicamente; y la memoria alcanzando sus topes con compactación y recibo.
Licencia Apache-2.0 y etiqueta `v0.1.0-beta` ya publicadas. Lo que queda para la versión
estable está en el [plan de lanzamiento](docs/plans/10-lanzamiento-publico.md).

## ¿Lo pruebas?

El comando del [inicio rápido](#inicio-rápido) es todo lo que hace falta. Para reportar tu
experiencia, comparte tu `mode-state` (`findings.jsonl`, `handoffs.jsonl`,
`verification-results.jsonl`, sin código de tu producto), los turnos que acabaron
retenidos y por qué: [abre un issue](https://github.com/MadManJohnSmith/Improvement/issues).
Ese es el informe más útil posible, y es exactamente el formato que el framework ya
produce.

## Documentación

- [Uso operativo](docs/usage.md) — el ciclo completo, integración y recuperación de espacio
- [Diagramas interactivos](https://madmanjohnsmith.github.io/Improvement/diagrams/ciclo-operativo.html) — el ciclo operativo y la [arquitectura instalada](https://madmanjohnsmith.github.io/Improvement/diagrams/arquitectura-instalacion.html), como HTML explorables
- [Preparación de DSH](docs/setup-dsh.md)
- [Estado comprobado](docs/status.md)
- [Arquitectura normativa](ARQUITECTURA_FLUJO_AGENTES.md)
- [Planes de implementación](docs/plans/README.md) · [Plan de lanzamiento](docs/plans/10-lanzamiento-publico.md)
- [Cambios](CHANGELOG.md) · [Atribuciones de terceros](THIRD_PARTY_NOTICES.md)
- [Notas de la beta v0.1.0](docs/plans/11-notas-beta-v0.1.0.md) (publicada el 2026-09-30)

## Licencia

Apache-2.0 ([LICENSE](LICENSE)). Las skills de terceros y sus atribuciones están en
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
