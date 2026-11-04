/**
 * doc-drift: deriva documental gobernada por el Harness, no por el prompt.
 *
 * ADR 0002. El plugin observa mutaciones de la sesión, ejecuta
 * `scripts/drift.py` al cierre del turno y actúa con tres niveles
 * deterministas:
 *
 *   1. Solo CURRENT / NON_GOVERNING_CHANGE: `repin` silencioso y cierre
 *      limpio. Cero tokens de LLM para detectar o refrescar.
 *   2. CONTRACT_DRIFT / STALE_REFERENCE / SOURCE_DRIFT: bloquea el cierre,
 *      emite el contexto estructurado con los símbolos exactos y confina
 *      `fs/write-intent` a los `.md` afectados mientras dure el paso de
 *      sincronización. Tras la edición, solo una re-verificación sin
 *      referencias rotas certifica y re-ancla la línea base.
 *   3. Sin entradas evaluables: cierre sin tocar estado.
 *
 * El motor corre como subproceso sin shell. Su salida es el mismo JSON que
 * firma la CLI (`drift.py check --json`) y sus códigos son contrato: 0
 * limpio, 1 deriva, 2 rechazo del motor. Un rechazo jamás se interpreta como
 * limpieza: el plugin falla cerrado y deja el turno bloqueado.
 *
 * La forma exacta de los payloads de `agent/turn-stopping` y del retorno con
 * `additionalContexts` pertenece al runtime DSH; aquí se implementa la lógica
 * determinista y los hooks se registran con detección de presencia, como
 * workflow-write. La regresión offline (`verify-doc-drift.mjs`) cubre la
 * lógica con un ctx simulado y el motor real contra repositorios sintéticos;
 * la sesión DSH real la cubre la suite que exige el módulo externo.
 */
import { spawn } from 'node:child_process';
import { basename, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const inject = ['tools', 'fs', 'systemPrompt'];

export const BLOCKING_STATUSES = Object.freeze([
  'CONTRACT_DRIFT', 'STALE_REFERENCE', 'SOURCE_DRIFT',
]);
export const CLEAN_STATUSES = Object.freeze(['CURRENT', 'NON_GOVERNING_CHANGE']);
export const DEFAULT_TIMEOUT_MS = 120000;

/** Normalized repository-relative or absolute path, forward slashes. */
export function normalizePath(value) {
  return String(value ?? '').replace(/\\/g, '/').replace(/^\.\//, '');
}

/**
 * Pure classification of an engine report into the plugin's next action.
 *
 * `action` is 'close' (nothing evaluable), 'repin' (clean verdict) or 'sync'
 * (at least one blocking status). `affectedDocs` is the sorted, deduplicated
 * list of documents the sync step may touch — the write confinement set.
 */
export function classify(report) {
  const entries = Array.isArray(report?.entries) ? report.entries : [];
  const blocking = entries.filter(
    (entry) => BLOCKING_STATUSES.includes(entry?.status));
  const affectedDocs = [...new Set(
    blocking.map((entry) => entry?.path).filter(Boolean))].sort();
  let action = 'close';
  if (entries.length > 0) action = blocking.length ? 'sync' : 'repin';
  return { report, entries: entries.length, blocking, affectedDocs, action };
}

/** True when a write target is one of the documents the sync step owns. */
export function writeAllowed(target, affectedDocs) {
  const path = normalizePath(target);
  if (!path) return false;
  return affectedDocs.some((doc) => {
    const normalized = normalizePath(doc);
    return path === normalized || path.endsWith('/' + normalized);
  });
}

/** The deterministic directive the Harness injects when drift blocks closure. */
export function syncDirective(decision) {
  const lines = [
    'DOC DRIFT BLOCKED: documentación desincronizada con el código '
    + '(scripts/drift.py, ADR 0002).',
    'Documentos afectados (únicos escribibles durante este paso): '
    + decision.affectedDocs.join(', '),
    'Estados:',
    ...decision.blocking.map((entry) => {
      const detail = entry.detail ? `: ${entry.detail}` : '';
      return `- ${entry.status} ${entry.path}${detail}`;
    }),
    'Actualiza solo esos documentos para describir el contrato vigente; '
    + 'el Host re-verificará y re-anclará la línea base antes de permitir '
    + 'el cierre.',
  ];
  return lines.join('\n');
}

/** Engine invocation: python + CLI, overridable for the offline verifier. */
export function engineCommand(config = {}, env = process.env) {
  const python = config.python || env.DSH_DOC_DRIFT_PYTHON || 'python3';
  const cli = config.enginePath || env.DSH_DOC_DRIFT_CLI
    || fileURLToPath(new URL('../drift.py', import.meta.url));
  return { python, cli };
}

/**
 * Project and workspace roots. The workspace is external state (the baseline
 * and the report live there), and defaults to the product's sibling, the same
 * convention bootstrap.py uses.
 */
export function engineRoots(config = {}, env = process.env,
                            cwd = process.cwd()) {
  const repoRoot = config.repoRoot || env.DSH_DOC_DRIFT_PROJECT || cwd;
  const workspace = config.workspace || env.DSH_DOC_DRIFT_WORKSPACE
    || join(dirname(repoRoot), `${basename(repoRoot)}-workspace`);
  return { repoRoot, workspace };
}

export function checkArgs(config = {}, env = process.env) {
  const { repoRoot, workspace } = engineRoots(config, env);
  const args = ['check', '--project', repoRoot, '--workspace', workspace,
                '--to', config.targetRev || 'WORKTREE'];
  if (config.dryRun) args.push('--dry-run');
  args.push('--json');
  return args;
}

export function repinArgs(config = {}, env = process.env) {
  const { repoRoot, workspace } = engineRoots(config, env);
  return ['repin', '--project', repoRoot, '--workspace', workspace,
          '--to', config.targetRev || 'WORKTREE'];
}

/**
 * Run the engine and parse its report. Exit 2 (engine refused) rejects: a
 * refused evaluation must never look clean. A timeout kills the child and
 * rejects with the same discipline.
 */
export function runEngine(config, args, env = process.env,
                          { json = true } = {}) {
  const { python, cli } = engineCommand(config, env);
  const timeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(python, ['-B', cli, ...args], {
      cwd: config.cwd || process.cwd(),
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      child.kill('SIGKILL');
      rejectPromise(new Error(
        `doc-drift engine timed out after ${timeoutMs} ms`));
    }, timeoutMs);
    child.stdout.on('data', (chunk) => { stdout += chunk; });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    child.on('error', (error) => {
      clearTimeout(timer);
      rejectPromise(error);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code === 2) {
        rejectPromise(new Error(
          'doc-drift engine refused the evaluation: ' + stderr.trim()));
        return;
      }
      if (!json) {
        // Certification commands (repin) report in prose; only `check`
        // promises the JSON the plugin classifies.
        resolvePromise({ code, stdout, stderr });
        return;
      }
      let report = null;
      try {
        report = JSON.parse(stdout);
      } catch (error) {
        rejectPromise(new Error(
          `doc-drift engine output is not JSON (exit ${code}): `
          + (stderr.trim() || error.message)));
        return;
      }
      resolvePromise({ code, report, stderr });
    });
  });
}

/**
 * Cordis plugin entry point.
 *
 * Session state: `observed` (paths the session touched, for provenance) and
 * `sync` (the confinement set while a documentation sync step is open). The
 * plugin is session-scoped by the runtime, so the state needs no key.
 */
export function apply(ctx, config = {}) {
  const env = config.env || process.env;
  const observed = new Set();
  let sync = null;

  const note = (target) => {
    const path = normalizePath(
      typeof target === 'string' ? target : target?.path);
    if (path) observed.add(path);
  };

  // Observation accumulation: every mutation the session performs is
  // provenance for the next verdict, never a reason to skip evaluation.
  ctx.on?.('fs/observed', (target) => { note(target); });
  ctx.on?.('tools/post-execute', async (_tool, args, _result, next) => {
    note(args?.file_path ?? args?.path);
    if (typeof next === 'function') return next();
    return undefined;
  });

  // Confinement: while a sync step is open, only the affected documents are
  // writable. This is the mechanical counterpart of the injected directive.
  ctx.on?.('fs/write-intent', async (target, _exec, next) => {
    if (sync) {
      const path = normalizePath(
        typeof target === 'string' ? target : target?.path);
      if (!writeAllowed(path, sync.affectedDocs)) {
        throw new Error(
          'doc-drift sync step: write outside the affected documents denied '
          + `(${path}); allowed: ${sync.affectedDocs.join(', ')}`);
      }
    }
    if (typeof next === 'function') return next();
    return undefined;
  });

  // Turn close: the deterministic verdict decides whether the session may
  // close, must sync documents, or can refresh its baseline silently.
  ctx.on?.('agent/turn-stopping', async () => {
    const { report } = await runEngine(config, checkArgs(config, env), env);
    const decision = classify(report);

    if (sync) {
      // Re-verification after the sync step. Contract drift is certified by
      // the Host's re-anchor; broken references are not — they keep blocking
      // until the documents resolve.
      const stale = decision.blocking.filter(
        (entry) => entry.status === 'STALE_REFERENCE');
      if (stale.length > 0) {
        sync = {
          affectedDocs: [...new Set(stale.map((e) => e.path))].sort(),
        };
        const blocked = { ...decision, affectedDocs: sync.affectedDocs };
        ctx.emit?.('doc-drift/blocked',
                   { affectedDocs: sync.affectedDocs, blocking: stale });
        return {
          decision: 'blocked',
          action: 'sync',
          affectedDocs: sync.affectedDocs,
          additionalContexts: [syncDirective(blocked)],
        };
      }
      await runEngine(config, repinArgs(config, env), env, { json: false });
      sync = null;
      const certified = await runEngine(
        config, checkArgs(config, env), env);
      const after = classify(certified.report);
      if (after.action === 'sync') {
        sync = { affectedDocs: after.affectedDocs };
        ctx.emit?.('doc-drift/blocked',
                   { affectedDocs: after.affectedDocs, blocking: after.blocking });
        return {
          decision: 'blocked',
          action: 'sync',
          affectedDocs: after.affectedDocs,
          additionalContexts: [syncDirective(after)],
        };
      }
      ctx.emit?.('doc-drift/clean', { action: 'certified' });
      return undefined;
    }

    if (decision.action === 'sync') {
      sync = { affectedDocs: decision.affectedDocs };
      ctx.emit?.('doc-drift/blocked',
                 { affectedDocs: decision.affectedDocs,  blocking: decision.blocking });
      return {
        decision: 'blocked',
        action: 'sync',
        affectedDocs: decision.affectedDocs,
        additionalContexts: [syncDirective(decision)],
      };
    }
    if (decision.action === 'repin') {
      await runEngine(config, repinArgs(config, env), env, { json: false });
    }
    ctx.emit?.('doc-drift/clean', { action: decision.action });
    return undefined;
  });
}
