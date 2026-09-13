"""Memoria de decisiones por misión: fixtures temporales; sin red, sin modelos, sin misión real.

python3 -B -m unittest tests.test_decisions -v
"""
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import decisions


class DecisionStoreTest(unittest.TestCase):
    """Contratos fail-closed del almacén de decisiones sobre directorios temporales."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix='decisions-test-')
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.mission = self.base / 'mission'

    def store(self, identity='host-a'):
        return decisions.create(self.mission, identity)

    def records(self):
        return self.mission / 'decisions'

    def test_01_create_exclusive_and_reopen(self):
        store = self.store()
        self.assertTrue((self.records() / 'identity.json').is_file())
        first = store.record('Elegir opción A', ['opción B'], ['u1'], authorization_ref='auth-1')
        reopened = self.store()
        self.assertEqual(reopened.identity, 'host-a')
        self.assertEqual(reopened.get(first['decision_id'])['motive'], 'Elegir opción A')
        # Identidad distinta: nunca reabre.
        with self.assertRaises(ValueError):
            self.store('host-b')
        with self.assertRaises(ValueError):
            decisions.create(self.mission, '')
        # Identidad alterada (bytes reescritos sin digest válido): falla cerrada.
        identity_path = self.records() / 'identity.json'
        envelope = json.loads(identity_path.read_bytes())
        envelope['payload']['identity'] = 'host-b'
        identity_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        with self.assertRaises(ValueError):
            self.store('host-a')
        # El almacén nunca dentro del árbol canónico (validación previa a cualquier escritura).
        target = decisions.ROOT / '.decision-store-intent-test'
        try:
            with self.assertRaises(ValueError):
                decisions.create(target, 'host-a')
        finally:
            shutil.rmtree(target, ignore_errors=True)

    def test_02_record_digest_and_tamper_fails_closed(self):
        store = self.store()
        record = store.record('Cambiar X por Y', ['mantener X'], ['u1'],
                              contract_ref='contract.json', authorization_ref='auth-1')
        self.assertTrue(record['decision_id'].startswith('D-'))
        self.assertEqual(record['status'], 'VIGENTE')
        self.assertEqual(record['motive'], 'Cambiar X por Y')
        self.assertEqual(record['alternatives'], ['mantener X'])
        self.assertEqual(record['affected_units'], ['u1'])
        self.assertEqual(record['contract_ref'], 'contract.json')
        self.assertEqual(record['authorization_ref'], 'auth-1')
        self.assertNotIn('replacement_ref', record)
        datetime.fromisoformat(record['created_at'])
        path = next(self.records().glob('d-*.json'))
        envelope = json.loads(path.read_bytes())
        content = {key: envelope[key] for key in ('version', 'event_id', 'payload')}
        self.assertEqual(hashlib.sha256(decisions._json_bytes(content)).hexdigest(),
                         envelope['content_sha256'])
        self.assertEqual(envelope['payload']['decision_id'], record['decision_id'])
        self.assertTrue(store.verify())
        # Alterar bytes del registro sin recomputar el digest: verify y lectura fallan cerradas.
        raw = path.read_bytes()
        tampered = raw.replace(record['motive'].encode(), b'bytes-manipulados')
        self.assertNotEqual(tampered, raw)
        path.write_bytes(tampered)
        with self.assertRaises(ValueError):
            store.verify()
        with self.assertRaises(ValueError):
            self.store().get_for_units(['u1'])

    def test_03_supersede_requires_authorization_and_preserves_history(self):
        store = self.store()
        original = store.record('Decisión original', [], ['u1'], authorization_ref='auth-1')
        replacement = store.record('Decisión reemplazo', [], ['u1'], authorization_ref='auth-2')
        original_id = original['decision_id']
        replacement_id = replacement['decision_id']
        # Sin authorization_ref no sustituye y no escribe nada.
        with self.assertRaises(ValueError):
            store.supersede(original_id, replacement_id)
        with self.assertRaises(ValueError):
            store.supersede(original_id, replacement_id, authorization_ref=None)
        self.assertEqual(list(self.records().glob('s-*.json')), [])
        self.assertTrue(store.verify())
        original_path = self.records() / ('d-' + original_id + '.json')
        before = original_path.read_bytes()
        view = store.supersede(original_id, replacement_id, authorization_ref='auth-3')
        self.assertEqual(view['status'], 'SUSTITUIDA')
        self.assertEqual(view['replacement_ref'], replacement_id)
        self.assertEqual(store.get(original_id)['status'], 'SUSTITUIDA')
        self.assertEqual(store.get(original_id)['replacement_ref'], replacement_id)
        still = store.get(replacement_id)
        self.assertEqual(still['status'], 'VIGENTE')
        self.assertNotIn('replacement_ref', still)
        # El historial permanece íntegro: el registro original no se reescribe.
        self.assertEqual(original_path.read_bytes(), before)
        self.assertTrue(store.verify())
        self.assertEqual([d['decision_id'] for d in store.get_for_units(['u1'])], [replacement_id])
        # Doble sustitución y referencias ausentes fallan cerradas.
        with self.assertRaises(ValueError):
            store.supersede(original_id, replacement_id, authorization_ref='auth-3')
        third = store.record('Tercera', [], ['u1'], authorization_ref='auth-4')
        with self.assertRaises(ValueError):
            store.supersede(third['decision_id'], 'D-9999-inexistente', authorization_ref='auth-5')
        with self.assertRaises(ValueError):
            store.supersede('D-9999-inexistente', third['decision_id'], authorization_ref='auth-5')
        self.assertTrue(store.verify())
        with self.assertRaises(KeyError):
            store.get('D-9999-inexistente')

    def test_04_get_for_units_filters_vigentes(self):
        store = self.store()
        r1 = store.record('Solo u1', [], ['u1'], authorization_ref='auth-1')
        r2 = store.record('Solo u2', [], ['u2'], authorization_ref='auth-2')
        r3 = store.record('u1 y u2', [], ['u1', 'u2'], authorization_ref='auth-3')

        def ids(units):
            return sorted(d['decision_id'] for d in store.get_for_units(units))

        self.assertEqual(ids(['u1']), sorted([r1['decision_id'], r3['decision_id']]))
        self.assertEqual(ids(['u2']), sorted([r2['decision_id'], r3['decision_id']]))
        self.assertEqual(ids(['u1', 'u2']),
                         sorted([r1['decision_id'], r2['decision_id'], r3['decision_id']]))
        self.assertEqual(ids(['u3']), [])
        store.supersede(r3['decision_id'], r1['decision_id'], authorization_ref='auth-4')
        self.assertEqual(ids(['u1']), [r1['decision_id']])
        self.assertEqual(ids(['u2']), [r2['decision_id']])
        # Argumentos inválidos fallan cerrados.
        with self.assertRaises(ValueError):
            store.get_for_units('u1')
        with self.assertRaises(ValueError):
            store.get_for_units([])
        with self.assertRaises(ValueError):
            store.get_for_units([42])

    def test_05_invalid_arguments_fail_without_partial_write(self):
        store = self.store()
        cases = [
            lambda: store.record('', [], ['u1'], authorization_ref='auth'),
            lambda: store.record(None, [], ['u1'], authorization_ref='auth'),
            lambda: store.record(['lista'], [], ['u1'], authorization_ref='auth'),
            lambda: store.record('motivo', 'texto', ['u1'], authorization_ref='auth'),
            lambda: store.record('motivo', ['ok', 42], ['u1'], authorization_ref='auth'),
            lambda: store.record('motivo', [], [], authorization_ref='auth'),
            lambda: store.record('motivo', [], 'u1', authorization_ref='auth'),
            lambda: store.record('motivo', [], ['u1'], contract_ref='', authorization_ref='auth'),
            lambda: store.record('motivo', [], ['u1'], contract_ref=None, authorization_ref=None),
            lambda: store.record('motivo', [], ['u1'], contract_ref=None, authorization_ref='  '),
        ]
        for case in cases:
            with self.assertRaises(ValueError):
                case()
        self.assertEqual(list(self.records().glob('d-*.json')), [])
        self.assertEqual(list(self.records().glob('s-*.json')), [])
        self.assertTrue(store.verify())


if __name__ == '__main__':
    unittest.main()
