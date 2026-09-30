# Improvement

**Dos modos especializados con memoria persistente para terminar tu proyecto con prompts
sencillos.** Improvement instala en tu repositorio un auditor y un reparador continuo
generados específicamente para tu proyecto, con memoria acotada que no satura, verificación
con evidencia y un núcleo fail-closed: los modos nunca publican ni tocan tu producto sin
que tú integres.

Es un framework real, probado en tres campañas completas sobre repositorios reales
(Syncify, una app de música en Rust/Tauri/Vue; RehabWeb, una app clínica en Django/Vue;
y LoboApp, una app Flutter fresh con el framework instalado desde un clon de GitHub).
Las métricas de abajo son de esas campañas, no promesas.

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

### 1. Requisitos

- Linux, `git` y Python 3.
- [DSH](docs/setup-dsh.md) instalado, con al menos un proveedor/modelo configurado por ti.
  El framework nunca lee ni pide tus API keys: solo comprueba que las variables existen.

### 2. Un comando

Clona este framework junto a tu proyecto (nunca dentro) y ejecuta:

```bash
python3 -B scripts/bootstrap.py install \
  --project /ruta/a/tu/proyecto \
  --launch-dsh
```

Eso descubre tu proyecto, genera `<TuProyecto>-auditor` y `<TuProyecto>-continuous-repair`
con sus skills, valida el paquete en 10 capas, hace backup, instala y activa — o hace
rollback dejando el estado recuperable. Tu producto no se toca durante la instalación.

### 3. Prompts simples

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

## Verificación contra tu proyecto real, nunca con stubs

Al instalar, Improvement lee tu proyecto y escribe un **plan de capacidades** en
`<proyecto>-workspace/.dsh-managed/capability-plan.json`: qué tecnologías compose tu
proyecto (incluidos monorepos), cuál es **el comando de test y el de análisis propios de
cada una**, y si esta máquina tiene ya lo necesario para ejecutarlos.

Ese plan es la única evidencia que el reparador puede registrar. Un comando inventado, un
mock o una copia del código del producto son material de investigación, nunca un
resultado. Si el comando no puede ejecutarse porque falta una herramienta, el registro es
`BLOCKED` nombrando exactamente qué falta y cómo se instala — nunca un `PASS` inventado.

```
stacks:
  dart-flutter  listo  (/home/tu/usuario/.local/share/flutter/bin/flutter test)
  java-gradle   falta java   (instalar un JDK 17+ fuera del producto y anteponerlo al PATH)
```

Un detalle que la beta teachings a la fuerza: si la herramienta está instalada pero fuera
del `PATH` por defecto, el plan la nombra **por su ruta absoluta**. Un nombre suelto que la
shell del modo no puede invocar convertiría una suite que funciona en un `BLOCKED` que el
runtime no se ha ganado.

## Casos reales

### Syncify — un proyecto con CI en rojo, cerrado

App de música (Rust/Tauri/Vue) con la suite fallando. A lo largo de la campaña, los modos
encontraron y repararon defectos reales, no solo de pruebas: un validador de WebP que
rechazaba archivos legales, un recuento de álbumes que etiquetaba un disco de 10 pistas
como de 1, un deadlock de SQLite que colgaba la CI con 0 % de CPU, un puente de descargas
que firmaba peticiones con un secreto vacío.

| Métrica | Resultado |
|---|---|
| Hallazgos distintos persistidos | 77 (114 registros con su historial) |
| Trabajo verificado | 78 items VERIFIED |
| Verificaciones persistidas | 67 (61 PASS, 6 BLOCKED declarados) |
| Commits generados por los modos e integrados | 15 |
| Resultado | CI verde en los 3 jobs (Rust, frontend, Python) |

### RehabWeb — seguridad de una app clínica, con un prompt de seis palabras

Instalación limpia de principio a fin con un solo comando. La primera auditoría encontró
**45 hallazgos (6 CRITICAL, 16 HIGH, 23 MEDIUM)**, entre ellos: cualquier usuario
autenticado podía leer el historial clínico de toda la población, y un paciente podía
reescribir el diagnóstico de otro. El prompt «Repara A-SEC-01 y A-SEC-02; no publiques.»
produjo la corrección de ambos con su prueba de regresión — 3 ficheros, 220 líneas — sin
tocar tu producto hasta la integración.

### LoboApp — la beta que encontró los límites de verdad

App Flutter (Android) instalada **desde un clon de GitHub del framework**, sobre un producto
recién clonado y sin contaminación previa: exactamente el escenario que se encuentra un
tester. La auditoría con un prompt simple persistió 9 hallazgos (1 CRITICAL, 2 HIGH,
4 MEDIUM, 2 LOW).
El CRITICAL era una promesa incumplida: el aviso de privacidad decía que cerrar sesión
borra del dispositivo lo que guardaste, pero el código solo quitaba una clave — el avance y
las notas seguían ahí y reaparecían al volver a entrar. «Repara F-01 y F-02; no publiques.»
produjo el arreglo con sus pruebas de regresión en 7 ficheros y 353 líneas, verificado con
**`flutter test` real** (125 pruebas en verde) y `flutter analyze` sin incidencias, y
integrado con `bb01cba..eb25ec3`: commit, fast-forward y push del operador.

Esta campaña es la que encontró los dos fallos que ninguna prueba sintética habría visto:
el framework emitía un comando de verificación que su propia shell no podía ejecutar, y el
sandbox dejaba el SDK montado en solo lectura mientras la herramienta se reescribe a sí
misma en cada ejecución. Los dos están corregidos, con regresión, y son la razón de que la
verificación sea real y no declarativa.

### El propio framework

Instalado sobre un clon de sí mismo, el auditor encontró 7 defectos reales del framework
(2 HIGH, 5 MEDIUM) y el reparador arregló los dos primeros con sus pruebas: la compactación
por límite descartaba registros **sin recibo** (la pérdida silenciosa que G3 debía haber
cerrado y solo cubrió a medias), y la herramienta de escritura no confinaba el estado
gestionado a su raíz, dejando la frontera de solo lectura del auditor apoyada únicamente en
un `git status` posterior. Verificado con la suite real del proyecto: **585 pruebas en
verde**.

La memoria se aplica también a sí misma: las unidades de endurecimiento nacieron de los
fallos de los pilotos (reserva de candidata antes de editar, reconciliación sin operador,
anti-escalada mecánica, retirada de candidatas documentada, base obsoleta que se re-ancla
probando el parentesco…), y una auditoría de la propia memoria descubrió una pérdida
silenciosa de registros en el preflight, corregida con regresión. Suite del framework:
**585 pruebas en verde**.

## Qué obtienes en tu repo

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
  producto limpio; integrar es tuyo. Esto es la frontera de seguridad, no una limitación.
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
validada mecánicamente; y la memoria alcanzando sus topes con compactación y recibo. Lo que
falta para la versión estable está en el
[plan de lanzamiento](docs/plans/10-lanzamiento-publico.md): elegir licencia (G0) y la
etiqueta de la beta (G6).

**Para reportar tu experiencia**, comparte tu `mode-state` (`findings.jsonl`,
`handoffs.jsonl`, `verification-results.jsonl` — sin código de tu producto), los turnos
que acabaron retenidos y por qué. Ese es el informe más útil posible, y es exactamente el
formato que el framework ya produce.

## Documentación

- [Uso operativo](docs/usage.md) — el ciclo completo, integración y recuperación de espacio
- [Preparación de DSH](docs/setup-dsh.md)
- [Estado comprobado](docs/status.md)
- [Arquitectura normativa](ARQUITECTURA_FLUJO_AGENTES.md)
- [Planes de implementación](docs/plans/README.md) · [Plan de lanzamiento](docs/plans/10-lanzamiento-publico.md)
- [Cambios](CHANGELOG.md) · [Atribuciones de terceros](THIRD_PARTY_NOTICES.md)

## Licencia

Sin definir todavía: es decisión del titular y es la puerta G0 del plan de lanzamiento.
Un repositorio accesible no concede por sí solo una licencia abierta.
