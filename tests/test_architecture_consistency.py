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


if __name__ == '__main__':
    unittest.main()
