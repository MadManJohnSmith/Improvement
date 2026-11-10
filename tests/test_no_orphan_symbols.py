"""Nada público queda huérfano: la auditoría E14 convertida en mecanismo.

E14 ("siete funciones públicas sin un solo llamador de producto") se cerró a
mano y la maleza volvió: `workflow_evidence.memory_sizes` y
`workflow_reasoning.normalize_level` volvieron a ser huérfanos, con
docstrings que afirmaban un uso inexistente. Este canary corre el mismo pase
AST para siempre: todo símbolo público de nivel superior (función o clase)
de `scripts/` y `eval/` debe tener una referencia cualificada en el árbol o
estar en ALLOWLIST con su motivo.

Cualificada: el fichero que usa el símbolo debe importar el módulo que lo
define (y nombrar al símbolo), o ser el propio módulo usando su símbolo por
dentro — la cadena interna de un módulo sin puerta de entrada muere en su
primer eslabón, que es el que se nombra. Los docstrings no cuentan: narrar
un propósito no es tenerlo. El pase es tolerante con colisiones de nombres
dentro de un fichero que ya importa el módulo: el error caro es señalar
trabajo vivo, no dejar pasar uno muerto.
"""
import ast
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ('scripts', 'eval')

# Superficies declaradas sin llamador hoy. Cada entrada nombra la deuda; una
# entrada que deja de ser verdad (se borra o se cablea) debe salir de aquí.
ALLOWLIST = {
    'capabilities.reusable': 'módulo de capability sin puerta de entrada '
                             'cableada: decisión del mantenedor entre borrar '
                             'el plano o cablearlo',
}


def _imports_and_names(source):
    """(módulos importados, nombres usados) de un fichero, por AST."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set(), set()
    imported, names = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Import):
            imported.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split('.')[0])
            names.update(alias.name for alias in node.names)
    return imported, names


def public_symbols(root=REPO_ROOT, scan_dirs=SCAN_DIRS):
    """Símbolos públicos de nivel superior cualificados módulo.símbolo."""
    symbols = []
    for folder in scan_dirs:
        for path in sorted((root / folder).glob('*.py')):
            try:
                tree = ast.parse(path.read_text(encoding='utf-8'))
            except SyntaxError:
                continue
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) \
                        and not node.name.startswith('_'):
                    symbols.append(f'{path.stem}.{node.name}')
    return symbols


def orphan_symbols(root=REPO_ROOT, scan_dirs=SCAN_DIRS):
    """Símbolos públicos sin referencia cualificada en el árbol."""
    files = {}
    for folder in (*scan_dirs, 'tests'):
        for path in sorted((root / folder).glob('*.py')):
            files[path.stem] = _imports_and_names(path.read_text(
                encoding='utf-8'))
    orphans = []
    for qualified in public_symbols(root, scan_dirs):
        module, symbol = qualified.split('.', 1)
        referenced = False
        for stem, (imported, names) in files.items():
            uses_module = module in imported or stem == module
            if uses_module and symbol in names:
                referenced = True
                break
        if not referenced and qualified not in ALLOWLIST:
            orphans.append(qualified)
    return sorted(orphans)


class NoOrphanPublicSymbolsTests(unittest.TestCase):
    """La clase de defecto E14 muere aquí: huérfano nuevo = suite roja."""

    def test_every_public_symbol_has_a_reference_or_a_named_debt(self):
        orphans = orphan_symbols()
        self.assertEqual(
            orphans, [],
            'símbolos públicos sin llamador: bórralos, cablealos o '
            'decláralos en ALLOWLIST con motivo')

    def test_the_allowlist_only_names_symbols_that_still_exist(self):
        """Una deuda saldada (borrada o cableada) sale de la lista; una
        entrada que nombra un símbolo inexistente es prosa podrida."""
        alive = set(public_symbols())
        stale = sorted(entry for entry in ALLOWLIST if entry not in alive)
        self.assertEqual(
            stale, [],
            'entradas de ALLOWLIST para símbolos que ya no existen')

    def test_the_pass_itself_catches_a_planted_orphan(self):
        """El detector detecta: un símbolo huérfano plantado en un árbol
        sintético es nombrado, y no lo es el que sí tiene llamador."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'scripts').mkdir()
            (root / 'eval').mkdir()
            (root / 'tests').mkdir()
            (root / 'scripts' / 'planta.py').write_text(
                'def orphan_sin_uso():\n'
                '    """Se usa para medir algo, dice el docstring."""\n'
                '    return 1\n'
                '\n'
                '\n'
                'def usada():\n'
                '    return 2\n')
            (root / 'tests' / 'test_planta.py').write_text(
                'import planta\n'
                'planta.usada()\n')
            found = orphan_symbols(root, ('scripts',))
            self.assertIn('planta.orphan_sin_uso', found)
            self.assertNotIn('planta.usada', found)

    def test_an_internal_chain_dies_at_its_unwired_entry(self):
        """load/validate/fingerprint se llaman por dentro, pero si nadie
        importa el módulo, la puerta es `reusable` y es la que se nombra."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'scripts').mkdir()
            (root / 'eval').mkdir()
            (root / 'tests').mkdir()
            (root / 'scripts' / 'cadena.py').write_text(
                'def _baja():\n'
                '    return 1\n'
                '\n'
                '\n'
                'def media():\n'
                '    return _baja()\n'
                '\n'
                '\n'
                'def puerta():\n'
                '    return media()\n')
            found = orphan_symbols(root, ('scripts',))
            self.assertEqual(found, ['cadena.puerta'])


if __name__ == '__main__':
    unittest.main()
