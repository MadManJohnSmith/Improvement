"""Ciclo sintético ejecutable; QA fixture NO representa revisión de agente real."""
import json
from pathlib import Path
import sys
import shutil
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import missions as m


class OperationalCycleTest(unittest.TestCase):
    def test_candidate_cycle_and_rejections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product = root / 'product'
            product.mkdir()
            (product / 'queue.py').write_text('def size(items): return len(items) + 1\n')
            (product / 'test_contract.py').write_text('from queue import size\nassert size([]) == 0\nprint("contract passed")\n')
            original = {p.name: p.read_bytes() for p in product.iterdir()}
            candidate = root / 'candidate'
            candidate.mkdir()
            for name, data in original.items():
                (candidate / name).write_bytes(data)
            task_path = root / 'task.json'
            argv = [shutil.which('python3'), '-B', 'test_contract.py']
            task = dict(version=1, mode='repair', objective='empty queue size',
                        authorization_ref='synthetic fixture only', executor='fixture-author',
                        criteria=['empty queue size is zero'], root=str(candidate),
                        files=sorted(original), change_scope=['queue.py'], commands=[argv], timeout_seconds=5,
                        base=m.snapshot(product, sorted(original)))
            m.save(task_path, task)
            red = m.run_check(task_path, root / 'red', argv, 5)
            self.assertNotEqual(red['exit_code'], 0)
            self.assertIn(b'AssertionError', (root / 'red/stderr.txt').read_bytes())
            (candidate / 'queue.py').write_text('def size(items): return len(items)\n')
            green = m.run_check(task_path, root / 'green', argv, 5)
            self.assertEqual(green['exit_code'], 0)
            self.assertEqual((root / 'green/stdout.txt').read_text(), 'contract passed\n')
            findings = root / 'findings.txt'
            findings.write_text('Synthetic fixture: remove off-by-one; empty queue test passes.')
            qa_path = root / 'qa.json'
            qa = dict(task_sha256=m.digest(task_path.read_bytes()), files=green['files'],
                      check_sha256=m.digest((root / 'green/check.json').read_bytes()),
                      reviewer='fixture-reviewer', session_ref='SIMULATED QA, not an agent session',
                      review='Fixture represents independent QA reference, not actual semantic review.',
                      verdict='ACCEPTED')
            m.save(qa_path, qa)
            result = dict(version=1, task_sha256=qa['task_sha256'], files=green['files'], status='ACCEPTED',
                          findings_ref=str(findings), findings_sha256=m.digest(findings.read_bytes()),
                          check_ref=str(root / 'green/check.json'), qa_ref=str(qa_path),
                          qa_sha256=m.digest(qa_path.read_bytes()))
            result_path = root / 'result.json'

            def verify(value):
                result_path.write_text(json.dumps(value))
                return m.verify(task_path, result_path)

            self.assertTrue(verify(result).startswith('ACCEPTED'))
            reaudit = m.reaudit(task_path, result_path, root / 'reaudit.json')
            self.assertEqual(reaudit['verdict'], 'PENDING_SEMANTIC_REVIEW')
            self.assertEqual(reaudit['files'], green['files'])
            for field in ('qa_ref', 'check_ref', 'findings_ref'):
                invalid = dict(result)
                invalid.pop(field)
                with self.subTest(field=field), self.assertRaises((ValueError, KeyError)):
                    verify(invalid)
            with self.assertRaises(ValueError):
                verify(dict(result, check_ref=str(root / 'red/check.json')))
            (candidate / 'queue.py').write_text('def size(items): return 99\n')
            with self.assertRaises(ValueError):
                verify(result)
            (candidate / 'queue.py').write_text('def size(items): return len(items)\n')
            (candidate / 'test_contract.py').write_text('from queue import size\nassert size([]) == 0\nprint("changed")\n')
            with self.assertRaises(ValueError):
                verify(result)
            (candidate / 'test_contract.py').write_bytes(original['test_contract.py'])
            (root / 'green/stdout.txt').write_text('invented')
            with self.assertRaises(ValueError):
                verify(result)
            (root / 'green/stdout.txt').write_text('contract passed\n')
            qa['reviewer'] = task['executor']
            qa_path.write_text(json.dumps(qa))
            with self.assertRaises(ValueError):
                verify(dict(result, qa_sha256=m.digest(qa_path.read_bytes())))
            self.assertEqual(original, {p.name: p.read_bytes() for p in product.iterdir()})

            missing_scope = dict(task)
            missing_scope.pop('change_scope')
            missing_path = root / 'missing-scope.json'
            m.save(missing_path, missing_scope)
            with self.assertRaises(ValueError):
                m.task_at(missing_path)
            with self.assertRaises(FileExistsError):
                m.run_check(task_path, root / 'green', argv, 5)
            with self.assertRaises(ValueError):
                m.run_check(task_path, root / 'unauthorized', ['sh', '-c', 'true'], 5)
            self.assertFalse((root / 'unauthorized').exists())
            with self.assertRaises(ValueError):
                m.run_check(task_path, candidate / 'evidence', argv, 5)
            with self.assertRaises(ValueError):
                m.external(m.FRAMEWORK / 'evidence')
            link = candidate / 'linked'
            link.symlink_to(product / 'queue.py')
            with self.assertRaises(ValueError):
                m.snapshot(candidate, ['linked'])

    def test_timeout_and_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / 'candidate'
            candidate.mkdir()
            (candidate / 'test.py').write_text('import time\ntime.sleep(10)\n')
            argv = [shutil.which('python3'), '-B', 'test.py']
            task = dict(version=1, mode='audit', objective='inspect', authorization_ref='fixture',
                        executor='fixture', criteria=['cite source'], root=str(candidate),
                        files=['test.py'], commands=[argv], timeout_seconds=1)
            path = root / 'task.json'
            m.save(path, task)
            check = m.run_check(path, root / 'timeout', argv, 1)
            self.assertTrue(check['timed_out'])
            report = root / 'report.txt'
            report.write_text('test.py sleeps; inspection only, no claim of correctness')
            result = dict(version=1, task_sha256=m.digest(path.read_bytes()),
                          files=m.snapshot(candidate, task['files']), status='ACCEPTED',
                          findings_ref=str(report), findings_sha256=m.digest(report.read_bytes()))
            result_path = root / 'result.json'
            m.save(result_path, result)
            self.assertTrue(m.verify(path, result_path).startswith('ACCEPTED'))


if __name__ == '__main__':
    unittest.main()
