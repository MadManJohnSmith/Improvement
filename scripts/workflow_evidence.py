#!/usr/bin/env python3
"""Memoria incremental entre campañas, owned por el Host (U7).

Qué es: un índice fichero->SHA-256 del producto, más el contexto que
condiciona su interpretación (revisión Git del producto, configuración del
workspace y skills activas). Se escribe en el run_root compartido por todas las
campañas del mismo workspace, no dentro del run dir de una sola campaña, y solo
al cierre con RUN_COMPLETED: un run retenido no publica memoria.

Qué NO es: autoridad. Ningún paso se salta ni ningún veredicto se declara por
lo que diga este índice. Cada reanudación vuelve a verificar el journal y las
observaciones; la memoria solo cuenta aciertos y fallos para que el operador y
las pruebas sepan cuánto del árbol revisado sigue igual.

Invalidación fail-closed: un contexto distinto (producto, base, configuración,
skills o exclusiones) invalida TODO el grupo anterior, no la entrada afectada:
una evidencia ligada a un árbol que ya no es el mismo árbol no es evidencia
parcial, es evidencia de otro árbol. Un fichero cambiado, borrado o renombrado
se cuenta como fallo; un symlink, un fichero que cambia mientras se lee o un
inventario ilegible descartan la memoria entera en lugar de degradarla.
"""
import hashlib
import json
import os
import stat
import subprocess

from pathlib import Path

MEMORY_NAME = 'memory.json'
MEMORY_KIND = 'workflow-memory'
MEMORY_VERSION = 1
SNAPSHOT_VERSION = 1
IDENTITY_NAME = 'project.json'
BASE_NAME = 'base.json'
MAX_FILES = 20000
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_MEMORY_BYTES = 4 * 1024 * 1024
# Raíces de estado generado por el propio flujo: no son parte del producto y su
# contenido no describe lo que la campaña evaluó, así que no se inventarían.
GENERATED_NAMES = frozenset({'evidence', 'mode-state', '.dsh-managed', 'node_modules',
                             '.git', '__pycache__', '.venv', 'runs'})
CONFIG_FILES = (IDENTITY_NAME, BASE_NAME)


class EvidenceError(ValueError):
    """Inventario o memoria ilegible; la memoria se descarta entera."""


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'))


def memory_path(run_root):
    """Memoria compartida por todas las campañas de un mismo run_root."""
    return Path(run_root) / MEMORY_NAME


def _walk_folders(root, prefix=''):
    """Inventario sin seguir symlinks; falla cerrada ante cualquier ambigüedad.

    Devuelve (digest por ruta, tamaño por ruta) del mismo recorrido, para que
    la medida de bytes ahorrados sea real y no estimada.
    """
    result = {}
    sizes = {}
    total = 0
    if not root.is_dir() or root.is_symlink():
        raise EvidenceError('raíz ausente o symlink: ' + prefix)
    with os.scandir(root) as entries:
        for entry in sorted(entries, key=lambda item: item.name):
            name = entry.name
            path = Path(entry.path)
            if '\x00' in name:
                raise EvidenceError('nombre inválido en ' + prefix)
            relative = prefix + name
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                # Un symlink dentro del árbol inventariado permite falsificar la
                # ruta cotejada: anula el inventario entero, no la entrada.
                raise EvidenceError('symlink en el inventario: ' + relative)
            if stat.S_ISDIR(info.st_mode):
                if name in GENERATED_NAMES:
                    continue
                sub_files, sub_sizes = _walk_folders(path, relative + '/')
                result.update(sub_files)
                sizes.update(sub_sizes)
                continue
            if not stat.S_ISREG(info.st_mode):
                raise EvidenceError('entrada no regular: ' + relative)
            if info.st_size > MAX_FILE_BYTES:
                raise EvidenceError('fichero excede el tope: ' + relative)
            total += info.st_size
            if total > MAX_TOTAL_BYTES or len(result) >= MAX_FILES:
                raise EvidenceError('inventario excede los topes')
            data = path.read_bytes()
            if len(data) != info.st_size:
                raise EvidenceError('fichero cambió durante la lectura: ' + relative)
            result[relative] = _digest(data)
            sizes[relative] = info.st_size
    return result, sizes


def _read_bounded_json(path, limit):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        return None
    try:
        value = json.loads(path.read_bytes().decode('utf-8'))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _workspace(workspace):
    """Workspace y producto canónicos, resueltos sin confiar en la ruta plana."""
    path = Path(workspace)
    if not path.is_dir() or path.is_symlink():
        raise EvidenceError('workspace ausente o symlink')
    try:
        resolved = path.resolve()
    except OSError as error:
        raise EvidenceError('workspace no resoluble') from error
    if not resolved.is_dir() or not resolved.is_absolute():
        raise EvidenceError('workspace no resoluble')
    identity = _read_bounded_json(resolved / IDENTITY_NAME, 64 * 1024)
    if identity is None or not isinstance(identity.get('project'), str):
        raise EvidenceError('project.json ausente o ilegible')
    product = Path(identity['project'])
    if product.is_symlink() or not product.is_absolute() or not product.is_dir():
        raise EvidenceError('producto ausente, symlink o no absoluto')
    return resolved, product


def _base(product):
    """Revisión exacta del producto; sin ella no hay memoria utilizable."""
    try:
        proc = subprocess.run(['git', '-C', str(product), 'rev-parse', '--verify', 'HEAD'],
                              capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise EvidenceError('base no verificable: ' + str(error)) from error
    base = proc.stdout.decode('utf-8', 'replace').strip() if proc.stdout else None
    if proc.returncode != 0 or not base or len(base) not in (40, 64):
        raise EvidenceError('base no verificable')
    return base


SKILL_ROOTS = ('.claude/skills', '.dsh/skills', 'skills')
SKILL_ENTRY_LIMIT = 2000
MAX_CONFIG_FILES = 16


def _bounded_tree_digest(root):
    """Huella de un árbol de skills: ruta + sha256 por fichero.

    Un symlink se registra por su destino, nunca se sigue: un skills que
    apuntara a otro árbol deja una huella distinta y no puede colarse como el
    mismo. Tope de entradas para que un árbol enorme no convierta el arranque
    de la campaña en una lectura larga (superado el tope, falla cerrada).
    """
    if os.path.islink(root) or not os.path.isdir(root):
        return 'ausente'
    entries = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(dirnames):
            path = os.path.join(dirpath, name)
            entries.append((os.path.relpath(path, root), 'd',
                            os.readlink(path) if os.path.islink(path) else ''))
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                entries.append((os.path.relpath(path, root), 'l',
                                os.readlink(path)))
                continue
            try:
                with open(path, 'rb') as stream:
                    data = stream.read(MAX_FILE_BYTES)
            except OSError:
                entries.append((os.path.relpath(path, root), 'x', 'ilegible'))
                continue
            entries.append((os.path.relpath(path, root), 'f', _digest(data)))
    if len(entries) > SKILL_ENTRY_LIMIT:
        raise EvidenceError('skills por encima del tope de entradas')
    return _digest(_canonical(entries).encode('utf-8'))


def _config_digest(workspace, base):
    """Huella de lo que condiciona la interpretación y no es el código.

    Cubre la configuración gestionada del workspace, las skills activas y la
    revisión del producto: cambia cualquiera de las tres y la memoria anterior
    deja de describir lo que esta campaña revisaría, así que se invalida el
    grupo entero en lugar de confiar en una parte que ya no se corresponde.
    """
    pieces = ['base:' + base]
    for name in CONFIG_FILES:
        value = _read_bounded_json(workspace / name, 512 * 1024)
        pieces.append(name + ':' + (_canonical(value) if value is not None else 'ausente'))
    for root in SKILL_ROOTS:
        pieces.append(root + ':' + _bounded_tree_digest(str(Path(workspace) / root)))
    return _digest('\n'.join(pieces).encode('utf-8'))


def snapshot(workspace):
    """Inventario verificado del producto con el contexto que lo condiciona."""
    workspace, product = _workspace(workspace)
    base = _base(product)
    files, sizes = _walk_folders(product)
    return {'version': SNAPSHOT_VERSION,
            'workspace': str(workspace.resolve()),
            'product': str(product.resolve()),
            'base': base,
            'config': _config_digest(workspace, base),
            'files': files, 'sizes': sizes}


def _valid_snapshot(value):
    return (isinstance(value, dict) and value.get('version') == SNAPSHOT_VERSION
            and all(isinstance(value.get(key), str)
                    for key in ('workspace', 'product', 'base', 'config'))
            and isinstance(value.get('files'), dict)
            and all(isinstance(path, str) and isinstance(digest, str)
                    and len(digest) == 64 for path, digest in value['files'].items()))


def reconcile(previous, current):
    """Compara dos snapshots: aciertos, fallos, invalidaciones y bytes medidos.

    Contexto distinto (producto, base, configuración...): todo el grupo anterior
    queda invalidado; nunca se reutiliza parcialmente. La medida de coste es
    `bytes_saved`, la suma real de los tamaños de los ficheros idénticos;
    `tokens_saved` se queda en None porque el Host no cuenta tokens.
    """
    if not _valid_snapshot(previous) or not _valid_snapshot(current):
        raise EvidenceError('snapshot inválido')
    if any(previous[key] != current[key]
           for key in ('workspace', 'product', 'base', 'config')):
        return {'hits': [], 'misses': [],
                'invalidated': sorted(previous['files']),
                'reason': 'contexto distinto: producto, base, configuración o skills',
                'bytes_saved': 0, 'tokens_saved': None}
    hits = sorted(path for path, digest in current['files'].items()
                  if previous['files'].get(path) == digest)
    misses = sorted(path for path in current['files']
                    if previous['files'].get(path) != current['files'][path])
    sizes = current.get('sizes') or {}
    return {'hits': hits, 'misses': misses,
            'invalidated': sorted(set(previous['files']) - set(current['files'])),
            'reason': None,
            'bytes_saved': sum(sizes.get(path, 0) for path in hits),
            'tokens_saved': None}


def publishes_memory(journal_tail_kind):
    """¿Puede esta ejecución publicar memoria? Solo tras RUN_COMPLETED.

    `journal_tail_kind` es el kind del último registro que el run escribió.
    Cualquier otro valor —RETAINED incluido, y None de un run que no cerró—
    devuelve False: la pista no puede sobrevivir a una campaña que no terminó.
    """
    return journal_tail_kind == 'RUN_COMPLETED'


def publish(workspace, target):
    """Escribe la memoria compartida en `target` (run_root), sin sobrescribir.

    Solo se llama tras RUN_COMPLETED, y falla con EvidenceError si la memoria
    existe ya con otro contenido: dos campañas no comparten escritura. El
    fallo jamás interrumpe el run que ya completó.
    """
    value = snapshot(workspace)
    data = (_canonical({'kind': MEMORY_KIND, 'version': MEMORY_VERSION,
                        'workspace': value['workspace'],
                        'product': value['product'], 'base': value['base'],
                        'config': value['config'],
                        'files': value['files'],
                        'sizes': value['sizes']}) + '\n').encode('utf-8')
    if len(data) > MAX_MEMORY_BYTES:
        raise EvidenceError('memoria demasiado grande')
    target = Path(target)
    if target.is_symlink():
        raise EvidenceError('memoria en symlink: ' + str(target))
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if target.exists():
        # Reanudación o campaña siguiente con el producto intacto: la memoria
        # ya publicada es la misma, y reescribirla no aporta nada. Si difiere,
        # es memoria ajena y no se pisa: la campaña que quiera publicar abrirá
        # memoria nueva o dejará la anterior para inspección.
        try:
            current = target.read_bytes()
        except OSError as error:
            raise EvidenceError('memoria existente ilegible') from error
        if current != data:
            raise EvidenceError('memoria existente con contenido distinto')
        return target
    try:
        with open(target, 'xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise EvidenceError('memoria creada por otro escritor') from error
    return target


def read_memory(path):
    """Lee la memoria compartida; None si no existe o está mal formada."""
    value = _read_bounded_json(Path(path), MAX_MEMORY_BYTES)
    if (value is None or value.get('kind') != MEMORY_KIND
            or value.get('version') != MEMORY_VERSION
            or not isinstance(value.get('files'), dict)
            or not all(isinstance(key, str) and isinstance(item, str) and len(item) == 64
                       for key, item in value['files'].items())):
        return None
    return value


def memory_sizes(path):
    """Tamaños por ruta que la memoria publicó; vacío si la memoria es ilegible.

    Solo se usa para medir `bytes_saved` sin volver a leer el producto, y un
    valor ausente o inválido deja la medida en 0 en lugar de estimarse.
    """
    value = read_memory(path)
    sizes = value.get('sizes') if value is not None else None
    if (not isinstance(sizes, dict)
            or any(not isinstance(key, str) or not isinstance(item, int)
                   or isinstance(item, bool) or item < 0
                   for key, item in sizes.items())):
        return {}
    return {key: item for key, item in sizes.items() if key in (value['files'] if value else {})}


def reconcile_hint(workspace, target):
    """Payload listo para MEMORY_RECONCILED: pista numérica, nunca autoridad.

    Sin memoria previa (primera campaña) o con memoria ilegible, la campaña
    arranca sin memoria y lo dice con misses = tamaño del inventario.
    """
    current = snapshot(workspace)
    previous = read_memory(target)
    if previous is None:
        return {'workspace': current['workspace'], 'product': current['product'],
                'base': current['base'], 'hits': 0,
                'misses': len(current['files']), 'invalidated': 0,
                'bytes_saved': 0, 'tokens_saved': None}
    outcome = reconcile({'version': SNAPSHOT_VERSION,
                         'workspace': previous.get('workspace', current['workspace']),
                         'product': previous.get('product', current['product']),
                         'base': previous.get('base', current['base']),
                         'config': previous.get('config', current['config']),
                         'files': previous['files']}, current)
    return {'workspace': current['workspace'], 'product': current['product'],
            'base': current['base'], 'hits': len(outcome['hits']),
            'misses': len(outcome['misses']),
            'invalidated': len(outcome['invalidated']),
            'bytes_saved': outcome['bytes_saved'],
            'tokens_saved': outcome['tokens_saved']}
