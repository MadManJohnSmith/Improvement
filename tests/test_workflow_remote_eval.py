"""El workflow manual de evaluación remota cumple su contrato sin ejecutarse.

El workflow de `eval` remota (issue #15, spec #11) gasta tokens de un
proveedor real: un error de disparo, de entradas o de secretos solo se
descubriría en la primera corrida facturada. Esta prueba es su contrato de
textos: parsea el YAML del workflow con aserciones dirigidas y un mini
analizador propio (sin PyYAML, como el resto de la suite), y comprueba
disparo manual, entradas, referencias a secretos, ausencia de clave literal
y de `localhost` en la configuración del proveedor, y rutas de artefactos.
Nunca ejecuta el workflow ni contacta proveedores: DSH escucha
legítimamente en 127.0.0.1 dentro del runner, así que la aserción de
`localhost` se acota a la configuración del proveedor y a las URLs
públicas del workflow, que no la necesitan.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "creator-remote-eval.yml"
sys.path.insert(0, str(Path(__file__).resolve().parent))

# The same literal-credential shape the template contract
# (tests/test_eval_config.py) rejects, from the one place that owns it: the
# workflow cannot reintroduce by hand what the template forbids.
from support_config_contract import LITERAL_KEY


def _workflow_text():
    return WORKFLOW.read_text(encoding="utf-8")


def _top_level_block(text, key):
    """The text under a top-level ``key:`` line, until the next top-level key.

    Sufficient for the `on:` trigger block of a workflow written with
    two-space indentation: child lines start with spaces, the block ends at
    the next non-indented, non-comment line.
    """
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.rstrip() == f"{key}:":
            start = index + 1
            break
    if start is None:
        return ""
    block = []
    for line in lines[start:]:
        if line.strip() and not line.startswith((" ", "\t")):
            break
        block.append(line)
    return "\n".join(block)


def _dispatch_inputs(text):
    """The workflow_dispatch inputs, as ``{name: {required, default, ...}}``.

    Minimal indentation parser over the trigger block: an input is a key at
    four levels of indentation under `inputs:`; its attributes sit one level
    deeper. Quoted scalars lose their quotes; absent attributes stay absent
    so a test can tell "no default" from "empty default".
    """
    block = _top_level_block(text, "on")
    lines = block.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == "inputs:":
            start = index + 1
            break
    if start is None:
        return {}
    inputs = {}
    current = None
    for line in lines[start:]:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= 4:
            break
        if indent == 6:
            current = {}
            inputs[line.strip().rstrip(":")] = current
            continue
        if current is None:
            continue
        attribute = re.match(r"^\s*([a-z_-]+):\s*(.*)$", line)
        if not attribute:
            continue
        value = attribute.group(2).strip().strip("'\"")
        if attribute.group(1) == "required":
            current["required"] = value == "true"
        else:
            current[attribute.group(1)] = value
    return inputs


def _steps(text):
    """The job steps in order, as ``{attrs: {key: [lines]}}`` dictionaries.

    Minimal indentation parser for the shape this repository writes:
    two-space indentation, one job, dash items under `steps:`, block
    scalars (`run: |`) for scripts. A step attribute is a `key: value` line
    one level under the dash; deeper lines extend the previous attribute,
    which is how `run` scripts and `with` payloads are kept as text for the
    assertions. Not a YAML implementation: it reads the contract the suite
    writes, and a step that breaks the shape surfaces as a failed assertion
    rather than a silent pass.
    """
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if re.match(r"^\s+steps:\s*$", line):
            start = index + 1
            break
    if start is None:
        return []
    item_indent = None
    steps = []
    current = None
    key = None
    for line in lines[start:]:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        content = line.strip()
        new_step = (item_indent is not None and indent == item_indent
                    and content.startswith("- "))
        if item_indent is None:
            match = re.match(r"^(\s*)- ", line)
            if match is None:
                continue
            item_indent = len(match.group(1))
            new_step = True
        if new_step:
            current = {"attrs": {}}
            steps.append(current)
            key = None
            content = content[2:].strip()
            indent = item_indent + 2
        if current is None:
            continue
        if indent == item_indent + 2:
            header = re.match(r"([A-Za-z_-]+):\s*(.*)$", content)
            if header:
                key = header.group(1)
                current["attrs"][key] = [header.group(2)]
                continue
        if key is not None and indent > item_indent + 2:
            current["attrs"][key].append(content)
    return steps


def _script(step):
    """The `run` script of a step as text, without the block scalar header."""
    lines = step["attrs"].get("run")
    if not lines:
        return ""
    body = lines[1:] if lines[0] in ("|", ">", "|-", ">-") else lines
    return "\n".join(body)


class PreflightTest(unittest.TestCase):
    def test_the_preflight_closes_before_any_token_is_spent(self):
        """Fixture, plantilla, secreto y descompresor se cierran antes del despacho.

        Un run sin fixture, con la plantilla ausente, el secreto vacío o sin
        zstd terminaría igual de facturado si el Creator se despachara
        primero. El preflight cierra esas piezas antes del primer uso de
        `creator_client`, sobre una imagen fija con Python, Node y el
        descompresor instalados, y el home de DSH apunta al runner, nunca al
        `~/.dsh` de nadie (docs/setup-dsh.md).
        """
        text = _workflow_text()
        steps = _steps(text)
        self.assertIn("runs-on: ubuntu-22.04", text,
                      "la imagen del runner no está fijada")
        uses = [step["attrs"]["uses"][0] for step in steps
                if "uses" in step["attrs"]]
        self.assertTrue(any("actions/setup-python@" in item for item in uses),
                        "falta setup-python")
        self.assertTrue(any("actions/setup-node@" in item for item in uses),
                        "falta setup-node")
        installed = [index for index, step in enumerate(steps)
                     if "apt-get install -y zstd" in _script(step)]
        self.assertEqual(len(installed), 1,
                         "el descompresor se instala una vez, por apt")
        preflight = [index for index, step in enumerate(steps)
                     if "command -v zstd" in _script(step)]
        self.assertEqual(len(preflight), 1,
                         "el preflight que cierra el descompresor es único")
        self.assertLess(installed[0], preflight[0],
                        "el descompresor se instala antes de prevalidarlo")
        dispatch = [index for index, step in enumerate(steps)
                    if "creator_client.py" in _script(step)]
        self.assertEqual(len(dispatch), 1,
                         "el Creator se despacha en un único paso")
        self.assertLess(preflight[0], dispatch[0],
                        "el preflight no precede al despacho del Creator")
        script = _script(steps[preflight[0]])
        self.assertIn("fixtures/$FIXTURE/product", script,
                      "el preflight no cierra el fixture")
        self.assertIn("eval/profile-dsh.patch.yml", script,
                      "el preflight no cierra la plantilla del perfil")
        self.assertIn('case "$PROVIDER_BASE_URL" in https://*', script,
                      "el preflight no cierra la URL pública del proveedor")
        for window in ("CONTEXT_WINDOW", "MAX_TOKENS"):
            self.assertIn(f'case "${window}" in', script,
                          f"el preflight no cierra {window} como entero")
        self.assertIn('[ -n "$DSH_PROVIDER_API_KEY" ] ||', script,
                      "el preflight no cierra el secreto vacío")
        self.assertIn('case "$AUTH" in', script,
                      "el secreto solo se exige en el modo secret")
        self.assertIn("keyless)", script,
                      "el modo keyless prescinde de la clave del proveedor")
        self.assertRegex(
            text, r'(?m)^\s*EVAL_ROOT="\$RUNNER_TEMP/creator-eval"',
            "los directorios efímeros cuelgan del temp del runner")
        self.assertRegex(
            text, r'(?m)^\s*DSH_HOME="\$EVAL_ROOT/dsh-home"',
            "DSH_HOME apunta a un home local del runner, nunca al de nadie")
        self.assertNotIn("~/.dsh", text)
        self.assertNotIn("$HOME/.dsh", text)
        self.assertNotIn(
            "${{ runner.", text,
            "el contexto runner no está disponible en el env del job y "
            "GitHub rechaza el workflow al dispararlo (HTTP 422): los "
            "directorios efímeros se publican por GITHUB_ENV con RUNNER_TEMP")


class ProfileRenderTest(unittest.TestCase):
    def test_the_profile_is_rendered_from_the_template_without_local_urls(self):
        """The profile is filled from the template; no local URL sneaks in.

        The recipe in eval/README.md copies the template as the profile
        bundle's cordis.patch.yml and substitutes its markers; every marker
        the template declares must be substituted by the workflow, and a
        leftover marker must fail the run instead of reaching DSH. The key
        is not substituted by anyone: `apiKeyEnv` names the variable the
        runner exports from the secret. The localhost assertion is scoped
        to provider configuration and public URLs: DSH legitimately listens
        on 127.0.0.1 inside the runner without the workflow naming it, so
        only URL-bearing and provider lines are checked, and no insecure
        `http://` may appear at all.
        """
        text = _workflow_text()
        steps = _steps(text)
        template = (ROOT / "eval" / "profile-dsh.patch.yml").read_text(
            encoding="utf-8")
        markers = sorted(set(re.findall(r"@([A-Z_]+)@", template)))
        self.assertEqual(len(markers), 6,
                         "la plantilla declara los marcadores de la receta")
        render = [step for step in steps
                  if "@DSH_PROFILE_PROVIDER@" in _script(step)]
        self.assertEqual(len(render), 1,
                         "el render del perfil es un único paso")
        script = _script(render[0])
        for marker in markers:
            self.assertIn(marker, script,
                          f"el render no sustituye el marcador @{marker}@")
        self.assertIn("eval/profile-dsh.patch.yml", script,
                      "el render no parte de la plantilla versionada")
        self.assertIn("cordis.patch.yml", script,
                      "el render no escribe el cordis.patch.yml del bundle")
        self.assertIn("profiles/web", script,
                      "el render no escribe el perfil del home de DSH")
        self.assertIn("package.json", script,
                      "el bundle del perfil no declara su package.json")
        self.assertRegex(script, r"grep -q '@DSH_PROFILE_'",
                         "el render no cierra los marcadores sin sustituir")
        code = "\n".join(line for line in script.splitlines()
                         if not line.lstrip().startswith("#"))
        self.assertNotIn("apiKeyEnv", code,
                         "el render no sustituye la referencia de la clave")
        dispatch = [index for index, step in enumerate(steps)
                    if "creator_client.py" in _script(step)]
        rendered = steps.index(render[0])
        self.assertLess(rendered, dispatch[0],
                        "el perfil no se renderiza antes de despachar")
        local = re.compile(r"localhost|127\.0\.0\.1", re.I)
        url_lines = [line for line in text.splitlines()
                     if "://" in line or "baseURL" in line.lower()
                     or line.strip().endswith("_URL")]
        self.assertTrue(url_lines, "el workflow declara URLs que revisar")
        for line in url_lines:
            self.assertNotRegex(
                line, local,
                f"configuración del proveedor con host local: {line.strip()}")
        self.assertNotIn("http://", text,
                         "toda URL pública del workflow es https")


class KeylessAuthTest(unittest.TestCase):
    def test_keyless_mode_strips_the_credential_reference_after_render(self):
        """auth=keyless removes apiKeyEnv so DSH sends no credential header.

        The opencode free tier accepts anonymous requests and answers with
        its own usage limit, not an authentication error (probed directly
        against its public endpoint). DSH only omits the header when the
        profile carries no `apiKeyEnv` at all: its own MISSING_CREDENTIAL
        message documents removing it for providers that authenticate from
        pi-ai's environment discovery, which on a clean runner finds
        nothing. The strip runs after the render and before the dispatch,
        guarded by the auth mode, and in secret mode the line survives so
        the runner-exported secret keeps working.
        """
        text = _workflow_text()
        steps = _steps(text)
        render = [index for index, step in enumerate(steps)
                  if "@DSH_PROFILE_PROVIDER@" in _script(step)]
        dispatch = [index for index, step in enumerate(steps)
                    if "creator_client.py" in _script(step)]
        strip = [index for index, step in enumerate(steps)
                 if "apiKeyEnv:/d" in _script(step)]
        self.assertEqual(len(strip), 1,
                         "la eliminación de apiKeyEnv es un paso único")
        self.assertLess(render[0], strip[0],
                        "el modo keyless actúa tras el render del perfil")
        self.assertLess(strip[0], dispatch[0],
                        "el modo keyless actúa antes de despachar el Creator")
        script = _script(steps[strip[0]])
        self.assertIn('[ "$AUTH" = "keyless" ]', script,
                      "la eliminación está guardada por el modo de auth")
        self.assertIn("cordis.patch.yml", script,
                      "la eliminación opera sobre el perfil renderizado")


class SecretHandlingTest(unittest.TestCase):
    def test_the_provider_key_is_referenced_and_never_printed(self):
        """Every appearance of the secret is an env assignment, never a print.

        The key lives in the repository secret and may only appear as
        `DSH_PROVIDER_API_KEY: ${{ secrets.DSH_PROVIDER_API_KEY }}` in an
        env block: Actions masks the expanded value, but an explicit echo
        of the variable would defeat the masking, and a literal key in the
        file would publish it. The variable NAME in a message is not the
        secret: only printing the value is banned.
        """
        text = _workflow_text()
        occurrences = [line for line in text.splitlines()
                       if "secrets.DSH_PROVIDER_API_KEY" in line]
        self.assertTrue(occurrences,
                        "el workflow no referencia el secreto del proveedor")
        for line in occurrences:
            self.assertRegex(
                line.strip(),
                r"^DSH_PROVIDER_API_KEY: "
                r"\$\{\{ secrets\.DSH_PROVIDER_API_KEY \}\}$",
                "el secreto aparece fuera de una asignación de env: "
                f"{line.strip()}")
        self.assertNotRegex(
            text, LITERAL_KEY,
            "hay una clave literal donde solo cabe la referencia")
        for line in text.splitlines():
            if "$DSH_PROVIDER_API_KEY" not in line:
                continue
            self.assertNotRegex(
                line, r"\b(echo|printf|cat|tee)\b[^\n]*\$\{?DSH_PROVIDER_API_KEY",
                "el workflow imprime el valor de la clave")


class RunPreparationTest(unittest.TestCase):
    def test_the_run_is_prepared_against_the_fixture_before_dispatch(self):
        """The fixture becomes a Git project and bootstrap creates the run.

        bootstrap requires a project git checkout with a HEAD and an
        external workspace, and the run (run.json with root_identity and
        budget) is created by `install --no-dispatch`; its run_dir feeds
        the dispatch. Both happen before the Creator is ever invoked, and
        neither depends on a maintainer's local path.
        """
        text = _workflow_text()
        steps = _steps(text)
        fixture = [step for step in steps
                   if 'git -C "$PROJECT_DIR" init' in _script(step)]
        self.assertEqual(len(fixture), 1,
                         "la conversión del fixture en proyecto Git es única")
        fixture_script = _script(fixture[0])
        self.assertIn("fixtures/$FIXTURE/product", fixture_script,
                      "el proyecto no sale del fixture elegido")
        # El commit del fixture es determinista: autor y fechas fijos en el
        # propio paso, de modo que el sha1 (y con él root_identity, el
        # sha256 del sha1 que bootstrap registra) sea estable entre corridas
        # y comparable con la identidad registrada del fixture.
        for piece in ('GIT_AUTHOR_NAME="CI"',
                      'GIT_AUTHOR_EMAIL="ci@users.noreply.github.com"',
                      'GIT_COMMITTER_NAME="CI"',
                      'GIT_COMMITTER_EMAIL="ci@users.noreply.github.com"',
                      'GIT_AUTHOR_DATE="', 'GIT_COMMITTER_DATE="'):
            self.assertIn(piece, fixture_script,
                          f"el commit del fixture no fija {piece}")
        prepared = [step for step in steps
                    if "scripts/bootstrap.py install" in _script(step)]
        self.assertEqual(len(prepared), 1,
                         "la preparación del run es un único paso")
        prepared_script = _script(prepared[0])
        for flag in ("--no-dispatch", '--creator-max-tokens "$BUDGET"',
                     '--project "$PROJECT_DIR"',
                     '--workspace "$WORKSPACE_DIR"'):
            self.assertIn(flag, prepared_script,
                          f"el run no se prepara con {flag}")
        # La exportación usa el MISMO nombre que consumen los pasos
        # siguientes ($RUN_DIR en despacho y evaluación): un desajuste de
        # caja expone una variable vacía y el Creator busca run.json en el
        # checkout (fallo real del primer despacho remoto).
        self.assertRegex(
            prepared_script, r'echo "RUN_DIR=\$RUN_DIR" >> "\$GITHUB_ENV"',
            "el run_dir no se exporta para los pasos siguientes")
        self.assertNotRegex(
            prepared_script, r'echo "run_dir=',
            "la exportación en minúsculas no la consume nadie")
        order = [steps.index(fixture[0]), steps.index(prepared[0]),
                 [index for index, step in enumerate(steps)
                  if "creator_client.py" in _script(step)][0]]
        self.assertEqual(order, sorted(order),
                        "fixture, run y despacho no van en orden")


class DispatchContinuityTest(unittest.TestCase):
    def test_a_retained_run_continues_into_evaluation(self):
        """RETAINED is continuity, not a workflow failure.

        `creator_client.main()` exits 1 when the verdict is RETAINED, and
        the evaluation still has to run on the retained run. But a Python
        crash also exits 1, so continuity requires seeing the verdict, not
        just the code: exit 0 continues, exit 1 with a RETAINED result in
        the run log continues, anything else fails the job. The run is
        dispatched against its prepared run_dir with a launched DSH.
        """
        steps = _steps(_workflow_text())
        dispatch = [step for step in steps
                    if "creator_client.py" in _script(step)]
        self.assertEqual(len(dispatch), 1)
        script = _script(dispatch[0])
        self.assertIn("--launch-dsh", script,
                      "el despacho no lanza DSH en el runner")
        self.assertIn('--run-dir "$RUN_DIR"', script,
                      "el despacho no va contra el run preparado")
        self.assertIn("set +e", script,
                      "sin set +e la tubería mata el paso antes de leer el código")
        self.assertIn("${PIPESTATUS[0]}", script,
                      "el código de creator_client se pierde por la tubería")
        self.assertIn("grep -q '\"result\": \"RETAINED\"'", script,
                      "la continuidad exige ver el veredicto, no solo el código")
        self.assertLessEqual(script.index("set +e"),
                             script.index("${PIPESTATUS[0]}"),
                             "el código se captura con la máscara de errores activa")


class CaseEvaluationTest(unittest.TestCase):
    def test_the_case_is_built_and_graded_from_the_finished_run(self):
        """The case builder and the evaluator run on the finished run.

        `creator_eval --from-run` derives the facts from the run, writes
        the case and grades it against the versioned criteria; the journal
        is discovered under the runner's DSH home (--dsh-home), the product
        root is passed (--project-root) so the facts carry the tree digest
        comparable with the fixture registration, and the report defaults
        inside the case. A closed failure of the builder or the evaluator
        exits the step, but the verdict itself never decides the workflow's
        outcome: it informs the merge.
        """
        text = _workflow_text()
        steps = _steps(text)
        graded = [step for step in steps
                  if "creator_eval.py" in _script(step)]
        self.assertEqual(len(graded), 1,
                         "la evaluación del caso es un único paso")
        script = _script(graded[0])
        for piece in ('--from-run "$RUN_DIR"',
                      '--criteria eval/criteria-remote-creator.json',
                      '--dsh-home "$DSH_HOME"',
                      '--project-root "$PROJECT_DIR"',
                      '--case "$CASE_DIR"'):
            self.assertIn(piece, script,
                          f"el evaluador no recibe {piece}")
        self.assertNotIn("--report", script,
                         "el reporte usa su defecto: dentro del caso")
        dispatch = [index for index, step in enumerate(steps)
                    if "creator_client.py" in _script(step)][0]
        self.assertLess(dispatch, steps.index(graded[0]),
                        "el caso no se construye tras el despacho")


class ArtifactsTest(unittest.TestCase):
    def test_the_evidence_is_published_and_the_log_even_on_failure(self):
        """Report, facts, criteria, journal, roster row and log travel as artifacts.

        The case (facts.json, criteria.json, the discovered journal and
        report.json) is uploaded whole; the roster row derived from it is
        uploaded beside it; the run log is uploaded with `if: always()`,
        also when the run fails, because it is the only evidence a
        retained run without a report leaves. A missing case or row is
        expected before the evaluation runs, so those uploads ignore empty
        results; a missing log would be a defect of the workflow itself
        and must not be silently ignored.
        """
        steps = _steps(_workflow_text())
        uploads = [step for step in steps if step["attrs"].get(
            "uses", [""])[0].startswith("actions/upload-artifact")]
        self.assertEqual(len(uploads), 3,
                         "tres artefactos: el caso evaluado, la fila del "
                         "roster y el log del run")

        def with_block(step):
            return "\n".join(step["attrs"].get("with", []))

        case = [step for step in uploads if "CASE_DIR" in with_block(step)]
        log = [step for step in uploads if "RUN_LOG" in with_block(step)]
        self.assertEqual(len(case), 1, "el caso evaluado no viaja completo")
        self.assertEqual(len(log), 1, "el log del run no viaja")
        for step in uploads:
            self.assertEqual(step["attrs"].get("if"), ["always()"],
                             "la publicación no sobrevive a un fallo")
        self.assertIn("if-no-files-found: ignore", with_block(case[0]),
                      "sin caso no hay artefacto de caso que publicar")
        self.assertNotIn("if-no-files-found", with_block(log[0]),
                         "un log ausente no se ignora: es un defecto propio")
        graded = [index for index, step in enumerate(steps)
                  if "creator_eval.py" in _script(step)][0]
        self.assertLess(graded, steps.index(case[0]),
                        "el caso se publica tras construirse")


class RosterRowArtifactTest(unittest.TestCase):
    def test_the_roster_row_is_derived_and_published_as_its_own_artifact(self):
        """The row travels as its own artifact; the workflow never commits it.

        The roster is the maintainer's history, not the repository's
        (#16): the workflow derives the row from the graded case as a
        closed projection and writes it outside the case tree, so the row
        artifact is its own evidence and the case artifact stays exactly
        the case. It uploads under the same publication condition as the
        case, and versioning the roster stays a maintainer decision: the
        only git commit in the file remains the fixture's.
        """
        text = _workflow_text()
        steps = _steps(text)

        def with_block(step):
            return "\n".join(step["attrs"].get("with", []))

        derived = [step for step in steps
                   if "creator_roster.py" in _script(step)]
        self.assertEqual(len(derived), 1,
                         "la derivación de la fila es un único paso")
        script = _script(derived[0])
        self.assertIn('--case "$CASE_DIR"', script,
                      "la fila no se deriva del caso evaluado")
        self.assertIn('--out "$ROSTER_ROW"', script,
                      "la fila no se escribe dentro del caso ya publicado")
        graded = [index for index, step in enumerate(steps)
                  if "creator_eval.py" in _script(step)][0]
        self.assertLess(graded, steps.index(derived[0]),
                        "la fila se deriva tras calificar el caso")
        self.assertRegex(
            text, r'(?m)^\s*ROSTER_ROW="\$EVAL_ROOT/roster-row\.json"',
            "la fila no vive bajo el temp del runner")
        uploads = [step for step in steps if step["attrs"].get(
            "uses", [""])[0].startswith("actions/upload-artifact")]
        row = [step for step in uploads if "ROSTER_ROW" in with_block(step)]
        self.assertEqual(len(row), 1,
                         "la fila del roster no viaja como artefacto propio")
        self.assertIn("name: creator-eval-roster-row", with_block(row[0]),
                      "el artefacto de la fila no lleva su nombre propio")
        self.assertEqual(row[0]["attrs"].get("if"), ["always()"],
                         "la fila no comparte la condición del caso")
        self.assertIn("if-no-files-found: ignore", with_block(row[0]),
                      "sin fila no hay artefacto de fila que publicar")
        commits = [step for step in steps if " commit " in _script(step)]
        self.assertEqual(len(commits), 1,
                         "el único commit del workflow es el del fixture")
        self.assertIn('git -C "$PROJECT_DIR" init', _script(commits[0]),
                      "el commit del workflow no es el del fixture")


class DispatchInputsTest(unittest.TestCase):
    def test_the_dispatch_inputs_cover_the_case_without_pinning_a_provider(self):
        """The case is pre-registered from inputs, never from the repository.

        The spec asks for prompt version, model, budget and fixture; the
        provider base URL is required too. Model and base URL carry no
        default: nobody pins a provider into the repository. The windows of
        the chosen model are overridable because the profile template needs
        them, with defaults from the observed case. The prompt_version
        default is bound to the Creator's own PROMPT_VERSION so it cannot
        rot when the prompt moves. The provider API channel and the auth
        mode are inputs too: the endpoint picks the protocol
        (openai-completions for opencode, openai-responses for the observed
        omniroute case) and the auth mode picks secret versus keyless.
        """
        inputs = _dispatch_inputs(_workflow_text())
        for name in ("model", "provider_base_url", "prompt_version",
                     "budget", "context_window", "max_tokens", "fixture",
                     "provider_api", "auth"):
            self.assertIn(name, inputs,
                          f"falta la entrada {name} del dispatch")
        self.assertTrue(inputs["model"]["required"])
        self.assertNotIn("default", inputs["model"],
                         "el modelo no lleva defecto: lo elige quien despacha")
        self.assertTrue(inputs["provider_base_url"]["required"])
        self.assertNotIn("default", inputs["provider_base_url"],
                         "la URL base no lleva defecto: sin proveedor fijado")
        self.assertEqual(inputs["auth"].get("default"), "secret",
                         "el modo de autenticación por defecto es el secreto")
        self.assertEqual(inputs["provider_api"].get("default"),
                         "openai-completions",
                         "el canal por defecto es el OpenAI estándar")
        for name, default in (("prompt_version", None), ("budget", None),
                              ("fixture", None), ("context_window", None),
                              ("max_tokens", None)):
            self.assertTrue(inputs[name].get("default"),
                            f"la entrada {name} debe llevar valor por defecto")
        declared = re.search(
            r'^PROMPT_VERSION = "([^"]+)"$',
            (ROOT / "scripts" / "creator_client.py").read_text(
                encoding="utf-8"), re.M)
        self.assertIsNotNone(declared)
        self.assertEqual(inputs["prompt_version"]["default"],
                         declared.group(1),
                         "el defecto de prompt_version no coincide con el "
                         "PROMPT_VERSION del Creator")


class ManualTriggerTest(unittest.TestCase):
    def test_the_workflow_fires_only_by_manual_dispatch(self):
        """The evaluation spends tokens only when the maintainer asks for it.

        A `push` or `pull_request` trigger would bill a provider on every
        commit; a schedule would bill nobody's decision. The spec fixes the
        trigger set to `workflow_dispatch` alone.
        """
        self.assertTrue(
            WORKFLOW.is_file(),
            f"falta el workflow de evaluación remota: {WORKFLOW}")
        trigger = _top_level_block(_workflow_text(), "on")
        self.assertIn("workflow_dispatch", trigger)
        for banned in ("push:", "pull_request:", "schedule:", "cron:"):
            self.assertNotIn(banned, trigger)


if __name__ == "__main__":
    unittest.main()
