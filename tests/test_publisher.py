import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from publisher import MAX_RECEIPT, Publisher


class PublisherTest(unittest.TestCase):
    def test_reserved_suffixes_and_batch_id_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Publisher(Path(tmp) / 'receipts')
            for length in (54, 71, 75, 80):
                with self.subTest(length=length), self.assertRaises(ValueError):
                    p.open_batch('o', 'a', 'objective', 'b' * length)
            self.assertEqual(list(p.root.iterdir()), [])
            batch = 'b' * 53
            p.open_batch('o', 'a', 'objective', batch)
            for suffix in ('open', 'close', 'executor', 'qa', 'auditor'):
                with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                    p.publish_batch_record('o', 'a', batch, 'evidence', {}, suffix)
            evidence = p.publish_batch_record('o', 'a', batch, 'evidence', {})['record_id']
            task = p.publish_batch_record('o', 'a', batch, 'task', {'evidence_id': evidence})['record_id']
            closed = p.close_batch('o', 'a', batch, 'COMPLETE', [evidence, task], [])
            self.assertEqual(p.resolve_handoff(p.handoff(closed['record_id'])), closed)
            p.report_stage('o', 'a', batch, 'executor', 'FAILED', 'fixture failure', 'ex')
            self.assertEqual(p.resolve(batch + '-executor')['payload']['status'], 'FAILED')

    def test_overlapping_batch_lifecycle_names(self):
        for order in (('b', 'b-x'), ('b-x', 'b')):
            with self.subTest(order=order), tempfile.TemporaryDirectory() as tmp:
                p = Publisher(tmp)
                p.open_batch('o', 'a', 'objective', order[0])
                for suffix in ('open', 'close', 'executor', 'qa', 'auditor'):
                    with self.assertRaises(ValueError):
                        p.publish_batch_record('o', 'a', order[0], 'evidence', {}, 'x-' + suffix)
                p.open_batch('o', 'a', 'objective', order[1])
                for suffix in ('open', 'close', 'executor', 'qa', 'auditor'):
                    with self.assertRaises(ValueError):
                        p.publish_batch_record('o', 'a', 'b', 'evidence', {}, 'x-' + suffix)
                for batch in order:
                    e = p.publish_batch_record('o', 'a', batch, 'evidence', {}, 'e')['record_id']
                    p.close_batch('o', 'a', batch, 'PARTIAL', [e], ['pending'])

    def test_closing_capacity_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Publisher(tmp)
            p.open_batch('o', 'a', 'objective', 'b')
            ids = [p.publish_batch_record('o', 'a', 'b', 'evidence', {}, 'e' + str(i))['record_id']
                   for i in range(11)]
            p = Publisher(tmp)  # Reservations survive a fresh instance.
            before = {path.name: path.read_bytes() for path in p.root.iterdir()}
            for operation in (
                lambda: p.publish_batch_record('o', 'a', 'b', 'evidence', {}, 'overflow'),
                lambda: p.publish('o', 'a', {}, 'generic'),
                lambda: p.open_batch('o', 'a', 'objective', 'other'),
            ):
                with self.assertRaises(ValueError):
                    operation()
                self.assertEqual({path.name: path.read_bytes() for path in p.root.iterdir()}, before)
            p.publish_batch_record('o', 'a', 'b', 'evidence', {}, 'e0')
            closed = p.close_batch('o', 'a', 'b', 'PARTIAL', ids, ['unfinished'])
            self.assertEqual(p.close_batch('o', 'a', 'b', 'PARTIAL', ids, ['unfinished']), closed)
            for i in range(3):
                p.publish('o', 'a', {}, 'released-' + str(i))
            self.assertEqual(len(list(p.root.glob('*.json'))), 16)
            with self.assertRaises(ValueError):
                p.publish('o', 'a', {}, 'overflow')
        with tempfile.TemporaryDirectory() as tmp:
            p = Publisher(tmp)
            for i in range(12):
                p.publish('o', 'a', {}, 'generic-' + str(i))
            with self.assertRaises(ValueError):
                p.open_batch('o', 'a', 'objective', 'b')
            self.assertFalse((p.root / 'b-open.json').exists())

        with tempfile.TemporaryDirectory() as tmp:
            p = Publisher(tmp)
            for batch in ('b', 'b-x', 'b-x-y'):
                p.open_batch('o', 'a', 'objective', batch)
            with self.assertRaises(ValueError):
                p.open_batch('o', 'a', 'objective', 'fourth')
            p.publish('o', 'a', {}, 'last-free')
            with self.assertRaises(ValueError):
                p.publish('o', 'a', {}, 'overflow')
            for batch in ('b', 'b-x', 'b-x-y'):
                p.close_batch('o', 'a', batch, 'PARTIAL', [], ['pending'])

    def test_nested_invalid_ids(self):
        for invalid in ([], {}, ['b-e'], 1, None):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as tmp:
                p = Publisher(tmp)
                p.open_batch('o', 'a', 'objective', 'b')
                e = p.publish_batch_record('o', 'a', 'b', 'evidence', {}, 'e')['record_id']
                t = p.publish_batch_record('o', 'a', 'b', 'task', {'evidence_id': invalid}, 't')['record_id']
                with self.assertRaises(ValueError):
                    p.close_batch('o', 'a', 'b', 'PARTIAL', [invalid], ['gap'])
                with self.assertRaises(ValueError):
                    p.close_batch('o', 'a', 'b', 'COMPLETE', [e, t], [])
                self.assertFalse((p.root / 'b-close.json').exists())
                p.close_batch('o', 'a', 'b', 'PARTIAL', [e, t], ['invalid link'])

    def test_malformed_generic_payload_does_not_close_batch(self):
        for kind in ('evidence', 'task'):
            for invalid in ([], None, 'text', 1, 1.5, True, False, 'missing'):
                for recovery in ('COMPLETE', 'PARTIAL'):
                    with self.subTest(kind=kind, invalid=invalid, recovery=recovery), tempfile.TemporaryDirectory() as tmp:
                        p = Publisher(tmp)
                        p.open_batch('o', 'a', 'objective', 'b')
                        payload = {'type': kind, 'batch_id': 'b'}
                        if invalid != 'missing':
                            payload['payload'] = invalid
                        bad = p.publish('o', 'a', payload, 'b-bad')['record_id']
                        if kind == 'evidence':
                            e = bad
                            t = p.publish_batch_record('o', 'a', 'b', 'task', {'evidence_id': e}, 't')['record_id']
                        else:
                            e = p.publish_batch_record('o', 'a', 'b', 'evidence', {}, 'e')['record_id']
                            t = bad
                        before = {path.name: path.read_bytes() for path in p.root.iterdir()}
                        with self.assertRaises(ValueError):
                            p.close_batch('o', 'a', 'b', 'COMPLETE', [e, t], [])
                        self.assertFalse((p.root / 'b-close.json').exists())
                        self.assertEqual({path.name: path.read_bytes() for path in p.root.iterdir()}, before)
                        p = Publisher(tmp)
                        if recovery == 'COMPLETE':
                            e = p.publish_batch_record('o', 'a', 'b', 'evidence', {}, 'fixed-e')['record_id']
                            t = p.publish_batch_record('o', 'a', 'b', 'task', {'evidence_id': e}, 'fixed-t')['record_id']
                        closed = p.close_batch('o', 'a', 'b', recovery, [e, t], [] if recovery == 'COMPLETE' else ['invalid payload'])
                        if recovery == 'COMPLETE':
                            self.assertEqual(p.resolve_handoff(p.handoff(closed['record_id'])), closed)
                        else:
                            self.assertEqual(p.resolve('b-close')['payload']['status'], 'PARTIAL')

    def test_generic_complete_requires_batch_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Publisher(Path(tmp) / 'empty')
            empty.publish('o', 'a', {'type': 'receipt', 'status': 'COMPLETE', 'records': []}, 'empty')
            with self.assertRaises(ValueError):
                empty.resolve_handoff(empty.handoff('empty'))
            for defect in ('valid', 'open', 'hash', 'gaps', 'empty', 'duplicate', 'shape', 'owner', 'batch', 'link', 'type'):
                with self.subTest(defect=defect):
                    p = Publisher(Path(tmp) / defect)
                    opened = p.open_batch('o', 'a', 'objective', 'b')['receipt']
                    evidence = p.publish('other' if defect == 'owner' else 'o', 'a',
                                         {'type': 'stage' if defect == 'type' else 'evidence',
                                          'batch_id': 'foreign' if defect == 'batch' else 'b', 'payload': {}}, 'b-e')
                    task = p.publish_batch_record('o', 'a', 'b', 'task',
                                                  {'evidence_id': 'missing' if defect == 'link' else 'b-e'}, 't')['receipt']
                    records = [{'record_id': r['record_id'], 'sha256': r['content_sha256']} for r in (evidence, task)]
                    payload = dict(type='receipt', status='COMPLETE', batch_id='b', records=records,
                                   gaps=[], open=opened['content_sha256'])
                    if defect == 'open':
                        (p.root / 'b-open.json').unlink()
                    elif defect == 'hash':
                        payload['open'] = 'wrong'
                    elif defect == 'gaps':
                        payload['gaps'] = ['missing']
                    elif defect == 'empty':
                        payload['records'] = []
                    elif defect == 'duplicate':
                        payload['records'].append(records[0])
                    elif defect == 'shape':
                        payload['records'] = [[], None]
                    p.publish('o', 'a', payload, 'b-close')
                    if defect == 'valid':
                        self.assertEqual(p.resolve_handoff(p.handoff('b-close'))['payload'], payload)
                    else:
                        with self.assertRaises(ValueError):
                            p.resolve_handoff(p.handoff('b-close'))

    def test_non_object_json_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Publisher(tmp)
            for value in ([], None, 'text', 1):
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        p.publish('o', 'a', value, 'invalid')
                    (p.root / 'invalid.json').write_text(json.dumps(value))
                    with self.assertRaises(ValueError):
                        p.resolve('invalid')
                    with self.assertRaises(ValueError):
                        p.handoff('invalid')
                    (p.root / 'invalid.json').unlink()
            receipt = p.publish('o', 'a', {}, 'payload')
            receipt['payload'] = []
            (p.root / 'payload.json').write_text(json.dumps(receipt))
            with self.assertRaises(ValueError):
                p.handoff('payload')
            import missions
            artifact = Path(tmp) / 'artifact.txt'
            artifact.write_text('[]')
            p.open_batch('o', 'a', 'shape rejection', 'shape')
            evidence = p.publish_batch_record('o', 'a', 'shape', 'evidence', {
                'task_ref': str(artifact), 'task_sha256': missions.digest(artifact.read_bytes()),
                'result_ref': str(artifact), 'result_sha256': missions.digest(artifact.read_bytes())}, 'e')['record_id']
            task = p.publish_batch_record('o', 'a', 'shape', 'task', {'evidence_id': evidence}, 't')['record_id']
            p.close_batch('o', 'a', 'shape', 'COMPLETE', [evidence, task], [])
            with self.assertRaises(ValueError):
                p.report_stage('o', 'a', 'shape', 'executor', 'CANDIDATE', evidence, 'actor')

    def test_publish_resolve_idempotency_conflict_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'receipts'
            publisher = Publisher(root)
            value = publisher.publish('agent-1', 'task-1', {'status': 'OPEN'})
            self.assertTrue(value['record_id'].startswith('r_'))
            self.assertEqual(publisher.resolve(value['record_id']), value)
            self.assertEqual(publisher.publish('agent-1', 'task-1', {'status': 'OPEN'}, value['record_id']), value)
            with self.assertRaises(ValueError):
                publisher.handoff(value['record_id'])
            with self.assertRaises(ValueError):
                publisher.resolve_handoff('INICIO_LOTE: {"receipt_id":"' + value['record_id'] + '"}')
            with self.assertRaises(ValueError):
                publisher.resolve_handoff('INICIO_LOTE: {"receipt_id":"missing"}')
            with self.assertRaises(ValueError):
                publisher.resolve_handoff('INICIO_LOTE: {"receipt_id":"../escape"}')
            with self.assertRaises(ValueError):
                publisher.resolve_handoff('bad handoff')
            with self.assertRaises(ValueError):
                publisher.publish('agent-1', 'task-1', {'status': 'CLOSED'}, value['record_id'])
            with self.assertRaises(ValueError):
                publisher.publish('', 'task-1', {})
            with self.assertRaises(ValueError):
                publisher.resolve('../escape')

            resolved = subprocess.check_output([
                shutil.which('python3'), '-B', '-c',
                'import sys; sys.path.insert(0, sys.argv[2]); from publisher import Publisher; '
                'print(Publisher(sys.argv[1]).resolve(sys.argv[3])["payload"]["status"])',
                str(root), str(Path(__file__).resolve().parents[1] / 'scripts'), value['record_id'],
            ], text=True)
            self.assertEqual(resolved.strip(), 'OPEN')

            path = root / (value['record_id'] + '.json')
            path.write_text(json.dumps({'version': 1, 'record_id': value['record_id']}))
            with self.assertRaises(ValueError):
                publisher.resolve(value['record_id'])

            with self.assertRaises(ValueError):
                publisher.handoff(value['record_id'])

            for index in range(1, 16):
                publisher.publish('agent-1', 'task-1', {'index': index}, 'record-' + str(index))
            with self.assertRaises(ValueError):
                publisher.publish('agent-1', 'task-1', {'index': 16}, 'record-16')

            batch_publisher = Publisher(Path(tmp) / 'batch-receipts')
            opened = batch_publisher.open_batch('agent-1', 'task-1', 'Audit delivery', 'batch-1')
            evidence = batch_publisher.publish_batch_record('agent-1', 'task-1', 'batch-1', 'evidence', {'finding': 'ok'}, 'evidence-1')
            task = batch_publisher.publish_batch_record('agent-1', 'task-1', 'batch-1', 'task', {'evidence_id': evidence['record_id']}, 'task-1')
            closed = batch_publisher.close_batch('agent-1', 'task-1', 'batch-1', 'COMPLETE', [evidence['record_id'], task['record_id']], [])
            self.assertEqual(closed['payload']['status'], 'COMPLETE')
            self.assertEqual(batch_publisher.close_batch('agent-1', 'task-1', 'batch-1', 'COMPLETE', [evidence['record_id'], task['record_id']], []), closed)
            with self.assertRaises(ValueError):
                batch_publisher.close_batch('agent-1', 'task-1', 'batch-1', 'PARTIAL', [evidence['record_id']], ['changed'])
            with self.assertRaises(ValueError):
                batch_publisher.publish_batch_record('other', 'task-1', 'batch-1', 'evidence', {'finding': 'no'})
            orphan_publisher = Publisher(Path(tmp) / 'orphan-receipts')
            orphan_publisher.open_batch('agent-1', 'task-1', 'Orphan test', 'batch-orphan')
            orphan_task = orphan_publisher.publish_batch_record('agent-1', 'task-1', 'batch-orphan', 'task', {'evidence_id': 'batch-orphan-missing'}, 'task-1')
            with self.assertRaises(ValueError):
                orphan_publisher.close_batch('agent-1', 'task-1', 'batch-orphan', 'COMPLETE', [orphan_task['record_id']], [])

            opened_partial = batch_publisher.open_batch('agent-1', 'task-1', 'Partial delivery', 'batch-2')
            partial = batch_publisher.close_batch('agent-1', 'task-1', 'batch-2', 'PARTIAL', [], ['missing QA'])
            self.assertEqual(partial['payload']['status'], 'PARTIAL')
            with self.assertRaises(ValueError):
                batch_publisher.close_batch('agent-1', 'task-1', 'batch-2', 'COMPLETE', [], [])
            role_publisher = Publisher(Path(tmp) / 'role-receipts')
            role_publisher.bind_role('executor-caller', 'executor')
            role_publisher.bind_role('qa-caller', 'qa')
            role_publisher.bind_role('auditor-caller', 'auditor')
            self.assertEqual(role_publisher.bind_role('executor-caller', 'executor')['role'], 'executor')
            with self.assertRaises(ValueError):
                role_publisher.bind_role('executor-caller', 'qa')
            role_publisher.open_batch('executor-caller', 'task-1', 'Role test', 'role-batch')
            with self.assertRaises(ValueError):
                role_publisher.report_stage('qa-caller', 'task-1', 'role-batch', 'executor', 'CANDIDATE', 'wrong role', 'executor-actor')
            with self.assertRaises(ValueError):
                batch_publisher.report_stage('wrong-caller', 'task-1', 'batch-1', 'qa', 'VERIFIED', 'without executor', 'qa-actor')
            with self.assertRaises(ValueError):
                batch_publisher.report_stage('agent-1', 'task-1', 'batch-1', 'qa', 'VERIFIED', 'without executor', 'qa-actor')
            with self.assertRaises(ValueError):
                batch_publisher.report_stage('agent-1', 'task-1', 'batch-1', 'executor', 'CANDIDATE', 'candidate ready', 'executor-actor')
            self.assertEqual(batch_publisher.resolve_handoff(batch_publisher.handoff(closed['record_id'])), closed)
            for kind in ('evidence', 'task'):
                with self.assertRaises(ValueError):
                    batch_publisher.publish_batch_record('agent-1', 'task-1', 'batch-1', kind, {}, 'late')
            foreign = batch_publisher.root / '.collision.tmp'
            foreign.write_text('owned by someone else')
            batch_publisher.publish('agent-1', 'task-1', {}, 'collision')
            self.assertEqual(foreign.read_text(), 'owned by someone else')
            link = batch_publisher.root / 'linked.json'
            link.symlink_to(batch_publisher.root / (closed['record_id'] + '.json'))
            with self.assertRaises(ValueError):
                batch_publisher.resolve('linked')
            (batch_publisher.root / (evidence['record_id'] + '.json')).unlink()
            with self.assertRaises(ValueError):
                batch_publisher.resolve_handoff(batch_publisher.handoff(closed['record_id']))
            with self.assertRaises(ValueError):
                batch_publisher.report_stage('agent-1', 'task-1', 'batch-1', 'executor', 'CANDIDATE', evidence['record_id'], 'executor-actor')

            oversized = root / 'oversized.json'
            oversized.write_bytes(b'x' * (MAX_RECEIPT + 1))
            with self.assertRaises(ValueError):
                Publisher(root).resolve('oversized')


if __name__ == '__main__':
    unittest.main()
