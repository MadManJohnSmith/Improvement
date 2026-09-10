# Entrada de usuario: incorporar, auditar o reparar una unidad

El mensaje identifica proyecto y objetivo; el procedimiento vive aquí para no exigir prompts largos. Lee `docs/usage.md` para el protocolo operativo v0.1.

## Despacho

- «Incorpora/prepara»: usa incorporación inferior. Preparar Auditor/Reparación para DSH incluye copia explícita de skills al workspace, no permiso de ejecutar producto.
- «Audita/revisa»: carga nativamente `workflow-auditor` y sigue una unidad dirigida. Si no está preparada, incorpora/copia con autorización; no confundas leer el SKILL.md del repo con cargarlo en DSH. Una auditoría no habilita reparación.
- «Repara esta tarea»: carga `workflow-continuous-repair`, reutiliza tarea y decisiones válidas; confirma solo permisos materialmente faltantes. No toca producto vivo por defecto.
- Si falta carga nativa, conserva el encargo en el perfil externo y devuelve preparación pendiente; no inventes ejecución del modo. Mantén la raíz padre de la sesión Standard; la preparación enlaza las skills del workspace en su raíz nativa, sin cambiar cwd.

Ante error de esquema de `sandbox_permissions`, corrige la llamada según el esquema efectivo, omitiendo parámetros opcionales de escalada y justificación en la llamada ordinaria (no uses null). No es denegación de acceso ni autoriza probar `danger-full-access`; si el error se repite, retén y conserva diagnóstico. «must be strictly wider» es rechazo de escalada, no motivo para subir otro nivel. En Auditor, si los controles disponibles no separan lectura de producto/framework y escritura de workspace, retén: no solicites acceso total para una lectura.

Antes de operar, comprueba lectura efectiva del producto hermano. Si el Host deniega o no permite verificarla, detén con rutas exactas y decisión de permisos necesaria; no cambies cwd ni herramientas para eludirlo. Escritura de evidencia externa y lectura del framework también requieren autoridad efectiva. Nunca editar el framework durante la misión.

## Alcance de esta entrada

La petición de incorporación autoriza descubrir el proyecto por lectura y preparar su perfil mínimo en un espacio externo. No autoriza cambios al producto, al clon de este framework, configuración personal, proveedores, instalaciones, red, builds, tests del producto, goals ni delegación adicional. Las políticas efectivas del runtime prevalecen; informar una denegación real sin eludirla.

## Procedimiento

1. Identifica el clon del framework desde este archivo y el proyecto indicado. Si el nombre corresponde inequívocamente a un directorio hermano, úsalo; si hay varios candidatos, pregunta solo cuál. No inventes rutas ni busques por todo el perfil del usuario.
2. Lee las instrucciones pertinentes del proyecto y `skills/project-onboarding/SKILL.md`. Distingue lectura explícita de carga nativa; no necesitas instalar skills para esta primera entrada.
3. Registra la revisión y el estado Git inicial de framework/producto cuando sean repositorios. Usa `git --no-optional-locks` para lecturas de estado. Conserva cambios preexistentes; un árbol modificado no exige limpiar ni invalida automáticamente la incorporación.
4. Busca espacios y canónicos existentes por las referencias del proyecto y ubicaciones hermanas pertinentes. Si existen, consérvalos; no crees un segundo backlog. Si su formato no coincide con onboard.py, no lo fuerces ni migres: informa qué se puede reutilizar y la decisión concreta faltante.
5. Si falta un espacio compatible, el destino convencional es un directorio hermano `<nombre-del-proyecto>-workspace`, externo tanto al producto como al framework. Inspecciona el destino antes de usarlo. Los enlaces y conflictos rechazados por el inicializador son límites, no permiso para borrar o cambiar rutas silenciosamente.
6. Usa el Python disponible y rutas absolutas verificadas para ejecutar `python3 -B scripts/onboard.py --project ... --workspace ... --name ...` desde el framework (o la ruta absoluta del script). Primero sin `--init`, después con `--init` si el destino es compatible. Deriva un nombre minúsculo con guiones del nombre del proyecto. No crees scripts auxiliares en el framework.
7. Si la misión autoriza preparar skills para DSH, usa `--prepare-skills` para copiarlas al workspace externo en `.agents/skills/`, primero en dry-run y después con `--init`. La copia recursiva es explícita, idéntica es idempotente; conflicto bloquea hasta autorizar `--update-skills` con respaldo externo según docs/usage.md. Compara revisión/cuerpos antes de cargar; no uses `~/.dsh`, `.agents` del usuario ni el producto. Añade `--session-root <padre-actual>` en ambas órdenes para crear enlaces gestionados desde `<padre-actual>/.agents/skills` a las copias del workspace, con manifiesto externo. Conserva el cwd padre actual; no requiere overlay, perfil nuevo ni modo personalizado. La autorización de preparación cubre estos enlaces, no entradas ajenas: conflictos bloquean. Solo un workspace gestionado por raíz padre, sin ancestro Git; otro proyecto necesita su propio padre. Retirada explícita: mismos argumentos con `--session-root`, `--remove-links` y sin `--prepare-skills`, dry-run y luego `--init`. No seguir enlaces para modificar sus destinos. Comprueba catálogo y carga nativa según docs/setup-dsh.md; la copia por sí sola no lo demuestra.
8. Completa solamente el perfil nuevo creado por esta misión con fuentes observadas, referencias a artefactos existentes y restricciones necesarias; usa escritura segura y conserva contenido si ya existía. No transformes antecedentes en observaciones vigentes. El primer encargo de auditoría/reparación sigue pendiente de mandato propio.
9. Repite la inicialización compatible y comprueba que el perfil completado no cambia. Verifica estado final del framework y del producto; cualquier diferencia nueva debe explicarse, no descartarse para aparentar limpieza.

## Retorno

Máximo unas diez líneas salvo un conflicto que necesite evidencia adicional: revisión del framework, proyecto y espacio utilizados, qué se creó/reutilizó, resultado de repetición, estado inicial/final, lectura o carga nativa de la skill y pendientes. Evidencia necesaria solo dentro del espacio externo; ningún log, captura o perfil real dentro del clon del framework. No volcar secretos ni configuraciones completas.

Si termina sin errores, informar «incorporación mínima preparada». No declarar motor autónomo listo, skill instalada, aislamiento OS ni auditoría del proyecto completada. Si requiere decisión, devolver una excepción concreta con recomendación; no otra lista de instrucciones que el usuario deba redactar.
