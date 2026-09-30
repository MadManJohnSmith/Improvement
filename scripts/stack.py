#!/usr/bin/env python3
"""Real-stack verification plan: the product's own entrypoints, tech-agnostic.

Resolves, from the product's lockfiles and manifests alone, a machine-readable
plan describing (a) which ecosystems the product is made of, (b) the product's
OWN test/lint entrypoints, (c) the exact provisioning steps that make them
runnable with everything materializing OUTSIDE the product, and (d) which
capabilities the current runtime already has. This module never executes an
install, never grants authority and never fabricates a result: a stack whose
capability is missing stays missing and the plan names the step. Verification
evidence for a candidate is the product's own entrypoint (or BLOCKED with the
named missing capability); a hand-written harness is investigation material,
never evidence.

The plan is written by the Host (install) to
`<workspace>/.dsh-managed/capability-plan.json` and read-only for the modes.
"""
import hashlib
import json
import os
import shutil
from pathlib import Path

VERSION = 1
PLAN_RELATIVE = ".dsh-managed/capability-plan.json"
MAX_PLAN_BYTES = 131_072

# Each stack: markers (lockfile first — the strongest signal), the product's
# own entrypoints, the provisioning steps and the capability binaries it needs.
# provision_outside=True means every artifact lands outside the product tree;
# otherwise the install path is the ecosystem convention and the plan reports
# whether the product ignores it (an unignored path would pollute the diff).
STACKS = {
    "python-django": {
        "markers": ("manage.py", "requirements.txt", "pyproject.toml", "Pipfile.lock", "poetry.lock", "uv.lock"),
        "verify": (["{python}", "manage.py", "test"], ["{python}", "-m", "django", "check"]),
        "provision_outside": True,
        "needs": ("python3",),
    },
    "python-generic": {
        "markers": ("pyproject.toml", "requirements.txt", "setup.cfg", "tox.ini", "pytest.ini"),
        "verify": (["{python}", "-m", "pytest", "-q"], ["{python}", "-m", "compileall", "-q", "."]),
        "provision_outside": True,
        "needs": ("python3",),
    },
    "node": {
        "markers": ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "package.json"),
        "verify": (["npm", "test"], ["npm", "run", "build"]),
        "provision_outside": False,
        "needs": ("node", "npm"),
    },
    "dart-flutter": {
        "markers": ("pubspec.lock", "pubspec.yaml"),
        "verify": (["flutter", "test"], ["flutter", "analyze"]),
        "provision_outside": False,
        "needs": ("flutter",),
    },
    "rust": {
        "markers": ("Cargo.lock", "Cargo.toml"),
        "verify": (["cargo", "test"], ["cargo", "clippy", "--", "-D", "warnings"]),
        "provision_outside": True,
        "needs": ("cargo",),
    },
    "go": {
        "markers": ("go.sum", "go.mod"),
        "verify": (["go", "test", "./..."], ["go", "vet", "./..."]),
        "provision_outside": True,
        "needs": ("go",),
    },
    "java-maven": {
        "markers": ("pom.xml",),
        "verify": (["mvn", "-q", "test"],),
        "provision_outside": True,
        "needs": ("mvn",),
    },
    "java-gradle": {
        "markers": ("gradlew", "build.gradle", "build.gradle.kts"),
        "verify": (["./gradlew", "test"],),
        "provision_outside": True,
        "needs": ("java",),
    },
    "php-composer": {
        "markers": ("composer.lock", "composer.json"),
        "verify": (["vendor/bin/phpunit"],),
        "provision_outside": False,
        "needs": ("php",),
    },
    "dotnet": {
        "markers": ("global.json", "*.sln", "*.csproj"),
        "verify": (["dotnet", "test"],),
        "provision_outside": True,
        "needs": ("dotnet",),
    },
    "ruby": {
        "markers": ("Gemfile.lock", "Gemfile"),
        "verify": (["bundle", "exec", "rspec"],),
        "provision_outside": True,
        "needs": ("bundle",),
    },
}

# The exact provision step per missing capability: what a mode (or operator) can
# do deterministically, always outside the product tree, and how the runtime can
# be pointed at it. Nothing here executes automatically.
PROVISION_HINTS = {
    "python3": {
        "what": "Intérprete Python 3 con el que materializar una venv fuera del producto",
        "check": "shutil.which('python3') o /usr/sbin/python3",
        "step": "python3 -m venv <workspace>/.stack/<stack>/venv && <venv>/bin/pip install -r <product>/requirements*.txt",
    },
    "node": {
        "what": "Node.js con npm (o pnpm/yarn según el lockfile del producto)",
        "check": "shutil.which('node') y shutil.which('npm')",
        "step": "instalar Node LTS fuera del producto; npm ci dentro del producto solo si node_modules está en .gitignore",
    },
    "npm": {
        "what": "npm (el lockfile del producto lo requiere)",
        "check": "shutil.which('npm')",
        "step": "instalar Node LTS fuera del producto; npm ci dentro del producto solo si node_modules está en .gitignore",
    },
    "flutter": {
        "what": "SDK de Flutter (incluye Dart; provee `flutter test` y `flutter analyze`)",
        "check": "shutil.which('flutter') o $HOME/.local/share/flutter/bin/flutter",
        "step": "git clone --depth 1 -b stable https://github.com/flutter/flutter.git ~/.local/share/flutter "
                "y anteponer ~/.local/share/flutter/bin al PATH (la primera corrida descarga el engine)",
    },
    "cargo": {
        "what": "Toolchain de Rust (cargo/rustc)",
        "check": "shutil.which('cargo')",
        "step": "rustup install stable (CARGO_TARGET_DIR fuera del producto para no ensuciar el diff)",
    },
    "go": {
        "what": "Toolchain de Go",
        "check": "shutil.which('go')",
        "step": "instalar Go estable; GOCACHE/GOMODCACHE fuera del producto",
    },
    "mvn": {
        "what": "Maven",
        "check": "shutil.which('mvn')",
        "step": "instalar Maven; ~/.m2 fuera del producto",
    },
    "php": {
        "what": "PHP con Composer",
        "check": "shutil.which('php')",
        "step": "instalar PHP; composer install dentro del producto solo si vendor/ está en .gitignore",
    },
    "java": {
        "what": "JDK 17+ (el wrapper de Gradle lo requiere; el proyecto puede fijar toolchain)",
        "check": "shutil.which('java')",
        "step": "instalar un JDK (Temurin 17/21) fuera del producto y anteponerlo al PATH",
    },
    "dotnet": {
        "what": "SDK de .NET",
        "check": "shutil.which('dotnet')",
        "step": "instalar el SDK .NET fuera del producto; NUGET_PACKAGES en el workspace",
    },
    "bundle": {
        "what": "Bundler de Ruby",
        "check": "shutil.which('bundle')",
        "step": "instalar Ruby+Bundler; vendor/bundle o BUNDLE_PATH fuera del producto",
    },
}


def _digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _safe_product(product):
    product = Path(product)
    if not product.is_dir() or product.is_symlink():
        raise ValueError(f'Producto inválido: {product}')
    resolved = product.resolve()
    if str(resolved) != str(product):
        # The plan is bound to the exact directory the Host validated; a
        # symlinked or relative product would make the recorded paths lie.
        raise ValueError('El producto debe ser su ruta real y absoluta')
    return resolved


def _gitignored(product, entries):
    """Whether the given install paths are ignored by the product's .gitignore."""
    ignore = product / '.gitignore'
    patterns = []
    if ignore.is_file():
        for line in ignore.read_text(encoding='utf-8', errors='replace').splitlines():
            line = line.split('#', 1)[0].strip()
            if line:
                patterns.append(line.rstrip('/'))
    return all(any(entry == pattern or entry.startswith(pattern.rstrip('*'))
                   for pattern in patterns) for entry in entries)


def _interpreter():
    return shutil.which('python3') or ('/usr/sbin/python3' if Path('/usr/sbin/python3').is_file() else None)


def detect(product):
    """Return the stacks the product is composed of, lockfile-first, deterministic."""
    product = _safe_product(product)
    found = []
    for stack, spec in STACKS.items():
        for marker in spec['markers']:
            root = _marker_root(product, marker)
            if root is not None:
                found.append({'stack': stack, 'markers': [marker], 'root': root})
                break
    return found


def _has_marker(product, marker):
    if '*' in marker:
        return any(Path(entry.name).match(marker) for entry in product.iterdir())
    return (product / marker).exists()


def _marker_root(product, marker):
    """Where a marker lives: the product root or one first-level subdirectory.

    Monorepos (backend/ + frontend/) are the norm in real projects, so a
    lockfile one level down still identifies the stack — the recorded root is
    where its entrypoint must run.
    """
    if _has_marker(product, marker):
        return ''
    for child in sorted(product.iterdir()):
        if not child.is_dir() or child.is_symlink() or child.name.startswith('.'):
            continue
        if any(child.glob(marker)):
            return child.name
    return None


def _flutter_ready(path):
    """A Flutter clone is not a usable capability until its engine cache exists."""
    root = Path(path).resolve().parent.parent
    return (root / 'bin' / 'cache' / 'dart-sdk').is_dir()


DECLARATION_FILE = "improvement-verification.json"


def declared(product):
    """Explicit, owner-written entrypoints for projects without a manifest.

    Detection never guesses: a project may declare its own stacks in
    `<product>/improvement-verification.json`; a declaration for a root that
    was auto-detected wins, because it is the owner speaking explicitly.
    """
    path = Path(product) / DECLARATION_FILE
    if not path.is_file() or path.stat().st_size > 32768:
        return []
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('version') != VERSION:
        raise ValueError('Declaración de verificación inválida')
    entries = value.get('stacks')
    if not isinstance(entries, list) or not entries:
        raise ValueError('Declaración de verificación sin stacks')
    resolved = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('Stack declarado inválido')
        root = entry.get('root', '')
        verify = entry.get('verify')
        lint = entry.get('lint')
        if not isinstance(root, str) or '/' in root or root.startswith('.'):
            raise ValueError('Raíz declarada inválida')
        if (not isinstance(verify, list) or not verify
                or any(not isinstance(part, str) or not part for part in verify)):
            raise ValueError('Comando de verificación declarado inválido')
        if lint is not None and (not isinstance(lint, list) or not lint
                                 or any(not isinstance(part, str) or not part for part in lint)):
            raise ValueError('Comando de lint declarado inválido')
        capabilities = entry.get('capabilities') or []
        if not isinstance(capabilities, list) or any(
                not isinstance(item, str) or not item for item in capabilities):
            raise ValueError('Capacidades declaradas inválidas')
        resolved.append({
            'stack': entry.get('stack', 'declared'),
            'declared': True,
            'markers': [DECLARATION_FILE],
            'root': root,
            'verify_command': verify,
            'lint_command': lint,
            'declared_capabilities': capabilities,
        })
    return resolved


def _capability_status(needs, *, path_env=None, home=None):
    status = []
    interpreter = _interpreter() if path_env is None else (
        shutil.which('python3', path=path_env) or _interpreter() or 'python3')
    home = home or Path.home()
    for binary in needs:
        resolved = (shutil.which(binary, path=path_env) if path_env is not None
                    else shutil.which(binary))
        if binary == 'python3' and not resolved:
            resolved = interpreter
        if resolved and not (binary == 'flutter' and not _flutter_ready(resolved)):
            status.append({'capability': binary, 'status': 'available', 'path': resolved})
            continue
        hint = PROVISION_HINTS.get(binary, {'what': binary, 'check': 'PATH', 'step': 'instalar ' + binary})
        candidate = home / '.local/share/flutter/bin' / binary
        if candidate.is_file() and not (binary == 'flutter' and not _flutter_ready(candidate)):
            status.append({'capability': binary, 'status': 'available', 'path': str(candidate)})
            continue
        status.append({
            'capability': binary,
            'status': 'missing',
            'what': hint['what'],
            'check': hint['check'],
            'provision_step': hint['step'],
        })
    return status


def _materialized_python(workspace, stack, interpreter):
    """A venv the plan itself asked for outranks the system interpreter.

    Once the operator or a mode materialized `<workspace>/.stack/<stack>/venv`
    exactly as the plan's provision step says, the entrypoint resolves to it:
    that is the difference between a plan that names a command and a project
    whose real suite can actually run.
    """
    candidate = Path(workspace) / '.stack' / stack / 'venv' / 'bin' / 'python'
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    return interpreter


def plan(product, *, workspace=None, env=None):
    """Build the real-stack verification plan for one product.

    The plan is data only: stacks detected, the product's own entrypoints with
    `{python}` resolved, provisioning steps and the per-capability status of
    this runtime. No step is executed here.
    """
    product = _safe_product(product)
    env = dict(os.environ if env is None else env)
    interpreter = shutil.which('python3', path=env.get('PATH')) or _interpreter() or 'python3'
    home = Path(env.get('HOME', str(Path.home())))
    flutter_home = home / '.local/share/flutter/bin'
    path = env.get('PATH', '')
    if flutter_home.is_dir() and str(flutter_home) not in path:
        env['PATH'] = f"{flutter_home}:{path}"
        interpreter = shutil.which('python3', path=env['PATH']) or interpreter
    workspace = Path(workspace) if workspace else product.parent
    stacks = []
    seen_roots = set()
    entries = detect(product)
    for declaration in declared(product):
        # An explicit declaration for a root replaces whatever was detected
        # there: the owner naming the entrypoint outranks a marker file.
        entries = [item for item in entries if item['root'] != declaration['root']]
        entries.append(declaration)
    for entry in entries:
        if entry['root'] in seen_roots:
            # One ecosystem per subdirectory: the most specific stack (STACKS
            # order) already claimed it, a second manifest cannot add evidence.
            continue
        seen_roots.add(entry['root'])
        if entry.get('declared'):
            stack_plan = {
                'stack': entry['stack'],
                'declared': True,
                'root': entry['root'],
                'markers': entry['markers'],
                'verify_command': [part.replace('{python}', interpreter)
                                   for part in entry['verify_command']],
                'verify_cwd': entry['root'] or '.',
                'lint_command': entry['lint_command'],
                'provision_outside_product': True,
                'capabilities': _capability_status(
                    entry['declared_capabilities'] or ('python3',),
                    path_env=env.get('PATH'), home=home),
            }
            stack_plan['verification_ready'] = all(
                capability['status'] == 'available'
                for capability in stack_plan['capabilities'])
            stacks.append(stack_plan)
            continue
        spec = STACKS[entry['stack']]
        effective_python = _materialized_python(workspace, entry['stack'], interpreter)
        verify = [[part.replace('{python}', effective_python) for part in command]
                  for command in spec['verify']]
        stack_plan = {
            'stack': entry['stack'],
            'root': entry['root'],
            'markers': entry['markers'],
            'verify_command': verify[0],
            'verify_cwd': entry['root'] or '.',
            'lint_command': verify[1] if len(verify) > 1 else None,
            'provision_outside_product': spec['provision_outside'],
            'capabilities': _capability_status(spec['needs'], path_env=env.get('PATH'),
                                               home=home),
        }
        if not spec['provision_outside']:
            in_product = {'node': ['node_modules'], 'dart-flutter': ['.dart_tool'],
                          'php-composer': ['vendor']}[entry['stack']]
            stack_plan['in_product_install'] = in_product
            stack_plan['in_product_install_gitignored'] = _gitignored(product, in_product)
        stack_plan['verification_ready'] = all(
            capability['status'] == 'available' for capability in stack_plan['capabilities'])
        stacks.append(stack_plan)
    result = {
        'version': VERSION,
        'product': str(product),
        'workspace': str(workspace),
        'stacks': stacks,
        'evidence': 'product-own-entrypoint-only',
        'stubs': 'investigation-material-never-verification-evidence',
        'missing_capability': 'BLOCKED-naming-capability-and-provision-step',
    }
    result['plan_sha256'] = _digest(json.dumps(
        {k: v for k, v in result.items()}, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    return result


def write(plan_value, workspace):
    """Write the plan under the managed workspace; refuse drift or oversized output."""
    workspace = Path(workspace)
    path = workspace / PLAN_RELATIVE
    encoded = json.dumps(plan_value, ensure_ascii=False, sort_keys=True, indent=1) + '\n'
    if len(encoded.encode('utf-8')) > MAX_PLAN_BYTES:
        raise ValueError('Capability plan excesivo')
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(encoded, encoding='utf-8')
    os.replace(temporary, path)
    return path


def load(workspace):
    """Read a previously written plan; fail closed on drift."""
    path = Path(workspace) / PLAN_RELATIVE
    if not path.is_file() or path.stat().st_size > MAX_PLAN_BYTES:
        raise ValueError('Capability plan ausente')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('version') != VERSION:
        raise ValueError('Capability plan inválido')
    expected = _digest(json.dumps(
        {k: v for k, v in value.items() if k != 'plan_sha256'},
        ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    if value.get('plan_sha256') != expected:
        raise ValueError('Capability plan alterado')
    return value


def _command_text(parts):
    """Canonical command field stored in verification-results.jsonl."""
    return json.dumps(parts, ensure_ascii=False, separators=(',', ':'))


def allowed_verification_commands(value):
    """Canonical command strings allowed as product verification evidence."""
    allowed = set()
    for stack in value['stacks']:
        allowed.add(_command_text(stack['verify_command']))
        if stack.get('lint_command'):
            allowed.add(_command_text(stack['lint_command']))
    return frozenset(allowed)


def validate_verification_results(value, records):
    """Mechanically reject stub evidence and false PASS/FAIL on missing stacks.

    Returns the records unchanged after validation. It does not execute them;
    execution is the mode's job. The Host can therefore enforce that every
    command is one of the exact product entrypoints it resolved, and that a
    stack with missing capabilities cannot yield PASS or FAIL.
    """
    if not isinstance(records, list):
        raise ValueError('Resultados de verificación inválidos')
    by_command = {}
    for entry in value['stacks']:
        ready = bool(entry['verification_ready'])
        by_command[_command_text(entry['verify_command'])] = ready
        if entry.get('lint_command'):
            by_command[_command_text(entry['lint_command'])] = ready
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f'Resultado {index} inválido')
        command = record.get('command')
        result = record.get('result')
        if command not in by_command:
            raise ValueError(f'Resultado {index} usa comando ajeno al stack real')
        if result not in {'PASS', 'FAIL', 'BLOCKED'}:
            raise ValueError(f'Resultado {index} tiene veredicto inválido')
        if not by_command[command] and result != 'BLOCKED':
            raise ValueError(
                f'Resultado {index} debe ser BLOCKED: falta capacidad del stack')
    return records


def summary(value):
    """Compact, operator-facing digest: per stack, ready or the named blocker."""
    lines = []
    for stack in value['stacks']:
        if stack['verification_ready']:
            lines.append(f"{stack['stack']}: listo ({' '.join(stack['verify_command'])})")
            continue
        missing = [c['capability'] for c in stack['capabilities'] if c['status'] == 'missing']
        lines.append(f"{stack['stack']}: falta {', '.join(missing) or 'entrypoint'}")
    return lines
