"""Architecture 3.0 consistency: no legacy plans, generic modes or local paths."""
from pathlib import Path
import re
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
        ]
        for relative in must_not_exist:
            with self.subTest(relative=relative):
                self.assertFalse(
                    (ROOT / relative).exists(),
                    f'{relative} must be removed from the canonical tree; Git preserves history')

    def test_entry_docs_do_not_present_generic_modes(self):
        agents = self.read('AGENTS.md')
        start = self.read('START.md')
        self.assertNotIn('los modos finales siguen siendo Auditor y Reparación continua', agents)
        self.assertIn('<Proyecto>-auditor', agents)
        self.assertNotIn('workflow-complete-auditor', start)
        self.assertNotIn('workflow-continuous-repair', start)
        self.assertNotIn('workflow-auditor', start)

    def test_status_ends_with_v3_backlog(self):
        status = self.read('docs/status.md')
        last_heading = list(re.finditer(r'(?m)^## ', status))[-1]
        last_section = status[last_heading.start():]
        self.assertIn('C0', last_section)
        self.assertNotIn('El contrato v0.1 sigue siendo', last_section)

    def test_operational_docs_have_no_maintainer_home_path(self):
        for relative in (
            'README.md', 'START.md', 'AGENTS.md', 'PLAN_IMPLEMENTACION.md',
            'docs/usage.md', 'docs/setup-dsh.md', 'docs/creator-preset-spec.md',
        ):
            with self.subTest(relative=relative):
                self.assertNotIn('/home/alan', self.read(relative))

    def test_creator_contract_is_generational(self):
        contract = self.read('docs/creator-preset-spec.md')
        self.assertIn('no es el flujo final', contract)
        self.assertIn('generation-manifest.json', contract)
        self.assertIn('<Proyecto>-auditor', contract)
        self.assertIn('<Proyecto>-continuous-repair', contract)

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
        for relative in ('README.md', 'START.md', 'PLAN_IMPLEMENTACION.md',
                         'docs/usage.md', 'docs/setup-dsh.md', 'docs/creator-preset-spec.md'):
            text = self.read(relative)
            for pattern in forbidden:
                with self.subTest(relative=relative, pattern=pattern):
                    self.assertNotIn(pattern, text)


if __name__ == '__main__':
    unittest.main()
