#!/usr/bin/env python3
"""Contratos deterministas para ciclos de auditoría y reparación externa."""
import hashlib
import json
from pathlib import Path

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


def _relative_files(root, files):
    root = checked(root)
    if not root.is_dir() or not isinstance(files, list) or not files:
        raise ValueError('Raíz o archivos inválidos')
    paths = []
    for raw in files:
        if not isinstance(raw, str):
            raise ValueError('Archivo inválido')
        p = Path(raw)
        if p.is_absolute() or '..' in p.parts or str(p) != raw:
            raise ValueError('Traversal o ruta absoluta')
        absolute = checked(root / p)
        if not absolute.is_file() or absolute.is_symlink():
            raise ValueError(f'Archivo no regular: {raw}')
        paths.append(raw)
    return tuple(paths)


def validate_units(root, units):
    root = checked(root)
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


def consolidate(root, cycle_id, base_revision, units, findings):
    validate_units(root, units)
    if not isinstance(cycle_id, str) or not cycle_id or not isinstance(base_revision, str) or not base_revision:
        raise ValueError('Ciclo o base inválidos')
    if not isinstance(findings, list):
        raise ValueError('Hallazgos inválidos')
    unique = {}
    for finding in findings:
        if not isinstance(finding, dict) or not finding.get('fingerprint'):
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
    return {
        'version': 1,
        'cycle_id': cycle_id,
        'base_revision': base_revision,
        'status': 'AUDIT_COMPLETE_WITH_RETAINED_ITEMS' if any(v.get('status') != 'READY_FOR_REPAIR' for v in unique.values()) else 'AUDIT_COMPLETE',
        'units': units,
        'findings': list(unique.values()),
        'repair_queue': active,
    }


def write_consolidated(root, cycle_id, base_revision, manifest, findings):
    root = checked(root)
    cycle = root / 'cycles' / cycle_id
    if cycle.exists():
        raise FileExistsError(cycle)
    if not isinstance(manifest, dict) or manifest.get('version') != 1:
        raise ValueError('Manifiesto v1 inválido')
    units = manifest.get('units')
    result = consolidate(Path(manifest['root']), cycle_id, base_revision, units, findings)
    cycle.mkdir(mode=0o700, parents=True)
    write_new(cycle / 'audit-manifest.json', result)
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
    if args.action == 'consolidate':
        manifest = read(args.manifest)
        findings = read(args.findings).get('findings')
        if not isinstance(findings, list):
            raise ValueError('findings debe ser una lista')
        result = write_consolidated(args.root, args.cycle_id, args.base_revision, manifest, findings)
    else:
        result = archive_cycle(args.root, args.cycle_id, read(args.summary), read(args.manifest))
    print(json.dumps(result, ensure_ascii=False, indent=2))


def archive_cycle(root, cycle_id, summary, manifest):
    root = checked(root)
    archive = root / 'archive' / cycle_id
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
