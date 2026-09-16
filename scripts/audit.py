#!/usr/bin/env python3
"""Contratos deterministas para ciclos de auditoría y reparación externa."""
import hashlib
import json
from pathlib import Path
import re
import stat

from onboard import checked

UNIT_STATES = {'PLANNED', 'AUDITING', 'ACCEPTED', 'RETAINED', 'UNVERIFIED', 'STALE'}
FINDING_STATES = {'READY_FOR_REPAIR', 'RETAINED', 'UNVERIFIED', 'DUPLICATE', 'NEEDS_DECISION', 'STALE'}
CYCLE_STATES = {'PLANNED', 'AUDITING', 'AUDIT_COMPLETE', 'REPAIRING', 'QA_PENDING',
                'REAUDIT_PENDING', 'CYCLE_REVIEW', 'CYCLE_COMPLETE', 'ARCHIVED',
                'RETAINED', 'UNVERIFIED', 'BLOCKED', 'STALE', 'INTERRUPTED', 'RECOVERY_REQUIRED'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    path = checked(path)
    if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Artefacto ausente o demasiado grande')
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('Se requiere objeto JSON')
    return value


def write_new(path, value):
    path = checked(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def _relative_name(raw):
    if not isinstance(raw, str) or not raw or '\x00' in raw:
        raise ValueError('Ruta relativa inválida')
    path = Path(raw)
    if path.is_absolute() or '..' in path.parts or str(path) != raw or raw == '.':
        raise ValueError('Traversal o ruta relativa no canónica')
    return path


def inventory(root, exclusions=None):
    """Snapshot regular files without reading explicitly excluded subtrees."""
    root = checked(root).resolve()
    if not root.is_dir():
        raise ValueError('Raíz de inventario inválida')
    if exclusions is None:
        exclusions = {}
    if not isinstance(exclusions, dict):
        raise ValueError('Exclusiones deben ser un mapa ruta a motivo')
    for name, reason in exclusions.items():
        _relative_name(name)
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('Exclusión sin justificación')
    files, excluded = {}, {}

    def visit(directory):
        for path in sorted(directory.iterdir()):
            checked(path)
            name = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise ValueError(f'Entrada no regular: {name}')
            if name in exclusions:
                excluded[name] = {
                    'kind': 'directory' if stat.S_ISDIR(mode) else 'file',
                    'reason': exclusions[name],
                }
            elif stat.S_ISDIR(mode):
                visit(path)
            else:
                sha = hashlib.sha256()
                with path.open('rb') as stream:
                    for block in iter(lambda: stream.read(65536), b''):
                        sha.update(block)
                files[name] = sha.hexdigest()

    visit(root)
    if set(excluded) != set(exclusions):
        raise ValueError('Exclusión ausente o anidada bajo otra exclusión')
    return {'version': 1, 'files': files, 'exclusions': excluded}


def validate_coverage(root, owners, snapshot):
    if snapshot is None:
        return {'status': 'UNVERIFIED', 'coverage_gaps': ['INVENTORY_MISSING']}
    if (not isinstance(snapshot, dict) or snapshot.get('version') != 1
            or not isinstance(snapshot.get('files'), dict)
            or not isinstance(snapshot.get('exclusions'), dict)):
        raise ValueError('Inventario v1 inválido')
    exclusions = {}
    for name, entry in snapshot['exclusions'].items():
        if not isinstance(entry, dict) or set(entry) != {'kind', 'reason'}:
            raise ValueError('Exclusión inválida')
        exclusions[name] = entry['reason']
    current = inventory(root, exclusions)
    if current != snapshot:
        raise ValueError('Inventario obsoleto o alterado')
    if set(owners) - set(current['files']):
        raise ValueError('Archivo asignado fuera del inventario incluido')
    gaps = sorted(set(current['files']) - set(owners))
    return {
        'status': 'UNVERIFIED' if gaps else 'PARTITION_VERIFIED',
        'inventory_sha256': digest(json.dumps(snapshot, sort_keys=True).encode()),
        'included_files': len(current['files']),
        'assigned_files': len(owners),
        'excluded_entries': len(exclusions),
        'coverage_gaps': gaps,
    }


def _relative_files(root, files):
    root = checked(root).resolve()
    if not root.is_dir() or not isinstance(files, list) or not files:
        raise ValueError('Raíz o archivos inválidos')
    paths = []
    for raw in files:
        if not isinstance(raw, str):
            raise ValueError('Archivo inválido')
        p = _relative_name(raw)
        if raw in paths:
            raise ValueError('Archivo duplicado en unidad')
        absolute = checked(root / p)
        if not absolute.is_file() or absolute.is_symlink():
            raise ValueError(f'Archivo no regular: {raw}')
        paths.append(raw)
    return tuple(paths)


def validate_units(root, units):
    root = checked(root).resolve()
    if not isinstance(units, list) or not units:
        raise ValueError('Unidades ausentes')
    seen = set()
    owners = {}
    for unit in units:
        if not isinstance(unit, dict) or not isinstance(unit.get('unit_id'), str):
            raise ValueError('Unidad inválida')
        unit_id = unit['unit_id']
        if unit_id in seen or unit.get('status', 'PLANNED') not in UNIT_STATES:
            raise ValueError('Unidad duplicada o estado inválido')
        seen.add(unit_id)
        files = _relative_files(root, unit.get('files'))
        for name in files:
            if name in owners and owners[name] != unit_id:
                raise ValueError(f'Solapamiento no declarado: {name}')
            owners[name] = unit_id
    graph = {u['unit_id']: set(u.get('depends_on', [])) for u in units}
    if any(dep not in graph or dep == name for name, deps in graph.items() for dep in deps):
        raise ValueError('Dependencia desconocida o autorreferente')
    _assert_acyclic(graph)
    return owners


def _assert_acyclic(graph):
    visiting, visited = set(), set()

    def visit(node):
        if node in visiting:
            raise ValueError('Dependencias circulares')
        if node in visited:
            return
        visiting.add(node)
        for child in graph[node]:
            visit(child)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def _cycle_id(cycle_id):
    if not isinstance(cycle_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', cycle_id):
        raise ValueError('Ciclo inválido')
    return cycle_id


def consolidate(root, cycle_id, base_revision, units, findings, snapshot=None):
    _cycle_id(cycle_id)
    owners = validate_units(root, units)
    if not isinstance(base_revision, str) or not base_revision.strip():
        raise ValueError('Base inválida')
    coverage = validate_coverage(root, owners, snapshot)
    coverage['pending_units'] = [u['unit_id'] for u in units if u.get('status') != 'ACCEPTED']
    if not isinstance(findings, list):
        raise ValueError('Hallazgos inválidos')
    unique = {}
    for finding in findings:
        if (not isinstance(finding, dict) or not isinstance(finding.get('fingerprint'), str)
                or not finding['fingerprint'].strip()):
            raise ValueError('Hallazgo sin fingerprint')
        state = finding.get('status')
        if state not in FINDING_STATES:
            raise ValueError('Estado de hallazgo inválido')
        key = finding['fingerprint']
        if key not in unique:
            unique[key] = dict(finding)
        elif state == 'READY_FOR_REPAIR' and unique[key].get('status') != 'READY_FOR_REPAIR':
            unique[key] = dict(finding)
        elif unique[key].get('status') == 'READY_FOR_REPAIR':
            unique[key]['status'] = 'READY_FOR_REPAIR'
        else:
            unique[key]['status'] = 'DUPLICATE'
    active = [v for v in unique.values() if v.get('status') == 'READY_FOR_REPAIR']
    if coverage['status'] != 'PARTITION_VERIFIED' or coverage['pending_units']:
        status = 'UNVERIFIED'
    else:
        status = 'AUDIT_COMPLETE_WITH_RETAINED_ITEMS' if any(v.get('status') != 'READY_FOR_REPAIR' for v in unique.values()) else 'AUDIT_COMPLETE'
    return {
        'version': 1,
        'cycle_id': cycle_id,
        'base_revision': base_revision,
        'status': status,
        'inventory': snapshot,
        'coverage': coverage,
        'units': units,
        'findings': list(unique.values()),
        'repair_queue': active,
    }


def write_consolidated(root, cycle_id, base_revision, manifest, findings):
    root = checked(root).resolve()
    cycle = checked(root / 'cycles' / _cycle_id(cycle_id))
    if cycle.exists():
        raise FileExistsError(cycle)
    if not isinstance(manifest, dict) or manifest.get('version') != 1:
        raise ValueError('Manifiesto v1 inválido')
    units = manifest.get('units')
    product = checked(manifest['root']).resolve()
    if root == product or product in root.parents or root in product.parents:
        raise ValueError('Workspace debe ser externo al producto')
    result = consolidate(product, cycle_id, base_revision, units, findings, manifest.get('inventory'))
    cycle.mkdir(mode=0o700, parents=True)
    write_new(cycle / 'audit-manifest.json', result)
    write_new(cycle / 'coverage-matrix.json', result['coverage'])
    write_new(cycle / 'repair-queue.json', {'version': 1, 'cycle_id': cycle_id,
                                             'base_revision': base_revision,
                                             'findings': result['repair_queue']})
    write_new(root / 'active' / 'current-cycle.json', {'version': 1, 'cycle_id': cycle_id,
                                                        'base_revision': base_revision,
                                                        'status': result['status']})
    write_new(root / 'active' / 'repair-queue.json', {'version': 1, 'cycle_id': cycle_id,
                                                       'base_revision': base_revision,
                                                       'findings': result['repair_queue']})
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    inventory_cmd = sub.add_parser('inventory')
    inventory_cmd.add_argument('--product', required=True)
    inventory_cmd.add_argument('--exclusions', help='Objeto JSON {ruta relativa: motivo}')
    consolidate_cmd = sub.add_parser('consolidate')
    consolidate_cmd.add_argument('--root', required=True)
    consolidate_cmd.add_argument('--manifest', required=True)
    consolidate_cmd.add_argument('--findings', required=True)
    consolidate_cmd.add_argument('--cycle-id', required=True)
    consolidate_cmd.add_argument('--base-revision', required=True)
    archive_cmd = sub.add_parser('archive')
    archive_cmd.add_argument('--root', required=True)
    archive_cmd.add_argument('--cycle-id', required=True)
    archive_cmd.add_argument('--summary', required=True)
    archive_cmd.add_argument('--manifest', required=True)
    args = parser.parse_args()
    if args.action == 'inventory':
        result = inventory(args.product, read(args.exclusions) if args.exclusions else {})
    elif args.action == 'consolidate':
        manifest = read(args.manifest)
        findings = read(args.findings).get('findings')
        if not isinstance(findings, list):
            raise ValueError('findings debe ser una lista')
        result = write_consolidated(args.root, args.cycle_id, args.base_revision, manifest, findings)
    else:
        result = archive_cycle(args.root, args.cycle_id, read(args.summary), read(args.manifest))
    print(json.dumps(result, ensure_ascii=False, indent=2))


def archive_cycle(root, cycle_id, summary, manifest):
    root = checked(root).resolve()
    archive = checked(root / 'archive' / _cycle_id(cycle_id))
    if archive.exists():
        raise FileExistsError(archive)
    archive.mkdir(mode=0o700, parents=True)
    write_new(archive / 'summary.json', summary)
    write_new(archive / 'manifest.json', manifest)
    index = {'version': 1, 'cycle_id': cycle_id,
             'summary_sha256': digest((archive / 'summary.json').read_bytes()),
             'manifest_sha256': digest((archive / 'manifest.json').read_bytes()),
             'warning': 'Detalle histórico no se carga automáticamente; referencias absolutas pueden ser antiguas.'}
    write_new(archive / 'index.json', index)
    return index


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f'RETAINED: {error}')
