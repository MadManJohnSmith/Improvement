"""Networkless Linux Host envelope; explicit read inputs, fresh external state only."""
import argparse
import os
import math
from pathlib import Path
import re
import stat
import subprocess
import tempfile


FRAMEWORK = Path(__file__).resolve().parents[1]


def canonical(value):
    path = Path(value)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError(f"Expected existing absolute path without symlinks/traversal: {path}")
    return path


def launch(*, reads, state_parent, cwd, argv, timeout=45):
    """Mount authorized, non-secret inputs at /inputs/NAME; return state and exit code.

    Caller owns input trust and must keep source trees stable during launch.
    No inherited environment, network, host /proc, /dev, /run, /tmp or home.
    """
    parent = canonical(state_parent)
    if not parent.is_dir() or parent == FRAMEWORK or FRAMEWORK in parent.parents:
        raise ValueError("State must be external to the canonical framework")
    if not reads or not argv or not argv[0].startswith('/') or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Explicit reads, absolute executable and positive timeout required")
    sources = {}
    for name, value in reads.items():
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", name):
            raise ValueError("Invalid input name")
        path = canonical(value)
        if path in (Path('/'), Path('/home'), Path.home(), Path('/tmp'), Path('/run'), Path('/etc'), Path('/usr')):
            raise ValueError("Broad/private system roots are not read inputs")
        if path == parent or path in parent.parents or parent in path.parents:
            raise ValueError("Read inputs and state parent must not overlap")
        # Read-only mounts still expose Unix sockets; refuse them before launching.
        entries = [path]
        if path.is_dir():
            def unreadable(error):
                raise error
            for root, dirs, files in os.walk(path, followlinks=False, onerror=unreadable):
                entries.extend(Path(root) / item for item in dirs + files)
        if any(stat.S_ISSOCK(item.lstat().st_mode) for item in entries):
            raise ValueError("Read input contains a host socket")
        sources[name] = path
    cwd = canonical(cwd)
    if cwd not in sources.values() or not cwd.is_dir():
        raise ValueError("cwd must be an original explicit directory input")
    if cwd.parts[1] in {'inputs', 'state', 'usr', 'bin', 'lib', 'lib64', 'proc', 'dev', 'etc', 'run'}:
        raise ValueError("cwd overlaps a reserved sandbox root")
    state = Path(tempfile.mkdtemp(prefix='host-', dir=parent))
    for name in ('home', 'dsh-home', 'tmp', 'config', 'cache', 'data', 'run'):
        (state / name).mkdir(mode=0o700)
    command = ['/usr/bin/bwrap', '--unshare-all', '--die-with-parent', '--new-session',
               '--cap-drop', 'ALL', '--clearenv', '--ro-bind', '/usr', '/usr']
    for name in ('bin', 'lib', 'lib64'):
        path = Path('/') / name
        if path.is_symlink():
            command += ['--symlink', os.readlink(path), str(path)]
        elif path.is_dir():
            command += ['--ro-bind', str(path), str(path)]
    command += ['--proc', '/proc', '--dev', '/dev', '--dir', '/inputs',
                '--bind', str(state), '/state', '--bind', str(state / 'tmp'), '/tmp']
    for name, path in sources.items():
        command += ['--ro-bind', str(path), f'/inputs/{name}']
    # Only this input is also mounted at its original path; parents are empty scaffolding.
    command += ['--ro-bind', str(cwd), str(cwd)]
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/state/home', 'DSH_HOME': '/state/dsh-home',
           'TMPDIR': '/state/tmp', 'XDG_CONFIG_HOME': '/state/config',
           'XDG_CACHE_HOME': '/state/cache', 'XDG_DATA_HOME': '/state/data',
           'XDG_RUNTIME_DIR': '/state/run', 'LANG': 'C.UTF-8'}
    for key, value in env.items():
        command += ['--setenv', key, value]
    command += ['--remount-ro', '/', '--chdir', str(cwd), '--', *argv]
    # ponytail: trusted stable input trees, not hostile concurrent mount-source mutation.
    with (state / 'stdout.log').open('wb') as out, (state / 'stderr.log').open('wb') as err:
        try:
            result = subprocess.run(command, env={}, stdin=subprocess.DEVNULL,
                                    stdout=out, stderr=err, timeout=timeout, close_fds=True)
            code = result.returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            err.write(f'FAIL CLOSED: {error}\n'.encode())
            code = 124 if isinstance(error, subprocess.TimeoutExpired) else 126
    return state, code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--read', action='append', required=True, metavar='NAME=ABSOLUTE_PATH')
    parser.add_argument('--state-parent', required=True)
    parser.add_argument('--cwd', required=True)
    parser.add_argument('--timeout', type=float, default=45)
    parser.add_argument('argv', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        reads = dict(item.split('=', 1) for item in args.read)
        if len(reads) != len(args.read):
            raise ValueError('Duplicate read input')
        state, code = launch(reads=reads, state_parent=args.state_parent, cwd=args.cwd,
                             argv=args.argv[1:] if args.argv[:1] == ['--'] else args.argv,
                             timeout=args.timeout)
    except (ValueError, OSError) as error:
        parser.exit(2, f'FAIL CLOSED: {error}\n')
    print(f'state={state} exit_code={code}')
    return code if code >= 0 else 128 - code


if __name__ == '__main__':
    raise SystemExit(main())
