"""Architecture 3.0 consistency checks for versioned behavioral documents."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ArchitectureConsistencyTest(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text()

    def test_normative_architecture_and_backlog_are_v3(self):
        architecture = self.read('ARQUITECTURA_FLUJO_AGENTES.md')
        plan = self.read('PLAN_IMPLEMENTACION.md')
        self.assertIn('**Versión:** 3.0', architecture)
        self.assertIn('C0', plan)
        self.assertIn('C7', plan)
        self.assertNotIn('todas las etapas globales permanecen `PARCIAL`', plan.lower())

    def test_entry_docs_do_not_present_generic_modes_as_final(self):
        agents = self.read('AGENTS.md')
        start = self.read('START.md')
        self.assertNotIn('los modos finales siguen siendo Auditor y Reparación continua', agents)
        self.assertIn('<Proyecto>-auditor', agents)
        self.assertIn('Despacho legado del MVP', start)
        self.assertIn('no deben instalarse, copiarse ni presentarse como modos finales', start)

    def test_mvp_skills_are_marked_fixture_and_have_no_shell_write_fallback(self):
        for relative in (
            'skills/workflow-auditor/SKILL.md',
            'skills/workflow-complete-auditor/SKILL.md',
            'skills/workflow-continuous-repair/SKILL.md',
        ):
            with self.subTest(relative=relative):
                text = self.read(relative)
                self.assertRegex(text, r'(?i)fixture|fuente normativa')
                self.assertIn('No es', text)
                self.assertNotIn('bash con redirección', text)
                self.assertNotRegex(text, r'(?m)^# .*v0\.1')

    def test_historical_plans_have_local_no_execute_markers(self):
        complete = self.read('docs/PLAN_EJECUCION_ARQUITECTURA_COMPLETA.md')
        pending = self.read('docs/PLAN_PENDIENTES_CIERRE_NUCLEO.md')
        self.assertIn('CONTENIDO HISTÓRICO — NO EJECUTAR', complete)
        self.assertIn('prompt archivado (NO pegar ni ejecutar)', complete)
        self.assertIn('ARCHIVO HISTÓRICO — NO EJECUTAR', pending)
        self.assertIn('superseded por C0–C7', pending)

    def test_status_ends_with_v3_backlog_not_v01_debt(self):
        status = self.read('docs/status.md')
        last_heading = list(re.finditer(r'(?m)^## ', status))[-1]
        last_section = status[last_heading.start():]
        self.assertIn('Pendiente vigente — arquitectura 3.0', last_section)
        self.assertIn('C0', last_section)
        self.assertNotIn('El contrato v0.1 sigue siendo', last_section)

    def test_operational_docs_have_no_maintainer_home_path(self):
        for relative in (
            'README.md', 'START.md', 'AGENTS.md', 'PLAN_IMPLEMENTACION.md',
            'docs/usage.md', 'docs/setup-dsh.md', 'docs/creator-preset-spec.md',
            'docs/trial-readiness.md', 'docs/diagrams/README.md',
        ):
            with self.subTest(relative=relative):
                self.assertNotIn('/home/alan', self.read(relative))

    def test_creator_contract_rejects_two_file_preset_as_final(self):
        contract = self.read('docs/creator-preset-spec.md')
        self.assertIn('no es el flujo final', contract)
        self.assertIn('generation-manifest.json', contract)
        self.assertIn('<Proyecto>-auditor', contract)
        self.assertIn('<Proyecto>-continuous-repair', contract)


if __name__ == '__main__':
    unittest.main()
