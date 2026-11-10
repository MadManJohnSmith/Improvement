#!/usr/bin/env python3
"""Puerta rápida: los tests de lo que cambió, no la suite entera.

`CODING_STANDARDS.md` exige el ciclo modular (el módulo afectado mientras se
trabaja), pero el mapeo módulo→tests era folklore de grep: `host_validator` se
prueba en `test_creator_and_validator.py` y `creator_client` en seis ficheros.
Este módulo concentra ese conocimiento detrás de una interfaz:

    python3 -B scripts/check_changed.py [--base REV | --staged] [--list] [--json]

Derivación del conjunto afectado, por orden y con su motivo:

1. Importación: cada `tests/test_*.py` se parsea con `ast` y los nombres
   importados que coinciden con módulos de `scripts/` o `eval/` ligan
   módulo→fichero de test (el mapa se deriva, no se mantiene a mano).
2. Overrides declarados (OVERRIDES): acoplamientos que la importación no
   puede ver —plugins `.mjs`, el hook, workflows— cada uno con su motivo.
3. Un fichero de test cambiado corre a sí mismo.
4. Canaries permanentes (CANARY_ALWAYS): la consistencia documental y la del
   árbol canónico re-leen docs y literales de todo el repo, así que corren
   con cualquier cambio.

Fail-closed: un módulo de `scripts/` o `eval/` sin cobertura derivada ni
override declarado aborta nombrándolo (código 2). El canary de cobertura de
`tests/test_check_changed.py` impide ese estado en la suite; esta puerta lo
impide en el ciclo. Códigos de salida: 0 verde, 1 tests en rojo, 2 mapa o
invocación rota. CI sigue siendo dueño de la suite completa; esta puerta es
el ciclo rápido del estándar y el preflight del hook pre-push.
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = REPO_ROOT / 'tests'
SCAN_DIRS = ('scripts', 'eval')

# Canaries que re-leen docs y literales de todo el árbol: corren siempre.
CANARY_ALWAYS = (
    'test_architecture_consistency.py',
    'test_canonical_tree_holds_no_run_artifacts.py',
)

# Acoplamientos que el análisis de importación no puede ver. Clave: ruta
# relativa al raíz del repo. Valor: tests que ejercitan ese fichero y el
# motivo por el que la importación no alcanza a declararlo.
OVERRIDES = {
    'scripts/dsh-plugins/workflow-write.mjs': {
        'tests': ('test_workflow_write_plugin.py',),
        'motivo': 'plugin .mjs ejercitado vía drivers de node, no importado',
    },
    'scripts/dsh-plugins/doc-drift.mjs': {
        'tests': ('test_doc_drift_plugin.py',),
        'motivo': 'plugin .mjs ejercitado vía drivers de node, no importado',
    },
    'scripts/dsh-plugins/anti-escalation.mjs': {
        'tests': ('test_creator_and_validator.py', 'test_skill_gate_run.py'),
        'motivo': 'el guard se fija por composición y texto del montaje, '
                  'no por importación',
    },
    'scripts/hooks/pre-push': {
        'tests': ('test_check_changed.py',),
        'motivo': 'shell, no Python: el canary liga hook y puerta rápida',
    },
    '.github/workflows/creator-remote-eval.yml': {
        'tests': ('test_workflow_remote_eval.py',),
        'motivo': 'contrato del workflow probado contra el YAML, sin import',
    },
    'eval/keyless_proxy.py': {
        'tests': ('test_keyless_proxy.py',),
        'motivo': 'se ejercita como servidor de subproceso, no por importación',
    },
    'scripts/capabilities.py': {
        'tests': (),
        'motivo': 'plano de capability sin puerta de entrada: deuda declarada '
                  'en el ALLOWLIST del gate de símbolos huérfanos',
    },
}


def changed_files(base=None, staged=False):
    """Rutas relativas cambiadas, deterministas, con `git -C` sobre el raíz."""
    if staged:
        cmd = ['git', '-C', str(REPO_ROOT), 'diff', '--cached', '--name-only',
               '--no-renames']
    elif base:
        cmd = ['git', '-C', str(REPO_ROOT), 'diff', '--name-only',
               '--no-renames', base]
    else:
        cmd = ['git', '-C', str(REPO_ROOT), 'diff', '--name-only',
               '--no-renames', 'HEAD']
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return sorted(line for line in out.stdout.splitlines() if line.strip())


def script_module_stems():
    """Stems de los módulos escaneables de scripts/ y eval/."""
    stems = set()
    for folder in SCAN_DIRS:
        for path in sorted((REPO_ROOT / folder).glob('*.py')):
            stems.add(path.stem)
    return stems


def build_import_map():
    """Módulo escaneado → ficheros de test que lo ejercitan (AST, sin magia).

    Transitivo: un test que importa `host_validator` ejercita también
    `layout_contract`, porque `host_validator` lo importa. El grafo interno
    de imports entre módulos escaneados se recorre al revés desde cada
    módulo; los tests de un módulo son los que importan a él o a cualquiera
    que lo alcance. Un módulo que nada alcanza no entra en el mapa: el
    canary de cobertura lo nombra y exige override o test.
    """
    stems = script_module_stems()

    def _names(source):
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split('.')[0])
        return names & stems

    internal = {}
    for folder in SCAN_DIRS:
        for path in sorted((REPO_ROOT / folder).glob('*.py')):
            internal[path.stem] = _names(path.read_text(encoding='utf-8'))

    importers = {stem: set() for stem in stems}
    for importer, targets in internal.items():
        for target in targets:
            importers[target].add(importer)

    test_direct = {}
    for test_path in sorted(TESTS_DIR.glob('test_*.py')):
        names = _names(test_path.read_text(encoding='utf-8'))
        for name in names:
            test_direct.setdefault(name, set()).add(test_path.name)

    mapping = {}
    for stem in stems:
        reached = {stem}
        stack = [stem]
        while stack:
            current = stack.pop()
            for upstream in importers.get(current, ()):
                if upstream not in reached:
                    reached.add(upstream)
                    stack.append(upstream)
        files = set()
        for name in reached:
            files |= test_direct.get(name, set())
        if files:
            mapping[stem] = files
    return mapping


def resolve_affected(changed, import_map):
    """Selección determinista con motivo por fichero, y huecos nombrados.

    Devuelve (seleccionados, sin_cubrir). Los motivos distinguen cómo entró
    cada fichero: canary fijo, override, fichero de test cambiado o mapa de
    importación. Un módulo escaneado sin mapa ni override propio es un hueco
    que se devuelve nombrado para fallar cerrado aguas arriba.
    """
    selected = {}
    test_names = {p.name for p in TESTS_DIR.glob('test_*.py')}

    def select(test_file, reason):
        if test_file not in selected:
            selected[test_file] = reason

    for name in CANARY_ALWAYS:
        select(name, 'canary permanente')
    for path in changed:
        if path in OVERRIDES:
            entry = OVERRIDES[path]
            for test_file in entry['tests']:
                select(test_file, f"override: {entry['motivo']}")
    uncovered = []
    for path in changed:
        rel = Path(path)
        if rel.parts and rel.parts[0] == 'tests' and rel.name in test_names:
            select(rel.name, 'fichero de test cambiado')
            continue
        if len(rel.parts) == 2 and rel.parts[0] in SCAN_DIRS \
                and rel.suffix == '.py':
            stem = rel.stem
            hits = import_map.get(stem, set())
            if hits:
                for test_file in sorted(hits):
                    select(test_file, f'mapa: importa {stem}')
            elif path not in OVERRIDES:
                uncovered.append(path)
    return dict(sorted(selected.items())), sorted(uncovered)


def run_selected(files):
    """Corre la selección en un proceso, con los tests/ en el sys.path."""
    sys.path.insert(0, str(TESTS_DIR))
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for name in files:
        suite.addTests(loader.loadTestsFromName(Path(name).stem))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Valida solo lo afectado por los cambios actuales.')
    parser.add_argument('--base', metavar='REV',
                        help='diff contra esa revisión (default: HEAD, '
                             'incluye staged y unstaged)')
    parser.add_argument('--staged', action='store_true',
                        help='solo lo indexado (git diff --cached)')
    parser.add_argument('--list', action='store_true',
                        help='muestra la selección sin correr nada')
    parser.add_argument('--json', action='store_true',
                        help='salida machine-parseable de la selección')
    args = parser.parse_args(argv)

    changed = changed_files(base=args.base, staged=args.staged)
    import_map = build_import_map()
    selected, uncovered = resolve_affected(changed, import_map)

    if args.json:
        print(json.dumps({
            'changed': changed,
            'selected': selected,
            'uncovered': uncovered,
        }, ensure_ascii=False, indent=2))
        return 0
    if uncovered:
        for path in uncovered:
            print(f'sin cobertura declarada: {path}', file=sys.stderr)
        print('declara un override con motivo en check_changed.py o añade '
              'el test que falta', file=sys.stderr)
        return 2
    if not changed:
        print('sin cambios; corriendo solo los canaries permanentes')
    print(f'selección ({len(selected)} ficheros):')
    for test_file, reason in selected.items():
        print(f'  {test_file}  [{reason}]')
    if args.list:
        return 0
    return run_selected(sorted(selected))


if __name__ == '__main__':
    sys.exit(main())
