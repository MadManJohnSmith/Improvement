# Plan 07 — C6: piloto clean-room

**Salida:** validar experiencia de usuario final en proyectos no usados durante el desarrollo.
**Precondiciones:** C0–C5 y DSH/proveedor configurado por el participante.

## Pilotos

1. Proyecto Python/backend.
2. Proyecto multiparte JS/Rust/UI o equivalente.

Ninguno comparte generación, perfil, candidatos, holdouts ni diagnósticos privados con implementación.

## Recorrido

- clone del tag de piloto;
- `bootstrap install` de un comando;
- Creator automático;
- aceptación automática;
- modos específicos visibles;
- auditoría completa y dirigida;
- reparación dirigida y de cola;
- QA/reauditoría;
- update con cambio material/drift;
- edición local de skill y resolución conservadora;
- rollback/uninstall;
- feedback sin secretos.

## Métricas

- comandos/mensajes visibles;
- decisiones humanas;
- troubleshooting;
- tiempo;
- requests/tokens por rol;
- fallos/retenciones;
- cambios de contexto;
- claridad percibida.

## Gate

Usuario sin conocimiento interno obtiene modos útiles, no edita JSON/prompts/recibos, no transporta IDs y puede abandonar/retomar. Cualquier intervención extraordinaria se registra y evita declarar UX limpia si era necesaria.

## Adaptación

No relajar controles por feedback de conveniencia. Clasificar cada comentario como bug, ambigüedad, capacidad ambiental, mejora opcional o cambio de alcance.
