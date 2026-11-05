#!/usr/bin/env python3
"""Lector delegado del Host: vista compacta y byte-anclada de un rango de archivo.

Contrato ratificado (2026-11-05): toda vista lleva ruta relativa, sha256 del
archivo completo, rango de líneas, total de líneas y el excerpt exacto. El texto
íntegro permanece en disco: la vista no lo copia ni lo resume en prosa. Un rango
que no puede anclarse se rechaza con nombre; nunca se devuelve una síntesis.

Uso:
    python3 -B scripts/read_view.py --root <producto> --path <rel> [--start N] [--end M]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

DEFAULT_MAX_CHARS = 65536


def _relative(raw):
    if not isinstance(raw, str) or not raw or '\x00' in raw or '\\' in raw:
        raise ValueError('Ruta relativa inválida')
    path = Path(raw)
    if path.is_absolute() or '..' in path.parts or str(path) != raw or raw == '.':
        raise ValueError('Ruta relativa inválida')
    return path


def build(root, relative, *, start=None, end=None, max_chars=DEFAULT_MAX_CHARS):
    """Devuelve la vista anclada del rango pedido; el original no se toca."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError('Raíz inválida')
    target = root / _relative(relative)
    try:
        target.resolve().relative_to(root)
    except ValueError as error:
        raise ValueError('Ruta fuera del producto') from error
    if not target.is_file():
        raise ValueError('Archivo ausente o no regular')
    raw = target.read_bytes()
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as error:
        raise ValueError('Archivo binario: no se delega su lectura') from error
    if '\x00' in text:
        raise ValueError('Archivo binario: no se delega su lectura')
    # Exact slice: split on LF only, keep CR and other separators inside lines,
    # and drop only the trailing terminator that ends the file.
    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    total = len(lines)
    if total == 0:
        if start not in (None, 1) or end not in (None, 0):
            raise ValueError('Rango fuera del archivo')
        start, end = 0, 0
    else:
        if start is None:
            start = 1
        if end is None:
            end = total
        for value in (start, end):
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError('Rango inválido')
        if start < 1 or end < start or end > total:
            raise ValueError('Rango fuera del archivo')
    if not isinstance(max_chars, int) or isinstance(max_chars, bool) or max_chars < 1:
        raise ValueError('Cota inválida')
    excerpt = '\n'.join(lines[start - 1:end]) if total else ''
    if len(excerpt) > max_chars:
        raise ValueError('Vista por encima de la cota; pide un rango menor')
    return {
        'path': relative,
        'sha256': hashlib.sha256(raw).hexdigest(),
        'start': start,
        'end': end,
        'total_lines': total,
        'excerpt': excerpt,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='read_view.py',
        description='Vista byte-anclada de un rango: ruta, sha256, rango y excerpt exacto.')
    parser.add_argument('--root', required=True)
    parser.add_argument('--path', required=True)
    parser.add_argument('--start', type=int)
    parser.add_argument('--end', type=int)
    parser.add_argument('--max-chars', type=int, default=DEFAULT_MAX_CHARS)
    args = parser.parse_args(argv)
    try:
        view = build(args.root, args.path, start=args.start, end=args.end,
                     max_chars=args.max_chars)
    except (OSError, ValueError) as error:
        print('read_view: %s' % error, file=sys.stderr)
        return 2
    print(json.dumps(view, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
