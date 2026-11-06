"""Almacén de notas de la libreta.

Las notas viven en un archivo JSON dentro del directorio de datos que indica
quien invoca; ninguna operación lee ni escribe fuera de ese directorio.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


class NotaInexistente(Exception):
    """No hay ninguna nota con el identificador pedido."""


def _ruta_almacen(directorio):
    directorio = Path(directorio)
    directorio.mkdir(parents=True, exist_ok=True)
    return directorio / "notas.json"


def _cargar(ruta):
    if not ruta.exists():
        return []
    with ruta.open("r", encoding="utf-8") as flujo:
        return json.load(flujo)


def _guardar(ruta, notas):
    texto = json.dumps(notas, ensure_ascii=False, indent=2, sort_keys=True)
    ruta.write_text(texto + "\n", encoding="utf-8")


def anadir_nota(directorio, titulo, cuerpo):
    ruta = _ruta_almacen(directorio)
    notas = _cargar(ruta)
    nota = {
        "id": uuid.uuid4().hex,
        "titulo": titulo,
        "cuerpo": cuerpo,
        "creada": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    notas.append(nota)
    _guardar(ruta, notas)
    return nota


def listar_notas(directorio):
    return _cargar(_ruta_almacen(directorio))


def buscar_notas(directorio, texto):
    aguja = texto.lower()
    return [
        nota for nota in listar_notas(directorio)
        if aguja in nota["titulo"].lower() or aguja in nota["cuerpo"].lower()
    ]


def eliminar_nota(directorio, identificador):
    ruta = _ruta_almacen(directorio)
    notas = _cargar(ruta)
    restantes = [nota for nota in notas if nota["id"] != identificador]
    if len(restantes) == len(notas):
        raise NotaInexistente(identificador)
    _guardar(ruta, restantes)
