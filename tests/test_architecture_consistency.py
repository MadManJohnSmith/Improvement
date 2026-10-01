"""Architecture 3.0 consistency: no legacy plans, generic modes or local paths."""
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ArchitectureConsistencyTest(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text()

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
        # working tree cannot fail a build that is otherwise clean.
        tracked = subprocess.run(
            ['git', 'ls-files', '-z', '--', '*.md', '*.mjs', '*.py', '*.sh'],
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
            'docs/diagrams/',
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
            """
            import unittest as ut
            discovered = ut.TestLoader().discover(
                str(ROOT / "tests")).countTestCases()
            self.assertGreater(discovered, 0, "la suite no se descubrió: el escaneo está roto")
            claim = re.compile(r"Suite del (?:propio )?framework: \*\*(\d+) pruebas en verde\*\*")
            paragraphs = [p for p in self.read("README.md").split("\n\n") if claim.search(p)]
            self.assertTrue(paragraphs, "no hay cifra de suite que comprobar")
            for paragraph in paragraphs:
                for said in claim.findall(paragraph):
                    with self.subTest(said=said):
                        if int(said) == discovered:
                            continue
                        self.assertIn("en ese punto", paragraph,
                                      f"el README afirma {said} pruebas y la suite tiene "
                                      f"{discovered}; una cifra antigua tiene que decir que lo es")


if __name__ == '__main__':
    unittest.main()
