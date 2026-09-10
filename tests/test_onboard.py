"""Ejecutar con python3 -B -m unittest discover -s tests -v."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('onboard', Path(__file__).resolve().parents[1] / 'scripts/onboard.py')
onboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(onboard)


class OnboardTest(unittest.TestCase):
    def test_framework_clean_detects_unexpected_edits(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            (root / 'tracked.txt').write_text('base')
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(root), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'base'], check=True)
            original = onboard.FRAMEWORK
            try:
                onboard.FRAMEWORK = root
                self.assertTrue(onboard.framework_clean())
                (root / 'tracked.txt').write_text('changed')
                self.assertFalse(onboard.framework_clean())
            finally:
                onboard.FRAMEWORK = original

    def test_prepare_project_skills_is_external_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / 'workspace'
            workspace.mkdir()
            source = root / 'skills'
            (source / 'demo').mkdir(parents=True)
            content = '---\\nname: demo\\ndescription: "demo"\\n---\\n'
            (source / 'demo' / 'SKILL.md').write_text(content)
            self.assertIn('DRY-RUN', onboard.prepare_project_skills(workspace, source))
            self.assertIn('CREADO', onboard.prepare_project_skills(workspace, source, apply=True))
            self.assertEqual((workspace / '.agents/skills/demo/SKILL.md').read_text(), content)
            with self.assertRaises(ValueError):
                onboard.prepare_project_skills(workspace, source, apply=True)
    def test_skill_destination_symlinks_fail_closed(self):
        for relative in ('.agents', '.agents/skills'):
            for apply in (False, True):
                with self.subTest(relative=relative, apply=apply), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    workspace, outside = root / 'workspace', root / 'outside'
                    workspace.mkdir()
                    outside.mkdir()
                    link = workspace / relative
                    link.parent.mkdir(parents=True, exist_ok=True)
                    link.symlink_to(outside, target_is_directory=True)
                    with self.assertRaises(ValueError):
                        onboard.prepare_project_skills(workspace, apply=apply)
                    self.assertEqual(list(outside.iterdir()), [])

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
