import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import missions
import onboard
from publisher import Publisher


class TwoModeCycleTest(unittest.TestCase):
    def test_external_onboard_audit_repair_qa_reaudit_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product = root / 'product'
            product.mkdir()
            (product / 'value.py').write_text('def value(): return 1\n')
            workspace = root / 'workspace'
            session_root = root
            self.assertIn('CREADO', onboard.initialize(product, workspace, 'synthetic', apply=True))
            self.assertIn('CREADO', onboard.prepare_project_skills(workspace, apply=True))
            self.assertIn('ENLAZADO', onboard.link_project_skills(session_root, workspace, apply=True))
            product_before = (product / 'value.py').read_bytes()

            audit_root = root / 'audit-candidate'
            shutil.copytree(product, audit_root)
            audit_test = audit_root / 'test_audit.py'
            audit_test.write_text('from value import value\nassert value() == 1\n')
            audit_task = root / 'audit-task.json'
            argv = [shutil.which('python3'), '-B', 'test_audit.py']
            audit = dict(version=1, mode='audit', objective='verify value contract',
                         authorization_ref='synthetic audit authorization', executor='audit-executor',
                         criteria=['value returns one'], root=str(audit_root), files=['value.py', 'test_audit.py'],
                         commands=[argv], timeout_seconds=5)
            missions.save(audit_task, audit)
            audit_check = missions.run_check(audit_task, root / 'audit-check', argv, 5)
            self.assertEqual(audit_check['exit_code'], 0)
            findings = root / 'audit-findings.md'
            findings.write_text('value.py satisfies the declared contract.')
            audit_result = root / 'audit-result.json'
            missions.save(audit_result, dict(version=1, task_sha256=missions.digest(audit_task.read_bytes()),
                files=audit_check['after'], status='ACCEPTED', findings_ref=str(findings),
                findings_sha256=missions.digest(findings.read_bytes())))
            self.assertTrue(missions.verify(audit_task, audit_result).startswith('ACCEPTED'))

            candidate = root / 'candidate'
            shutil.copytree(product, candidate)
            (candidate / 'test_contract.py').write_text('from value import value\nassert value() == 2\nprint("green")\n')
            repair_base = root / 'repair-base'
            shutil.copytree(candidate, repair_base)
            repair_task = root / 'repair-task.json'
            repair_argv = [shutil.which('python3'), '-B', 'test_contract.py']
            repair = dict(version=1, mode='repair', objective='correct value contract',
                authorization_ref='synthetic repair authorization', executor='repair-executor',
                criteria=['value returns two'], root=str(candidate), files=['value.py', 'test_contract.py'],
                change_scope=['value.py'], commands=[repair_argv], timeout_seconds=5,
                base=missions.snapshot(repair_base, ['value.py', 'test_contract.py']))
            missions.save(repair_task, repair)
            red = missions.run_check(repair_task, root / 'repair-red', repair_argv, 5)
            self.assertNotEqual(red['exit_code'], 0)
            (candidate / 'value.py').write_text('def value(): return 2\n')
            green = missions.run_check(repair_task, root / 'repair-green', repair_argv, 5)
            self.assertEqual(green['exit_code'], 0)
            qa = root / 'repair-qa.json'
            missions.save(qa, dict(task_sha256=missions.digest(repair_task.read_bytes()), files=green['files'],
                check_sha256=missions.digest((root / 'repair-green/check.json').read_bytes()),
                reviewer='synthetic-qa', session_ref='fixture-only',
                review='Simulated QA; not independent agent evidence.', verdict='ACCEPTED'))
            result = root / 'repair-result.json'
            missions.save(result, dict(version=1, task_sha256=missions.digest(repair_task.read_bytes()),
                files=green['files'], status='ACCEPTED', findings_ref=str(findings),
                findings_sha256=missions.digest(findings.read_bytes()),
                check_ref=str(root / 'repair-green/check.json'), qa_ref=str(qa),
                qa_sha256=missions.digest(qa.read_bytes())))
            self.assertTrue(missions.verify(repair_task, result).startswith('ACCEPTED'))
            reaudit = missions.reaudit(repair_task, result, root / 'repair-reaudit.json')
            self.assertEqual(reaudit['verdict'], 'PENDING_SEMANTIC_REVIEW')

            publisher = Publisher(root / 'receipts')
            opened = publisher.open_batch('owner', 'auth', 'synthetic repair', 'trial-batch')
            evidence = publisher.publish_batch_record('owner', 'auth', 'trial-batch', 'evidence', {'finding': 'verified'}, 'evidence')
            task = publisher.publish_batch_record('owner', 'auth', 'trial-batch', 'task', {'evidence_id': evidence['record_id']}, 'task')
            publisher.close_batch('owner', 'auth', 'trial-batch', 'COMPLETE', [evidence['record_id'], task['record_id']], [])
            publisher.report_stage('owner', 'auth', 'trial-batch', 'executor', 'CANDIDATE', 'candidate green', 'executor-actor')
            publisher.report_stage('owner', 'auth', 'trial-batch', 'qa', 'VERIFIED', 'fixture QA only', 'qa-actor')
            publisher.report_stage('owner', 'auth', 'trial-batch', 'auditor', 'ACCEPTED', 'mechanical acceptance only', 'auditor-actor')
            handoff = publisher.handoff(opened['record_id'])
            self.assertEqual(publisher.resolve_handoff(handoff)['payload']['status'], 'OPEN')
            self.assertEqual((product / 'value.py').read_bytes(), product_before)


if __name__ == '__main__':
    unittest.main()
