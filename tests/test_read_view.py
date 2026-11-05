"""Lector delegado del Host: vista byte-anclada de un rango, nunca una síntesis.

Seams confirmados 2026-11-05: build() (función pura) y el CLI (exit 0/2).
La vista lleva ruta, sha256 del archivo completo, rango, total de líneas y el
excerpt exacto; el original permanece en disco y los rangos que no se pueden
anclar se rechazan con nombre.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'read_view.py'
sys.path.insert(0, str(ROOT / 'scripts'))
import read_view


class BuildViewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='read-view-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'docs').mkdir()
        self.text = 'linea uno\nlinea dos\nlinea tres\n'
        (self.root / 'docs' / 'spec.md').write_text(self.text)

    def test_range_view_is_anchored_and_exact(self):
        view = read_view.build(self.root, 'docs/spec.md', start=2, end=3)
        self.assertEqual(view['path'], 'docs/spec.md')
        self.assertEqual(view['sha256'],
                         hashlib.sha256(self.text.encode()).hexdigest())
        self.assertEqual((view['start'], view['end']), (2, 3))
        self.assertEqual(view['total_lines'], 3)
        self.assertEqual(view['excerpt'], 'linea dos\nlinea tres')

    def test_whole_file_when_no_range(self):
        view = read_view.build(self.root, 'docs/spec.md')
        self.assertEqual((view['start'], view['end']), (1, 3))
        self.assertEqual(view['excerpt'],
                         'linea uno\nlinea dos\nlinea tres')

    def test_outside_root_is_refused(self):
        with self.assertRaises(ValueError):
            read_view.build(self.root, '../secret')

    def test_absolute_path_is_refused(self):
        with self.assertRaises(ValueError):
            read_view.build(self.root, '/etc/passwd')

    def test_missing_file_is_refused(self):
        with self.assertRaises(ValueError):
            read_view.build(self.root, 'docs/missing.md')

    def test_directory_is_refused(self):
        with self.assertRaises(ValueError):
            read_view.build(self.root, 'docs')

    def test_binary_is_refused(self):
        (self.root / 'blob.bin').write_bytes(b'\x00\x01\xff\xfe')
        with self.assertRaises(ValueError):
            read_view.build(self.root, 'blob.bin')

    def test_cap_is_enforced(self):
        with self.assertRaisesRegex(ValueError, 'cota'):
            read_view.build(self.root, 'docs/spec.md', max_chars=5)

    def test_bad_bounds_are_refused(self):
        with self.assertRaises(ValueError):
            read_view.build(self.root, 'docs/spec.md', start=0)
        with self.assertRaises(ValueError):
            read_view.build(self.root, 'docs/spec.md', start=3, end=2)
        with self.assertRaises(ValueError):
            read_view.build(self.root, 'docs/spec.md', end=9)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='read-view-cli-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'a.txt').write_text('uno\ndos\n')

    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPT), *args],
                              capture_output=True, text=True)

    def test_cli_view_exits_zero(self):
        done = self.run_cli('--root', str(self.root), '--path', 'a.txt',
                            '--start', '2', '--end', '2')
        self.assertEqual(done.returncode, 0, done.stderr)
        view = json.loads(done.stdout)
        self.assertEqual(view['excerpt'], 'dos')
        self.assertEqual(view['sha256'],
                          hashlib.sha256(b'uno\ndos\n').hexdigest())

    def test_cli_refusal_exits_two_with_named_error(self):
        done = self.run_cli('--root', str(self.root), '--path', '../escape')
        self.assertEqual(done.returncode, 2)
        self.assertIn('read_view:', done.stderr)


if __name__ == '__main__':
    unittest.main()
