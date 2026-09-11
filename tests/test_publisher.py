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
    def test_publish_resolve_idempotency_conflict_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'receipts'
            publisher = Publisher(root)
            value = publisher.publish('agent-1', 'task-1', {'status': 'OPEN'})
            self.assertTrue(value['record_id'].startswith('r_'))
            self.assertEqual(publisher.resolve(value['record_id']), value)
            self.assertEqual(publisher.publish('agent-1', 'task-1', {'status': 'OPEN'}, value['record_id']), value)
            handoff = publisher.handoff(value['record_id'])
            self.assertEqual(handoff, 'INICIO_LOTE: {"receipt_id":"' + value['record_id'] + '"}')
            self.assertEqual(publisher.resolve_handoff(handoff), value)
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
            with self.assertRaises(ValueError):
                batch_publisher.publish_batch_record('other', 'task-1', 'batch-1', 'evidence', {'finding': 'no'})
            opened_partial = batch_publisher.open_batch('agent-1', 'task-1', 'Partial delivery', 'batch-2')
            partial = batch_publisher.close_batch('agent-1', 'task-1', 'batch-2', 'PARTIAL', [], ['missing QA'])
            self.assertEqual(partial['payload']['status'], 'PARTIAL')
            with self.assertRaises(ValueError):
                batch_publisher.close_batch('agent-1', 'task-1', 'batch-2', 'COMPLETE', [], [])

            oversized = root / 'oversized.json'
            oversized.write_bytes(b'x' * (MAX_RECEIPT + 1))
            with self.assertRaises(ValueError):
                Publisher(root).resolve('oversized')


if __name__ == '__main__':
    unittest.main()
