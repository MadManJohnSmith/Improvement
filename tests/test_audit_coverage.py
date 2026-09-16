import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import audit


class AuditCoverageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='audit-coverage-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.product = self.root / 'product'
        self.product.mkdir()
        (self.product / 'a.py').write_text('a')
        (self.product / 'b.py').write_text('b')
        self.units = [
            {'unit_id': 'a', 'files': ['a.py'], 'depends_on': [], 'status': 'ACCEPTED'},
            {'unit_id': 'b', 'files': ['b.py'], 'depends_on': ['a'], 'status': 'ACCEPTED'},
        ]
        self.snapshot = audit.inventory(self.product)

    def consolidate(self, units=None, snapshot=None, findings=None):
        return audit.consolidate(self.product, 'c1', 'base1',
                                 self.units if units is None else units,
                                 [] if findings is None else findings,
                                 self.snapshot if snapshot is None else snapshot)

    def test_deterministic_snapshot_and_explicit_exclusions(self):
        hidden = self.product / '.git'
        hidden.mkdir()
        (hidden / 'secret').write_text('fixture-only')
        snapshot = audit.inventory(self.product, {'.git': 'Authorized metadata exclusion'})
        self.assertEqual(list(snapshot['files']), ['a.py', 'b.py'])
        self.assertEqual(snapshot['files']['a.py'], hashlib.sha256(b'a').hexdigest())
        self.assertEqual(snapshot['exclusions']['.git']['kind'], 'directory')
        (hidden / 'secret').write_text('not part of the inspected boundary')
        self.assertEqual(snapshot, audit.inventory(self.product, {'.git': 'Authorized metadata exclusion'}))
        self.assertIn('.git/secret', audit.inventory(self.product)['files'])
        with self.assertRaisesRegex(ValueError, 'justificación'):
            audit.inventory(self.product, {'.git': ''})
        with self.assertRaisesRegex(ValueError, 'ausente'):
            audit.inventory(self.product, {'missing': 'reason'})
        with self.assertRaisesRegex(ValueError, 'anidada'):
            audit.inventory(self.product, {'.git': 'reason', '.git/secret': 'reason'})

    def test_total_partition_only_closes_with_accepted_units(self):
        result = self.consolidate()
        self.assertEqual(result['status'], 'AUDIT_COMPLETE')
        self.assertEqual(result['coverage']['status'], 'PARTITION_VERIFIED')
        self.assertEqual(result['coverage']['assigned_files'], 2)
        retained = self.consolidate(findings=[{'fingerprint': 'f', 'status': 'RETAINED'}])
        self.assertEqual(retained['status'], 'AUDIT_COMPLETE_WITH_RETAINED_ITEMS')
        for state in ['PLANNED', 'AUDITING', 'RETAINED', 'UNVERIFIED', 'STALE', None]:
            with self.subTest(state=state):
                units = copy.deepcopy(self.units)
                if state is None:
                    units[0].pop('status')
                else:
                    units[0]['status'] = state
                result = self.consolidate(units=units)
                self.assertEqual(result['status'], 'UNVERIFIED')
                self.assertEqual(result['coverage']['pending_units'], ['a'])

    def test_unassigned_file_is_gap_not_silent_completion(self):
        result = self.consolidate(units=self.units[:1])
        self.assertEqual(result['status'], 'UNVERIFIED')
        self.assertEqual(result['coverage']['coverage_gaps'], ['b.py'])
        self.assertEqual(result['findings'], [])
        self.assertEqual(result['coverage']['included_files'], 2)
        self.assertEqual(result['coverage']['assigned_files'], 1)

    def test_legacy_without_snapshot_preserves_queue_not_coverage_claim(self):
        findings = [{'fingerprint': 'f', 'status': 'READY_FOR_REPAIR'},
                    {'fingerprint': 'f', 'status': 'DUPLICATE'}]
        result = audit.consolidate(self.product, 'legacy', 'base1', self.units, findings)
        self.assertEqual(result['status'], 'UNVERIFIED')
        self.assertEqual(result['coverage']['coverage_gaps'], ['INVENTORY_MISSING'])
        self.assertEqual(result['repair_queue'], [findings[0]])

    def test_changed_added_removed_or_forged_files_invalidate_snapshot(self):
        for change in ['changed', 'added', 'removed', 'forged_hash', 'omitted', 'invented']:
            with self.subTest(change=change):
                snapshot = copy.deepcopy(self.snapshot)
                if change == 'changed':
                    (self.product / 'a.py').write_text('changed')
                elif change == 'added':
                    (self.product / 'new.py').write_text('new')
                elif change == 'removed':
                    (self.product / 'b.py').unlink()
                elif change == 'forged_hash':
                    snapshot['files']['a.py'] = '0' * 64
                elif change == 'omitted':
                    del snapshot['files']['b.py']
                else:
                    snapshot['files']['absent.py'] = '0' * 64
                with self.assertRaises(ValueError):
                    self.consolidate(snapshot=snapshot)
                (self.product / 'a.py').write_text('a')
                (self.product / 'b.py').write_text('b')
                if (self.product / 'new.py').exists():
                    (self.product / 'new.py').unlink()

    def test_exclusions_cannot_also_be_assigned_or_changed_in_shape(self):
        snapshot = audit.inventory(self.product, {'b.py': 'Outside agreed scope'})
        with self.assertRaisesRegex(ValueError, 'fuera del inventario'):
            self.consolidate(snapshot=snapshot)
        result = self.consolidate(units=self.units[:1], snapshot=snapshot)
        self.assertEqual(result['status'], 'AUDIT_COMPLETE')
        self.assertEqual(result['coverage']['excluded_entries'], 1)
        snapshot['exclusions']['b.py']['kind'] = 'directory'
        with self.assertRaisesRegex(ValueError, 'obsoleto'):
            self.consolidate(units=self.units[:1], snapshot=snapshot)

    def test_inventory_rejects_links_special_files_and_unsafe_paths(self):
        link = self.product / 'link'
        link.symlink_to(self.root)
        with self.assertRaises(ValueError):
            audit.inventory(self.product)
        with self.assertRaises(ValueError):
            audit.inventory(self.product, {'link': 'Not permission to follow a link'})
        link.unlink()
        for name in ['../x', '/absolute', '.', './a.py', 'a.py/', 'x//y']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                audit.inventory(self.product, {name: 'reason'})
        if hasattr(os, 'mkfifo'):
            os.mkfifo(self.product / 'pipe')
            with self.assertRaisesRegex(ValueError, 'no regular'):
                audit.inventory(self.product)

    def test_dependencies_overlap_and_duplicates_rejected_independently(self):
        self.assertEqual(audit.validate_units(self.product, self.units), {'a.py': 'a', 'b.py': 'b'})
        for mode in ['cycle', 'unknown', 'overlap', 'duplicate']:
            units = copy.deepcopy(self.units)
            if mode == 'cycle':
                units[0]['depends_on'] = ['b']
            elif mode == 'unknown':
                units[0]['depends_on'] = ['missing']
            elif mode == 'overlap':
                units[1]['files'] = ['a.py']
            else:
                units[0]['files'].append('a.py')
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                audit.validate_units(self.product, units)

    def test_real_cli_inventory_and_consolidation(self):
        command = [sys.executable, '-B', str(ROOT / 'scripts/audit.py')]
        result = subprocess.run(command + ['inventory', '--product', str(self.product)],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), self.snapshot)
        manifest = self.root / 'manifest.json'
        manifest.write_text(json.dumps({'version': 1, 'root': str(self.product),
                                        'inventory': self.snapshot, 'units': self.units}))
        findings = self.root / 'findings.json'
        findings.write_text('{"findings": []}')
        run = self.root / 'run'
        run.mkdir()
        (run / 'started.json').write_text('{"status":"STARTED","cycle_id":"c1"}')
        workspace = self.root / 'workspace'
        args = command + ['consolidate', '--root', str(workspace), '--manifest', str(manifest),
                          '--findings', str(findings), '--cycle-id', 'c1', '--base-revision', 'base1']
        result = subprocess.run(args, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['status'], 'AUDIT_COMPLETE')
        coverage = json.loads((workspace / 'cycles/c1/coverage-matrix.json').read_text())
        self.assertEqual(coverage['status'], 'PARTITION_VERIFIED')
        self.assertEqual(json.loads((workspace / 'active/repair-queue.json').read_text())['findings'], [])
        before = {str(p): p.read_bytes() for p in workspace.rglob('*') if p.is_file()}
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, {str(p): p.read_bytes() for p in workspace.rglob('*') if p.is_file()})
        self.assertEqual(audit.inventory(self.product), self.snapshot)

    def test_invalid_publish_fails_before_writes(self):
        workspace = self.root / 'workspace'
        manifest = {'version': 1, 'root': str(self.product), 'units': self.units, 'inventory': self.snapshot}
        for cycle in ['../escape', '/absolute', '.', '', 'a/b']:
            with self.subTest(cycle=cycle), self.assertRaises(ValueError):
                audit.write_consolidated(workspace, cycle, 'base1', manifest, [])
            self.assertFalse(workspace.exists())
        for target in [self.product, self.product / 'output', self.root,
                       Path('/' + str(self.product / 'output'))]:
            with self.subTest(target=target), self.assertRaises(ValueError):
                audit.write_consolidated(target, 'c1', 'base1', manifest, [])
        alternate = dict(manifest, root='/' + str(self.product))
        with self.assertRaises(ValueError):
            audit.write_consolidated(self.product / 'output', 'c1', 'base1', alternate, [])
        self.assertFalse((self.product / 'output').exists())
        (self.product / 'a.py').write_text('changed')
        with self.assertRaises(ValueError):
            audit.write_consolidated(workspace, 'c1', 'base1', manifest, [])
        self.assertFalse(workspace.exists())
        oversized = self.root / 'oversized.json'
        oversized.write_text(json.dumps({'data': 'x' * (2 * 1024 * 1024)}))
        with self.assertRaisesRegex(ValueError, 'grande'):
            audit.read(oversized)


if __name__ == '__main__':
    unittest.main()
