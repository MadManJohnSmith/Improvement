"""Soporte común stdlib: digest sha256 y escritura atómica temp+`os.replace`.

`scripts/` repetía tres utilidades copiadas a mano en cada módulo. Este módulo
concentra la versión canónica para los sitios cuya semántica exacta es la de
aquí; las variantes con semántica propia quedan donde están. Este inventario
es el mapa de lo que NO consolida, y por qué:

- `acceptance.py _replace`, `bootstrap.py _replace_json`,
  `host_validator.py _atomic_write_json`, `transaction.py _replace_json`,
  `state_commit.py _write`, `host_controller.py _save_queue`,
  `workflow.py _write_head`, `mode_lifecycle.py _replace_bytes`,
  `episodes.py _write_index`, `campaign_plan.py _write_if_changed`,
  `reflection.py _trim`: `fsync` antes del replace (protocolo de
  durabilidad); varios además rechazan symlink destino o fsync el directorio.
- `budget.py`, `decisions.py`, `publisher.py`: write-once con `os.link`,
  no replace.
- `campaign.py`, `stack.py`: escritura con `dir_fd` + `O_NOFOLLOW` sobre el
  descriptor del directorio gestionado.
- `episodes.py` (ledger): append `O_APPEND` in place; un replace borraría el
  historial anterior.
- `metrics.py`: creación exclusiva `'xb'` y topes de tamaño (protocolo de
  journal).
- `drift.py _atomic_write_json` y los punteros `ACTIVE` de `transaction.py`:
  el temporal nace con permisos derivados de la umask; aquí nace 0600.
- `creator_client.py _write_json`: exclusión `O_EXCL` opcional + fsync de
  directorio.
- `corpus_compiler.py`, `skill_router.py`, `stack.py` `_digest`: digieren
  JSON canónico, no bytes crudos. `capabilities.py _digest`: módulo fuera de
  alcance (ticket #31). `reflection.py _digest`: valida un hex existente, no
  calcula nada.

Un caso llano nuevo usa estas funciones en vez de copiarlas de nuevo.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

_CHUNK = 65536


def digest_bytes(data: bytes) -> str:
    """Hexdigest sha256 de bytes crudos; quien tiene str lo codifica antes."""
    return hashlib.sha256(data).hexdigest()


def digest_file(path) -> str:
    """Hexdigest sha256 de un fichero, leído en trozos de 64 KiB."""
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path, data: bytes | str, *, mode: int | None = None) -> None:
    """Escribe `data` y lo publica con `os.replace` dentro del mismo directorio.

    `str` se codifica utf-8; el temporal nace oculto junto a `path` con
    permiso 0600 (o `mode` si se da) y un fallo de escritura o de replace lo
    retira sin tocar el destino.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        if mode is not None:
            os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
