"""Pruebas del paso ask del ejecutor de workflow (U3) con cliente DSH falso
inyectado (patrón del FakeClient de test_acceptance_reviewer): despacho con
preset verificado, quiescencia transitiva fail-closed, deadline con cancelación
y gracia, trampa de red, y reanudación [corr-3] (mismo request_id a la misma
sesión viva; sesión perdida retiene, nunca sesión nueva). Todo en /tmp."""
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
import urllib.error

from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

import workflow
from workflow import WorkflowError, read_journal, run_plan, verify

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


class FakeSession:
    """Sesión DSH falsa: transcript, estado vivo y guion de finalización."""

    def __init__(self, client, workspace, preset):
        self.client = client
        self.workspace = Path(workspace)
        self.preset = preset
        self.events = []
        self.seq = 0
        self.turn = 0
        self.running = True
        self.descendants = []
        self.jobs = []
        self.sent = []  # request_ids encolados
        self.queue_only = False  # no registrar el mensaje en el transcript
        self.assistant_text = 'texto del asistente'
        # Uso facturable del turno, como DSH lo persiste en assistant/message;
        # totalTokens >= input + output + cacheRead (norma de _normalise_usage).
        self.usage = {'inputTokens': 120, 'outputTokens': 40,
                      'cacheReadTokens': 300, 'totalTokens': 460}
        self.completed = False
        self.observed = 0

    @property
    def complete_after(self):
        """Observaciones tras el send para completar; lo decide el cliente."""
        return self.client.complete_after

    @property
    def on_complete(self):
        """Callback de finalización; lo decide el cliente."""
        return self.client.on_complete

    def add_event(self, event_type, **data):
        self.seq += 1
        self.events.append({'seq': self.seq, 'type': event_type, 'data': data})

    def queue(self, request_id):
        self.sent.append(request_id)
        if self.queue_only:
            return
        self.turn += 1
        self.add_event('turn/start', turn=self.turn)
        self.add_event('user/message', turn=self.turn, source={'rpcId': request_id})

    def complete(self):
        if self.completed or not self.turn:
            return
        self.completed = True
        extra = {} if self.usage is None else {'usage': dict(self.usage)}
        self.add_event('assistant/message', turn=self.turn,
                       message={'text': self.assistant_text}, **extra)
        self.add_event('turn/end', turn=self.turn, reason='completed')
        self.running = False
        if self.on_complete is not None:
            self.on_complete(self)

    def observation(self, cursor):
        self.observed += 1
        if (self.complete_after is not None and not self.completed
                and self.observed > self.complete_after):
            self.complete()
        return {'cursor': self.seq,
                'events': [event for event in self.events if event['seq'] > cursor],
                'running': self.running,
                'descendants': list(self.descendants),
                'jobs': list(self.jobs)}


class FakeAskClient:
    """Cliente DSH falso: presets, sesiones nuevas por intento, prompts,
    observaciones y cancelación."""

    def __init__(self, *, preset_id='cordis', content=GOOD_COMPOSITION,
                 roster=None):
        self.preset_id = preset_id
        self.content = content
        self.roster = roster if roster is not None else [{'id': preset_id, 'broken': False}]
        self.sessions = {}
        self.created = []         # (session_id, workspace, preset)
        self.sent = []            # (session_id, request_id)
        self.prompts = []         # (session_id, prompt_text)
        self.cancels = []         # session_id
        self.observation_calls = []  # (session_id, cursor)
        self.obs_error_after = None  # 1 => la 2ª observación falla
        self.obs_error = None     # excepción puntual de la próxima observación
        self.cancel_clears = True  # la cancelación deja la sesión quiescente
        self.on_send = None       # callable(session) tras encolar el prompt
        self.auto_complete_on_send = False  # la sesión completa al encolar
        self.queue_only_new = False  # las sesiones nuevas no registran transcript
        self.complete_after = None  # observaciones tras send para completar
        self.on_complete = None  # callback de finalización de cada sesión

    # --- presets
    def list_agent_presets(self):
        return {'value': {'items': [dict(item) for item in self.roster]}}

    def read_agent_preset(self, preset_id):
        return {'value': {'agentPreset': preset_id, 'content': self.content}}

    # --- sesiones
    def create_creator_session(self, *, workspace_path, agent_preset=None,
                               session_id=None):
        session = FakeSession(self, workspace_path, agent_preset)
        session.queue_only = self.queue_only_new
        sid = 'session-%d' % (len(self.sessions) + 1)
        self.sessions[sid] = session
        self.created.append((sid, Path(workspace_path), agent_preset))
        return sid

    def send_prompt(self, session_id, prompt, request_id=None):
        self.sent.append((session_id, request_id))
        self.prompts.append((session_id, prompt))
        session = self.sessions[session_id]
        session.queue(request_id)
        if self.on_send is not None:
            self.on_send(session)
        if self.auto_complete_on_send:
            session.complete()
        return {'queued': True}

    def creator_observation(self, session_id, cursor=-1):
        self.observation_calls.append((session_id, cursor))
        session = self.sessions.get(session_id)
        if session is None:
            # Mismo contrato que DshLocalClient.creator_observation.
            raise ValueError(
                'DSH session %s no aparece en session/list' % session_id)
        if self.obs_error is not None:
            error, self.obs_error = self.obs_error, None
            raise error
        if self.obs_error_after is not None:
            if len(self.observation_calls) > self.obs_error_after:
                raise urllib.error.URLError('red caída a mitad del poll')
        return session.observation(cursor)

    def cancel_session(self, session_id):
        self.cancels.append(session_id)
        if self.cancel_clears:
            session = self.sessions[session_id]
            session.running = False
            session.descendants = []
            session.jobs = []
        return {'accepted': True}


class WorkflowAskTests(unittest.TestCase):
    def test_intermediate_tool_only_message_does_not_abort_correlated_turn(self):
        state = workflow._new_ask_state()
        observed = {"running": True, "events": [
            {"seq": 1, "type": "turn/start", "data": {"turn": 4}},
            {"seq": 2, "type": "user/message", "data": {"turn": 4,
             "message": {"source": {"rpcId": "req-4"}}}},
            {"seq": 3, "type": "assistant/message", "data": {"turn": 4,
             "message": {"content": [{"type": "reasoning", "text": "private"},
                                      {"type": "tool-call", "name": "skill"}]}}},
        ], "descendants": [], "jobs": []}
        self.assertEqual(workflow._fold_ask(observed, state, "req-4")["texts"], [])
        self.assertFalse(state["terminal"])

    def test_assistant_text_accepts_real_content_blocks_without_tool_payload(self):
        self.assertEqual(workflow._assistant_text({"message": {"content": [
            {"type": "text", "text": "Audit complete"},
            {"type": "tool_use", "name": "skill", "input": {"secret": "hidden"}},
            {"type": "text", "text": "Evidence recorded"},
        ]}}), "Audit complete\nEvidence recorded")
        self.assertIsNone(workflow._assistant_text({"message": {"content": [
            {"type": "tool_use", "name": "skill", "input": {"secret": "hidden"}},
        ]}}))

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.workspace = self.tmp / 'proyecto'
        self.workspace.mkdir()
        self.run_root = self.tmp / 'proyecto-workflow'
        # Polls y gracia cortos para los plazos de prueba.
        poll = mock.patch.object(workflow, 'ASK_POLL_SECONDS', 0.01)
        grace = mock.patch.object(workflow, 'ASK_CANCEL_GRACE_SECONDS', 0.2)
        poll.start()
        grace.start()
        self.addCleanup(poll.stop)
        self.addCleanup(grace.stop)

    def write_plan(self, steps, *, filename='plan.json', preset='cordis'):
        plan = {'schema_version': 1, 'name': 'prueba', 'workspace': str(self.workspace),
                'steps': steps}
        if preset is not None:
            plan['preset'] = preset
        path = self.tmp / filename
        path.write_bytes(json.dumps(plan, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8') + b'\n')
        return path

    @staticmethod
    def ask(step_id='a1', prompt='resume el estado', **extra):
        # Techo alto por defecto: el uso diminuto del fake no lo toca; los
        # tests del techo lo reducen por paso.
        step = {'id': step_id, 'type': 'ask', 'prompt': prompt, 'timeout_s': 1,
                'budget_tokens': 1000000}
        step.update(extra)
        return step

    def expected_request_id(self, plan_path, step_id, attempt):
        run_id = 'r-' + hashlib.sha256(plan_path.read_bytes()).hexdigest()[:24]
        return hashlib.sha256(
            ('%s|%s|%d' % (run_id, step_id, attempt)).encode('utf-8')).hexdigest()

    def payloads(self, run_dir):
        return read_journal(run_dir)

    # -- ask completo: STEP_COMPLETED con digests, texto en observations/

    def test_ask_completo_registra_digests_y_texto(self):
        client = FakeAskClient()
        plan_path = self.write_plan([
            self.ask('a1', result_contract={'path': 'resultado.json'}),
            {'id': 'g2', 'type': 'gate', 'command': ['printenv', 'WORKFLOW_OBSERVATION'],
             'on_fail': {'action': 'abort', 'rounds': 1}},
        ])
        client.complete_after = 1
        client.on_complete = lambda session: _write_result(
            session.workspace, 'resultado.json', {'ok': True, 'detalle': 'hecho'})
        outcome = run_plan(plan_path, ask_client=client)
        self.assertEqual(outcome['result'], 'COMPLETED')
        # Sesión nueva con el preset verificado del plan; request determinista.
        self.assertEqual(len(client.created), 1)
        session_id, workspace, preset = client.created[0]
        self.assertEqual(preset, 'cordis')
        self.assertEqual(workspace, self.workspace)
        expected_request = self.expected_request_id(plan_path, 'a1', 1)
        self.assertEqual(client.sent, [(session_id, expected_request)])

    def test_the_result_contract_travels_in_the_prompt(self):
        """El nombre exacto de la evidencia llega EN el prompt del turno.

        La campaña operativa del 2026-11-13 midió un turno que hizo toda la
        auditoría (34 pasos, findings, handoffs, verificaciones reales) y
        falló solo por el nombre del fichero de evidencia: el plan exigía
        auditoria.json y la sesión nunca lo recibió, así que el modelo escribió
        audit-report.md. El contrato viaja ahora en el prompt.
        """
        client = FakeAskClient()
        plan_path = self.write_plan([
            self.ask('auditar', prompt='Audita el producto.',
                     result_contract={'evidence_name': 'campana',
                                      'path': 'auditoria.json'}),
        ])
        client.complete_after = 1
        client.on_complete = lambda session: _write_result(
            session.workspace, 'campana/auditoria.json', {'verdict': 'PASS'})
        outcome = run_plan(plan_path, ask_client=client)
        self.assertEqual(outcome['result'], 'COMPLETED')
        session_id, prompt = client.prompts[0]
        self.assertIn('evidence/campana/auditoria.json', prompt)
        self.assertIn('Resultado obligatorio de este paso', prompt)
        # El prompt original no se pierde: el contrato se añade al final.
        self.assertTrue(prompt.startswith('Audita el producto.'))
        session_id, workspace, preset = client.created[0]
        self.assertEqual(preset, 'cordis')
        self.assertEqual(workspace, self.workspace)
        expected_request = self.expected_request_id(plan_path, 'a1', 1)
        self.assertEqual(client.sent, [(session_id, expected_request)])
        payloads = self.payloads(outcome['run_dir'])
        completed = [p for p in payloads
                     if p['kind'] == 'STEP_COMPLETED' and p['payload']['step_id'] == 'a1']
        self.assertEqual(len(completed), 1)
        payload = completed[0]['payload']
        self.assertEqual(payload['prompt_sha256'],
                         hashlib.sha256(client.prompts[0][1].encode('utf-8')).hexdigest())
        self.assertIn('evidence/resultado.json', client.prompts[0][1],
                      'el contrato de resultado debe viajar en el prompt')
        self.assertEqual(payload['result_path'], 'evidence/resultado.json')
        result_bytes = (self.workspace / 'evidence' / 'resultado.json').read_bytes()
        self.assertEqual(payload['result_sha256'], hashlib.sha256(result_bytes).hexdigest())
        observation = Path(outcome['run_dir']) / payload['observation']
        self.assertEqual(hashlib.sha256(observation.read_bytes()).hexdigest(),
                         payload['output_sha256'])
        body = json.loads(observation.read_bytes())
        self.assertEqual(body['text'], 'texto del asistente')
        self.assertEqual(body['status'], 'completed')
        self.assertEqual(body['session_id'], session_id)
        # WORKFLOW_OBSERVATION: la gate posterior recibió la ruta del resultado.
        gate_observation = [p for p in payloads
                            if p['kind'] == 'STEP_COMPLETED' and p['payload']['step_id'] == 'g2']
        gate_body = json.loads((Path(outcome['run_dir']) /
                                gate_observation[0]['payload']['observation']).read_bytes())
        self.assertEqual(gate_body['stdout'],
                         str(self.workspace / 'evidence' / 'resultado.json') + '\n')
        self.assertEqual(verify(outcome['run_dir'])['events'], len(payloads))

    def test_the_result_contract_travels_in_the_prompt(self):
        """El nombre exacto de la evidencia llega EN el prompt del turno.

        La campaña operativa del 2026-11-13 midió un turno que hizo toda la
        auditoría (34 pasos, findings, handoffs, verificaciones reales) y
        falló solo por el nombre del fichero de evidencia: el plan exigía
        auditoria.json y la sesión nunca lo recibió, así que el modelo escribió
        audit-report.md. El contrato viaja ahora en el prompt.
        """
        client = FakeAskClient()
        plan_path = self.write_plan([
            self.ask('auditar', prompt='Audita el producto.',
                     result_contract={'evidence_name': 'campana',
                                      'path': 'auditoria.json'}),
        ])
        client.complete_after = 1
        client.on_complete = lambda session: _write_result(
            session.workspace, 'campana/auditoria.json', {'verdict': 'PASS'})
        outcome = run_plan(plan_path, ask_client=client)
        self.assertEqual(outcome['result'], 'COMPLETED')
        session_id, prompt = client.prompts[0]
        self.assertIn('evidence/campana/auditoria.json', prompt)
        self.assertIn('Resultado obligatorio de este paso', prompt)
        # El prompt original no se pierde: el contrato se añade al final.
        self.assertTrue(prompt.startswith('Audita el producto.'))
        session_id, workspace, preset = client.created[0]
        self.assertEqual(preset, 'cordis')
        self.assertEqual(workspace, self.workspace)
        expected_request = self.expected_request_id(plan_path, 'auditar', 1)
        self.assertEqual(client.sent, [(session_id, expected_request)])

    # -- abstención por preset antes de crear run dir

    def test_ask_sin_preset_verificado_abstiene_sin_run_dir(self):
        cases = [
            ({'preset': None}, FakeAskClient(), 'el plan no declara preset'),
            ({}, FakeAskClient(roster=[{'id': 'otro', 'broken': False}]),
             'preset ausente en agentPresets/list'),
            ({}, FakeAskClient(roster=[{'id': 'cordis', 'broken': True}]),
             'preset roto en agentPresets/list'),
            ({}, FakeAskClient(content=GOOD_COMPOSITION.replace(
                "name: ./anti-escalation.mjs", "name: '@deepseek-ai/dsh-tool-nota'")),
             'guardián anti-escalación ausente'),
        ]
        for index, (extra, client, fragment) in enumerate(cases):
            with self.subTest(case=index):
                plan_path = self.write_plan([self.ask()],
                                            preset=extra.get('preset', 'cordis'),
                                            filename='preset-%d.json' % index)
                outcome = run_plan(plan_path, ask_client=client)
                self.assertEqual(outcome['result'], 'ABSTAINED')
                self.assertIn('preset', outcome['reason'])
                self.assertIn(fragment, outcome['reason'])
                self.assertFalse(self.run_root.exists())

    # -- hijos malformados bloquean la quiescencia aunque el turno termine

    def test_hijos_malformados_bloquean_quiescencia(self):
        client = FakeAskClient()
        plan_path = self.write_plan([self.ask()])

        def al_enviar(session):
            # El turno termina, pero un hijo malformado cuenta como activo.
            session.descendants = [{'running': True}]
            session.complete()

        client.on_send = al_enviar
        outcome = run_plan(plan_path, ask_client=client)
        self.assertEqual(outcome['result'], 'RETAINED')
        self.assertIn('ask-deadline', outcome['cause'])
        session = client.sessions[client.created[0][0]]
        self.assertTrue(any(event['type'] == 'turn/end' for event in session.events),
                        'el turno terminó pero la quiescencia siguió bloqueada')
        self.assertGreaterEqual(len(client.observation_calls), 2)
        self.assertEqual(client.cancels, [client.created[0][0]])
        kinds = [p['kind'] for p in self.payloads(outcome['run_dir'])]
        self.assertNotIn('STEP_COMPLETED', kinds)

    # -- deadline: cancel_session + gracia y RETAINED

    def test_deadline_cancela_y_retina(self):
        client = FakeAskClient()
        plan_path = self.write_plan([self.ask()])
        outcome = run_plan(plan_path, ask_client=client)
        self.assertEqual(outcome['result'], 'RETAINED')
        self.assertEqual(outcome['cause'], 'ask-deadline:a1:cancelada y quiescente')
        self.assertEqual(client.cancels, [client.created[0][0]])
        kinds = [p['kind'] for p in self.payloads(outcome['run_dir'])]
        self.assertNotIn('STEP_COMPLETED', kinds)

        client = FakeAskClient()
        client.cancel_clears = False  # la cancelación no logra quiescencia
        # Prompt distinto: bytes de plan distintos, run dir nuevo (sin
        # reanudación del run anterior).
        plan_path = self.write_plan([self.ask(prompt='otra cosa')],
                                    filename='sin-cierre.json')
        outcome = run_plan(plan_path, ask_client=client)
        self.assertEqual(outcome['result'], 'RETAINED')
        self.assertEqual(outcome['cause'], 'ask-deadline:a1:sin quiescencia confirmada')

    # -- trampa de red: URLError a mitad -> RETAINED con causa

    def test_urlerror_a_mitad_retina(self):
        client = FakeAskClient()
        client.obs_error_after = 1  # la 2ª observación lanza URLError
        plan_path = self.write_plan([self.ask()])
        outcome = run_plan(plan_path, ask_client=client)
        self.assertEqual(outcome['result'], 'RETAINED')
        self.assertIn('ask-observacion-fallo:a1', outcome['cause'])
        self.assertEqual(client.cancels, [client.created[0][0]],
                         'la sesión no se abandona sin cierre confirmado')
        kinds = [p['kind'] for p in self.payloads(outcome['run_dir'])]
        self.assertNotIn('STEP_COMPLETED', kinds)

    # -- [corr-3]: reanudación re-envía el mismo request_id a la misma sesión

    def test_reanudacion_reenvia_mismo_request_id_a_la_misma_sesion(self):
        client = FakeAskClient()
        plan_path = self.write_plan([self.ask()])
        # Primera ejecución: el prompt se encola pero el transcript nunca lo
        # muestra y la observación falla a mitad -> RETAINED.
        client.queue_only_new = True
        first = run_plan(plan_path, ask_client=client)
        self.assertEqual(first['result'], 'RETAINED')
        expected_request = self.expected_request_id(plan_path, 'a1', 1)
        self.assertEqual(len(client.sent), 1)

        # Segunda ejecución: la sesión vive; el transcript sigue sin mostrar
        # el request, así que se re-envía el MISMO request_id a la MISMA sesión.
        client.sessions[client.created[0][0]].queue_only = False
        client.obs_error_after = None
        client.auto_complete_on_send = True
        second = run_plan(plan_path, ask_client=client)
        self.assertEqual(second['result'], 'COMPLETED')
        self.assertEqual(len(client.created), 1, 'nunca sesión nueva')
        self.assertEqual([request for _sid, request in client.sent],
                         [expected_request, expected_request])
        payloads = self.payloads(second['run_dir'])
        started = [p for p in payloads if p['kind'] == 'STEP_STARTED'
                   and p['payload']['step_id'] == 'a1']
        self.assertEqual(len(started), 1, 'la reanudación no abre un intento nuevo')
        completed = [p for p in payloads if p['kind'] == 'STEP_COMPLETED'
                     and p['payload']['step_id'] == 'a1']
        self.assertEqual(completed[0]['payload']['attempt'], 1)
        self.assertEqual(verify(second['run_dir'])['events'], len(payloads))

    # -- [corr-3]: turno ya terminado -> re-observación sin re-envío

    def test_reanudacion_reobserva_transcript_sin_reenvio(self):
        client = FakeAskClient()
        plan_path = self.write_plan([self.ask()])
        client.obs_error_after = 1  # la 2ª observación falla a mitad del poll
        first = run_plan(plan_path, ask_client=client)
        self.assertEqual(first['result'], 'RETAINED')
        self.assertEqual(len(client.sent), 1)

        # La sesión ya terminó en el transcript: la re-observación basta.
        session = client.sessions[client.created[0][0]]
        session.complete()
        client.obs_error_after = None
        second = run_plan(plan_path, ask_client=client)
        self.assertEqual(second['result'], 'COMPLETED')
        self.assertEqual(len(client.sent), 1, 'no se re-envía un turno terminado')
        self.assertEqual(len(client.created), 1)
        completed = [p for p in self.payloads(second['run_dir'])
                     if p['kind'] == 'STEP_COMPLETED' and p['payload']['step_id'] == 'a1']
        self.assertEqual(completed[0]['payload']['attempt'], 1)

    # -- [corr-3]: sesión perdida -> RETAINED, nunca re-despacho a sesión nueva

    def test_sesion_perdida_retina_sin_sesion_nueva(self):
        client = FakeAskClient()
        plan_path = self.write_plan([self.ask()])
        client.obs_error_after = 1
        first = run_plan(plan_path, ask_client=client)
        self.assertEqual(first['result'], 'RETAINED')

        client.obs_error = ValueError(
            'DSH session %s no aparece en session/list' % client.created[0][0])
        second = run_plan(plan_path, ask_client=client)
        self.assertEqual(second['result'], 'RETAINED')
        self.assertIn('ask-sesion-perdida:a1', second['cause'])
        self.assertEqual(len(client.created), 1, 'nunca re-despacho a sesión nueva')
        self.assertEqual(len(client.sent), 1, 'nunca re-despacho a sesión nueva')

        # Estado de despacho ilegible/ausente: fail-closed sin sesión nueva.
        client.obs_error = None
        observations = Path(first['run_dir']) / 'observations'
        for entry in observations.iterdir():
            if entry.name.endswith('-a1-ask.json'):
                body = json.loads(entry.read_bytes())
                if body.get('status') == 'dispatched':
                    entry.unlink()
        third = run_plan(plan_path, ask_client=client)
        self.assertEqual(third['result'], 'RETAINED')
        self.assertIn('ask-sesion-desconocida', third['cause'])
        self.assertEqual(len(client.created), 1)

    def test_preset_por_ask_y_fallback_del_plan(self):
        client = FakeAskClient(roster=[{'id': 'cordis', 'broken': False},
                                       {'id': 'especial', 'broken': False}])
        client.auto_complete_on_send = True
        path = self.write_plan([self.ask('a1', preset='especial'), self.ask('a2')])
        outcome = run_plan(path, ask_client=client)
        self.assertEqual(outcome['result'], 'COMPLETED')
        self.assertEqual([created[2] for created in client.created], ['especial', 'cordis'])
        self.assertEqual(verify(outcome['run_dir'])['events'], len(self.payloads(outcome['run_dir'])))

    def test_preset_por_ask_ausente_abstiene_antes_del_run_dir(self):
        client = FakeAskClient()
        path = self.write_plan([self.ask('a1'), self.ask('a2', preset='ausente')])
        outcome = run_plan(path, ask_client=client)
        self.assertEqual(outcome['result'], 'ABSTAINED')
        self.assertIn('ausente', outcome['reason'])
        self.assertFalse(self.run_root.exists())
        self.assertFalse(client.created)

    def test_if_veredicto_coincide_despacha(self):
        client = FakeAskClient()
        client.auto_complete_on_send = True
        client.on_complete = lambda session: _write_result(
            session.workspace, 'fuente/veredicto.json', {'decision': {'valor': 'GO'}})
        path = self.write_plan([
            self.ask('fuente', result_contract={'path': 'veredicto.json',
                                                 'evidence_name': 'fuente'}),
            self.ask('destino', if_veredicto={'from': 'fuente', 'path': 'veredicto.json',
                                              'field': 'decision.valor', 'equals': 'GO'}),
        ])
        outcome = run_plan(path, ask_client=client)
        self.assertEqual(outcome['result'], 'COMPLETED')
        self.assertEqual(len(client.created), 2)
        self.assertFalse(any(item['kind'] == 'ASK_SKIPPED' for item in
                             self.payloads(outcome['run_dir'])))

    def test_if_veredicto_no_coincide_skipped_verify_reanudacion(self):
        client = FakeAskClient()
        client.auto_complete_on_send = True
        client.on_complete = lambda session: _write_result(
            session.workspace, 'fuente/veredicto.json', {'decision': {'valor': 'STOP'}})
        path = self.write_plan([
            self.ask('fuente', result_contract={'path': 'veredicto.json',
                                                 'evidence_name': 'fuente'}),
            self.ask('destino', if_veredicto={'from': 'fuente', 'path': 'veredicto.json',
                                              'field': 'decision.valor', 'equals': 'GO'}),
        ])
        first = run_plan(path, ask_client=client)
        self.assertEqual(first['result'], 'COMPLETED')
        events = self.payloads(first['run_dir'])
        skipped = [item['payload'] for item in events if item['kind'] == 'ASK_SKIPPED']
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]['step_id'], 'destino')
        self.assertEqual(skipped[0]['from'], 'fuente')
        self.assertEqual(skipped[0]['esperado'], 'GO')
        self.assertEqual(skipped[0]['real'], 'STOP')
        self.assertIn('source_digest', skipped[0])
        self.assertNotIn('destino', [item['payload']['step_id'] for item in events
                                     if item['kind'] == 'STEP_COMPLETED'])
        self.assertEqual(verify(first['run_dir'])['events'], len(events))
        second = run_plan(path, ask_client=client)
        self.assertEqual(second['result'], 'COMPLETED')
        self.assertEqual(len(client.created), 1)
        self.assertEqual(sum(item['kind'] == 'ASK_SKIPPED' for item in
                             self.payloads(second['run_dir'])), 1)
        self.assertEqual(verify(second['run_dir'])['events'], len(self.payloads(second['run_dir'])))

        with self.subTest(case='ask_skipped_no_es_terminal_si_gate_se_repite_con_nuevo_digest'):
            evidence = self.workspace / 'evidence'
            evidence.mkdir(parents=True, exist_ok=True)
            s = self.workspace / 'gate_first.py'
            s.write_text(
                'import json, pathlib, sys\n'
                'pathlib.Path("evidence/veredicto.json").write_text(json.dumps({"verdict": "PASS"}))\n'
                'sys.exit(0)\n',
                encoding='utf-8')
            repeat_client = FakeAskClient()
            repeat_client.auto_complete_on_send = True
            plan = self.write_plan([
                {'id': 'g1', 'type': 'gate', 'command': [PYTHON, str(s)],
                 'on_fail': {'action': 'continue', 'rounds': 1}},
                self.ask('a1', if_veredicto={'from': 'g1', 'path': 'veredicto.json',
                                             'field': 'verdict', 'equals': 'FAIL'}),
            ], filename='gate-repeat.json')

            res1 = run_plan(plan, ask_client=repeat_client)
            self.assertEqual(res1['result'], 'COMPLETED')
            self.assertEqual(repeat_client.created, [])
            events1 = self.payloads(res1['run_dir'])
            skipped1 = [e['payload'] for e in events1 if e['kind'] == 'ASK_SKIPPED']
            self.assertEqual(len(skipped1), 1)
            self.assertEqual(skipped1[0]['step_id'], 'a1')
            self.assertIn('source_digest', skipped1[0])

            # Ahora simulamos que un segundo intento de g1 falla (FAIL con continue)
            # dejando un digest diferente. El ASK_SKIPPED previo no debe ser terminal.
            run_dir = Path(res1['run_dir'])
            raw_events = self.payloads(res1['run_dir'])
            writer = workflow._JournalWriter(run_dir, workflow.MAX_STORE, len(raw_events),
                                             raw_events[-1]['content_sha256'], len(raw_events))
            writer.append('STEP_STARTED', {'step_id': 'g1', 'step_type': 'gate', 'attempt': 2})
            obs2_path = run_dir / 'observations' / '03-g1-gate.json'
            obs2_data = json.dumps({
                'status': 'failed',
                'exit_code': 1,
                'result': {'verdict': 'FAIL'},
                'result_path': 'evidence/veredicto.json',
                'result_sha256': '1' * 64,
            }).encode('utf-8')
            obs2_path.write_bytes(obs2_data)
            obs2_sha = hashlib.sha256(obs2_data).hexdigest()
            writer.append('GATE_REJECTED', {'step_id': 'g1', 'attempt': 2,
                                            'observation': 'observations/03-g1-gate.json',
                                            'output_sha256': obs2_sha,
                                            'exit_code': 1})
            writer.append('STEP_FAILED', {'step_id': 'g1', 'attempt': 2,
                                          'observation': 'observations/03-g1-gate.json',
                                          'exit_code': 1,
                                          'action': 'continue'})
            res2 = run_plan(plan, ask_client=repeat_client)
            self.assertEqual(res2['result'], 'COMPLETED')
            self.assertEqual(len(repeat_client.created), 1)
            events2 = self.payloads(res1['run_dir'])
            self.assertIn('STEP_COMPLETED', [e['kind'] for e in events2
                                             if e['payload'].get('step_id') == 'a1'])
            self.assertEqual(verify(res1['run_dir'])['events'], len(events2))

        with self.subTest(case='if_veredicto_campo_no_string_null_o_false_verify_acepta'):
            for valor, esperado_real in [(None, 'null'), (False, 'false')]:
                c = FakeAskClient()
                c.auto_complete_on_send = True
                c.on_complete = lambda session, v=valor: _write_result(
                    session.workspace, 'veredicto.json', {'campo': v})
                f_id = 'f_' + esperado_real
                d_id = 'd_' + esperado_real
                p = self.write_plan([
                    self.ask(f_id, result_contract={'path': 'veredicto.json'}),
                    self.ask(d_id, if_veredicto={'from': f_id, 'path': 'veredicto.json',
                                                'field': 'campo', 'equals': 'GO'}),
                ], filename='non-string-%s.json' % esperado_real)
                out = run_plan(p, ask_client=c)
                self.assertEqual(out['result'], 'COMPLETED')
                sk = [x['payload'] for x in self.payloads(out['run_dir']) if x['kind'] == 'ASK_SKIPPED']
                self.assertEqual(len(sk), 1)
                self.assertEqual(sk[0]['real'], esperado_real)
                self.assertEqual(verify(out['run_dir'])['events'], len(self.payloads(out['run_dir'])))

    def test_join_depende_de_ask_skipped_retiene(self):
        client = FakeAskClient()
        client.auto_complete_on_send = True
        client.on_complete = lambda session: _write_result(
            session.workspace, 'veredicto.json', {'estado': 'NO'})
        path = self.write_plan([
            self.ask('fuente', result_contract={'path': 'veredicto.json'}),
            self.ask('destino', if_veredicto={'from': 'fuente', 'path': 'veredicto.json',
                                              'field': 'estado', 'equals': 'SI'}),
            {'id': 'j', 'type': 'join', 'depends': ['destino']},
        ])
        outcome = run_plan(path, ask_client=client)
        self.assertEqual(outcome['result'], 'RETAINED')
        self.assertEqual(outcome['cause'], 'join-dep-not-completed:j:destino')
        self.assertEqual(len(client.created), 1)
        self.assertEqual(verify(outcome['run_dir'])['events'], len(self.payloads(outcome['run_dir'])))

    def test_if_veredicto_invalido_rechazado_sin_run_dir(self):
        valid = {'from': 'fuente', 'path': 'veredicto.json', 'field': 'estado', 'equals': 'SI'}
        cases = [
            ([self.ask('destino', if_veredicto={**valid, 'from': 'fuente'}),
              self.ask('fuente')], 'no previo'),
            ([self.ask('fuente'), self.ask('destino', if_veredicto={**valid, 'path': '../x'})],
             'path inválido'),
            ([self.ask('fuente'), self.ask('destino', if_veredicto={**valid, 'path': 'a/b'})],
             'path inválido'),
            ([self.ask('fuente'), self.ask('destino', if_veredicto={**valid, 'field': 'a..b'})],
             'field inválido'),
            ([self.ask('fuente'), self.ask('destino', if_veredicto={**valid, 'equals': 4})],
             'equals'),
            ([self.ask('fuente'), self.ask('destino', if_veredicto={'from': 'fuente'})],
             'requiere from'),
        ]
        for index, (steps, fragment) in enumerate(cases):
            with self.subTest(case=index):
                path = self.write_plan(steps, filename='if-invalido-%d.json' % index)
                with self.assertRaisesRegex(WorkflowError, fragment):
                    run_plan(path, ask_client=FakeAskClient())
                self.assertFalse(self.run_root.exists())

    def test_evidence_name_invalida_rechazada_sin_run_dir(self):
        for index, name in enumerate(('..', '../fuera', '/tmp/fuera', 'sub/ruta', 'sub\\ruta')):
            with self.subTest(name=name):
                path = self.write_plan([self.ask(result_contract={
                    'path': 'veredicto.json', 'evidence_name': name})],
                    filename='evidence-invalida-%d.json' % index)
                with self.assertRaisesRegex(WorkflowError, 'evidence_name inválido'):
                    run_plan(path, ask_client=FakeAskClient())
                self.assertFalse(self.run_root.exists())

    def test_resultado_evidence_symlink_retiene_con_causa(self):
        outside = self.tmp / 'fuera'
        outside.mkdir()
        (outside / 'resultado.json').write_text('{"estado":"SI"}\n', encoding='utf-8')
        (self.workspace / 'evidence').symlink_to(outside, target_is_directory=True)
        client = FakeAskClient()
        client.auto_complete_on_send = True
        path = self.write_plan([self.ask(result_contract={'path': 'resultado.json'})])
        outcome = run_plan(path, ask_client=client)
        self.assertEqual(outcome['result'], 'RETAINED')
        self.assertIn('evidence fuera del workspace', outcome['cause'])
        self.assertEqual(verify(outcome['run_dir'])['events'], len(self.payloads(outcome['run_dir'])))

    def test_if_veredicto_desde_gate_lee_la_raiz_de_evidencia(self):
        (self.workspace / 'evidence').mkdir()
        for index, verdict in enumerate(('FAIL', 'PASS')):
            with self.subTest(verdict=verdict):
                (self.workspace / 'evidence' / 'veredicto.json').write_text(
                    json.dumps({'verdict': verdict}) + '\n', encoding='utf-8')
                client = FakeAskClient()
                client.auto_complete_on_send = True
                # El prompt cambia por caso porque el run_id se deriva de los
                # bytes del plan: dos planes idénticos serían el mismo run.
                path = self.write_plan([
                    {'id': 'verificar', 'type': 'gate', 'command': ['true'],
                     'on_fail': {'action': 'continue', 'rounds': 1}},
                    self.ask('destino', prompt='destino ' + verdict,
                             if_veredicto={'from': 'verificar', 'path': 'veredicto.json',
                                           'field': 'verdict', 'equals': 'FAIL'})],
                    filename='gate-veredicto-%d.json' % index)
                outcome = run_plan(path, ask_client=client)
                self.assertEqual(outcome['result'], 'COMPLETED')
                events = self.payloads(outcome['run_dir'])
                skipped = [item['payload'] for item in events if item['kind'] == 'ASK_SKIPPED']
                if verdict == 'FAIL':
                    self.assertEqual(skipped, [])
                    self.assertEqual(len(client.created), 1)
                else:
                    self.assertEqual(len(skipped), 1)
                    self.assertEqual(skipped[0]['step_id'], 'destino')
                    self.assertEqual(skipped[0]['from'], 'verificar')
                    self.assertEqual(skipped[0]['esperado'], 'FAIL')
                    self.assertEqual(skipped[0]['real'], 'PASS')
                    self.assertIn('source_digest', skipped[0])
                    self.assertEqual(client.created, [])
                self.assertEqual(verify(outcome['run_dir'])['events'], len(events))

    def test_if_veredicto_de_gate_fail_continue_abre_reparacion_y_reanuda(self):
        (self.workspace / 'evidence').mkdir()
        (self.workspace / 'evidence' / 'veredicto.json').write_text(
            '{"verdict":"FAIL"}\n', encoding='utf-8')
        client = FakeAskClient()
        client.auto_complete_on_send = True
        plan = self.write_plan([
            {'id': 'verify', 'type': 'gate', 'command': ['false'],
             'on_fail': {'action': 'continue', 'rounds': 1}},
            self.ask('repair', if_veredicto={'from': 'verify', 'path': 'veredicto.json',
                                            'field': 'verdict', 'equals': 'FAIL'})],
            filename='gate-fail-repair.json')
        first = run_plan(plan, ask_client=client)
        self.assertEqual(first['result'], 'COMPLETED')
        self.assertEqual(len(client.created), 1)
        events = self.payloads(first['run_dir'])
        self.assertIn('STEP_FAILED', [entry['kind'] for entry in events])
        self.assertFalse(any(entry['kind'] == 'STEP_COMPLETED' and
                             entry['payload']['step_id'] == 'verify' for entry in events))
        self.assertEqual(run_plan(plan, ask_client=client)['result'], 'COMPLETED')
        self.assertEqual(len(client.created), 1)
        self.assertEqual(verify(first['run_dir'])['events'], len(self.payloads(first['run_dir'])))

        with self.subTest(case='posterior_gate_pass_no_reescribe_decision_de_gate_anterior'):
            evidence = self.workspace / 'evidence'
            evidence.mkdir(parents=True, exist_ok=True)
            s1 = self.workspace / 'gate1.py'
            s1.write_text('import json, pathlib, sys\n'
                          'pathlib.Path("evidence/veredicto.json").write_text(json.dumps({"verdict": "FAIL"}))\n'
                          'sys.exit(1)\n', encoding='utf-8')
            s2 = self.workspace / 'gate2.py'
            s2.write_text('import json, pathlib, sys\n'
                          'pathlib.Path("evidence/veredicto.json").write_text(json.dumps({"verdict": "PASS"}))\n'
                          'sys.exit(0)\n', encoding='utf-8')
            overwrite_client = FakeAskClient()
            overwrite_client.auto_complete_on_send = True
            overwrite_plan = self.write_plan([
                {'id': 'verificar-pre', 'type': 'gate', 'command': [PYTHON, str(s1)],
                 'on_fail': {'action': 'continue', 'rounds': 1}},
                self.ask('reparar-1', if_veredicto={'from': 'verificar-pre', 'path': 'veredicto.json',
                                                    'field': 'verdict', 'equals': 'FAIL'}),
                {'id': 'verificar-post', 'type': 'gate', 'command': [PYTHON, str(s2)],
                 'on_fail': {'action': 'continue', 'rounds': 1}},
                self.ask('reparar-2', if_veredicto={'from': 'verificar-pre', 'path': 'veredicto.json',
                                                    'field': 'verdict', 'equals': 'FAIL'}),
                self.ask('reparar-3', if_veredicto={'from': 'verificar-post', 'path': 'veredicto.json',
                                                    'field': 'verdict', 'equals': 'FAIL'}),
            ], filename='gate-overwrite-prevention.json')
            outcome = run_plan(overwrite_plan, ask_client=overwrite_client)
            self.assertEqual(outcome['result'], 'COMPLETED')
            self.assertEqual(len(overwrite_client.created), 2)
            events = self.payloads(outcome['run_dir'])
            skipped = [e['payload'] for e in events if e['kind'] == 'ASK_SKIPPED']
            self.assertEqual(len(skipped), 1)
            self.assertEqual(skipped[0]['step_id'], 'reparar-3')
            self.assertEqual(skipped[0]['from'], 'verificar-post')
            self.assertEqual(skipped[0]['real'], 'PASS')
            self.assertEqual(skipped[0]['esperado'], 'FAIL')
            resumed = run_plan(overwrite_plan, ask_client=overwrite_client)
            self.assertEqual(resumed['result'], 'COMPLETED')
            self.assertEqual(len(overwrite_client.created), 2)
            self.assertEqual(verify(outcome['run_dir'])['events'], len(self.payloads(outcome['run_dir'])))

    def test_resultado_ausente_retiene_sin_pass(self):
        client = FakeAskClient()
        client.auto_complete_on_send = True
        (self.workspace / 'evidence').mkdir()
        path = self.write_plan([self.ask(result_contract={'path': 'faltante.json'})])
        outcome = run_plan(path, ask_client=client)
        self.assertEqual(outcome['result'], 'RETAINED')
        self.assertIn('faltante.json', outcome['cause'])
        self.assertFalse(any(item['kind'] == 'STEP_COMPLETED' for item in
                             self.payloads(outcome['run_dir'])))
        self.assertEqual(verify(outcome['run_dir'])['events'], len(self.payloads(outcome['run_dir'])))

    # -- persistencia reclamada fail-closed (issue #37, síntoma b)

    def _write_handoff(self, handoff_id, finding_ids,
                       prompt='Repara los hallazgos de la auditoría; no publiques.',
                       base='b' * 40):
        """handoffs.jsonl en el mode-state, como el turno lo habría aterrizado."""
        state = self.workspace / 'mode-state'
        state.mkdir(parents=True, exist_ok=True)
        record = {'handoff_id': handoff_id, 'base_revision': base,
                  'finding_ids': finding_ids, 'next_prompt': prompt}
        path = state / 'handoffs.jsonl'
        existing = path.read_text() if path.exists() else ''
        path.write_text(existing + json.dumps(record, ensure_ascii=False) + '\n')

    def _audit_plan_and_result(self, result, filename='auditar.json',
                               prompt='audita el producto'):
        client = FakeAskClient()
        client.complete_after = 1
        plan_path = self.write_plan(
            [self.ask('auditar', prompt=prompt,
                      result_contract={'evidence_name': 'campana',
                                       'path': 'auditoria.json'})],
            filename=filename)
        client.on_complete = lambda session: _write_result(
            session.workspace, 'campana/auditoria.json', result)
        return client, plan_path

    def test_handoff_reclamado_sin_aterrizar_retiene(self):
        """La observación del run r-e03534cc mentía y el journal la grabó igual.

        El resultado del audit reclamó handoff_id audit-complete-b40829ad-7 y
        persisted_count 1 que nunca aterrizó en handoffs.jsonl: ningún fichero
        del mode-state tiene mtime dentro de la ventana del run — el turno no
        emitió ninguna escritura gestionada y aun así reportó persistencia.
        No hubo dedup (workflow_write escribe o lanza en voz alta) ni error
        tragado; el autoreporte se journalizó sin cruzarlo contra el disco.
        Fail-closed: sin aterrizaje el turno no reporta persistencia —
        retención citable y sin STEP_COMPLETED que lo haga verdad.
        """
        client, plan_path = self._audit_plan_and_result({
            'handoff_id': 'audit-complete-b40829ad-7', 'persisted_count': 1,
            'next_prompt': 'Repara los hallazgos de la auditoría; no publiques.',
            'audit_scope': 'complete'})
        outcome = run_plan(plan_path, ask_client=client)
        self.assertEqual(outcome['result'], 'RETAINED')
        self.assertIn('ask-persistencia-sin-aterrizaje', outcome['cause'])
        self.assertIn('audit-complete-b40829ad-7', outcome['cause'])
        payloads = self.payloads(outcome['run_dir'])
        self.assertFalse([p for p in payloads if p['kind'] == 'STEP_COMPLETED'
                          and p['payload'].get('step_id') == 'auditar'],
                         'la observación que miente no se journaliza como paso completado')
        self.assertEqual(verify(outcome['run_dir'])['events'], len(payloads))

    def test_persisted_count_y_prompt_reclamados_deben_coincidir_con_el_disco(self):
        """Un número o un prompt que el disco no dice es la misma mentira."""
        cases = [
            # El handoff aterrizó pero cubre dos hallazgos: persist 1 miente.
            (lambda index: self._write_handoff('audit-caso-%d' % index,
                                               ['A-05', 'A-06']),
             {'persisted_count': 1}, 'no coincide'),
            # El handoff aterrizó con otro next_prompt que el reclamado.
            (lambda index: self._write_handoff(
                 'audit-caso-%d' % index, ['A-05'],
                 prompt='Repara los hallazgos; ya está.'),
             {'persisted_count': 1,
              'next_prompt': 'Repara los hallazgos de la auditoría; no publiques.'},
             'next_prompt'),
            # persisted_count ≥ 1 sin handoff_id reclamado ni aterrizado.
            (lambda index: (self.workspace / 'mode-state' / 'handoffs.jsonl').unlink(
                 missing_ok=True),
             {'handoff_id': None, 'persisted_count': 1}, 'sin handoff'),
        ]
        for index, (seed, result_extra, fragment) in enumerate(cases):
            with self.subTest(case=index):
                seed(index)
                client, plan_path = self._audit_plan_and_result(
                    {'handoff_id': 'audit-caso-%d' % index, **result_extra},
                    filename='auditar-%d.json' % index,
                    prompt='audita el producto, caso %d' % index)
                outcome = run_plan(plan_path, ask_client=client)
                self.assertEqual(outcome['result'], 'RETAINED', outcome)
                self.assertIn('ask-persistencia-sin-aterrizaje', outcome['cause'])
                self.assertIn(fragment, outcome['cause'])

    def test_handoff_reclamado_aterrizado_completa(self):
        """El caso sano: lo reclamado está en disco, el paso completa igual."""
        self._write_handoff('audit-complete-b40829ad-7', ['A-05'])
        client, plan_path = self._audit_plan_and_result({
            'handoff_id': 'audit-complete-b40829ad-7', 'persisted_count': 1,
            'next_prompt': 'Repara los hallazgos de la auditoría; no publiques.',
            'audit_scope': 'complete'})
        outcome = run_plan(plan_path, ask_client=client)
        self.assertEqual(outcome['result'], 'COMPLETED', outcome.get('cause'))
        self.assertTrue([p for p in self.payloads(outcome['run_dir'])
                         if p['kind'] == 'STEP_COMPLETED'
                         and p['payload'].get('step_id') == 'auditar'])

    def test_handoff_aterrizado_convive_con_el_historico_derivado(self):
        """El handoff histórico derivado (-6, issue #38) no bloquea al sano.

        El -6 real aterrizó con «no públicas» y el guarda compara el prompt
        reclamado con el aterrizado del registro RECLAMADO, no con el ledger
        entero: una campaña que aterriza su -7 con el prompt del contrato y lo
        reclama tal cual completa, con el derivado conviviendo en el disco.
        """
        self._write_handoff('audit-complete-b40829ad-6', ['A-05'],
                            prompt='Repara los hallazgos de la auditoría; no públicas.')
        self._write_handoff('audit-complete-b40829ad-7', ['A-05'])
        client, plan_path = self._audit_plan_and_result({
            'handoff_id': 'audit-complete-b40829ad-7', 'persisted_count': 1,
            'next_prompt': 'Repara los hallazgos de la auditoría; no publiques.',
            'audit_scope': 'complete'})
        outcome = run_plan(plan_path, ask_client=client)
        self.assertEqual(outcome['result'], 'COMPLETED', outcome.get('cause'))
        self.assertTrue([p for p in self.payloads(outcome['run_dir'])
                         if p['kind'] == 'STEP_COMPLETED'
                         and p['payload'].get('step_id') == 'auditar'])

    # -- techo de lectura: presupuesto forzado fail-closed por intento ask

    def test_techo_de_lectura_retiene_con_causa_citable(self):
        client = FakeAskClient()
        client.complete_after = 1
        plan_path = self.write_plan([self.ask(budget_tokens=10)])
        outcome = run_plan(plan_path, ask_client=client)
        self.assertEqual(outcome['result'], 'RETAINED')
        # El cause lleva paso, total facturado y techo: citable sin cargar el
        # plan (regla R2: el techo solo sube si el reason lo dice).
        self.assertEqual(outcome['cause'],
                         'ask-techo-tokens:a1:460/10:cancelada y quiescente')
        self.assertEqual(client.cancels, [client.created[0][0]],
                         'la sesión excedida no se abandona sin cierre')
        payloads = self.payloads(outcome['run_dir'])
        self.assertEqual(payloads[-1]['kind'], 'RUN_RETAINED')
        self.assertEqual(payloads[-1]['payload']['cause'], outcome['cause'])
        self.assertNotIn('STEP_COMPLETED', [p['kind'] for p in payloads])

        client = FakeAskClient()
        client.cancel_clears = False  # la cancelación no logra quiescencia
        # Uso sobre el techo sin terminal: la sesión sigue viva al retener.
        client.on_send = lambda session: session.add_event(
            'assistant/message', turn=session.turn, message={'text': 'intermedio'},
            usage={'inputTokens': 10, 'outputTokens': 5, 'cacheReadTokens': 0,
                   'totalTokens': 5000})
        plan_path = self.write_plan([self.ask(prompt='otra cosa', budget_tokens=10)],
                                    filename='techo-sin-cierre.json')
        outcome = run_plan(plan_path, ask_client=client)
        self.assertEqual(outcome['result'], 'RETAINED')
        self.assertEqual(outcome['cause'],
                         'ask-techo-tokens:a1:5000/10:sin quiescencia confirmada')

    def test_dentro_del_techo_completa_y_registra_el_uso(self):
        client = FakeAskClient()
        client.complete_after = 1
        plan_path = self.write_plan([self.ask(budget_tokens=1000000)])
        outcome = run_plan(plan_path, ask_client=client)
        self.assertEqual(outcome['result'], 'COMPLETED')
        payloads = self.payloads(outcome['run_dir'])
        self.assertEqual(payloads[-1]['kind'], 'RUN_COMPLETED')
        self.assertNotIn('RUN_RETAINED', [p['kind'] for p in payloads],
                         'el techo no penaliza el caso sano')
        completed = next(p['payload'] for p in payloads if p['kind'] == 'STEP_COMPLETED')
        body = json.loads((Path(outcome['run_dir']) / completed['observation']).read_bytes())
        self.assertEqual(body['usage_tokens'], 460)
        self.assertEqual(verify(outcome['run_dir'])['events'], len(payloads))

    def test_usage_ambiguo_retiene_sin_seguir(self):
        # total < input + output + cacheRead: la cifra persistida se contradice
        # y el registro sin usage deja el coste real desconocido. Ambos
        # retienen con causa citable; jamás se estima ni se continúa mudo.
        for index, usage in enumerate((
                {'inputTokens': 10, 'outputTokens': 5, 'cacheReadTokens': 20,
                 'totalTokens': 5},
                None)):
            with self.subTest(case=index):
                client = FakeAskClient()
                client.complete_after = 1
                client.on_send = lambda session, u=usage: setattr(session, 'usage', u)
                plan_path = self.write_plan(
                    [self.ask(prompt='turno ambiguo %d' % index)],
                    filename='uso-ambiguo-%d.json' % index)
                outcome = run_plan(plan_path, ask_client=client)
                self.assertEqual(outcome['result'], 'RETAINED')
                self.assertIn('ask-uso-ambiguo:a1', outcome['cause'])
                self.assertEqual(client.cancels, [client.created[0][0]])
                self.assertNotIn('STEP_COMPLETED',
                                 [p['kind'] for p in self.payloads(outcome['run_dir'])])

    def test_ask_sin_budget_tokens_rechazado_sin_run_dir(self):
        base = {'id': 'a1', 'type': 'ask', 'prompt': 'p'}
        cases = [
            ({**base}, 'budget_tokens'),      # plan viejo sin techo: no se ejecuta
            ({**base, 'budget_tokens': 0}, 'budget_tokens'),
            ({**base, 'budget_tokens': -5}, 'budget_tokens'),
            ({**base, 'budget_tokens': 'mucho'}, 'budget_tokens'),
            ({**base, 'budget_tokens': True}, 'budget_tokens'),
        ]
        for index, (step, fragment) in enumerate(cases):
            with self.subTest(case=index):
                path = self.write_plan([step], filename='budget-invalido-%d.json' % index)
                with self.assertRaisesRegex(WorkflowError, fragment):
                    run_plan(path, ask_client=FakeAskClient())
                self.assertFalse(self.run_root.exists())
        # Un gate NUNCA recibe techo: la política de inferencia no le da autoridad.
        path = self.write_plan([{'id': 'g1', 'type': 'gate', 'command': ['true'],
                                 'on_fail': {'action': 'abort', 'rounds': 1},
                                 'budget_tokens': 10}], filename='budget-gate.json')
        with self.assertRaisesRegex(WorkflowError, 'solo para ask'):
            run_plan(path)
        self.assertFalse(self.run_root.exists())

    def test_fold_ask_usage_deduplica_por_seq_y_falla_cerrada(self):
        state = workflow._new_ask_state()
        usage = {'inputTokens': 10, 'outputTokens': 5, 'cacheReadTokens': 20,
                 'totalTokens': 35}
        observation = {'running': False, 'events': [
            {'seq': 1, 'type': 'turn/start', 'data': {'turn': 1}},
            {'seq': 2, 'type': 'assistant/message',
             'data': {'turn': 1, 'usage': usage}},
        ]}
        workflow._fold_ask_usage(observation, state)
        workflow._fold_ask_usage(observation, state)  # página re-enviada
        self.assertEqual(state['usage_tokens'], 35)
        # Mismo seq con otra cifra: cuenta ambigua, no reconciliación silenciosa.
        replay = {'running': False, 'events': [
            {'seq': 2, 'type': 'assistant/message',
             'data': {'turn': 1, 'usage': {**usage, 'totalTokens': 99}}}],
        }
        with self.assertRaises(workflow.CreatorUsageAmbiguous):
            workflow._fold_ask_usage(replay, state)
        # usage sin seq durable: no se puede desduplicar una re-observación.
        with self.assertRaises(workflow.CreatorUsageAmbiguous):
            workflow._fold_ask_usage({'running': False, 'events': [
                {'type': 'assistant/message', 'data': {'usage': usage}}]},
                workflow._new_ask_state())


def _write_result(workspace, relative, value):
    """Escribe el resultado estructurado en <workspace>/evidence ([corr-4])."""
    path = Path(workspace) / 'evidence' / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
