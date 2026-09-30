"""Real-stack verification plan: detección, entrypoints propios y capabilities honestas.

python3 -B -m unittest tests.test_stack -v

Fixture con productos temporales (monorepo Django+Node, Flutter, proyecto sin
manifiesto) y un entorno controlado: el resolutor no ejecuta instalaciones,
solo nombra la entrypoint del producto, el estado real de cada capacidad y el
paso exacto de provisión. Sin stubs: la evidencia es el entrypoint del producto
o BLOCKED nombrando lo que falta.
"""
import json
import sys
import tempfile
import unittest

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import stack  # noqa: E402


def _product(root, files):
    product = root / 'Product'
    product.mkdir(parents=True)
    for name, content in files.items():
        path = product / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return product


class StackPlanTests(unittest.TestCase):
    maxDiff = None

    def test_django_monorepo_detects_backend_root_and_node_frontend(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product = _product(root, {
                'backend/manage.py': 'import django\n',
                'backend/requirements.txt': 'Django==6.0.2\n',
                'frontend/package-lock.json': '{}\n',
                'frontend/package.json': '{"name": "web"}\n',
            })
            value = stack.plan(product, workspace=root / 'ws')
            by_stack = {entry['stack']: entry for entry in value['stacks']}
            self.assertEqual(set(by_stack), {'python-django', 'node'})
            django = by_stack['python-django']
            self.assertEqual(django['root'], 'backend')
            self.assertEqual(django['verify_cwd'], 'backend')
            self.assertEqual(django['verify_command'][-2:], ['manage.py', 'test'])
            self.assertEqual(django['lint_command'][-1], 'check')
            self.assertTrue(django['provision_outside_product'])
            self.assertNotIn('declared', django)
            self.assertEqual(by_stack['node']['root'], 'frontend')
            self.assertEqual(by_stack['node']['verify_command'], ['npm', 'test'])
            self.assertEqual(value['evidence'], 'product-own-entrypoint-only')
            self.assertEqual(value['stubs'],
                             'investigation-material-never-verification-evidence')
            self.assertEqual(value['missing_capability'],
                             'BLOCKED-naming-capability-and-provision-step')

    def test_missing_capability_names_the_exact_provision_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product = _product(root, {'pubspec.yaml': 'name: app\n',
                                       'pubspec.lock': 'packages: {}\n'})
            value = stack.plan(product, workspace=root / 'ws',
                               env={'PATH': '/nonexistent', 'HOME': str(root)})
            entry, = value['stacks']
            self.assertEqual(entry['stack'], 'dart-flutter')
            self.assertFalse(entry['verification_ready'])
            missing, = [c for c in entry['capabilities'] if c['status'] == 'missing']
            self.assertEqual(missing['capability'], 'flutter')
            self.assertIn('git clone', missing['provision_step'])
            self.assertIn('.local/share/flutter', missing['provision_step'])
            self.assertEqual(stack.summary(value),
                             ['dart-flutter: falta flutter'])

    def test_flutter_clone_without_engine_cache_is_not_a_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product = _product(root, {'pubspec.lock': 'packages: {}\n'})
            home = root / 'home'
            flutter_bin = home / '.local/share/flutter/bin'
            flutter_bin.mkdir(parents=True)
            binary = flutter_bin / 'flutter'
            binary.write_text('#!/bin/sh\nexit 0\n')
            binary.chmod(0o755)
            env = {'PATH': '/nonexistent', 'HOME': str(home)}
            value = stack.plan(product, workspace=root / 'ws', env=env)
            self.assertFalse(value['stacks'][0]['verification_ready'])
            # Engine cache present: the same clone becomes a real capability.
            (home / '.local/share/flutter/bin/cache/dart-sdk').mkdir(parents=True)
            value = stack.plan(product, workspace=root / 'ws', env=env)
            self.assertTrue(value['stacks'][0]['verification_ready'])
            self.assertEqual(value['stacks'][0]['capabilities'][0]['path'],
                             str(binary))

    def test_in_product_install_is_flagged_unless_the_product_ignores_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product = _product(root, {'package-lock.json': '{}\n'})
            entry, = stack.plan(product, workspace=root / 'ws')['stacks']
            self.assertEqual(entry['in_product_install'], ['node_modules'])
            self.assertFalse(entry['in_product_install_gitignored'])
            (product / '.gitignore').write_text('node_modules/\n')
            entry, = stack.plan(product, workspace=root / 'ws')['stacks']
            self.assertTrue(entry['in_product_install_gitignored'])

    def test_declared_entrypoints_override_detection_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product = _product(root, {'pubspec.lock': 'packages: {}\n'})
            invalid = {
                'version': 2, 'stacks': [{'root': '', 'verify': ['flutter', 'test']}],
            }
            (product / stack.DECLARATION_FILE).write_text(json.dumps(invalid))
            with self.assertRaises(ValueError):
                stack.plan(product, workspace=root / 'ws')
            for bad in ({'root': '../escape', 'verify': ['x']},
                        {'root': '', 'verify': []},
                        {'root': '', 'verify': 'flutter test'}):
                (product / stack.DECLARATION_FILE).write_text(json.dumps(
                    {'version': 1, 'stacks': [bad]}))
                with self.assertRaises(ValueError):
                    stack.plan(product, workspace=root / 'ws')
            (product / stack.DECLARATION_FILE).write_text(json.dumps({
                'version': 1,
                'stacks': [{'stack': 'dart-flutter', 'root': '',
                            'verify': ['flutter', 'test', '--reporter', 'compact'],
                            'capabilities': ['flutter']}],
            }))
            entry, = stack.plan(product, workspace=root / 'ws',
                                env={'PATH': '/nonexistent', 'HOME': str(root)})['stacks']
            self.assertTrue(entry['declared'])
            self.assertEqual(entry['verify_command'][-1], 'compact')
            self.assertFalse(entry['verification_ready'])

    def test_materialized_workspace_venv_becomes_the_real_python_entrypoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product = _product(root, {'requirements.txt': 'Django==6.0.2\n',
                                       'manage.py': 'print(1)\n'})
            workspace = root / 'ws'
            python = workspace / '.stack/python-django/venv/bin/python'
            python.parent.mkdir(parents=True)
            python.write_text('#!/bin/sh\nexit 0\n')
            python.chmod(0o755)
            entry, = stack.plan(product, workspace=workspace)['stacks']
            self.assertEqual(entry['verify_command'][0], str(python))

    def test_plan_is_digest_bound_and_load_fails_closed_on_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product = _product(root, {'go.mod': 'module x\n', 'go.sum': ''})
            workspace = root / 'ws'
            workspace.mkdir()
            value = stack.plan(product, workspace=workspace)
            path = stack.write(value, workspace)
            self.assertEqual(path, workspace / stack.PLAN_RELATIVE)
            self.assertEqual(stack.load(workspace)['plan_sha256'], value['plan_sha256'])
            tampered = json.loads(path.read_text())
            tampered['stacks'][0]['verify_command'] = ['echo', 'ok']
            path.write_text(json.dumps(tampered))
            with self.assertRaisesRegex(ValueError, 'alterado'):
                stack.load(workspace)

    def test_product_without_markers_resolves_to_no_stacks_not_invention(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product = _product(root, {'README.md': '# app\n'})
            value = stack.plan(product, workspace=root / 'ws')
            self.assertEqual(value['stacks'], [])
            self.assertEqual(stack.summary(value), [])

    def test_product_must_be_a_real_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                stack.plan(root / 'missing')
            target = root / 'real'
            target.mkdir()
            link = root / 'link'
            link.symlink_to(target)
            with self.assertRaises(ValueError):
                stack.plan(link)

    def test_declared_python_stack_resolves_the_live_interpreter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product = _product(root, {'README.md': '# self\n'})
            (product / stack.DECLARATION_FILE).write_text(json.dumps({
                'version': 1,
                'stacks': [{'stack': 'python-unittest', 'root': '',
                            'verify': ['{python}', '-B', '-m', 'unittest',
                                       'discover', '-s', 'tests'],
                            'capabilities': ['python3']}],
            }))
            entry, = stack.plan(product, workspace=root / 'ws')['stacks']
            self.assertNotEqual(entry['verify_command'][0], '{python}')
            self.assertEqual(entry['verify_command'][1:],
                             ['-B', '-m', 'unittest', 'discover', '-s', 'tests'])
            self.assertTrue(entry['verification_ready'])


if __name__ == '__main__':
    unittest.main()
