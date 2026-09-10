---
name: project-onboarding
description: "Incorporar o reconocer un proyecto para auditoría o reparación. Usar al iniciar una misión en un proyecto nuevo, localizar su perfil externo o repetir onboarding sin sobrescribir decisiones."
---

# Incorporación compartida

Disponible desde Auditor y Reparación continua; no es un tercer modo. La skill orienta, no concede permisos ni implementa aislamiento.

1. Identifica el producto real y el clon del framework. Descubre instrucciones, raíces Git, enlaces, canónicos y espacios privados pertinentes. No leas todos los logs ni confundas adjuntos con fuentes vigentes.
2. Reutiliza decisiones del perfil existente. Si falta workspace, elige un destino externo al producto y al framework con autorización. No crees perfiles en un repositorio público ni alteres canónicos.
3. Usa `scripts/onboard.py` del clon identificado, mediante Python 3.9+. Pasa `--project`, `--workspace` absolutos y `--name` estable. Sin `--init` solo comprueba; añade `--init` únicamente con autorización de creación. No inventes una ruta relativa al cwd de DSH: resuelve el script desde el clon.
4. Si rechaza enlace, conflicto o perfil incompleto, conserva y diagnostica. No borres, renombres ni sobrescribas para forzar éxito. Repetición compatible conserva PROJECT.md; el script no actualiza ni migra perfiles automáticamente.
5. Completa solo lo necesario para el primer encargo: objetivo, fuentes/canónicos, comandos permitidos, datos excluidos, criterios, presupuesto y paradas. El perfil no constituye autorización por sí mismo. No generes dashboards ni evidencia ficticia.
6. Distingue preparación local de carga y ejecución DSH. No cambies configuración global, modelos o credenciales ni inicies red por incorporar un proyecto.

Devuelve identidad y workspace, decisiones reutilizadas, resultado real del inicializador y siguiente acción autorizada. Auditor entrega diagnóstico sin modificar producto; reparación necesita mandato propio. Ante decisión humana indispensable, pregunta solo esa decisión.
