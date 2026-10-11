#!/usr/bin/env python3
"""Esfuerzo de razonamiento por paso: vocabulario cerrado y precedencia (U7).

Este módulo decide QUÉ nivel pide un paso y con qué fuente. No llama a
ningún proveedor: la aplicación real vive en el cliente DSH del Host.

Reglas que hacen el mecanismo utilizable sin inventar autoridad:

- El vocabulario es CERRADO y coincide con los identificadores que los
  adaptadores instalados anuncian (`ModelReasoningEffort.id` de DSH): off,
  minimal, low, medium, high, xhigh, max. El framework no deduce nombres
  propios ni asume que una ruta concreta los tenga. Un valor desconocido
  falla al cargar el plan y NUNCA se degrada en silencio.
- Precedencia: paso > plan > comportamiento legado (`effective`). Sin
  declaración en ninguno de los dos, el plan no cambia de bytes y el run
  sigue siendo idéntico al de siempre.
- `apply_effort` es la barrera contra lo que no se puede sostener: sobre la
  selección proveedor/modelo ya fijada, un nivel que el cliente o la ruta no
  soportan produce abstención explícita con motivo. NUNCA fallback a otro
  modelo, NUNCA un PASS inventado.
- Solo los pasos `ask` cambian inferencia. Fases, gates y joints conservan
  su peso: una fase que declara esfuerzo solo documenta la política de la
  campaña, y jamás otorga veredicto, capacidad ni permiso.
"""

# Unión de identificadores de los adaptadores DSH v0.2.0-rc.2 leídos en el
# árbol instalado: pi-ai anuncia off/minimal/low/medium/high/xhigh/max
# (dsh-llm-pi-ai/lib/index.js:296-304) y DeepSeek off/low/high/max
# (dsh-llm-deepseek/lib/index.js:452-476). Cualquier otro nombre es invento.
LEVELS = frozenset(('off', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'))

# Etapas de campaña que el operador puede declarar. verificacion y revision
# son gates al aplicar la política: no reciben nivel porque no razonan.
STAGES = frozenset(('auditoria', 'implementacion', 'verificacion', 'revision'))


class ReasoningError(ValueError):
    """Nivel o política no aplicable: se abstiene con motivo, sin degradar."""


def validate(level):
    """Nivel del vocabulario cerrado, o ReasoningError. Sin sustitución."""
    if type(level) is not str or level not in LEVELS:
        raise ReasoningError('nivel de esfuerzo desconocido: ' + repr(level))
    return level


def normalize_level(level):
    """Alias explícito para puntos que normalizan al cargar el plan."""
    return validate(level)


def effective(plan, step):
    """(nivel pedido, fuente) con precedencia paso > plan > legacy.

    El comportamiento legado no adquiere un nivel por inferencia: sin
    declaración en el paso ni en el plan, el esfuerzo sigue siendo el que el
    preset y el modelo ya tenían fijados.
    """
    step_level = step.get('reasoning_effort')
    if step_level is not None:
        return validate(step_level), 'step'
    plan_level = (plan or {}).get('reasoning_effort')
    if plan_level is not None:
        return validate(plan_level), 'plan'
    return None, 'legacy'


def stage_policy(policy):
    """Valida la política declarativa del operador sin alterar ninguna etapa.

    Claves fuera del vocabulario de etapas y niveles desconocidos fallan
    antes de generar nada, así que el operador nunca ve un plan degradado en
    silencio.
    """
    if not isinstance(policy, dict) or set(policy) - STAGES:
        raise ReasoningError('etapas de razonamiento desconocidas: '
                             + repr(sorted(set(policy) - STAGES)))
    return {stage: validate(level) for stage, level in policy.items()}



def apply_effort(level, session_selection, *, client_supports=True):
    """Aplica el nivel sobre la selección proveedor/modelo ya fijada.

    `session_selection` es la selección efectiva de la sesión
    ({provider, model, efforts?}). La composición del preset no se toca: solo
    cambia el esfuerzo. Sin soporte del cliente o de la ruta, se abstiene con
    motivo en lugar de degradar a otro nivel, a otro modelo o a un PASS.
    """
    requested = validate(level)
    if not client_supports:
        raise ReasoningError(
            'el cliente DSH no expone selectModel: nivel no aplicado')
    if not isinstance(session_selection, dict):
        raise ReasoningError('selección de sesión ilegible: '
                             + repr(session_selection))
    provider = session_selection.get('provider')
    model = session_selection.get('model')
    if not isinstance(provider, str) or not provider.strip():
        raise ReasoningError('selección de sesión sin proveedor')
    if not isinstance(model, str) or not model.strip():
        raise ReasoningError('selección de sesión sin modelo')
    route = '%s/%s' % (provider, model)
    efforts = session_selection.get('efforts')
    if not isinstance(efforts, (list, tuple)) or not efforts:
        # Sin catálogo publicado no se puede afirmar que se aplicó: se
        # registra el pedido sin inventar el resultado.
        raise ReasoningError(route + ' no publica niveles de razonamiento')
    known = {value if isinstance(value, str) else
             (value.get('id') if isinstance(value, dict) else None)
             for value in efforts}
    known.discard(None)
    if requested not in known:
        raise ReasoningError(route + ' no soporta el nivel ' + requested
                             + ' (admite ' + ', '.join(sorted(known)) + ')')
    return {'provider': provider, 'model': model,
            'reasoning_effort': requested, 'applied': requested}
