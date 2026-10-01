"""Pruebas del almacén de métricas append-only (fixtures /tmp, sin red ni modelos)."""
import json
import sys
import tempfile
import unittest

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from metrics import NO_DISPONIBLE, record_event, summarize, verify


class MetricsStoreTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / 'mision-estado'
        self.root.mkdir(mode=0o700)

    def test_registro_y_agregacion_con_dos_fuentes(self):
        record_event(self.root, 'turn', source='session-uno', unit='turno',
                     requests=13, tokens_input=100_000, tool_calls=28)
        record_event(self.root, 'turn', source='session-dos', unit='turno',
                     requests=61, tokens_input=50_000, tokens_cache_read=200_000, tool_calls=57)
        resumen = summarize(self.root)
        self.assertEqual(resumen['requests'],
                         {'total': 74, 'count': 2, 'sources': ['session-dos', 'session-uno']})
        self.assertEqual(resumen['tokens_input'],
                         {'total': 150_000, 'count': 2, 'sources': ['session-dos', 'session-uno']})
        self.assertEqual(resumen['tokens_cache_read'],
                         {'total': 200_000, 'count': 1, 'sources': ['session-dos']})
        self.assertEqual(resumen['tool_calls']['total'], 85)
        self.assertEqual(verify(self.root)['events'], 2)

    def test_clave_nunca_registrada_es_no_disponible(self):
        record_event(self.root, 'turn', source='logs-sesion-DSH', requests=20)
        resumen = summarize(self.root)
        self.assertIs(resumen['tokens_output'], NO_DISPONIBLE)
        self.assertIsNot(resumen['tokens_output'], 0)
        self.assertEqual(resumen['requests']['total'], 20)

    def test_evento_alterado_falla_cerrado(self):
        record_event(self.root, 'turn', source='session-uno', requests=13)
        events = self.root / 'events.jsonl'
        lines = events.read_bytes().splitlines(keepends=True)
        self.assertEqual(len(lines), 1)
        envelope = json.loads(lines[0])
        envelope['payload']['values']['requests'] = 1
        lines[0] = json.dumps(envelope, ensure_ascii=False, sort_keys=True,
                              separators=(',', ':')).encode() + b'\n'
        events.write_bytes(b''.join(lines))
        with self.assertRaises(ValueError):
            verify(self.root)
        with self.assertRaises(ValueError):
            summarize(self.root)

    def test_entrada_invalida_falla_sin_escribir(self):
        with self.assertRaises(ValueError):
            record_event(self.root, 'turn', source='', requests=1)
        with self.assertRaises(ValueError):
            record_event(self.root, 'turn', source='   ', requests=1)
        with self.assertRaises(ValueError):
            record_event(self.root, 'turn', source='session-uno', tokens_desconocidos=1)
        with self.assertRaises(ValueError):
            record_event(self.root, 'ritual', source='session-uno')
        with self.assertRaises(ValueError):
            record_event(self.root, 'turn', source='session-uno', requests=-1)
        with self.assertRaises(ValueError):
            record_event(self.root, 'turn', source='session-uno', requests=True)
        self.assertFalse((self.root / 'events.jsonl').exists())
        self.assertFalse((self.root / 'head.json').exists())
        record_event(self.root, 'turn', source='session-uno', requests=7)
        before = (self.root / 'events.jsonl').read_bytes()
        with self.assertRaises(ValueError):
            record_event(self.root, 'turn', source='session-uno', tokens_desconocidos=1)
        self.assertEqual((self.root / 'events.jsonl').read_bytes(), before)
        self.assertEqual(verify(self.root)['events'], 1)

    def test_summarize_filtra_por_kind(self):
        record_event(self.root, 'turn', source='session-uno', requests=13)
        record_event(self.root, 'audit', source='session-dos', requests=5, tool_calls=3)
        auditoria = summarize(self.root, kinds=['audit'])
        self.assertEqual(auditoria['requests'],
                         {'total': 5, 'count': 1, 'sources': ['session-dos']})
        self.assertIs(auditoria['tokens_input'], NO_DISPONIBLE)
        turnos = summarize(self.root, kinds=['turn', 'audit'])
        self.assertEqual(turnos['requests']['total'], 18)
        self.assertEqual(summarize(self.root)['requests']['total'], 18)
        with self.assertRaises(ValueError):
            summarize(self.root, kinds=['ritual'])
        with self.assertRaises(ValueError):
            summarize(self.root, kinds=[])

    def test_reapertura_con_digest_global_distinto_falla_cerrado(self):
        record_event(self.root, 'turn', source='session-uno', requests=13)
        record_event(self.root, 'turn', source='session-dos', requests=61)
        events = self.root / 'events.jsonl'
        lines = events.read_bytes().splitlines(keepends=True)
        events.write_bytes(b''.join(lines[:1]))  # Truncado del último evento persistido.
        with self.assertRaises(ValueError):
            verify(self.root)
        events.write_bytes(b''.join(lines))  # Restaurado; ahora head alterado.
        head = self.root / 'head.json'
        checkpoint = json.loads(head.read_text())
        checkpoint['head_sha256'] = 'f' * 64
        head.write_text(json.dumps(checkpoint, ensure_ascii=False, sort_keys=True) + '\n')
        with self.assertRaises(ValueError):
            verify(self.root)


    def test_la_operacion_que_lee_el_ledger_existe_y_esta_cableada(self):
        """El controlador escribe un evento por turno y nadie lo leía.

        `metrics.summarize` y `metrics.verify` tenían seis regresiones que
        probaban que el almacén funciona y ninguna que probara que alguien lo
        consulta: una misión acumulaba coste y no había forma de preguntarle
        cuánto. `docs/status.md` listaba «métricas append-only» entre los
        servicios del framework, que era cierto del escritura y falso del
        servicio.

        Así que el comando tiene que existir, agregar lo registrado, declarar
        NO_DISPONIBLE lo que nunca se registró —nunca cero, que afirmaría que la
        misión costó nada— y fallar cerrado sobre un ledger manipulado antes de
        devolver cualquier total.
        """
        import os
        import shutil
        import subprocess

        mission = self.root
        store = mission / 'metrics'
        store.mkdir(mode=0o700)
        record_event(store, 'turn', source='session-uno', unit='U-1', requests=3)
        record_event(store, 'turn', source='session-uno', unit='U-2', requests=4)

        def run(*extra):
            # shutil.which('python3') and not sys.executable: in this host
            # sys.executable is the ZCode AppImage, which starts a GUI.
            return subprocess.run(
                [shutil.which('python3'), '-B',
                 str(Path(__file__).resolve().parents[1] / 'scripts' / 'bootstrap.py'),
                 'metrics', '--mission', str(mission), *extra],
                capture_output=True, text=True, timeout=120,
                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})

        finished = run()
        self.assertEqual(finished.returncode, 0, finished.stderr[-2000:])
        report = json.loads(finished.stdout)
        self.assertEqual(report['chain']['events'], 2)
        self.assertEqual(report['summary']['requests']['total'], 7)
        # Never recorded is unavailable, not zero: zero would say the mission
        # ran and cost nothing, which is a different and false claim.
        self.assertEqual(report['summary']['tokens_input'], NO_DISPONIBLE)

        # A mission that closed no unit has no ledger, and that is a
        # measurement rather than an error.
        empty = Path(self.root).parent / 'mision-vacia'
        empty.mkdir()
        finished = subprocess.run(
            [shutil.which('python3'), '-B',
             str(Path(__file__).resolve().parents[1] / 'scripts' / 'bootstrap.py'),
             'metrics', '--mission', str(empty)],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        self.assertEqual(finished.returncode, 0, finished.stderr[-2000:])
        self.assertEqual(json.loads(finished.stdout)['chain']['events'], 0)

        # A tampered ledger produces no total at all.
        head = store / 'head.json'
        checkpoint = json.loads(head.read_text())
        checkpoint['head_sha256'] = 'a' * 64
        head.write_text(json.dumps(checkpoint, ensure_ascii=False, sort_keys=True) + '\n')
        refused = run()
        self.assertNotEqual(refused.returncode, 0)
        self.assertNotIn('summary', refused.stdout)


if __name__ == '__main__':
    unittest.main()
