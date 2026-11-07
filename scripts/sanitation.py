"""Patrones de saneamiento compartidos por los gates de contenido publicado.

Un solo lugar para las formas que un fichero publicado no debe llevar: rutas
locales de una máquina, claves con nombre de credencial, bearer, correo y
dirección postal. Los gates los aplican; este módulo no decide nada.
"""
import re

# Absolute paths of a machine, not of a project. `/home/alice` in a published
# fixture is somebody's directory; `/opt/app` is not.
LOCAL_PATH = re.compile(
    r"(?<![\w.])/(?:home|Users|root|var/folders)/[\w.-]+"
    r"|[A-Za-z]:\\\\?[\w.\\-]+")
# What a credential looks like in a JSON document. Digests are hex and are not
# on this list; only names that would carry a secret are.
CREDENTIAL_KEY = re.compile(
    r"\"(?:token|secret|password|passwd|api[_-]?key|apikey|bearer|cookie|"
    r"session|authorization|credentials?)\"\s*:", re.IGNORECASE)
BEARER_VALUE = re.compile(r"Bearer\s+[A-Za-z0-9._\-]{8,}")
# Personal data a published file must not carry. The address pattern is
# deliberately narrow: a street name followed by a number is what a real
# postal address looks like, and the false positives it could take are prose
# these directories do not contain.
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
POSTAL_ADDRESS = re.compile(
    r"\b(?:calle|avenida|paseo|carrer|avinguda|street|avenue|road|boulevard|"
    r"strasse)\b[^\n]{0,60}?\b\d{1,4}\b", re.IGNORECASE)

# Orden fijo para que un informe de gate sea determinista.
PATTERNS = (("local-path", LOCAL_PATH), ("credential-key", CREDENTIAL_KEY),
            ("bearer", BEARER_VALUE), ("email", EMAIL),
            ("postal-address", POSTAL_ADDRESS))


def violations(text):
    """Nombres de patrón que casan en el texto, en orden fijo."""
    return [name for name, pattern in PATTERNS if pattern.search(text)]
