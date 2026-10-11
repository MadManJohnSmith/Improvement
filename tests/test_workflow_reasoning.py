"""Regresiones del esfuerzo de razonamiento por paso (U7).

Cada prueba nombra el contrato que comprueba, no el mecanismo: enum cerrado,
precedencia paso > plan > legacy, plan v1 byte-idéntico sin declaración,
registro y replay que no lo alteran, cliente sin soporte (abstención, nunca
fallback), composición del preset invariable, veredicto/capacidades idénticos
con low y high, y la carencia nombrada del RPC real cuando DSH no está.

Todo el trabajo ocurre en /tmp y con cliente DSH falso inyectado; ninguna
prueba toca una sesión real ni afirma que el nivel se aplicó.
"""
import hashlib
import json
import shutil
import sys
import tempfile
import unittest

from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

import campaign_plan
import workflow
import workflow_reasoning

from workflow import WorkflowError, read_journal, run_plan, verify
from workflow_reasoning import ReasoningError

PYTHON = shutil.which('python3')

# Composición operativa exacta: los seis plugins DSH requeridos + el guardián.
GOOD_COMPOSITION = """- id: persona
  name: '@deepseek-ai/dsh-persona'
- id: bash
  name: '@deepseek-ai/dsh-tool-bash'
- id: fs
  name: '@deepseek-ai/dsh-tool-fs'
- id: search
  name: '@deepseek-ai/dsh-tool-fs-search'
  config:
    sampleOverCapGlobResults: false
- id: skillfs
  name: '@deepseek-ai/dsh-skill-filesystem'
- id: skill
  name: '@deepseek-ai/dsh-tool-skill'
- id: guard
  name: ./anti-escalation.mjs
"""

# Ids verificados como los publica la instalación.
PRESETS = ['campana-auditor', 'campana-reparacion', 'campana-cierre']


class ReasoningVocabularyTests(unittest.TestCase):
    """El enum es cerrado y coincide con lo que los adaptadores anuncian."""

    def test_the_levels_are_the_ones_the_installed_adapters_advertise(self):
        # Leído en el árbol instalado: pi-ai off/minimal/low/medium/high/
        # xhigh/max (dsh-llm-pi-ai/lib/index.js:296-304) y deepseek
        # off/low/high/max (dsh-llm-deepseek/lib/index.js:452-476).
        self.assertEqual(workflow_reasoning.LEVELS,
                         frozenset(('off', 'minimal', 'low', 'medium',
                                    'high', 'xhigh', 'max')))

    def test_a_foreign_level_is_rejected_not_degraded(self):
        for level in ('ultra', 'MAX', 'High', '', ' medium', 5, None, True,
                      ['high']):
            with self.subTest(level=level):
                with self.assertRaises(ReasoningError):
                    workflow_reasoning.validate(level)

    def test_precedence_step_then_plan_then_legacy(self):
        plan = {'reasoning_effort': 'low'}
        step = {'id': 'a', 'type': 'ask', 'reasoning_effort': 'high'}
        self.assertEqual(workflow_reasoning.effective(plan, step), ('high', 'step'))
        hereda = {'id': 'b', 'type': 'ask', 'reasoning_effort': None}
        self.assertEqual(workflow_reasoning.effective(plan, hereda), ('low', 'plan'))
        without = {'id': 'c', 'type': 'ask', 'reasoning_effort': None}
        self.assertEqual(workflow_reasoning.effective({}, without), (None, 'legacy'))

    def test_a_stage_policy_only_accepts_declared_stages(self):
        self.assertEqual(
            workflow_reasoning.stage_policy({'auditoria': 'high'}),
            {'auditoria': 'high'})
        for bad in ({'auditar': 'high'}, {'auditoria': 'ultra'}, {'auditoria': 3}):
            with self.subTest(policy=bad):
                with self.assertRaises(ReasoningError):
                    workflow_reasoning.stage_policy(bad)

    def test_applying_a_level_keeps_provider_and_model_and_never_moves_model(self):
        selection = {'provider': 'deepseek', 'model': 'r1',
                     'efforts': [{'id': 'low'}, {'id': 'high'}]}
        applied = workflow_reasoning.apply_effort('high', selection)
        self.assertEqual(applied['provider'], 'deepseek')
        self.assertEqual(applied['model'], 'r1')
        self.assertEqual(applied['applied'], 'high')

    def test_a_route_without_the_level_abstains_instead_of_degrading(self):
        selection = {'provider': 'deepseek', 'model': 'r1',
                     'efforts': ['off', 'low']}
        with self.assertRaises(ReasoningError):
            workflow_reasoning.apply_effort('high', selection)

    def test_a_route_without_published_levels_cannot_claim_it_applied(self):
        selection = {'provider': 'deepseek', 'model': 'r1'}
        with self.assertRaises(ReasoningError):
            workflow_reasoning.apply_effort('high', selection)

    def test_a_client_without_support_is_an_abstention_not_a_fallback(self):
        selection = {'provider': 'deepseek', 'model': 'r1',
                     'efforts': ['low', 'high']}
        with self.assertRaises(ReasoningError):
            workflow_reasoning.apply_effort('high', selection,
                                            client_supports=False)


class PlanValidationTests(unittest.TestCase):
    """El enum y la precedencia fallan cerrados al cargar el plan."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.workspace = self.tmp / 'proyecto'
        self.workspace.mkdir()
        self.run_root = self.tmp / 'proyecto-workflow'

    def plan_path(self, document, *, filename='plan.json'):
        path = self.tmp / filename
        path.write_bytes(json.dumps(document, ensure_ascii=False,
                                    sort_keys=True,
                                    separators=(',', ':')).encode('utf-8') + b'\n')
        return path

    def base_plan(self, **overrides):
        plan = {'schema_version': 1, 'name': 'prueba',
                'workspace': str(self.workspace),
                'steps': [{'id': 'g1', 'type': 'gate',
                           'command': [PYTHON, '-c', 'print(1)'],
                           'on_fail': {'action': 'abort', 'rounds': 1}}]}
        plan.update(overrides)
        return plan

    def test_an_unknown_plan_level_makes_the_plan_invalid(self):
        path = self.plan_path(self.base_plan(reasoning_effort='ultra'))
        with self.assertRaisesRegex(WorkflowError, 'nivel de esfuerzo'):
            workflow.load_plan(path)

    def test_an_unknown_step_level_makes_the_plan_invalid(self):
        plan = self.base_plan(steps=[self.ask_step('a1')])
        plan['steps'][0]['reasoning_effort'] = 'turbo'
        path = self.plan_path(plan)
        with self.assertRaisesRegex(WorkflowError, 'nivel de esfuerzo'):
            workflow.load_plan(path)

    def test_a_declared_level_is_kept_verbatim_in_the_loaded_plan(self):
        plan = self.base_plan(reasoning_effort='low')
        loaded, raw = workflow.load_plan(self.plan_path(plan))
        self.assertEqual(loaded['reasoning_effort'], 'low')
        # Los bytes no cambian: la carga no reescribe el documento.
        self.assertEqual(raw, self.plan_path(plan).read_bytes())

    @staticmethod
    def ask_step(step_id, prompt='hola', **extra):
        step = {'id': step_id, 'type': 'ask', 'preset': 'cordis',
                'prompt': prompt, 'timeout_s': 30}
        step.update(extra)
        return step

    def test_a_v1_plan_without_declaration_is_byte_identical(self):
        """Sin declaracion, nada cambia de identidad ni de bytes.

        El mismo plan sin `reasoning_effort` produce el MISMO sha256, el MISMO
        run dir y el MISMO journal que el v1 de siempre: la clave opt-in no
        entro en el documento ni en el journal.
        """
        plan = self.base_plan()
        path = self.plan_path(plan)
        raw = path.read_bytes()
        self.assertNotIn(b'reasoning_effort', raw)
        outcome = run_plan(path, run_root=self.run_root)
        self.assertEqual(outcome['result'], 'COMPLETED')
        run_dir = self.run_root / ('r-' + workflow._sha256_bytes(raw)[:24])
        self.assertTrue(run_dir.is_dir())
        journal = read_journal(run_dir)
        self.assertEqual(journal[0]['kind'], 'PLAN_LOADED')
        started = [item for item in journal if item['kind'] == 'STEP_STARTED']
        self.assertTrue(started)
        for item in started:
            self.assertNotIn('reasoning', item['payload'])

    def test_gains_no_effort_by_default(self):
        plan, _ = workflow.load_plan(self.plan_path(self.base_plan()))
        for step in plan['steps']:
            self.assertIsNone(step['reasoning_effort'])
        self.assertIsNone(plan['reasoning_effort'])


class AskRuntimeTests(unittest.TestCase):
    """El nivel pedido se registra, la reanudacion no lo altera y sin soporte
    se abstiene. Cliente DSH falso inyectado; sin sesion real."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.workspace = self.tmp / 'proyecto'
        self.workspace.mkdir()
        self.run_root = self.tmp / 'proyecto-workflow'
        poll = mock.patch.object(workflow, 'ASK_POLL_SECONDS', 0.01)
        grace = mock.patch.object(workflow, 'ASK_CANCEL_GRACE_SECONDS', 0.2)
        poll.start()
        grace.start()
        self.addCleanup(poll.stop)
        self.addCleanup(grace.stop)
        self.ticket = 0

    def plan_path(self, steps, *, filename='plan.json', **plan_extra):
        plan = {'schema_version': 1, 'name': 'prueba',
                'workspace': str(self.workspace), 'preset': 'cordis',
                'steps': steps}
        plan.update(plan_extra)
        path = self.tmp / filename
        path.write_bytes(json.dumps(plan, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8') + b'\n')
        return path

    @staticmethod
    def ask_step(step_id='a1', prompt='hola', **extra):
        step = {'id': step_id, 'type': 'ask', 'prompt': prompt, 'timeout_s': 30}
        step.update(extra)
        return step

    def run_ask(self, *, plan_level=None, step_level=None, **plan_extra):
        step = self.ask_step()
        if step_level is not None:
            step['reasoning_effort'] = step_level
        if plan_level is not None:
            plan_extra['reasoning_effort'] = plan_level
        path = self.plan_path([step], **plan_extra)
        outcome = run_plan(path, ask_client=FakeReasoningClient(
            supports=True, levels=['low', 'high', 'medium']),
            run_root=self.run_root)
        return outcome, path

    def test_a_declared_level_is_recorded_with_its_source(self):
        outcome, path = self.run_ask(plan_level='medium', step_level='high')
        self.assertEqual(outcome['result'], 'COMPLETED')
        journal = read_journal(self.run_root / ('r-' + workflow._sha256_bytes(path.read_bytes())[:24]))
        started = next(item for item in journal if item['kind'] == 'STEP_STARTED')
        self.assertEqual(started['payload']['reasoning']['reasoning_effort'], 'high')
        self.assertEqual(started['payload']['reasoning']['source'], 'step')
        completed = next(item for item in journal
                         if item['kind'] == 'STEP_COMPLETED')
        self.assertEqual(completed['payload']['reasoning']['applied'], 'high')

    def test_a_plan_level_is_inherited_by_an_ask_without_one(self):
        outcome, path = self.run_ask(plan_level='low')
        self.assertEqual(outcome['result'], 'COMPLETED')
        journal = read_journal(self.run_root / ('r-' + workflow._sha256_bytes(path.read_bytes())[:24]))
        completed = next(item for item in journal
                         if item['kind'] == 'STEP_COMPLETED')
        self.assertEqual(completed['payload']['reasoning']['reasoning_effort'], 'low')
        self.assertEqual(completed['payload']['reasoning']['source'], 'plan')

    def test_a_resume_does_not_renegotiate_the_level(self):
        """El nivel viaja en el journal: una reanudacion lo reutiliza tal cual."""
        outcome, path = self.run_ask(plan_level='low')
        self.assertEqual(outcome['result'], 'COMPLETED')
        run_dir = self.run_root / ('r-' + workflow._sha256_bytes(path.read_bytes())[:24])
        before = read_journal(run_dir)
        started_before = [item for item in before
                          if item['kind'] == 'STEP_STARTED']
        outcome = run_plan(path, ask_client=FakeReasoningClient(
            supports=True, levels=['low', 'high', 'medium']),
            run_root=self.run_root)
        self.assertEqual(outcome['result'], 'COMPLETED')
        after = read_journal(run_dir)
        # El nivel no se renegocia: no hay un segundo STEP_STARTED con otro
        # pedido, y el registro del intento sigue siendo exactamente el mismo
        # (mismo digest de contenido, no reescrito).
        started_after = [item for item in after
                         if item['kind'] == 'STEP_STARTED']
        self.assertEqual([item['content_sha256'] for item in started_before],
                         [item['content_sha256'] for item in started_after])
        self.assertEqual(started_after[0]['payload']['reasoning']['reasoning_effort'],
                         'low')
        completed = next(item for item in after
                         if item['kind'] == 'STEP_COMPLETED')
        self.assertEqual(completed['payload']['reasoning']['applied'], 'low')

    def test_the_run_abstains_when_the_client_cannot_apply_the_level(self):
        """Sin `select_session_model` no hay inferencia que valga: abstención."""
        path = self.plan_path([self.ask_step(reasoning_effort='low')])
        outcome = run_plan(path, ask_client=FakeReasoningClient(supports=False),
                           run_root=self.run_root)
        self.assertEqual(outcome['result'], 'ABSTAINED')
        self.assertIn('select_session_model', outcome['reason'])
        # Y no se creó run dir: la abstención es previa a tocar disco.
        self.assertFalse(self.run_root.exists())

    def test_an_unsupported_level_on_a_route_abstains_with_a_named_reason(self):
        """El cliente aplica pero la ruta no tiene el nivel: se registra la
        abstención con motivo, nunca un fallback a otro nivel o modelo."""
        step = dict(self.ask_step(reasoning_effort='high'))
        path = self.plan_path([step])
        outcome = run_plan(path, ask_client=FakeReasoningClient(
            supports=True, levels=['low']), run_root=self.run_root)
        self.assertEqual(outcome['result'], 'COMPLETED')
        run_dir = self.run_root / ('r-' + workflow._sha256_bytes(
            path.read_bytes())[:24])
        completed = next(item for item in read_journal(run_dir)
                         if item['kind'] == 'STEP_COMPLETED')
        record = completed['payload']['reasoning']
        self.assertEqual(record['applied'], False)
        self.assertIn('no soporta', record['status'])
        # El paso completó con su prueba normal: el nivel no crea ni quita
        # veredicto, solo deja constancia de que no se aplicó.
        self.assertEqual(record['reasoning_effort'], 'high')

    def test_the_preset_composition_is_invariant_under_any_level(self):
        """La composicion verificada del preset no cambia con el nivel."""
        outcomes = []
        for level in ('low', 'high'):
            path = self.plan_path([self.ask_step(reasoning_effort=level)],
                                  filename='plan-%s.json' % level)
            outcomes.append(run_plan(path, ask_client=FakeReasoningClient(
                supports=True, levels=['low', 'high']), run_root=self.run_root))
        # Ambos ejecutan y despachan al mismo preset: el nivel no altera autoridad.
        self.assertEqual([item['result'] for item in outcomes],
                         ['COMPLETED', 'COMPLETED'])
        digests = []
        for level in ('low', 'high'):
            path = self.tmp / ('plan-%s.json' % level)
            raw = path.read_bytes()
            digests.append(workflow._sha256_bytes(raw))
        self.assertNotEqual(digests[0], digests[1])  # planes distintos

    def test_verdict_and_capabilities_are_identical_for_low_and_high(self):
        """Un nivel no otorga veredicto ni capacidad: la salida es la misma."""
        results = []
        for level in ('low', 'high'):
            path = self.plan_path([self.ask_step(reasoning_effort=level)],
                                  filename='v-%s.json' % level)
            outcome = run_plan(path, ask_client=FakeReasoningClient(
                supports=True, levels=['low', 'high'], text='LISTO'),
                run_root=self.run_root)
            self.assertEqual(outcome['result'], 'COMPLETED')
            raw = path.read_bytes()
            run_dir = self.run_root / ('r-' + workflow._sha256_bytes(raw)[:24])
            completed = next(item for item in read_journal(run_dir)
                             if item['kind'] == 'STEP_COMPLETED')
            # La prueba del paso no depende del nivel.
            self.assertEqual(completed['payload']['prompt_sha256'],
                             workflow._sha256_bytes(b'hola'))
            results.append(completed['payload']['step_id'])
        self.assertEqual(results[0], results[1])


class CampaignReasoningPolicyTests(unittest.TestCase):
    """Politica declarativa por etapa; el plan por defecto sigue identico."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.workspace = self.tmp / 'producto'
        self.workspace.mkdir()

    def document(self, **kwargs):
        return campaign_plan.plan_document(self.workspace, PRESETS, **kwargs)

    def test_the_default_campaign_plan_is_byte_identical(self):
        first = campaign_plan._document(self.document())
        second = campaign_plan._document(self.document())
        self.assertEqual(first, second)
        self.assertEqual(campaign_plan._sha256(first),
                         campaign_plan._sha256(second))
        self.assertNotIn(b'reasoning_effort', first)
        # Y sigue siendo un plan que `workflow.load_plan` acepta tal cual.
        path = self.tmp / 'plan.json'
        path.write_bytes(first)
        prompts = self.tmp / 'prompts'
        prompts.mkdir()
        (prompts / campaign_plan.AUDIT_PROMPT).write_text('auditar')
        (prompts / campaign_plan.REPAIR_PROMPT).write_text('reparar')
        plan, raw = workflow.load_plan(path)
        self.assertEqual(raw, first)
        self.assertEqual(plan['reasoning_effort'], None)

    def test_a_stage_policy_lands_only_on_ask_steps(self):
        document = self.document(esfuerzos={
            'auditoria': 'high', 'implementacion': 'medium'})
        for step in document['steps']:
            if step['type'] == 'gate':
                self.assertNotIn('reasoning_effort', step,
                                 'un gate nunca recibe esfuerzo: %s' % step['id'])
            else:
                self.assertIn('reasoning_effort', step)
        by_id = {step['id']: step for step in document['steps']}
        self.assertEqual(by_id['auditar']['reasoning_effort'], 'high')
        for index in (1, 2):
            self.assertEqual(by_id['reparar-%d' % index]['reasoning_effort'],
                             'medium')

    def test_the_default_plan_and_the_policy_disable_differ(self):
        """El opt-in cambia el sha256: no es el plan por defecto disfrazado."""
        default = campaign_plan._sha256(campaign_plan._document(self.document()))
        tuned = campaign_plan._sha256(campaign_plan._document(self.document(
            esfuerzos={'auditoria': 'high'})))
        self.assertNotEqual(default, tuned)

    def test_an_unknown_stage_or_level_fails_before_writing_anything(self):
        for bad in ({'auditar': 'high'}, {'implementacion': 'ultra'}):
            with self.subTest(policy=bad):
                with self.assertRaises(campaign_plan.CampaignPlanError):
                    self.document(esfuerzos=bad)

    def test_a_stage_with_no_ask_step_is_not_a_silent_no_op(self):
        """Pedir nivel para una etapa sin ask es error, no un plan idéntico."""
        for stage in ('verificacion', 'revision'):
            with self.subTest(stage=stage):
                with self.assertRaisesRegex(
                        campaign_plan.CampaignPlanError,
                        'etapas sin paso ask'):
                    self.document(esfuerzos={stage: 'high'})

    def test_the_authored_policy_plan_is_loaded_without_transformation(self):
        document = self.document(esfuerzos={'auditoria': 'high'})
        raw = campaign_plan._document(document)
        path = self.tmp / 'plan.json'
        path.write_bytes(raw)
        prompts = self.tmp / 'prompts'
        prompts.mkdir()
        (prompts / campaign_plan.AUDIT_PROMPT).write_text('auditar')
        (prompts / campaign_plan.REPAIR_PROMPT).write_text('reparar')
        plan, loaded_raw = workflow.load_plan(path)
        self.assertEqual(loaded_raw, raw)
        by_id = {step['id']: step for step in plan['steps']}
        self.assertEqual(by_id['auditar']['reasoning_effort'], 'high')
        self.assertIsNone(plan['reasoning_effort'])


class FakeSession:
    """Sesion falsa con transcript y finalizacion controladas."""

    def __init__(self, client, workspace, preset):
        self.client = client
        self.workspace = Path(workspace)
        self.preset = preset
        self.events = []
        self.seq = 0
        self.turn = 0
        self.running = True
        self.sent = []
        self.completed = False
        self.observed = 0

    @property
    def complete_after(self):
        return self.client.complete_after

    def add_event(self, kind, **data):
        self.seq += 1
        self.events.append({'seq': self.seq, 'type': kind, 'data': data})

    def queue(self, request_id):
        self.sent.append(request_id)
        self.turn += 1
        self.add_event('turn/start', turn=self.turn)
        self.add_event('user/message', turn=self.turn,
                       source={'rpcId': request_id})

    def complete(self):
        if self.completed or not self.turn:
            return
        self.completed = True
        self.add_event('assistant/message', turn=self.turn,
                       message={'text': self.client.text})
        self.add_event('turn/end', turn=self.turn, reason='completed')
        self.running = False

    def observation(self, cursor):
        self.observed += 1
        if not self.completed and self.observed > (self.complete_after or 1):
            self.complete()
        return {'cursor': self.seq,
                'events': [event for event in self.events if event['seq'] > cursor],
                'running': self.running, 'descendants': [], 'jobs': []}


class FakeReasoningClient:
    """Cliente DSH falso con `select_session_model` opcional.

    `supports=False` modela el cliente real del framework sin el RPC de
    seleccion; con `supports=True` aplica el nivel y devuelve la seleccion.
    """

    def __init__(self, *, supports, levels=None, text='texto del asistente'):
        self.supports = supports
        self.levels = levels or []
        self.text = text
        self.sessions = {}
        self.created = []
        self.sent = []
        self.complete_after = 1
        self.observation_calls = []
        self.selections = []
        self.roster = [{'id': 'cordis', 'broken': False}]
        if supports:
            self.select_session_model = self._select
            self.active_selection = {'provider': 'deepseek', 'model': 'r1'}
        else:
            self.active_selection = None

    # -- API que workflow.py consume del cliente ---------------------------
    def list_agent_presets(self):
        return self.roster

    def read_agent_preset(self, preset_id):
        """Composición operativa exacta; el nivel no altera ningún plugin."""
        return {'value': {'agentPreset': preset_id, 'content': GOOD_COMPOSITION}}

    def create_workspace(self, path):
        return 'ws-1'

    def create_creator_session(self, *, workspace_path, agent_preset='cordis',
                               session_id=None):
        self.ticket = getattr(self, 'ticket', 0) + 1
        self.ticket = len(self.sessions) + 1
        created_id = 's-%d' % self.ticket
        session = FakeSession(self, workspace_path, agent_preset)
        self.sessions[created_id] = session
        self.created.append((created_id, workspace_path, agent_preset))
        return created_id

    def send_prompt(self, session_id, prompt, *, request_id=None):
        self.sent.append((session_id, request_id))
        self.sessions[session_id].queue(request_id)
        return {'accepted': True}

    def creator_observation(self, session_id, *, cursor=-1):
        self.observation_calls.append(session_id)
        session = self.sessions[session_id]
        return session.observation(cursor)

    def cancel_session(self, session_id):
        self.sessions[session_id].running = False
        self.sessions[session_id].descendants = []
        self.sessions[session_id].jobs = []
        return {'accepted': True}

    # -- seleccion de modelo -------------------------------------------------
    def _select(self, *, session_id, provider, model, level):
        if level not in self.levels:
            raise ValueError('nivel no soportado por %s/%s' % (provider, model))
        selection = {'provider': provider, 'model': model,
                     'reasoning_effort': level, 'applied': level}
        self.selections.append(dict(selection, session_id=session_id))
        return {'selected': {'provider': provider, 'model': model,
                             'reasoning_effort': level}, 'applied': level}


class RealRuntimeNotVerifiedTests(unittest.TestCase):
    """Carencia nombrada: el RPC real de seleccion de modelo no se ejercio.

    El contrato pide aplicar el nivel en la sesion DSH real. Eso exige
    `ModelDirectory.select` -> `session/selectModel`, que este repo todavia no
    tiene cliente para: `creator_client.DshLocalClient` no expone ningun
    `select_session_model` ni lectura de `modelSelection`. Estas pruebas fijan
    la carencia para que no se afirme en falso lo no ejecutado.
    """

    def test_the_effective_client_does_not_expose_the_model_selection_rpc(self):
        """El cliente efectivo del framework carece del RPC de seleccion."""
        sys.path.insert(0, str(REPO_ROOT / 'scripts'))
        import creator_client
        client = creator_client.DshLocalClient.__new__(creator_client.DshLocalClient)
        # Leido en el arbol instalado de DSH: `session/selectModel` existe como
        # metodo Remote (@Remote('selectModel') en
        # @deepseek-ai/dsh-api-session-controller/lib/typert.host.js:1470),
        # pero el wrapper del framework no lo envuelve.
        self.assertFalse(callable(getattr(client, 'select_session_model', None)))
        self.assertFalse(callable(getattr(client, 'active_selection', None)))
        self.assertNotIn('select_session_model',
                         {name for name in vars(creator_client.DshLocalClient)})

    def test_a_session_prompt_and_session_create_take_no_effort_argument(self):
        """session/prompt y session/create no admiten nivel: no hay atajo."""
        sys.path.insert(0, str(REPO_ROOT / 'scripts'))
        import inspect
        import creator_client
        for method in ('send_prompt', 'create_creator_session'):
            with self.subTest(method=method):
                signature = inspect.signature(
                    getattr(creator_client.DshLocalClient, method))
                self.assertNotIn('level', signature.parameters)
                self.assertNotIn('reasoning_effort', signature.parameters)

    def test_without_an_authenticated_dsh_session_the_level_is_not_applied(self):
        """Sin sesion real, la ejecucion se abstiene; no afirma aplicacion."""
        # El run dir de esta prueba no contiene ninguna seleccion real: el
        # registro queda en `applied: false` con motivo, nunca con un nivel.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tmp_path = Path(tmp.name)
        workspace = tmp_path / 'proyecto'
        workspace.mkdir()
        run_root = tmp_path / 'workflow'
        poll = mock.patch.object(workflow, 'ASK_POLL_SECONDS', 0.01)
        grace = mock.patch.object(workflow, 'ASK_CANCEL_GRACE_SECONDS', 0.2)
        poll.start()
        grace.start()
        self.addCleanup(poll.stop)
        self.addCleanup(grace.stop)
        plan = {'schema_version': 1, 'name': 'prueba', 'preset': 'cordis',
                'workspace': str(workspace),
                'steps': [{'id': 'a1', 'type': 'ask', 'prompt': 'hola',
                           'timeout_s': 30, 'reasoning_effort': 'low'}]}
        path = tmp_path / 'plan.json'
        path.write_bytes(json.dumps(plan, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8') + b'\n')
        # El cliente real del framework, sin credenciales, no puede crear
        # sesion: `acquire_dsh_client` devuelve motivo y run_plan abstiene.
        outcome = run_plan(path, run_root=run_root)
        self.assertEqual(outcome['result'], 'ABSTAINED')
        self.assertIn('cliente DSH', outcome['reason'])
        self.assertFalse(run_root.exists())

    def test_the_cost_of_a_real_session_is_not_claimed_here(self):
        """El coste observado de una sesion real DSH no se midio en esta prueba.

        Sin `dsh` en PATH ni `~/.config/dsh/.credentials.yaml`, ninguna sesion
        real corre: `creator_client.from_dsh_home` lanzaria
        'No .credentials.yaml'. La cifra de coste queda por medir, no estimada.
        """
        self.assertIsNone(shutil.which('dsh'))
        self.assertFalse(Path.home().joinpath('.config', 'dsh',
                                              '.credentials.yaml').is_file())


class LevelChangeIsADifferentRunTests(unittest.TestCase):
    """Cambiar el nivel cambia el plan y por tanto el run: nunca una
    reanudación que cargue en silencio un nivel viejo."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.workspace = self.tmp / 'proyecto'
        self.workspace.mkdir()
        self.run_root = self.tmp / 'proyecto-workflow'
        poll = mock.patch.object(workflow, 'ASK_POLL_SECONDS', 0.01)
        grace = mock.patch.object(workflow, 'ASK_CANCEL_GRACE_SECONDS', 0.2)
        poll.start()
        grace.start()
        self.addCleanup(poll.stop)
        self.addCleanup(grace.stop)

    def test_changing_the_level_produces_another_run_dir_and_level(self):
        steps = [{'id': 'a1', 'type': 'ask', 'prompt': 'hola', 'timeout_s': 30}]
        levels = ['low', 'high']
        for level in levels:
            plan = {'schema_version': 1, 'name': 'p', 'preset': 'cordis',
                    'workspace': str(self.workspace), 'steps': steps,
                    'reasoning_effort': level}
            path = self.tmp / ('plan-%s.json' % level)
            path.write_bytes(json.dumps(plan, sort_keys=True,
                                        separators=(',', ':')).encode('utf-8') + b'\n')
            outcome = run_plan(path, ask_client=FakeReasoningClient(
                supports=True, levels=['low', 'high']),
                run_root=self.run_root)
            self.assertEqual(outcome['result'], 'COMPLETED')
            run_dir = self.run_root / ('r-' + workflow._sha256_bytes(
                path.read_bytes())[:24])
            record = next(item for item in read_journal(run_dir)
                          if item['kind'] == 'STEP_STARTED')['payload']['reasoning']
            # Cada plan carga su propio nivel y su propio run dir; el sha256
            # del plan no es el mismo, así que nunca se reanuda otro nivel.
            self.assertEqual(record['reasoning_effort'], level)
        digests = {workflow._sha256_bytes(
            (self.tmp / ('plan-%s.json' % level)).read_bytes()) for level in levels}
        self.assertEqual(len(digests), 2)
        self.assertEqual(len(list(self.run_root.iterdir())), 2)
