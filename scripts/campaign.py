#!/usr/bin/env python3
"""Gate de campaña: deriva el veredicto de verificación real (U6b).

Es un gate más del ejecutor de workflow, no un subcomando nuevo: el run dir y
el journal siguen siendo del Host, y este proceso solo lee el plan de
capacidades, la candidata y el ledger de verificación para decir PASS, FAIL o
BLOCKED con nombres.

Reglas que este archivo no rompe:

- NUNCA escribe en `mode-state/verification-results.jsonl`. Ese ledger lo escribe
  el plugin desde la sesión y lo poda la instalación; un gate que lo tocara
  fabricaría la evidencia que después va a leer.
- SÍ registra episodios en `mode-state/episodes.jsonl` cuando el veredicto
  derivado es PASS: el registro es Host-owned (`episodes.py`), y una campaña
  que cierra una reparación verificada sin dejar episodio deja el ciclo de
  memoria vacío — el auditor siguiente repite el hallazgo que la candidata
  acaba de cerrar. La firma es la receta única (`episodes.signature`, la que
  el plugin consume); el hallazgo sin identidad se nombra en el veredicto en
  lugar de desaparecer, y un registro que falla convierte el PASS en
  BLOCKED con la causa citable: la fase nunca miente.
- BLOCKED significa "falta una pieza": una capability ausente o un plan
  ilegible. FAIL significa "hay evidencia y no dice PASS". Nunca PASS por no
  tener nada que mirar.
- SÍ promueve DIRTY→PATCH_READY cuando el veredicto derivado es PASS sobre la
  candidata registrada: los comandos Host de reparación solo escriben
  PROVISIONED/DIRTY, y sin la promoción una reparación verificada quedaba
  DIRTY para siempre (issue #36). La escritura usa el registro de candidata
  Host; falla cerrada a BLOCKED, nunca PASS con promoción perdida.
- El veredicto se escribe en la raíz de evidencia, que es donde lo lee el
  `if_veredicto` del paso de reparación; el detalle de la auditoría y de cada
  reparación viven bajo `evidence/campana/`.

Se llama `campaign` y no `workflow` a propósito: `workflow` es un término
prohibido en la composición de plugins (`composition_contract`).
"""
import argparse
import json
import os
import secrets
import stat
import subprocess
import sys

from pathlib import Path

import audit
import capabilities
import episodes
import state_reconcile
import stack as capability_plan

from mode_lifecycle import BYTE_LIMITS

MARKER = '__IMPROVEMENT_GATE__'
EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_BLOCKED = EXIT_FAIL  # veredicto con artefacto: el runner solo conoce 0/1
STATE_DIRNAME = 'mode-state'
MANAGED_DIRNAME = '.dsh-managed'
CAPABILITY_IMPLEMENT_NAME = 'capability-implement.json'
EVIDENCE_DIRNAME = 'evidence'
VERDICT_NAME = 'veredicto.json'
EVIDENCE_NAME = 'campana'
LEDGER_NAME = 'verification-results.jsonl'
WORK_ITEMS_NAME = 'work-items.json'
MANIFEST_RELATIVE = '.dsh-managed/campaign/manifest.json'


class CampaignBlocked(Exception):
    """Falta una pieza para pronunciarse; el gate sale con BLOCKED."""


def exclusion_ceiling(workspace):
    """Techo de exclusión del manifiesto de campaña; audit.py lo hace cumplir."""
    try:
        return audit.campaign_ceiling(Path(workspace))
    except ValueError as error:
        raise CampaignBlocked('manifiesto de campaña: ' + str(error)) from error


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def _read_bounded(path, limit):
    if path.is_symlink() or not path.is_file():
        return None
    try:
        data = path.read_bytes()
    except OSError as error:
        raise CampaignBlocked('ilegible %s: %s' % (path.name, error.strerror or error))
    if len(data) > limit:
        raise CampaignBlocked('%s excede el límite gestionado' % path.name)
    try:
        return json.loads(data.decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as error:
        raise CampaignBlocked('%s no es JSON: %s' % (path.name, error))


def _ledger(state):
    """Registros de verificación del ledger; vacío si el ledger no existe.

    Solo lectura: quien escribe ese fichero es el plugin, desde la sesión."""
    path = state / LEDGER_NAME
    if path.is_symlink() or not path.is_file():
        return []
    try:
        data = path.read_bytes()
    except OSError as error:
        raise CampaignBlocked('ledger ilegible: ' + str(error.strerror or error))
    if len(data) > BYTE_LIMITS[LEDGER_NAME]:
        raise CampaignBlocked('ledger por encima del límite gestionado')
    records = []
    for number, line in enumerate(data.decode('utf-8', 'replace').splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except ValueError as error:
            raise CampaignBlocked('%s:%d no es JSON: %s' % (LEDGER_NAME, number, error))
    return records


def _candidate(state):
    work_items = _read_bounded(state / WORK_ITEMS_NAME,
                               BYTE_LIMITS[WORK_ITEMS_NAME]) or {}
    if not isinstance(work_items, dict):
        raise CampaignBlocked(WORK_ITEMS_NAME + ' no tiene la forma del contrato')
    candidate = work_items.get('candidate')
    return candidate if isinstance(candidate, dict) else None


def _missing_capabilities(value):
    """Stacks que no pueden verificarse y la capability concreta que falta."""
    gaps = []
    for entry in value['stacks']:
        if entry.get('verification_ready'):
            continue
        missing = sorted(capability['capability'] for capability
                         in entry.get('capabilities', [])
                         if capability.get('status') != 'available')
        gaps.append({'stack': entry.get('stack'), 'missing': missing})
    return gaps


def write_verdict(workspace, payload):
    """Escribe sin seguir enlaces, incluso si evidence cambia durante la escritura."""
    workspace_fd = os.open(workspace, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            os.mkdir(EVIDENCE_DIRNAME, mode=0o700, dir_fd=workspace_fd)
        except FileExistsError:
            pass
        evidence_fd = os.open(EVIDENCE_DIRNAME, os.O_RDONLY | os.O_DIRECTORY |
                              os.O_NOFOLLOW, dir_fd=workspace_fd)
        try:
            for subdir in (None, EVIDENCE_NAME):
                if subdir:
                    try:
                        os.mkdir(subdir, mode=0o700, dir_fd=evidence_fd)
                    except FileExistsError:
                        pass
                    target_fd = os.open(subdir, os.O_RDONLY | os.O_DIRECTORY |
                                        os.O_NOFOLLOW, dir_fd=evidence_fd)
                else:
                    target_fd = os.dup(evidence_fd)
                try:
                    temporary = '.veredicto-' + secrets.token_hex(12)
                    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                 os.O_NOFOLLOW, 0o600, dir_fd=target_fd)
                    try:
                        with os.fdopen(fd, 'wb') as stream:
                            stream.write(_canonical(payload) + b'\n')
                            stream.flush()
                            os.fsync(stream.fileno())
                        try:
                            current = os.stat(VERDICT_NAME, dir_fd=target_fd,
                                              follow_symlinks=False)
                        except FileNotFoundError:
                            current = None
                        if current is not None and not stat.S_ISREG(current.st_mode):
                            raise CampaignBlocked('veredicto no es un fichero regular')
                        os.replace(temporary, VERDICT_NAME, src_dir_fd=target_fd,
                                   dst_dir_fd=target_fd)
                    finally:
                        try:
                            os.unlink(temporary, dir_fd=target_fd)
                        except FileNotFoundError:
                            pass
                finally:
                    os.close(target_fd)
        finally:
            os.close(evidence_fd)
    finally:
        os.close(workspace_fd)
    return workspace / EVIDENCE_DIRNAME / VERDICT_NAME


def _verdict_payload(fase, verdict, derived, candidate, gaps=None, reason=None):
    counts = derived.get('counts', {'PASS': 0, 'BLOCKED': 0, 'FAIL': 0, 'PARTIAL': 0})
    unverified = derived.get('unverified', [])
    payload = {
        'fase': fase,
        'verdict': verdict,
        'counts': counts,
        'partial': [item['finding_id'] for item in unverified
                    if item.get('verdict') == 'PARTIAL'],
        'unverified': unverified,
        'records': derived.get('records', 0),
        'usable': derived.get('usable', 0),
        'candidate_head': (candidate or {}).get('head'),
        'candidate_diff_digest': (candidate or {}).get('candidate_diff_digest'),
    }
    if gaps:
        payload['missing_capabilities'] = gaps
    if reason:
        payload['reason'] = reason
    return payload


def _product_head(product):
    """HEAD del producto canónico (la base limpia de la candidata implement)."""
    out = subprocess.run(["git", "-C", str(product), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=False)
    if out.returncode:
        raise CampaignBlocked("el producto no tiene HEAD de git: " + out.stderr[:200])
    return out.stdout.strip()


def _atomic_json_write(directory, name, value):
    """Escribe JSON en <directory>/<name> sin seguir enlaces, atómicamente.

    El mismo disciplinamiento que write_verdict aplica a su veredicto:
    temporal exclusivo + fsync + os.replace con O_NOFOLLOW en ambos extremos.
    """
    directory = Path(directory)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    dir_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        temporary = "." + name + "-" + secrets.token_hex(12)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     os.O_NOFOLLOW, 0o600, dir_fd=dir_fd)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload.encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            try:
                current = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            except FileNotFoundError:
                current = None
            if current is not None and not stat.S_ISREG(current.st_mode):
                raise CampaignBlocked(name + " no es un fichero regular")
            os.replace(temporary, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        except BaseException:
            try:
                os.unlink(temporary, dir_fd=dir_fd)
            except OSError:
                pass
            raise
    finally:
        os.close(dir_fd)


def _register_candidate(workspace, candidate):
    """Registra/actualiza la candidata en work-items.json, sin seguir enlaces."""
    _atomic_json_write(Path(workspace) / STATE_DIRNAME, WORK_ITEMS_NAME,
                       {**(_read_bounded(Path(workspace) / STATE_DIRNAME / WORK_ITEMS_NAME,
                                         BYTE_LIMITS[WORK_ITEMS_NAME]) or {}),
                         "candidate": candidate})


def provision_implement(workspace, request):
    """Aprovisiona la candidata kind=implement (solo el Host) y la registra.

    La candidata la provisiona el Host, ligada a la petición exacta y a la base
    limpia del producto (mode_lifecycle.provision_implementation); el registro
    en work-items.json es lo que la sesión del implementer lee para verificar
    su base y trabajar dentro de la sombra. El registro respeta el schema de
    estado (`state_schema()`): la identidad de la candidata implement viaja en
    `finding_ids_digest`, su estado inicial es `PROVISIONED`.
    """
    import mode_lifecycle
    try:
        plan = capability_plan.load(workspace)
        product = Path(plan["product"])
        base = _product_head(product)
        receipt = mode_lifecycle.provision_implementation(
            Path(product), Path(workspace), request, declared_base=base)
    except (ValueError, OSError) as error:
        raise CampaignBlocked("aprovisionamiento de implement: " + str(error))
    receipt_path = Path(receipt["path"])
    # El schema de estado guarda la ruta RELATIVA a la raíz de
    # sesión (^[^/]...): el convenio que la variante repair usó en
    # la campaña completada ("workspace/candidates/...").
    try:
        relative = receipt_path.relative_to(Path(workspace).parent)
    except ValueError:
        raise CampaignBlocked(
            "la candidata provisionada no cuelga de la raíz de sesión: "
            + str(receipt_path))
    candidate = {
        "base_revision": receipt["base_revision"],
        # La identidad de la candidata implement: implementation_identity(base,
        # petición). El schema de estado nombra el campo por la variante repair;
        # es el mismo digest de enlace de 64 hex para ambas variantes.
        "finding_ids_digest": receipt["request_sha256"],
        "path": relative.as_posix(),
        "branch": "candidate",
        "head": receipt["base_revision"],
        "status": "PROVISIONED",
        "changed_paths": [],
    }
    _register_candidate(workspace, candidate)
    # La capability que autoriza este turno: sesión = la candidata provisionada
    # (su path es único por petición+base), raíces acotadas a lo que el modo
    # puede tocar. El fingerprint idéntico es lo que permite el reuso en la
    # reanudación — el mismo mecanismo que el exact-resume de los runs.
    framework = Path(__file__).resolve().parents[1]
    shadow_absolute = str((Path(workspace).parent / candidate["path"]).resolve())
    capability = {
        "version": 1,
        "capability_id": "implement-" + candidate["finding_ids_digest"][:16],
        "session_id": candidate["path"],
        "project": str(product),
        "executor": "campaign-runner",
        "roots": {"product_read": [str(product)],
                  "framework_execute": [str(framework)],
                  "workspace_write": [shadow_absolute,
                                      str(Path(workspace) / STATE_DIRNAME),
                                      str(Path(workspace) / EVIDENCE_DIRNAME)]},
        "scope": ["implementar"],
    }
    _atomic_json_write(Path(workspace) / MANAGED_DIRNAME,
                       CAPABILITY_IMPLEMENT_NAME, capability)
    return EXIT_PASS, {"fase": "provision-implement", "verdict": "PASS",
                       "candidate": candidate,
                       "capability_fingerprint":
                           capabilities.fingerprint(capability)}


def verify_implement(workspace, request):
    """Aceptación de comportamiento del cambio, sobre la candidata en su sombra.

    mode_lifecycle.verify_implementation valida la identidad (petición + base),
    revalida la frontera de aprovisionamiento, ejecuta el caso de aceptación con
    el entrypoint del producto dentro de la sombra y mide el diff. PASS sale por
    exit 0; FAIL y BLOCKED por exit 1 con el veredicto en el payload.
    """
    import mode_lifecycle
    try:
        plan = capability_plan.load(workspace)
    except (ValueError, OSError) as error:
        raise CampaignBlocked("plan de capacidades: " + str(error))
    product = Path(plan["product"])
    candidate = _candidate(workspace / STATE_DIRNAME) or {}
    base = _product_head(product)
    # La ruta registrada es relativa a la raíz de sesión (workspace.parent).
    stored = candidate.get("path")
    session_root = Path(workspace).parent
    receipt_path = ((session_root / stored).resolve() if stored
                    else Path(workspace) / "implement" / "candidates")
    receipt = {"path": str(receipt_path),
               "base_revision": candidate.get("base_revision") or base,
               "request_sha256": mode_lifecycle.implementation_identity(
                   base, request)}
    # La autoridad del turno se valida antes de aceptar comportamiento: una
    # capability de otra sesión/proyecto/ejecutor, con raíces fuera de la
    # candidata o ausente, bloquea la aceptación (la emisión fue en el
    # provision del propio run; el fingerprint de reuso es el del exact-resume).
    shadow_absolute = str(receipt_path)
    try:
        capabilities.validate(
            Path(workspace) / MANAGED_DIRNAME / CAPABILITY_IMPLEMENT_NAME,
            session_id=candidate.get("path") or str(receipt_path),
            project=str(product), executor="campaign-runner",
            roots={"workspace_write": [shadow_absolute,
                                       str(Path(workspace) / STATE_DIRNAME),
                                       str(Path(workspace) / EVIDENCE_DIRNAME)]})
    except (ValueError, OSError) as error:
        return EXIT_FAIL, {"fase": "verificar-implement", "verdict": "BLOCKED",
                           "reason": "capability: " + str(error)}
    ready = [entry for entry in plan.get("stacks", [])
             if entry.get("verification_ready")]
    if not ready:
        return EXIT_FAIL, {"fase": "verificar-implement", "verdict": "BLOCKED",
                           "reason": "sin stack con verificación disponible",
                           "request": request[:200]}
    try:
        verdict = mode_lifecycle.verify_implementation(
            product, Path(workspace), request, receipt,
            acceptance_command=list(ready[0]["verify_command"]))
    except ValueError as error:
        raise CampaignBlocked("verificación de implementación: " + str(error))
    code = EXIT_PASS if verdict.get("verdict") == "PASS" else EXIT_FAIL
    return code, {"fase": "verificar-implement", **verdict}


def _episode_unit(candidate):
    """La unidad que cierra el hallazgo: la candidata verificada de campaña.

    Mismo rol que el `unit_id` del cierre E2 del Host: nombra a quien cerró,
    y `state_reconcile.memory` valida las citas `prior_episode` contra las
    unidades que el ledger realmente conserva."""
    return 'campana.' + candidate['head'][:16]


def _register_closed_episodes(workspace, fase, candidate):
    """Registra el episodio de cada hallazgo que la candidata verificada cerró.

    El ciclo de memoria quedaba vacío en campaña: `episodes.record` solo tenía
    un llamador (el cierre E2 de misiones del Host, `host_controller.
    _record_episode`), así que una campaña con reparaciones verificadas dejaba
    `memory: {signatures: 0, episodes: 0}` en `bootstrap.py state` y el
    auditor siguiente volvía a presentar el hallazgo que la candidata acaba de
    cerrar. Este es el puente mínimo por la maquinaria existente: el mismo
    contrato del payload `episode`, la misma receta de firma única y la misma
    superficie (`mode-state/episodes.jsonl`) que el lector del plugin consulta.

    Un hallazgo sin registro en `findings.jsonl` o sin ancla no tiene firma
    posible: no se inventa identidad, se nombra en el veredicto. Un registro
    que falla no se traga — el llamador convierte el PASS en retención con la
    causa citable. Y una fase que re-deriva el mismo PASS (reintento del gate,
    verificar-post y verificar-final sobre la misma candidata) no duplica: el
    par (firma, unidad) ya en el ledger basta para no escribir de nuevo.
    """
    usable = [record for record in _ledger(workspace / STATE_DIRNAME)
              if isinstance(record.get('finding_id'), str)
              and isinstance(record.get('candidate_head'), str)
              and record.get('result') in ('PASS', 'BLOCKED', 'FAIL')]
    derived = capability_plan.derived_verdicts(usable)
    findings = state_reconcile.latest_findings(workspace / STATE_DIRNAME)
    unit = _episode_unit(candidate)
    registered, unfiled = [], []
    for (finding_id, head), group in derived.items():
        if group['verdict'] != 'PASS' or head != candidate.get('head'):
            continue
        evidence = (findings.get(finding_id) or {}).get('evidence')
        if not isinstance(evidence, dict) or not isinstance(evidence.get('path'), str) \
                or not isinstance(evidence.get('excerpt'), str):
            unfiled.append(finding_id)
            continue
        fingerprint = episodes.signature(evidence['path'], evidence['excerpt'],
                                         evidence.get('fingerprint'))
        if any(entry.get('unit') == unit
               for entry in episodes.recall(workspace, fingerprint=fingerprint)):
            continue
        episodes.record(
            workspace, unit=unit, path=evidence['path'],
            excerpt=evidence['excerpt'], fingerprint=evidence.get('fingerprint'),
            verdict='PASS',
            evidence='evidence/veredicto.json fase=%s head=%s' % (fase, head),
            repair='candidata %s diff %s' % (candidate.get('path'),
                                             candidate.get('candidate_diff_digest')))
        registered.append(finding_id)
    return registered, unfiled


def verification_verdict(workspace, fase):
    """PASS / FAIL / BLOCKED desde la evidencia real, más el código de salida."""
    try:
        value = capability_plan.load(workspace)
    except ValueError as error:
        raise CampaignBlocked('plan de capacidades: ' + str(error))
    except OSError as error:
        raise CampaignBlocked('plan de capacidades ilegible: ' + str(error))
    state = workspace / STATE_DIRNAME
    candidate = _candidate(state)
    records = _ledger(state)
    # La readiness va antes que la validación: un stack sin capability no puede
    # producir PASS ni FAIL, y el ledger que afirme lo contrario se descarta
    # como BLOCKED, no como FAIL.
    gaps = _missing_capabilities(value)
    derived = state_reconcile.verification_verdicts(state)
    if gaps:
        return EXIT_BLOCKED, _verdict_payload(fase, 'BLOCKED', derived, candidate, gaps)
    if not candidate or not candidate.get('head') or not candidate.get('candidate_diff_digest'):
        return EXIT_BLOCKED, _verdict_payload(
            fase, 'BLOCKED', derived, candidate,
            reason='candidato vigente sin identidad verificable en work-items.json')
    if records:
        try:
            capability_plan.validate_verification_results(value, records, candidate)
        except ValueError as error:
            return EXIT_FAIL, _verdict_payload(fase, 'FAIL', derived, candidate,
                                              reason=str(error))
    counts = derived['counts']
    unverified = derived['unverified']
    if derived['usable'] == 0:
        return EXIT_BLOCKED, _verdict_payload(
            fase, 'BLOCKED', derived, candidate,
            reason='sin registros de verificación utilizables')
    if unverified or counts['FAIL'] or counts['BLOCKED'] or counts['PARTIAL']:
        return EXIT_FAIL, _verdict_payload(fase, 'FAIL', derived, candidate)
    # El PASS solo se emite si la memoria recoge lo que la candidata cerró:
    # un registro que falla no es un PASS con episodio perdido en silencio.
    # FAIL diría "hay evidencia y no dice PASS", que es falso aquí; BLOCKED
    # es exactamente "falta una pieza", y la pieza que falta se nombra.
    try:
        registered, unfiled = _register_closed_episodes(workspace, fase, candidate)
    except (OSError, ValueError, TypeError, KeyError) as error:
        return EXIT_BLOCKED, _verdict_payload(
            fase, 'BLOCKED', derived, candidate,
            reason='episodio de memoria no registrado: ' + str(error))
    # Promoción DIRTY→PATCH_READY (issue #36): los comandos Host de reparación
    # solo saben escribir PROVISIONED/DIRTY, así que sin esta promoción una
    # candidata verificada quedaba DIRTY para siempre y --integrate (que exige
    # PATCH_READY) era inalcanzable. PATCH_READY pasa a significar exactamente
    # "verificada por este gate y lista para integración". La escritura es el
    # mismo contrato Host que el registro en provision-implement
    # (_register_candidate, escritura atómica sin enlaces); si falla, el
    # veredicto no miente: BLOCKED citable, nunca un PASS con la promoción
    # perdida en silencio. Re-PASS sobre la misma candidata es idempotente:
    # en PATCH_READY no hay nada que promover.
    promoted = False
    if candidate.get('status') == 'DIRTY':
        try:
            _register_candidate(workspace, dict(candidate, status='PATCH_READY'))
        except (CampaignBlocked, OSError) as error:
            return EXIT_BLOCKED, _verdict_payload(
                fase, 'BLOCKED', derived, candidate,
                reason='promoción PATCH_READY no registrada: ' + str(error))
        promoted = True
    payload = _verdict_payload(fase, 'PASS', derived, candidate)
    if promoted:
        payload['candidate_status_promoted'] = 'PATCH_READY'
    if registered:
        payload['episodes_registered'] = registered
    if unfiled:
        payload['episodes_unfiled'] = unfiled
    return EXIT_PASS, payload


def preflight(workspace):
    """Comprueba, antes de gastar una auditoría, que el runtime puede hacerla."""
    manifest = _read_bounded(workspace / MANIFEST_RELATIVE, capability_plan.MAX_PLAN_BYTES)
    if not isinstance(manifest, dict):
        raise CampaignBlocked('manifiesto de campaña ausente: ' + MANIFEST_RELATIVE)
    preset_ids = manifest.get('preset_ids')
    if not isinstance(preset_ids, list) or not preset_ids:
        raise CampaignBlocked('el manifiesto no declara preset_ids')
    ceiling = exclusion_ceiling(workspace)
    try:
        import creator_client
        import workflow
    except ImportError as error:
        raise CampaignBlocked('cliente DSH no disponible: ' + str(error))
    client, reason = creator_client.acquire_dsh_client(launch=False)
    if client is None:
        raise CampaignBlocked('cliente DSH no disponible: ' + str(reason))
    for preset_id in preset_ids:
        detail = workflow._verify_preset(client, preset_id)
        if detail is not None:
            raise CampaignBlocked('preset no verificado %s: %s' % (preset_id, detail))
    try:
        value = capability_plan.load(workspace)
        stacks = value['stacks']
        gaps = _missing_capabilities(value)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise CampaignBlocked('plan de capacidades: ' + str(error)) from error
    if not stacks:
        raise CampaignBlocked('plan de capacidades sin stacks verificables')
    if gaps:
        raise CampaignBlocked('stacks no verificables: ' + json.dumps(gaps, ensure_ascii=False))
    return EXIT_PASS, {'fase': 'preflight', 'verdict': 'PASS', 'preset_ids': preset_ids,
                       'exclusion_ceiling': ceiling.isoformat() if ceiling else None}


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='campaign.py',
        description='Gate de campaña: veredicto de verificación real del producto.')
    parser.add_argument('--fase', required=True,
                        help='preflight, una ronda (pre/post/ronda-N), final o cerrar')
    parser.add_argument('--workspace', default=None,
                        help='workspace del producto (por defecto, el cwd del gate)')
    parser.add_argument('--request', default=None,
                        help='petición de cambio para provision-implement y '
                             'verificar-implement')
    arguments = parser.parse_args(argv)
    workspace = Path(arguments.workspace or Path.cwd()).resolve()
    if not workspace.is_dir():
        _emit({'fase': arguments.fase, 'verdict': 'BLOCKED',
               'reason': 'workspace inexistente: ' + str(workspace)})
        return EXIT_BLOCKED
    try:
        if arguments.fase == 'preflight':
            code, payload = preflight(workspace)
        elif arguments.fase == 'cerrar':
            code, payload = EXIT_PASS, {'fase': 'cerrar', 'verdict': 'PASS'}
        elif arguments.fase == 'provision-implement':
            if not arguments.request:
                raise CampaignBlocked(
                    'provision-implement exige --request con la petición de cambio')
            code, payload = provision_implement(workspace, arguments.request)
        elif arguments.fase == 'verificar-implement':
            if not arguments.request:
                raise CampaignBlocked(
                    'verificar-implement exige --request con la petición de cambio')
            code, payload = verify_implement(workspace, arguments.request)
        else:
            code, payload = verification_verdict(workspace, arguments.fase)
    except CampaignBlocked as blocked:
        code = EXIT_BLOCKED
        payload = {'fase': arguments.fase, 'verdict': 'BLOCKED', 'reason': str(blocked)}
    if arguments.fase not in ('preflight', 'cerrar'):
        # La evidencia se publica también para FAIL/BLOCKED, sin seguir enlaces.
        try:
            write_verdict(workspace, payload)
        except (OSError, CampaignBlocked) as error:
            code = EXIT_BLOCKED
            payload = {'fase': arguments.fase, 'verdict': 'BLOCKED',
                       'reason': 'veredicto no escribible: ' + str(error)}
    _emit(payload)
    return code


def _emit(payload):
    print(MARKER + ' ' + json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')), file=sys.stderr)


if __name__ == '__main__':
    sys.exit(main())