"""Plomería compartida: toquetear un artifact y re-firmar el manifest.

El patrón vivía repetido 12 veces en `test_creator_and_validator.py` con
firmas ligeramente distintas por copia — una divergencia esperando a pasar.
Un solo helper, un solo formato de reescritura.

Los fixtures de composición de los ficheros-validador NO viven aquí: son
copias deliberadas (antitautología) — si el fixture lo generara
`mode_lifecycle`, un bug del generador sería invisible para sus propios
tests. Cada fichero-validador se queda el suyo.
"""
import json
from pathlib import Path

from acceptance import _digest_bytes


def resign_artifact(generated, manifest, relative_path, new_bytes):
    """Firma `new_bytes` como artifact `relative_path` y reescribe el manifest.

    Muta `manifest` in place —los tests reutilizan el objeto entre
    toqueteos— y reescribe `generation-manifest.json` con el formato exacto
    que el validador espera: `json.dumps(indent=2)` más newline.
    """
    for artifact in manifest["artifacts"]:
        if artifact["path"] == relative_path:
            artifact["sha256"] = _digest_bytes(new_bytes)
    (Path(generated) / "generation-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n")
