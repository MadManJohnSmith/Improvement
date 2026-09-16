# Evaluación del borrador de orquestación externa

Fecha: 2026-09-13. Evaluación documental contra arquitectura v2.4, código ya revisado y estado registrado. No se instalaron ni probaron Factory, Kiro, Cursor, Vibe Kanban, Aider, motores de embeddings o perfiles Codex en esta evaluación. Sus capacidades descritas en el borrador requieren verificación antes de cualquier adopción.

## Conclusión

Conviene recuperar capacidades concretas, no adoptar otra plataforma como dependencia del flujo. La prioridad es completar el recorrido por DSH para el usuario no técnico: incorporación, auditoría exhaustiva, reparación, QA, reauditoría y continuación dentro del mandato. El borrador es material de entrada, no autoridad ni arquitectura alternativa.

| Propuesta | Recomendación | Condiciones |
|---|---|---|
| F1: especificaciones durables/EARS | Incorporar trazabilidad de requisitos al mandato | EARS es redacción estructurada, no verificación mecánica de verdad. Vincular criterio→prueba→veredicto. Usar especificación externa mínima y `task.json` como contrato operativo; no tres backlogs con estados divergentes ni documentación pesada para tareas triviales. |
| F2: Coding→Audits | Prioridad del núcleo ya acordado | Falta composición Host real; no es suficiente ejecutar otro fixture. Conectar identidad, autoridad, estado, presupuesto, QA y siguiente unidad; separar QA de reauditoría posterior. |
| F3: revisión por eventos | Útil como extensión local posterior al ciclo normal | Eventos deduplicados, base/hash, cancelación de revisión obsoleta, límites y notificación local. Comentarios en PRs o publicación remota necesitan autorización específica; no son requisito de primera instalación. |
| F4: kanban/worktrees | No adoptar Vibe Kanban ni Codex como requisito | Un worktree separa fuentes, no procesos, red, credenciales o caches. DSH conserva la interfaz; coordinar primero unidades propias con aislamiento efectivo. Evaluar herramienta externa solo si demuestra una ventaja medible y no elude QA/integración. |
| F5-B: índice local | Incorporación gradual, condicionada a utilidad | Primero inventario/símbolos/localizadores por hash, consulta a demanda y presupuesto. Añadir embeddings solo tras comparación con navegación existente y autorización de dependencias/modelo local. No cargar mapas grandes siempre. |
| F5-C: memoria episódica | Útil como evidencia e hipótesis, no instrucciones autoaprobadas | Separar de decisiones normativas; procedencia, ámbito, caducidad y presupuesto. No archivar datos privados en Git automáticamente ni elevar frecuencia a autoridad. Compatible con RSI acotada en mantenimiento separado. |

## Decisiones recomendadas para el ejecutor

1. **D1:** specs en workspace externo por defecto. Versionarlas dentro de un producto únicamente si el titular lo solicita y autoriza su integración. Un contrato estructurado y vistas derivadas, no múltiples fuentes de estado.
2. **D2:** DSH y sus capacidades nativas como camino obligatorio de aceptación. No exigir al usuario aprender otro CLI ni abrir sesiones de ejecutor/QA manualmente. Una herramienta alternativa es opcional, no un atajo para declarar DSH terminado.
3. **D3:** entrega local recuperable y notificación por DSH. Publicación remota desactivada salvo mandato separado de destino/contenido/credenciales.
4. **D4:** no elegir anticipadamente SQLite-vec, Ollama o fastembed. Medir mapa local y búsqueda existentes; fijar cuotas e invalidación. Si embeddings aportan valor, documentar motor/modelo, licencia, descarga autorizada, almacenamiento y no salida a red.
5. **D5:** el Host posee autorización, entornos y exclusión de escritor. Una tarjeta o worktree de terceros nunca concede autoridad de merge ni seguridad OS.

## Correcciones necesarias al interpretar el borrador

- El soporte de un endpoint `responses` por un cliente no demuestra compatibilidad con el broker actual, que admite `chat/completions` acotado. No montar conectividad general para eludir esa diferencia.
- La restricción de índice/memoria local evita subir una base persistente adicional, pero no garantiza que ningún código salga del equipo: las inferencias autorizadas pueden enviar fragmentos al proveedor. Declarar categorías de datos y destinos; no introducir una promesa absoluta incompatible con la inferencia remota existente.
- `missions.verify` verifica integridad documental y algunas condiciones de ejecución, no el significado de un requisito EARS. Mantener QA semántica real y evidencia humana donde sea necesaria.
- Configuración global o versión instalada descrita en el borrador no es portable. Descubrir capacidades efectivas en el entorno dedicado, sin cambiar routing ni credenciales personales por inferencia.
- La afirmación «nada estructural nuevo» de F2 subestima integración, estado durable, autenticación, recuperación y pruebas de extremo a extremo. Son trabajo sustancial pendiente.
- La selección de dos proyectos distintos y la prueba de usuario objetivo son gates del núcleo; instalar herramientas de terceros no es criterio de completitud.

## Encaje con el plan de cierre

El [plan de ejecución](PLAN_EJECUCION_ARQUITECTURA_COMPLETA.md) organiza la implementación del núcleo completo y separa las extensiones recomendadas de las dependencias opcionales. Antes de materializar un cambio de diseño, actualizar el mismo documento normativo y mantener la matriz de etapas como única fuente de progreso. Esta evaluación no acredita capacidades implementadas ni autoriza instalaciones, gasto, publicación o cambios de producto.
