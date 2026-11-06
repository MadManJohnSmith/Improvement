"""Unidades del 2026-11-05: techo de exclusión, ancla leída y shim roto.

Cada prueba falla sin el cambio correspondiente: el techo rechaza una exclusión
posterior al manifiesto de campaña, el ancla ausente bloquea el cierre y una
capacidad con intérprete #! inexistente queda `unrunnable` sin ejecutarla.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import audit
import stack


class ExclusionCeilingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ceiling-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'src').mkdir()
        (self.root / 'src' / 'a.py').write_text('a')
        self.manifest = self.root / '.dsh-managed' / 'campaign' / 'manifest.json'
        self.manifest.parent.mkdir(parents=True)
        self.manifest.write_text(json.dumps(
            {'preset_ids': ['p'], 'exclusion_ceiling': '2026-12-31'}))
        self.exclusions = {'src': {'reason': 'legacy tree', 'owner': 'owner@example',
                                   'receipt': 'r-1', 'expires_at': '2026-12-01'}}

    def test_exclusion_after_the_campaign_ceiling_is_rejected(self):
        late = dict(self.exclusions['src'], expires_at='2027-01-01')
        with self.assertRaisesRegex(ValueError, 'techo'):
            audit.inventory(self.root, {'src': late})

    def test_exclusion_within_the_ceiling_is_kept(self):
        result = audit.inventory(self.root, self.exclusions)
        self.assertIn('src', result['exclusions'])

    def test_invalid_ceiling_fails_closed(self):
        self.manifest.write_text(json.dumps(
            {'preset_ids': ['p'], 'exclusion_ceiling': 'tomorrow'}))
        with self.assertRaisesRegex(ValueError, 'Techo'):
            audit.inventory(self.root, self.exclusions)


class AnchorRecheckTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='anchor-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'a.py').write_text('primera linea\nsegunda linea\n')
        self.units = [{'unit_id': 'a', 'files': ['a.py'], 'depends_on': [],
                       'status': 'ACCEPTED'}]
        self.snapshot = audit.inventory(self.root)

    def consolidate(self, findings):
        return audit.consolidate(self.root, 'c1', 'base1', self.units, findings,
                                 self.snapshot)

    def test_located_anchor_survives_closure(self):
        result = self.consolidate([{
            'fingerprint': 'f1', 'status': 'READY_FOR_REPAIR',
            'evidence': {'path': 'a.py', 'excerpt': 'segunda linea', 'line': 2}}])
        evidence = result['findings'][0]['evidence']
        self.assertEqual(result['findings'][0]['anchor_status'], 'located')
        self.assertEqual(evidence['line'], 2)

    def test_moved_anchor_is_relocated_with_receipt(self):
        result = self.consolidate([{
            'fingerprint': 'f2', 'status': 'READY_FOR_REPAIR',
            'evidence': {'path': 'a.py', 'excerpt': 'primera linea', 'line': 9}}])
        self.assertEqual(result['reanchored'],
                         [{'fingerprint': 'f2', 'from': 9, 'to': 1}])
        self.assertEqual(result['findings'][0]['evidence']['line'], 1)
        self.assertEqual(result['findings'][0]['anchor_status'], 'moved')

    def test_absent_anchor_blocks_closure(self):
        with self.assertRaisesRegex(ValueError, 'Ancla ausente'):
            self.consolidate([{
                'fingerprint': 'f3', 'status': 'READY_FOR_REPAIR',
                'evidence': {'path': 'a.py', 'excerpt': 'ya no existe'}}])


class ShebangCapabilityTest(unittest.TestCase):
    def test_dead_interpreter_is_unrunnable_without_executing(self):
        temp = tempfile.TemporaryDirectory(prefix='shim-')
        self.addCleanup(temp.cleanup)
        bindir = Path(temp.name)
        shim = bindir / 'broken-tool'
        shim.write_text('#!/nonexistent/interpreter\n')
        shim.chmod(0o755)
        entry, = stack._capability_status(['broken-tool'], path_env=str(bindir))
        self.assertEqual(entry['status'], 'unrunnable')


if __name__ == '__main__':
    unittest.main()
