"""Shared text contracts of the tests that gate versioned configuration.

El contrato de la plantilla del perfil (tests/test_eval_config.py) y el del
workflow que la rellena (tests/test_workflow_remote_eval.py) escanean el
mismo texto publicado buscando una clave literal: la forma de la
credencial literal es un solo contrato y vive en un solo sitio. Módulo de
soporte, no de regresión: el patrón de descubrimiento (``test*.py``) no lo
recoge y cada consumidor añade este directorio a sys.path, de modo que
corre igual bajo ``python3 -B -m unittest discover -s tests`` que en una
ejecución de módulo único.
"""
import re

# What a literal credential looks like in text. apiKeyEnv names a variable;
# only a value would match these.
LITERAL_KEY = re.compile(
    r"\bsk-[A-Za-z0-9_-]{16,}|Bearer\s+[A-Za-z0-9._-]{8,}|[A-Za-z0-9]{32,}")
