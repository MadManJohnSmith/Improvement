import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

import sys
sys.path.insert(0, str(ROOT / 'scripts'))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = load('audit')
cap = load('capabilities')


class AuditCycleTest(unittest.TestCase):
    def test_partition_consolidation_and_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'product'
            root.mkdir()
            (root / 'a.py').write_text('a')
            (root / 'b.py').write_text('b')
            units = [
                {'unit_id': 'u-a', 'files': ['a.py'], 'depends_on': [], 'status': 'PLANNED'},
                {'unit_id': 'u-b', 'files': ['b.py'], 'depends_on': ['u-a'], 'status': 'PLANNED'},
            ]
            findings = [
                {'fingerprint': 'f1', 'status': 'READY_FOR_REPAIR', 'change_scope': ['a.py']},
                {'fingerprint': 'f1', 'status': 'DUPLICATE'},
                {'fingerprint': 'f2', 'status': 'RETAINED'},
            ]
            result = audit.consolidate(root, 'c1', 'base1', units, findings)
            self.assertEqual([f['fingerprint'] for f in result['repair_queue']], ['f1'])
            self.assertEqual(result['status'], 'UNVERIFIED')
            self.assertEqual(result['coverage']['coverage_gaps'], ['INVENTORY_MISSING'])
            index = audit.archive_cycle(Path(tmp), 'c1', {'status': 'done'}, result)
            self.assertTrue((Path(tmp) / 'archive/c1/index.json').is_file())
            self.assertEqual(index['cycle_id'], 'c1')
            with self.assertRaises(FileExistsError):
                audit.archive_cycle(Path(tmp), 'c1', {}, {})

    def test_cli_consolidation_writes_active_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product = root / 'product'
            product.mkdir()
            (product / 'a.py').write_text('a')
            manifest = {'version': 1, 'root': str(product), 'units': [
                {'unit_id': 'u-a', 'files': ['a.py'], 'depends_on': [], 'status': 'PLANNED'}]}
            manifest_path = root / 'manifest.json'
            findings_path = root / 'findings.json'
            manifest_path.write_text(json.dumps(manifest))
            findings_path.write_text(json.dumps({'findings': [
                {'fingerprint': 'f1', 'status': 'READY_FOR_REPAIR', 'change_scope': ['a.py']},
                {'fingerprint': 'f2', 'status': 'RETAINED'}]}))
            workspace = root / 'workspace'
            result = audit.write_consolidated(workspace, 'c1', 'base1', manifest, json.loads(findings_path.read_text())['findings'])
            self.assertEqual(result['status'], 'UNVERIFIED')
            self.assertTrue((workspace / 'active/repair-queue.json').is_file())
            self.assertEqual(result['repair_queue'][0]['fingerprint'], 'f1')

    def test_rejects_overlap_and_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'product'
            root.mkdir()
            (root / 'a').write_text('x')
            units = [
                {'unit_id': 'a', 'files': ['a'], 'depends_on': ['b']},
                {'unit_id': 'b', 'files': ['a'], 'depends_on': ['a']},
            ]
            with self.assertRaises(ValueError):
                audit.validate_units(root, units)
            with self.assertRaises(ValueError):
                audit.validate_units(root, [{'unit_id': 'x', 'files': ['../a'], 'depends_on': []}])

    def test_capability_reuse_and_scope_expansion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product, framework, workspace = (root / n for n in ('product', 'framework', 'workspace'))
            for path in (product, framework, workspace):
                path.mkdir()
            capability = {
                'version': 1, 'capability_id': 'cap-1', 'session_id': 's1',
                'project': 'p', 'executor': 'e',
                'roots': {'product_read': [str(product)], 'framework_execute': [str(framework)],
                          'workspace_write': [str(workspace)]},
                'scope': ['u1'],
            }
            path = root / 'capability.json'
            path.write_text(json.dumps(capability))
            current = cap.validate(path, session_id='s1', project='p', executor='e', scope=['u1'])
            self.assertEqual(cap.reusable(path, current, session_id='s1', project='p', executor='e', scope=['u1'])['capability_id'], 'cap-1')
            with self.assertRaises(ValueError):
                cap.reusable(path, current, session_id='s1', project='p', executor='e', scope=['u1', 'u2'])


if __name__ == '__main__':
    unittest.main()
