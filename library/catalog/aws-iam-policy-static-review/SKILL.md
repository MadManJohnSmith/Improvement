---
name: aws-iam-policy-static-review
description: "Revisión estática de políticas IAM de AWS sobre documentos observados, marcando wildcards y distinguiendo política declarada de permisos efectivos. Se activa solo con políticas IAM en juego y encargo de permisos. Sin credenciales."
---

# Revisión estática de políticas IAM

## Activación
El patrón solo se selecciona si el proyecto presenta evidencia real:
- políticas IAM como documentos JSON o en Terraform, CloudFormation o CDK observados en el proyecto
- recursos o roles AWS (Lambda, API Gateway, roles, policies) observados en el proyecto
- encargo explícito de revisión de permisos o mínimo privilegio

Sin esas señales el patrón no aplica; la mera presencia de Terraform no lo activa.

## Cuándo aplicar
Con las señales de activación presentes: revisar documentos de política
observados en busca de sobreconcesión y riesgos declarables estáticamente.

## Procedimiento
Fija cada documento de política revisado por hash; la revisión corresponde
a ese contenido exacto.
Marca Action o Resource con wildcard (`*`) salvo justificación explícita
y verificable en el propio documento o en el encargo.
Distingue política declarada de permisos efectivos: la evaluación real
depende de adjunciones, condiciones y límites que el documento no muestra;
sin esa evidencia, el resultado es UNVERIFIED para lo efectivo.
Clasifica cada hallazgo: sobreconcesión declarable,Wildcard justificado
o ambiguo, con la ruta y línea como fuente.
Registra qué aspectos requieren herramientas AWS (evaluador de políticas,
simulación) y quedan fuera de esta revisión estática.

## Invariantes
Sin credenciales ni llamadas a AWS: la revisión es estática sobre documentos.
Action o Resource con wildcard se marca salvo justificación verificable.
Política declarada y permisos efectivos se distinguen siempre.
Cada documento revisado queda fijado por hash.

## Prohibido y límites
No uses credenciales AWS ni invoques servicios para "comprobar" permisos.
No declares mínimo privilegio alcanzado: el resultado es un inventario de
hallazgos, no un certificado.
No afirmes ahorro de costes ni impacto sin datos de uso y precios versionados.
La simulación de permisos efectivos requiere encargo y autorización propios.

## Escenarios y cierre
Escenarios: SC-153 (positiva), SC-154 (wildcard sin marcar), SC-155
(capability-denial: uso de credenciales).
Entrega: documentos con hash, hallazgos clasificados con fuente y límites
efectivos declarados como no verificados.

## Procedencia
Adaptado de aws-waf-apg — instantánea observada de awsdocs/iam-user-guide
(f63d5a275d29d74f56086c09cccf7e02ed285652; términos del vendedor por página).
Reimplementación propia para este framework, sin copia textual de AWS.
