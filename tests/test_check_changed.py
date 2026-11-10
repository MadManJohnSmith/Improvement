"""La puerta rápida se prueba a sí misma: sin mapa podrido ni hook fantasma.

`scripts/check_changed.py` concentra el conocimiento módulo→tests detrás de
una interfaz. Este fichero fija su contrato: derivación transitiva por
importación, overrides con motivo, canaries permanentes, cobertura total de
`scripts/` y `eval/`, y un hook pre-push que hace preflight antes de correr
la suite completa (la retro del 2026-11-06 versionó el hook; este canary
impide que vuelva a ser un fantasma o que pierda la suite como última
puerta).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
import check_changed  # noqa: E402


class ImportMapTests(unittest.TestCase):
    """La derivación transitiva: quien importa al importador, ejercita al
    importado."""

    def _fake_repo(self, tmp):
        root = Path(tmp)
        (root / 'scripts').mkdir()
        (root / 'eval').mkdir()
        (root / 'tests').mkdir()
        (root / 'scripts' / 'a.py').write_text('import b\n')
        (root / 'scripts' / 'b.py').write_text('X = 1\n')
        (root / 'tests' / 'test_a.py').write_text('import a\n')
        (root / 'tests' / 'test_b.py').write_text('import b\n')
        return root

    def test_a_test_exercises_the_module_it_imports_and_its_importees(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._fake_repo(tmp)
            with mock.patch.object(check_changed, 'REPO_ROOT', root), \
                 mock.patch.object(check_changed, 'TESTS_DIR',
                                   root / 'tests'):
                mapping = check_changed.build_import_map()
            # test_b importa b directamente; test_a no importa b, pero a sí.
            self.assertEqual(mapping['b'],
                             {'test_a.py', 'test_b.py'})
            self.assertEqual(mapping['a'], {'test_a.py'})

    def test_a_module_reached_by_nothing_does_not_enter_the_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._fake_repo(tmp)
            (root / 'scripts' / 'orphan.py').write_text('Y = 2\n')
            with mock.patch.object(check_changed, 'REPO_ROOT', root), \
                 mock.patch.object(check_changed, 'TESTS_DIR',
                                   root / 'tests'):
                mapping = check_changed.build_import_map()
            self.assertNotIn('orphan', mapping)


class ResolveAffectedTests(unittest.TestCase):
    """Selección determinista: cada fichero entra con su motivo nombrado."""

    def _resolve(self, changed, import_map=None, test_names=('test_a.py',)):
        import_map = import_map or {}
        with tempfile.TemporaryDirectory() as tmp:
            fake_tests = Path(tmp)
            for name in test_names:
                (fake_tests / name).write_text('')
            with mock.patch.object(check_changed, 'TESTS_DIR', fake_tests):
                return check_changed.resolve_affected(changed, import_map)

    def test_the_permanent_canaries_always_run(self):
        selected, uncovered = self._resolve([])
        for name in check_changed.CANARY_ALWAYS:
            self.assertEqual(selected[name], 'canary permanente')
        self.assertEqual(uncovered, [])

    def test_a_changed_test_file_runs_itself(self):
        selected, _ = self._resolve(['tests/test_a.py'])
        self.assertEqual(selected['test_a.py'], 'fichero de test cambiado')

    def test_an_override_selects_its_tests_naming_the_reason(self):
        key = next(iter(check_changed.OVERRIDES))
        entry = check_changed.OVERRIDES[key]
        selected, _ = self._resolve([key], {}, test_names=(
            'test_architecture_consistency.py',))
        for test_file in entry['tests']:
            self.assertIn('override:', selected[test_file])

    def test_an_uncovered_module_comes_back_named(self):
        selected, uncovered = self._resolve(['scripts/sin_mapa.py'], {})
        self.assertEqual(uncovered, ['scripts/sin_mapa.py'])
        self.assertNotIn('test_a.py', selected)

    def test_a_module_covered_by_its_own_override_is_not_a_gap(self):
        path = 'scripts/capabilities.py'
        self.assertIn(path, check_changed.OVERRIDES)
        selected, uncovered = self._resolve([path], {})
        self.assertEqual(uncovered, [])


class CoverageCanaryTests(unittest.TestCase):
    """El mapa no puede pudrirse: todo módulo escaneado se deriva o se
    declara. Un módulo nuevo sin tests ni override rompe aquí, no en la
    puerta de un agente."""

    def test_every_scanned_module_resolves_to_tests_or_a_named_override(self):
        mapping = check_changed.build_import_map()
        stems = check_changed.script_module_stems()
        missing = sorted(
            stem for stem in stems
            if stem not in mapping
            and f'scripts/{stem}.py' not in check_changed.OVERRIDES
            and f'eval/{stem}.py' not in check_changed.OVERRIDES)
        self.assertEqual(
            missing, [],
            'módulos sin cobertura derivada ni override declarado')

    def test_every_override_declares_its_reason(self):
        for key, entry in check_changed.OVERRIDES.items():
            with self.subTest(key=key):
                self.assertTrue(entry['motivo'].strip())
                self.assertTrue(entry['tests'] or
                                'huérfano' in entry['motivo'])


class PrePushHookCanaryTests(unittest.TestCase):
    """El hook existe para actuar: preflight rápido y suite completa."""

    def test_the_hook_runs_the_fast_gate_before_the_full_suite(self):
        hook = (REPO_ROOT / 'scripts' / 'hooks' / 'pre-push').read_text(
            encoding='utf-8')
        self.assertIn('check_changed.py', hook)
        self.assertIn('merge-base', hook)
        self.assertIn('unittest discover -s tests', hook)


class CliContractTests(unittest.TestCase):
    """Contrato de salida: la selección es JSON estable y nombra canaries."""

    def test_list_json_reports_the_permanent_canaries(self):
        out = subprocess.run(
            [sys.executable, '-B', 'scripts/check_changed.py', '--list',
             '--staged', '--json'],
            capture_output=True, text=True, cwd=str(REPO_ROOT), check=True)
        payload = json.loads(out.stdout)
        self.assertEqual(payload['uncovered'], [])
        self.assertIn('test_architecture_consistency.py', payload['selected'])


if __name__ == '__main__':
    unittest.main()
