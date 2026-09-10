"""Ejecutar con python3 -B -m unittest discover -s tests -v."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('onboard', Path(__file__).resolve().parents[1] / 'scripts/onboard.py')
onboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(onboard)


class OnboardTest(unittest.TestCase):
    def test_lifecycle_and_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / 'product'
            project.mkdir()
            source = project / 'data.txt'
            source.write_text('conservar')
            workspace = root / 'private'
            run = lambda p=project, w=workspace, n='demo', apply=False: onboard.initialize(str(p), str(w), n, apply)
            self.assertIn('DRY-RUN', run())
            self.assertFalse(workspace.exists())
            self.assertIn('CREADO', run(apply=True))
            profile = workspace / 'PROJECT.md'
            profile.write_text('decisión humana conservada')
            before = {p.name: p.read_bytes() for p in workspace.iterdir()}
            self.assertIn('EXISTENTE', run(apply=True))
            self.assertEqual(before, {p.name: p.read_bytes() for p in workspace.iterdir()})
            self.assertEqual(workspace.stat().st_mode & 0o777, 0o700)
            for destination in [project, project / 'nested', root, onboard.FRAMEWORK / 'private']:
                with self.assertRaises(ValueError):
                    run(w=destination, apply=True)
            for name in ['../escape', '', 'A', 'a\nb', 'a' * 65]:
                with self.assertRaises(ValueError):
                    run(n=name, apply=True)
            with self.assertRaises(ValueError):
                run(n='different', apply=True)
            link = root / 'linked'
            link.symlink_to(project, target_is_directory=True)
            with self.assertRaises(ValueError):
                run(p=link)
            with self.assertRaises(ValueError):
                run(w=link / 'child', apply=True)
            with self.assertRaises(ValueError):
                run(w=root / 'missing' / '..' / 'escape')
            conflict = root / 'conflict'
            conflict.mkdir()
            with self.assertRaises(ValueError):
                run(w=conflict, apply=True)
            profile.unlink()
            profile.symlink_to(source)
            with self.assertRaises(ValueError):
                run(apply=True)
            (root / '.git').write_text('gitdir: elsewhere')
            with self.assertRaises(ValueError):
                run(w=root / 'another', apply=True)
            self.assertEqual(source.read_text(), 'conservar')
            self.assertEqual(sorted(p.name for p in project.iterdir()), ['data.txt'])


if __name__ == '__main__':
    unittest.main()
