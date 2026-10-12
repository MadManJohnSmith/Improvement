"""Architecture 3.0 consistency: no legacy plans, generic modes or local paths."""
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ArchitectureConsistencyTest(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text()

    def test_every_current_document_has_english_and_spanish_paths(self):
        """Docs stay bilingual when a new operational document is added."""
        for root in (ROOT / 'docs', ROOT / 'docs' / 'plans'):
            english = sorted(path for path in root.glob('*.md')
                             if not path.name.endswith('.es.md'))
            self.assertTrue(english)
            for path in english:
                with self.subTest(path=str(path.relative_to(ROOT))):
                    spanish = path.with_name(path.stem + '.es.md')
                    self.assertTrue(spanish.is_file())
                    en = path.read_text(encoding='utf-8')
                    es = spanish.read_text(encoding='utf-8')
                    self.assertIn(spanish.name, en)
                    self.assertIn(path.name, es)

    def test_the_plans_index_lists_the_lifecycle_and_decision_designs(self):
        """Two designs a reader must find from the index, in both languages."""
        english = self.read('docs/plans/README.md')
        spanish = self.read('docs/plans/README.es.md')
        for name in ('project-lifecycle-modes.md',
                     'system-one-decision-channel.md'):
            self.assertIn(name, english)
            self.assertIn(name.replace('.md', '.es.md'), spanish)

    def test_normative_architecture_is_v3(self):
        architecture = self.read('ARQUITECTURA_FLUJO_AGENTES.md')
        plan = self.read('PLAN_IMPLEMENTACION.md')
        self.assertIn('**Versión:** 3.0', architecture)
        self.assertIn('C0', plan)
        self.assertIn('C7', plan)

    def test_legacy_plans_and_diagrams_do_not_exist(self):
        must_not_exist = [
            'docs/PLAN_EJECUCION_ARQUITECTURA_COMPLETA.md',
            'docs/PLAN_PENDIENTES_CIERRE_NUCLEO.md',
            'docs/EVALUACION_ORQUESTACION_EXTERNA.md',
            'docs/trial-readiness.md',
            'docs/cycle-artifacts.md',
            'docs/diagrams/README.md',
            'docs/diagrams/flujo-arquitectura.html',
            'docs/diagrams/flujo-operativo.html',
            'skills/workflow-auditor/SKILL.md',
            'skills/workflow-complete-auditor/SKILL.md',
            'skills/workflow-continuous-repair/SKILL.md',
            # Placeholders for the generic modes that generation replaced. No
            # code substitutes {{PROJECT_NAME}} or {{SKILL_NAME}}, so the tree
            # could only mislead someone into editing a file nothing reads.
            'templates/modes/auditor.md',
            'templates/modes/continuous-repair.md',
            'templates/modes/mode-contract.template.json',
            'templates/contracts/plugin-contract.template.json',
            'templates/skills/SKILL.md.template',
            'templates/skills/skill-contract.template.json',
            'tests/test_dsh_launchers.py',
            'tests/test_dsh_preset_mapping.py',
        ]
        for relative in must_not_exist:
            with self.subTest(relative=relative):
                self.assertFalse(
                    (ROOT / relative).exists(),
                    f'{relative} must be removed from the canonical tree; Git preserves history')

    def test_entry_docs_do_not_present_generic_modes(self):
        agents = self.read('AGENTS.md')
        readme = self.read('README.md')
        self.assertNotIn('los modos finales siguen siendo Auditor y Reparación continua', agents)
        self.assertIn('<Proyecto>-auditor', agents)
        self.assertNotIn('workflow-complete-auditor', readme)
        self.assertNotIn('workflow-continuous-repair', readme)
        self.assertNotIn('workflow-auditor', readme)

    def test_status_ends_with_v3_backlog(self):
        status = self.read('docs/status.md')
        last_heading = list(re.finditer(r'(?m)^## ', status))[-1]
        last_section = status[last_heading.start():]
        self.assertIn('C7', last_section)
        self.assertIn('C0', status)
        self.assertNotIn('El contrato v0.1 sigue siendo', last_section)

    def test_the_readmes_publish_the_real_session_both_ways(self):
        """The 2026-10-10 pass is published as real work, and as unproven work.

        The README is the public face, so it has to say both: what the real
        DSH session actually did, and what it did not. A claim that only lists
        the wins would read as a full pass, and the run that carries them ended
        `RETAINED` on the Creator.
        """
        for name, proved, blocked, claim in (
                ('README.md', 'real DSH session', 'Creator end-to-end',
                 'and is not claimed'),
                ('README.es.md', 'sesión DSH real', 'Creator end-to-end',
                 'no se afirma')):
            with self.subTest(readme=name):
                text = self.read(name)
                self.assertIn(proved, text,
                              f"{name} no publica el caso real")
                self.assertIn(blocked, text,
                              f"{name} omite el límite que no se probó")
                self.assertIn(claim, text,
                              f"{name} nombra el caso real pero no dice qué "
                              f"queda sin probar")
                self.assertIn('ab5c0c6', text, "el commit verificado del reparador")
                progress_path = ('docs/progreso-agentico.es.md' if name.endswith('.es.md')
                                 else 'docs/progreso-agentico.md')
                self.assertIn(progress_path, text,
                              "la vista de hitos no está enlazada desde la portada")

    def test_status_documents_have_no_trailing_whitespace(self):
        # A status file that is one character per line is still valid markdown to
        # every reader and to the tests, and it is unreadable to a person. This
        # happened once here: assigning a string to a list slice inserts one
        # character per element, and nothing else noticed.
        for name in ('docs/status.md', 'PLAN_IMPLEMENTACION.md', 'README.md',
                     'CHANGELOG.md'):
            with self.subTest(name=name):
                text = self.read(name)
                offenders = [index for index, line in enumerate(text.split('\n'), 1)
                             if line != line.rstrip()]
                self.assertEqual(offenders[:5], [], f"{name}: {offenders[:5]}")
                self.assertNotIn('\n \n', text)

    def test_a_status_document_is_not_one_character_per_line(self):
        for name in ('docs/status.md', 'PLAN_IMPLEMENTACION.md'):
            with self.subTest(name=name):
                lines = self.read(name).split('\n')
                single = sum(1 for line in lines if len(line.strip()) == 1)
                self.assertLess(single, len(lines) * 0.01,
                                f"{name}: {single} líneas de un solo carácter")

    def test_a_launch_plan_with_every_gate_closed_is_not_still_en_curso(self):
        # The gate table and the plan header are two places stating the same
        # thing, and they drifted: all seven gates read HECHO while the header
        # still announced EN CURSO. A reader takes the header as the verdict.
        plan = self.read('docs/plans/10-lanzamiento-publico.md')
        rows = re.findall(r'(?m)^\| G\d \|.*\| ([A-ZÁÉÍÓÚÑ][^|]*)\|$', plan)
        self.assertGreaterEqual(len(rows), 7, plan[:400])
        closed = [row for row in rows if row.strip().startswith('HECHO')]
        self.assertEqual(sorted(closed), sorted(rows),
                         'every launch gate is closed but the plan disagrees')
        self.assertIn('Estado: **HECHO**', plan)

    def test_no_versioned_file_carries_a_maintainer_home_path(self):
        # The rule is about publishable files, not only about the documents an
        # earlier round happened to list: a hand-kept list rots the moment a new
        # file lands, and the CHANGELOG sat outside it for months with a workspace
        # path of the maintainer in it. Source and prose are judged the same way,
        # because both ship.
        # Only tracked files are judged, so ignored scratch a tool leaves in the
        # working tree cannot fail a build that is otherwise clean. Tests are
        # excluded because the guard itself and the negative cases that prove a
        # path is refused have to contain the string they are refusing.
        # JSON and YAML were missing from the list until this round: a schema or
        # a preset is published exactly like a document, and `schemas/_policy.json`
        # states the same rule the guard was enforcing for prose.
        tracked = subprocess.run(
            ['git', 'ls-files', '-z', '--', '*.md', '*.mjs', '*.py', '*.sh',
             '*.json', '*.yml', '*.yaml'],
            cwd=ROOT, capture_output=True, text=True, check=True).stdout
        offenders = [name for name in tracked.split('\0')
                     if name
                     and not name.startswith('tests/')
                     and '/home/alan' in
                     (ROOT / name).read_text(encoding='utf-8', errors='replace')]
        self.assertEqual(sorted(offenders), [])

    def test_creator_contract_is_generational_and_prefers_reuse(self):
        contract = self.read('docs/creator-preset-spec.md')
        self.assertIn('fuera del árbol canónico', contract)
        self.assertIn('generation-manifest.json', contract)
        self.assertIn('<Proyecto>-auditor', contract)
        self.assertIn('<Proyecto>-continuous-repair', contract)
        self.assertIn('biblioteca base inmutable', contract)
        self.assertIn('extensión específica generada', contract)

    def test_plans_define_adaptation_and_reuse_order(self):
        index = self.read('docs/plans/README.md')
        creator = self.read('docs/plans/03-c2-creator.md')
        adaptation = self.read('docs/plans/09-adaptacion.md')
        self.assertIn('adaptables', index.lower())
        self.assertIn('base inmutable', creator)
        self.assertIn('catálogo especializado', creator)
        self.assertIn('No se sustituye una base por una extensión', adaptation)

    def test_no_legacy_references_in_operational_docs(self):
        forbidden = [
            'PLAN_EJECUCION_ARQUITECTURA_COMPLETA',
            'PLAN_PENDIENTES_CIERRE_NUCLEO',
            'EVALUACION_ORQUESTACION_EXTERNA',
            'trial-readiness',
            'cycle-artifacts',
            'bash con redirección',
        ]
        for relative in ('README.md', 'PLAN_IMPLEMENTACION.md',
                         'docs/usage.md', 'docs/setup-dsh.md', 'docs/creator-preset-spec.md'):
            text = self.read(relative)
            for pattern in forbidden:
                with self.subTest(relative=relative, pattern=pattern):
                    self.assertNotIn(pattern, text)


    def test_every_skipped_regression_is_skipped_for_a_named_external_component(self):
        """A skip is an honest absence of proof, and only while it names why.

        The suite reports "N skipped", and that number was never accounted for:
        the README said the suite was green without saying which regressions did
        not run. A skip whose reason is a component this repository does not
        ship is legitimate — a DSH runtime, `node`, `bubblewrap`, `jsonschema` —
        and saying so is what makes it honest. A skip with any other reason, or
        no reason, is a regression that stopped testing while still counting as
        one, which is the failure this framework exists to prevent and the one
        it had already committed once.

        So every `skipTest` in the suite has to name a component from that list.
        The list is the declaration, and adding a component to it is a decision
        somebody can see; a silent skip is not possible any more.
        """
        declared = ("DSH_MODULE_ROOT", "node", "node_modules", "bubblewrap",
                    "jsonschema", "dsh-tools", "runtime")
        offenders = []
        for path in sorted((ROOT / "tests").glob("*.py")):
            source = path.read_text(encoding="utf-8")
            for match in re.finditer(r"skipTest\(\s*(['\"])(.*?)\1", source,
                                     re.DOTALL):
                reason = match.group(2)
                line = source[:match.start()].count("\n") + 1
                if not any(name in reason for name in declared):
                    offenders.append(f"{path.name}:{line}: {reason[:70]}")
        self.assertEqual(offenders, [])

    def test_every_cli_subcommand_is_mentioned_in_the_usage_document(self):
        """A command nobody can find is a command nobody runs.

        `audit.py archive`, `missions.py reaudit` and the `transaction.py`
        entry points had regressions and no mention in `docs/usage.md`, and the
        operator-facing `skill-gate-run` was named only in the status document.
        All of them work; none of them were discoverable, which for a framework
        whose whole claim is that it is operable means they were not really
        part of the product.

        The check is over the parsers themselves rather than a hand-kept list,
        so adding a subcommand without documenting it fails here instead of
        being noticed by whoever needed it first. The name has to appear
        anywhere in the document, code blocks included, because a command shown
        in a ```bash fence is documented; requiring inline backticks would only
        push the documentation somewhere less useful. A short name like
        `install` can therefore pass on another command's mention, which makes
        this check looser than a per-command index — deliberately, since a
        false alarm here costs more than the collision it would catch.
        """
        usage = self.read('docs/usage.md')
        declared = set()
        for path in sorted((ROOT / 'scripts').glob('*.py')):
            declared.update(re.findall(
                r'add_parser\(\s*[\'"]([a-z][a-z0-9-]*)[\'"]', path.read_text()))
        self.assertTrue(declared, 'no subcommands found: the scan is broken')
        missing = sorted(name for name in declared if name not in usage)
        self.assertEqual(missing, [])

    def test_every_flag_the_usage_document_shows_exists(self):
        """The other half of the check above, one level deeper.

        A subcommand that works but is undocumented is invisible; a flag that is
        documented and does not exist is worse, because it is discovered at the
        operator's terminal, on a mission, after the command has been read. The
        usage document is the only place a flag is taught, so whatever it shows
        has to exist.

        Scoped to the lines that invoke `bootstrap.py`, which is the surface the
        document teaches; a flag of `git`, `npm` or `flutter` shown in the same
        examples is not this repository's to define.
        """
        usage = self.read('docs/usage.md')
        defined = set()
        for path in sorted((ROOT / 'scripts').glob('*.py')):
            source = path.read_text()
            defined.update(re.findall(r"['\"](--[a-z][a-z0-9-]+)['\"]", source))
        documented = set()
        for line in usage.splitlines():
            if 'bootstrap.py' in line:
                documented.update(
                    re.findall(r"(?<![\w-])(--[a-z][a-z0-9-]+)", line))
        self.assertTrue(documented, 'ningún flag encontrado: el escaneo está roto')
        missing = sorted(flag for flag in documented if flag not in defined)
        self.assertEqual(missing, [],
                         f'flags documentadas que bootstrap.py no define: {missing}')

    def test_the_skipped_regressions_are_named_where_the_suite_count_is(self):
        """The number that goes green has to say what did not run.

        "N pruebas en verde" is a claim about the whole suite, and eleven of
        those do not execute without a DSH runtime, `node`, `bubblewrap` or
        `jsonschema` present. The count is worth publishing precisely because it
        is not total, so the document that publishes it has to name the gap in
        the same breath.
        """
        status = self.read("docs/status.md")
        for component in ("DSH_MODULE_ROOT", "node", "bubblewrap", "jsonschema"):
            with self.subTest(component=component):
                self.assertIn(component, status)

    def test_every_schema_file_names_the_validator_that_enforces_it(self):
        """A schema nothing parses is a contract that exists only as a file.

        Nineteen of the twenty-two schemas were reachable through the
        `generation_contracts` registry, and the remaining three — the corpus
        contracts — were enforced by hand-written validators in
        `corpus_compiler` that no name pointed at. Both shapes work and both
        rot the same way: edit the schema, keep enforcing the old shape, and
        the repository publishes a contract the code does not hold. Two of the
        reachable ones were additionally addressed by a name that was not their
        file's, which is the same drift one rename away.

        So the binding is declared in the product (`SCHEMA_VALIDATORS`) and
        required here to be an exact bijection with the directory: a new schema
        file without a validator fails, a binding without a file fails, and a
        binding that names something which is not callable fails.
        """
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        import generation_contracts as gc

        on_disk = {path.name[: -len(".schema.json")]
                   for path in (ROOT / "schemas").glob("*.schema.json")}
        self.assertNotIn("_policy", on_disk, "the cross-cutting policy is not a contract")
        self.assertEqual(sorted(on_disk), sorted(gc.SCHEMA_VALIDATORS))
        for stem, target in sorted(gc.SCHEMA_VALIDATORS.items()):
            with self.subTest(schema=stem):
                self.assertTrue(callable(gc.schema_enforcement(stem)),
                                f"{stem} nombra {target}, que no se puede llamar")
        # Non-vacuity in the direction that matters: a schema with nothing
        # enforcing it is refused rather than quietly accepted as covered.
        with self.assertRaises(gc.ContractError):
            gc.schema_enforcement("schema-que-no-existe")
        with self.assertRaises(gc.ContractError):
            gc.schema_enforcement("_policy")

    def test_a_schema_can_be_addressed_by_the_name_of_its_file(self):
        """`modes` and `mode-contract` are one contract with two spellings.

        The emitted lifecycle is validated as `mode-contract` while the file it
        belongs to is `modes.schema.json`; nothing used to say so, so either
        name could have been the one that rotted.
        """
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        import generation_contracts as gc

        for stem, alias in sorted(gc.SCHEMA_ALIASES.items()):
            with self.subTest(schema=stem):
                self.assertEqual(gc.schema_enforcement(stem),
                                 gc.schema_enforcement(alias))
        with self.assertRaises(gc.ContractError):
            gc.validate("schema-que-no-existe", {})


    def test_the_published_suite_count_is_the_count_that_runs(self):
        """A count of the suite is a claim about this repository, right now.

        Two of them sat sixteen lines apart — "743 pruebas en verde" and "755
        pruebas en verde" — both about the framework, both in the README, with
        nothing saying which was current. Updating that by hand each round is
        the fragile version: the count drifts the moment a regression is added
        and nobody notices until a reader does.

        So the number is discovered rather than remembered. A claim that
        disagrees with the suite has to say it belongs to an earlier moment, in
        which case it is history and is allowed to be wrong.

        The claim lives in both README languages, and paragraphs may wrap mid-phrase, so each paragraph is whitespace-normalized before matching.
        """
        import unittest as ut
        discovered = ut.TestLoader().discover(
            str(ROOT / "tests")).countTestCases()
        self.assertGreater(discovered, 0, "la suite no se descubrió: el escaneo está roto")
        published = [
            ("README.md", "at that point",
             re.compile(r"Framework suite: \*\*(\d+) tests green\*\*")),
            ("README.es.md", "en ese punto",
             re.compile(r"Suite del (?:propio )?framework: \*\*(\d+) pruebas en verde\*\*")),
        ]
        for relative, historical, claim in published:
            if not (ROOT / relative).exists():
                continue
            claims = 0
            for paragraph in self.read(relative).split("\n\n"):
                text = re.sub(r"\s+", " ", paragraph)
                for said in claim.findall(text):
                    claims += 1
                    with self.subTest(relative=relative, said=said):
                        if int(said) == discovered:
                            continue
                        self.assertIn(historical, text,
                                      f"{relative} afirma {said} pruebas y la suite tiene "
                                      f"{discovered}; una cifra antigua tiene que decir que lo es")
            self.assertGreater(claims, 0,
                               f"{relative} no publica cifra de suite que comprobar")

    def test_the_suite_runs_without_writing_to_stderr(self):
        """CLIs that must exit 2 write their complaint to stderr by design.

        `argparse` prints usage to stderr and it is stdout the tests redirect,
        so one regression exercising `main()` with a missing required flag
        leaves two lines of usage text in the output of *every* suite run,
        printed over the progress dots where they read as a real failure. That
        happened with `host_validator.main()` and its `--run-dir`: the suite
        exited 1 for an unrelated reason while stderr advertised a broken
        validator, and it was the only leak in the whole suite.

        The fix is per-regression — capture stderr where the flag is missing —
        and this test is the one that catches a return. It runs the tests that
        drive a CLI's `main()` as a subprocess, the way the plan runs the
        suite, and requires stderr to hold nothing but the runner's own
        progress dots. A regression that moves a `main()` call back outside its
        `redirect_stderr` fails here, naming the run, instead of leaving two
        lines of argparse usage for whoever reads the suite output next.
        """
        result = subprocess.run(
            ["/usr/bin/python3", "-B", "-m", "unittest",
             "tests.test_creator_and_validator.ValidatorTests"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=900)
        self.assertEqual(result.returncode, 0, result.stderr)
        # Everything the runner itself writes below the progress line is
        # legitimate ("----", "Ran N tests", "OK", a traceback for a real
        # failure). The complaint is the line *above* it: unittest prints the
        # dots first and flushes, so a stray write interleaves there instead
        # of landing where the report can hide it.
        dots = [line for line in result.stderr.splitlines()
                if line and re.fullmatch(r"[.sFEx]*", line)]
        stray = []
        for line in result.stderr.splitlines():
            if not line.strip() or line in dots:
                continue
            if line.startswith(("-", "Ran ", "OK", "FAILED", "Traceback")) \
                    or line.startswith("  ") or line.startswith("Assertion"):
                continue
            stray.append(line)
        self.assertEqual(
            stray, [],
            "stderr de la suite con ruido: una regresión escribe fuera de "
            "redirect_stderr y contamina la salida de toda la suite")

    def test_the_progress_view_covers_every_milestone_family(self):
        """A one-page view of the milestones is only one page if it has them all.

        `docs/progreso-agentico.md` exists so no identifier has to be hunted
        through the tree. The families are fixed by the vocabulary the other
        documents already use, so a family that silently drops out is a hole in
        the view and not a simplification: `U` in particular lives only in the
        status document and would be the first to be forgotten.
        """
        progress = self.read('docs/progreso-agentico.md')
        families = {
            'B': ('B0', 'B4'),
            'C': ('C0', 'C7'),
            'D': ('D1', 'D9'),
            'E': ('E1', 'E9'),
            'F': ('F1', 'F6'),
            'G': ('G0', 'G7'),
            'M': ('M1', 'M9'),
            'P': ('P0', 'P11'),
            'U': ('U1', 'U6'),
            'X': ('X1', 'X3'),
        }
        # Each family's own section heading, so a mention in passing inside
        # prose does not count as coverage. Two of them (P) legitimately have
        # more than one heading, and the ranges are written with an en dash or
        # a hyphen depending on the section.
        headings = {m.group(1) for m in re.finditer(
            r'(?m)^## ([A-Z])[0-9][\u2013-]', progress)}
        for family, (first, last) in sorted(families.items()):
            with self.subTest(family=family):
                self.assertIn(family, headings,
                              f"falta una sección propia para la familia {family}")
                self.assertIn(first, progress)
                self.assertIn(last, progress)

    def test_the_progress_view_marks_reused_history_as_history(self):
        """A withdrawn family reused from Git must not read as live work.

        `M` and the phases `P0`–`P9` are only reachable with
        `git show c8aed51^:…`, and `docs/status.md` says plainly that no plan
        from them lives in the current documentation. A view that lists them
        without saying so invites someone to read them as a backlog.
        """
        progress = self.read('docs/progreso-agentico.md')
        for family in ('M1', 'P0'):
            with self.subTest(family=family):
                row = next((line for line in progress.splitlines()
                            if line.startswith(f"| {family} |")), None)
                self.assertIsNotNone(
                    row, f"no hay fila para {family}: la vista no lo cubre")
                self.assertIn('RETIRADO', row.upper(),
                              f"{family} tiene que decir que está retirado")
        self.assertIn('git show c8aed51^', progress)
        self.assertIn('homonimia', progress.lower(),
                      'las dos acepciones de P exigen aviso de homonimia')

    def test_no_document_claims_a_real_dsh_session_that_did_not_happen(self):
        """The difference between what the real session did and did not do.

        A claim that the Creator finished end-to-end, or that the corpus gate
        ran against a real mode, is exactly the kind that reads as true and is
        not: the run that produced these files ended `RETAINED`. The status
        document carries the three blockers and the one retainer, and this test
        keeps the vocabulary attached to them.
        """
        status = self.read('docs/status.md')
        for phrase in ('Creator end-to-end no se probó',
                       'no hay sesión DSH utilizable',
                       'fatal: cannot lock ref',
                       'RETAINED'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, status)
        # The pass did happen and is recorded, so the limits are not the whole
        # truth about it either.
        self.assertIn('PING-OK', status)
        self.assertIn('READY_FOR_ACCEPTANCE', status)

    def test_the_progress_view_links_only_to_files_the_repository_has(self):
        """A link that points at nothing is the most common way a view rots.

        The one-page progress view is meant to be the entry point, so each
        relative link in it is resolved against the tree: a moved document has
        to fail here rather than in a reader's click.
        """
        progress = self.read('docs/progreso-agentico.md')
        broken = []
        for target in re.findall(r'\]\(([^)#]+?)(?:#[^)]*)?\)', progress):
            if target.startswith(('http:', 'https:', 'mailto:')):
                continue
            for candidate in (ROOT / 'docs' / target, ROOT / target):
                if candidate.is_file():
                    break
            else:
                broken.append(target)
        self.assertTrue(re.findall(r'\]\(([^)#]+?)\)', progress),
                        "la vista no enlaza nada: el escaneo está roto")
        self.assertEqual(broken, [],
                         f"enlaces rotos en docs/progreso-agentico.md: {broken}")

    def test_the_dsh_maintenance_skill_is_portable_and_never_leaks_a_secret(self):
        """A permanent skill that teaches a real session is published like code.

        It is installed into every user's project by `prepare_project_skills`,
        which is where the other five are checked. Anything with a maintainer
        path, a credential or an absolute DSH_HOME inside would be copied to a
        stranger's tree and then never load or never be safe.
        """
        import sys
        sys.path.insert(0, str(ROOT / 'scripts'))
        import onboard
        skill = ROOT / 'skills' / 'dsh-maintenance-session'
        skill_md = skill / 'SKILL.md'
        self.assertTrue(skill_md.is_file(),
                        "skills/dsh-maintenance-session/SKILL.md no existe")
        match = onboard.SKILL_FRONTMATTER.match(
            skill_md.read_text(encoding='utf-8'))
        self.assertIsNotNone(match, "frontmatter que un cargador no leería")
        self.assertEqual(match.group(1), 'dsh-maintenance-session')
        self.assertLessEqual(len(match.group(2)), 512)
        text = skill_md.read_text(encoding='utf-8')
        # The procedure has to be the verified one, not a paraphrase.
        self.assertIn('--profile headless --json', text)
        self.assertIn('DSH_HOME', text)
        for forbidden in ('/home/', 'Improvement-herramientas',
                          'NROUTER_API_KEY=sk', 'ssh-rsa', 'BEGIN PRIVATE KEY'):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text,
                                 f"la skill publica {forbidden!r}")
        # A symlink in the tree would install as a link and then dangle.
        for part in skill.rglob('*'):
            self.assertFalse(part.is_symlink(), f"{part.name}")
            if part.is_file():
                self.assertNotIn('/home/', part.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
