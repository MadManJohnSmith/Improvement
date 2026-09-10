#!/usr/bin/env python3
"""Inicialización local explícita; sin dependencias ni ejecución del proyecto."""
import argparse
import json
import os
from pathlib import Path
import re

FRAMEWORK = Path(__file__).resolve().parents[1]


def framework_clean():
    """Return whether the canonical framework worktree is unchanged."""
    import subprocess
    result = subprocess.run(
        ['git', '-C', str(FRAMEWORK), '--no-optional-locks', 'status', '--porcelain'],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise ValueError('No se pudo comprobar el estado Git del framework')
    return not result.stdout


def checked(raw):
    p = Path(raw)
    if not p.is_absolute() or '..' in p.parts:
        raise ValueError('Se requiere ruta absoluta sin ..')
    for part in [*reversed(p.parents), p]:
        if part.is_symlink():
            raise ValueError('Enlace simbólico rechazado')
    return p


def prepare_project_skills(workspace, source=FRAMEWORK / 'skills', apply=False):
    """Prepare a non-overwriting DSH project skill root in the external workspace."""
    workspace, source = checked(workspace), checked(source)
    if not workspace.is_dir() or not source.is_dir():
        raise ValueError('Workspace y origen de skills deben existir')
    names = sorted(p.name for p in source.iterdir() if p.is_dir() and (p / 'SKILL.md').is_file())
    if not names:
        raise ValueError('No hay skills portables en el origen')
    target = workspace / '.agents' / 'skills'
    if not apply:
        return f'DRY-RUN: preparar {len(names)} skills en {target}; sin escrituras'
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name in names:
        destination = target / name
        if destination.exists() or destination.is_symlink():
            raise ValueError(f'Skill existente en conflicto: {destination}')
        destination.mkdir(mode=0o700)
        (destination / 'SKILL.md').write_bytes((source / name / 'SKILL.md').read_bytes())
    return f'CREADO: {len(names)} skills en {target}'


def initialize(project, workspace, name, apply=False):
    project, workspace = checked(project), checked(workspace)
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', name):
        raise ValueError('Identidad inválida: use minúsculas, números y guiones')
    if not project.is_dir() or not workspace.parent.is_dir():
        raise ValueError('Proyecto y padre del workspace deben existir')
    for other in (project, FRAMEWORK):
        if workspace == other or workspace in other.parents or other in workspace.parents:
            raise ValueError('Workspace debe ser externo al proyecto y framework')
    for parent in [workspace.parent, *workspace.parent.parents]:
        if (parent / '.git').exists() or (parent / '.git').is_symlink():
            raise ValueError('Workspace no puede estar dentro de un repositorio Git')
    identity = {'schema': 1, 'name': name, 'project': str(project)}
    # ponytail: padres locales confiables; para adversarios concurrentes usar sandbox OS.
    if workspace.exists():
        if not workspace.is_dir():
            raise ValueError('Destino en conflicto')
        for filename in ('project.json', 'PROJECT.md'):
            p = checked(str(workspace / filename))
            if not p.is_file() or p.stat().st_nlink != 1 or p.stat().st_size > 65536:
                raise ValueError('Perfil incompleto o en conflicto; conservar y reconciliar')
        if json.loads((workspace / 'project.json').read_text()) != identity:
            raise ValueError('Identidad existente en conflicto')
        return 'EXISTENTE: no se modificó el perfil'
    if not apply:
        return f'DRY-RUN: crear {workspace} para {name}; sin escrituras'
    workspace.mkdir(mode=0o700)
    try:
        for filename, content in {
            'project.json': json.dumps(identity, ensure_ascii=False, indent=2) + '\n',
            'PROJECT.md': f'# Proyecto {name}\n\nFuente: {project}\n\n'
                          '## Primer encargo\nPendiente de objetivo y autorización.\n\n'
                          '## Restricciones\nSin permiso implícito para modificar producto, '
                          'ejecutar sus scripts, acceder a credenciales, red o publicar.\n\n'
                          '## Descubrimiento pendiente\nIdentificar instrucciones, canónicos, '
                          'comandos seguros y datos excluidos antes de actuar. '
                          'Crear evidencia solo cuando el encargo la necesite.\n',
        }.items():
            fd = os.open(workspace / filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as stream:
                stream.write(content)
    except Exception:
        # Conservar inicialización parcial: no borrar evidencia ni reintentar a ciegas.
        raise
    return f'CREADO: {workspace}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--init', action='store_true', help='Crear; sin esta opción solo inspecciona')
    parser.add_argument('--prepare-skills', action='store_true', help='Copiar skills al workspace externo sin sobrescribir')
    args = parser.parse_args()
    try:
        result = initialize(args.project, args.workspace, args.name, args.init)
        if args.prepare_skills:
            workspace = checked(args.workspace)
            if not workspace.is_dir():
                raise ValueError('Inicializa primero el workspace con --init')
            result += '\n' + prepare_project_skills(workspace, apply=args.init)
        print(result)
    except (OSError, ValueError) as error:
        parser.exit(1, f'ERROR: {error}\n')


if __name__ == '__main__':
    main()
