#!/usr/bin/env python3
"""Recibos locales v1; no concede autoridad, sandbox ni autenticidad de QA."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

from onboard import FRAMEWORK, checked


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    path = checked(path)
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError('JSON ausente o demasiado grande')
    return json.loads(path.read_text())


def external(path):
    path = checked(path)
    if path == FRAMEWORK or FRAMEWORK in path.parents or path in FRAMEWORK.parents:
        raise ValueError('Destino debe ser externo al framework')
    return path


def snapshot(root, files):
    root = checked(root)
    if not root.is_dir() or not isinstance(files, list) or not files:
        raise ValueError('Raíz o archivos inválidos')
    result = {}
    for name in files:
        p = Path(name)
        if p.is_absolute() or '..' in p.parts or str(p) != name or name in result:
            raise ValueError('Archivo relativo inválido o duplicado')
        p = checked(root / p)
        if not p.is_file() or p.stat().st_nlink != 1:
            raise ValueError('Se requiere archivo regular sin enlaces')
        result[name] = digest(p.read_bytes())
    return result


def task_at(path):
    task = read_json(path)
    if task.get('version') != 1 or task.get('mode') not in ('audit', 'repair'):
        raise ValueError('Contrato v1 inválido')
    for field in ('objective', 'authorization_ref', 'executor', 'criteria'):
        if not task.get(field):
            raise ValueError('Falta ' + field)
    root = external(task['root'])
    snapshot(root, task['files'])
    if task['mode'] == 'repair':
        scope = task.get('change_scope')
        if (not isinstance(scope, list) or not scope or
                any(not isinstance(name, str) or name not in task['files'] for name in scope)):
            raise ValueError('Repair requiere change_scope con archivos incluidos en files')
    return task


def save(path, value):
    path = external(path)
    # ponytail: almacén local confiable, sin transacciones multiarchivo; Host para concurrencia hostil.
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def run_check(task_path, output, argv, timeout):
    task_path = checked(task_path)
    task = task_at(task_path)
    output = external(output)
    root = checked(task['root'])
    if root == output or root in output.parents or output in root.parents:
        raise ValueError('Evidencia fuera del candidato')
    if not argv or not all(isinstance(x, str) and x for x in argv) or not Path(argv[0]).is_absolute():
        raise ValueError('Comando argv explícito con ejecutable absoluto requerido')
    if argv not in task.get('commands', []) or not 0 < timeout <= task.get('timeout_seconds', 0) <= 600:
        raise ValueError('Comando o timeout fuera del mandato; confirmar autoridad humana aparte')
    before = snapshot(root, task['files'])
    output.mkdir(mode=0o700)  # Exclusivo: nunca reemplazar una ejecución anterior.
    with (output / 'stdout.txt').open('xb') as stdout, (output / 'stderr.txt').open('xb') as stderr:
        process = subprocess.Popen(argv, cwd=root, stdout=stdout, stderr=stderr,
                                   shell=False, start_new_session=True)
        timed_out = False
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            code = process.wait()
    after = snapshot(root, task['files'])
    record = dict(version=1, task_sha256=digest(task_path.read_bytes()), root=str(root),
                  files=before, after=after, argv=argv, timeout_seconds=timeout,
                  exit_code=code, timed_out=timed_out,
                  stdout_sha256=digest((output / 'stdout.txt').read_bytes()),
                  stderr_sha256=digest((output / 'stderr.txt').read_bytes()))
    save(output / 'check.json', record)
    return record


def reaudit(task_path, result_path, report_path):
    """Write a bounded incremental re-audit receipt; semantic review stays external."""
    task_path = checked(task_path)
    task = task_at(task_path)
    result = read_json(result_path)
    report_path = external(report_path)
    current = snapshot(task['root'], task['files'])
    if (result.get('version') != 1 or result.get('task_sha256') != digest(task_path.read_bytes())
            or result.get('files') != current or result.get('status') != 'ACCEPTED'):
        raise ValueError('Resultado no aceptado o candidato obsoleto')
    if task['mode'] == 'repair' and not result.get('check_ref'):
        raise ValueError('Reaudit de repair requiere check_ref')
    if not verify(task_path, result_path).startswith('ACCEPTED:'):
        raise ValueError('Resultado no aceptado')
    receipt = dict(version=1, task_sha256=result['task_sha256'], files=current,
                   result_sha256=digest(checked(result_path).read_bytes()),
                   verdict='PENDING_SEMANTIC_REVIEW',
                   review='Revisión incremental mecánica completada; semántica requiere Auditor/QA.')
    save(report_path, receipt)
    return receipt


def verify(task_path, result_path):
    task_path = checked(task_path)
    task = task_at(task_path)
    result = read_json(result_path)
    current = snapshot(task['root'], task['files'])
    if result.get('version') != 1 or result.get('task_sha256') != digest(task_path.read_bytes()):
        raise ValueError('Resultado de otro contrato')
    if result.get('files') != current:
        raise ValueError('Candidato obsoleto')
    if result.get('status') != 'ACCEPTED':
        return 'RETAINED: ' + str(result.get('reason', 'sin aceptación'))
    if not result.get('findings_ref'):
        raise ValueError('Falta entrega recuperable')
    findings = checked(result['findings_ref'])
    if not findings.is_file() or digest(findings.read_bytes()) != result.get('findings_sha256'):
        raise ValueError('Entrega ausente o alterada')
    if task['mode'] == 'repair':
        base = task.get('base')
        if not isinstance(base, dict) or any(name not in base for name in task['files']):
            raise ValueError('Base incompleta para comprobar alcance de reparación')
        unauthorized = [name for name in task['files']
                        if current[name] != base[name] and name not in task['change_scope']]
        if unauthorized:
            raise ValueError('Cambio fuera de change_scope: ' + ', '.join(unauthorized))
        check_path = checked(result['check_ref'])
        check = read_json(check_path)
        if (check.get('task_sha256') != result['task_sha256'] or check.get('root') != task['root']
                or check.get('files') != current or check.get('after') != current
                or check.get('exit_code') != 0 or check.get('timed_out') is not False
                or check.get('argv') not in task.get('commands', [])):
            raise ValueError('Prueba fallida, ajena o desactualizada')
        for name in ('stdout', 'stderr'):
            data = checked(check_path.parent / (name + '.txt')).read_bytes()
            if digest(data) != check.get(name + '_sha256'):
                raise ValueError('Salida ausente o alterada')
        qa_path = checked(result['qa_ref'])
        if digest(qa_path.read_bytes()) != result.get('qa_sha256'):
            raise ValueError('QA alterada')
        qa = read_json(qa_path)
        if (qa.get('task_sha256') != result['task_sha256'] or qa.get('files') != current
                or qa.get('verdict') != 'ACCEPTED' or not qa.get('reviewer')
                or qa['reviewer'] == task['executor'] or not qa.get('session_ref')
                or not qa.get('review') or qa.get('check_sha256') != digest(check_path.read_bytes())):
            raise ValueError('Falta referencia QA independiente ligada a prueba y candidato')
    return 'ACCEPTED: integridad documental; semántica y autoridad corresponden al revisor/Host'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    run = sub.add_parser('run-check')
    run.add_argument('--task', required=True)
    run.add_argument('--output', required=True)
    run.add_argument('--timeout', required=True, type=int)
    run.add_argument('argv', nargs=argparse.REMAINDER)
    check = sub.add_parser('verify')
    check.add_argument('--task', required=True)
    check.add_argument('--result', required=True)
    audit = sub.add_parser('reaudit')
    audit.add_argument('--task', required=True)
    audit.add_argument('--result', required=True)
    audit.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        if args.action == 'verify':
            print(verify(args.task, args.result))
        elif args.action == 'reaudit':
            print(json.dumps(reaudit(args.task, args.result, args.output)))
        else:
            argv = args.argv[1:] if args.argv[:1] == ['--'] else args.argv
            result = run_check(args.task, args.output, argv, args.timeout)
            print(json.dumps(result))
            return 0 if result['exit_code'] == 0 and not result['timed_out'] and result['files'] == result['after'] else 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('RETAINED: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
