"""Ejecutar con python3 -B -m unittest discover -s tests -v."""
import importlib.util
from pathlib import Path
import shutil
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
            content = '---\nname: demo\ndescription: "demo"\n---\n'
            (source / 'demo' / 'SKILL.md').write_text(content)
            self.assertIn('DRY-RUN', onboard.prepare_project_skills(workspace, source))
            self.assertIn('CREADO', onboard.prepare_project_skills(workspace, source, apply=True))
            self.assertEqual((workspace / '.agents/skills/demo/SKILL.md').read_text(), content)
            self.assertIn('0 cambios', onboard.prepare_project_skills(workspace, source, apply=True))
            refs = source / 'demo/references'
            refs.mkdir()
            (refs / 'contract.txt').write_text('reference')
            with self.assertRaises(ValueError):
                onboard.prepare_project_skills(workspace, source, apply=True)
            destination = workspace / '.agents/skills/demo/SKILL.md'
            destination.write_text('user edit')
            self.assertIn('DRY-RUN', onboard.prepare_project_skills(workspace, source, update=True))
            self.assertEqual(destination.read_text(), 'user edit')
            onboard.prepare_project_skills(workspace, source, apply=True, update=True)
            backups = list(workspace.glob('skills-backup-*/demo/SKILL.md'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), 'user edit')
            self.assertEqual((destination.parent / 'references/contract.txt').read_text(), 'reference')
            (refs / 'linked').symlink_to(refs / 'contract.txt')
            with self.assertRaises(ValueError):
                onboard.prepare_project_skills(workspace, source, apply=True, update=True)
            with self.assertRaises(ValueError):
                onboard.prepare_project_skills(onboard.FRAMEWORK, source, apply=True)

    def test_a_skill_that_would_not_load_is_refused_before_it_is_copied(self):
        """What the installer used to do silently, it now refuses to do.

        The five skills the framework ships are copied verbatim into every
        user's project, and the copy path never parsed them: a `SKILL.md`
        without frontmatter, or one naming something other than its own
        directory, would be installed and then never discovered, with an install
        result that reported success. A populated directory without a
        `SKILL.md` was worse still — it was not selected, so it was not copied,
        and nothing in the result said it had been left behind.
        """
        def source_with(skill_md=None, *, under=None, extra=None):
            root = Path(tempfile.mkdtemp(prefix='skills-src-', dir='/tmp'))
            self.addCleanup(shutil.rmtree, root, True)
            source = root / 'skills'
            source.mkdir()
            if skill_md is not None:
                (source / 'demo').mkdir()
                (source / 'demo' / 'SKILL.md').write_text(skill_md, encoding='utf-8')
            if under is not None:
                (source / under).mkdir()
                (source / under / 'notes.txt').write_text('contenido', encoding='utf-8')
            if extra is not None:
                (source / extra).mkdir()
            return source

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / 'workspace'
            workspace.mkdir()
            cases = [
                ('frontmatter ausente', '---\nname: demo\n', None),
                ('nombre distinto del directorio',
                 '---\nname: otro\ndescription: "x"\n---\n', None),
                ('descripción ausente', '---\nname: demo\n---\n', None),
            ]
            for label, content, _ in cases:
                with self.subTest(caso=label):
                    source = source_with(content)
                    with self.assertRaises(ValueError) as caught:
                        onboard.prepare_project_skills(workspace, source)
                    self.assertIn('demo', str(caught.exception))
                    self.assertEqual(list(workspace.iterdir()), [],
                                     'una skill ilegible no debe dejar nada instalado')
            # A directory with content and no SKILL.md is a loss, and is named.
            source = source_with(None, under='sin-skill')
            with self.assertRaises(ValueError) as caught:
                onboard.prepare_project_skills(workspace, source)
            self.assertIn('sin-skill', str(caught.exception))
            # An empty one loses nothing and is left alone.
            source = source_with('---\nname: demo\ndescription: "d"\n---\n', extra='vacia')
            self.assertIn('DRY-RUN', onboard.prepare_project_skills(workspace, source))

    def test_the_skills_this_framework_ships_are_the_ones_it_can_load(self):
        """The population the installer proves nothing about, checked directly.

        `test_prepare_project_skills_is_external_and_no_clobber` installs a
        synthetic skill, so every property the real five rely on — frontmatter
        that parses, a name equal to the directory it ships in, a description
        inside the budget a loader will read — was true of the fixtures and
        unchecked in the repository.
        """
        source = onboard.FRAMEWORK / 'skills'
        names = sorted(p.name for p in source.iterdir() if p.is_dir())
        self.assertTrue(names, 'skills/ vacío: el escaneo está roto')
        for name in names:
            with self.subTest(skill=name):
                skill_md = source / name / 'SKILL.md'
                self.assertFalse(skill_md.is_symlink())
                match = onboard.SKILL_FRONTMATTER.match(
                    skill_md.read_text(encoding='utf-8'))
                self.assertIsNotNone(match, f'{name}: frontmatter que un cargador no leería')
                self.assertEqual(match.group(1), name)
                self.assertLessEqual(len(match.group(2)), 512)
                for part in (source / name).rglob('*'):
                    self.assertFalse(part.is_symlink(), f'{name}: {part.name}')
                    if part.is_file():
                        self.assertNotIn('/home/', part.read_text(encoding='utf-8'))

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

    def test_parent_links_owned_idempotent_and_removable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / 'private'
            workspace.mkdir()
            onboard.prepare_project_skills(workspace, apply=True)
            target = root / '.agents/skills'
            self.assertIn('DRY-RUN', onboard.link_project_skills(root, workspace))
            self.assertFalse(target.exists())
            onboard.link_project_skills(root, workspace, apply=True)
            self.assertIn('0 cambios', onboard.link_project_skills(root, workspace, apply=True))
            unrelated = target / 'personal'
            unrelated.mkdir()
            link = target / 'project-onboarding'
            link.unlink()
            link.symlink_to(root / 'foreign')
            with self.assertRaises(ValueError):
                onboard.link_project_skills(root, workspace, apply=True, remove=True)
            self.assertTrue(link.is_symlink())
            link.unlink()
            onboard.link_project_skills(root, workspace, apply=True)
            onboard.link_project_skills(root, workspace, apply=True, remove=True)
            self.assertEqual(list(target.iterdir()), [unrelated])
            self.assertTrue((workspace / '.agents/skills/project-onboarding/SKILL.md').is_file())
            link.mkdir()
            with self.assertRaises(ValueError):
                onboard.link_project_skills(root, workspace, apply=True)
            self.assertFalse((root / '.agents/workflow-skills.json').exists())
            link.rmdir()
            manifest = root / '.agents/workflow-skills.json'
            foreign = root / 'foreign.json'
            foreign.write_text('{}')
            manifest.symlink_to(foreign)
            with self.assertRaises(ValueError):
                onboard.link_project_skills(root, workspace, apply=True)
            self.assertEqual(foreign.read_text(), '{}')
            manifest.unlink()
            override = root / '.dsh/skills/project-onboarding'
            override.mkdir(parents=True)
            with self.assertRaises(ValueError):
                onboard.link_project_skills(root, workspace, apply=True)
            override.rmdir()
            onboard.link_project_skills(root, workspace, apply=True)
            second = root / 'second'
            second.mkdir()
            onboard.prepare_project_skills(second, apply=True)
            with self.assertRaises(ValueError):
                onboard.link_project_skills(root, second, apply=True)
            (root / '.git').write_text('gitdir: elsewhere')
            with self.assertRaises(ValueError):
                onboard.link_project_skills(root, workspace, apply=True)

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
