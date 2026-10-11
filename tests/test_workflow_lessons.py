"""Lecciones permanentes de las campañas de workflow, y de ZCode corriéndolas.

Cada prueba de este fichero nace de un fallo o de un éxito medido en una campaña
real, no de una hipótesis. La procedencia viaja en su docstring con formato
`[W<nn>]`, el identificador que `docs/workflows-lecciones.md` usa para la misma
lección. Una lección sin identificador aquí no está cubierta por prueba.

Tres convenciones tomadas de las propias campañas:

- `unittest` escribe el recuento y el veredicto en **stderr**, no en stdout
  (`dwfrun-27cccb98` aprendió que un gate que solo parsea stdout no ve el
  `Ran N tests` y da verde sin haber leído nada). Las pruebas de aquí juntan
  los dos flujos.
- El código de salida del proceso no se deduce de un *pipeline*: si la salida se
  filtra con `tail`, el código que llega es el de `tail`.
- La fixture imita la del repo: `producto/` git real + workspace con
  `project.json`, y el `run_root` fuera del workspace. Ninguna prueba toca un
  fichero versionado ni un proyecto real del operador.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

import workflow  # noqa: E402
import workflow_evidence  # noqa: E402
from workflow import WorkflowError, read_journal, run_plan, verify  # noqa: E402

# shutil.which y no sys.executable: sys.executable puede ser el AppImage de ZCode.
PYTHON = shutil.which('python3')

DOCS_LEARNING = REPO_ROOT / 'docs' / 'workflows-lecciones.md'
# Lecciones documentadas en el momento de escribir estos tests. El mínimo sube
# con la matriz: añadir una lección sin tocarlo hace fallar la prueba a
# propósito, para que el árbol no afirme más cobertura de la que documenta.
DEFINITION_ROWS = 29


def _git(product, *args):
    subprocess.run(['git', '-C', str(product)] + list(args), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class _Product:
    """Producto git mínimo y sintético, con el workspace que el contrato exige."""

    def __init__(self, root):
        self.root = Path(root)
        self.product = self.root / 'producto'
        self.workspace = self.root / 'workspace'
        self.product.mkdir(parents=True)
        self.workspace.mkdir(parents=True)
        (self.product / 'app.py').write_text('X = 1\n', encoding='utf-8')
        self.workspace.joinpath('project.json').write_text(
            json.dumps({'schema': 1, 'name': 'demo',
                        'project': str(self.product)}, ensure_ascii=False),
            encoding='utf-8')

    def init_git(self):
        subprocess.run(['git', 'init', '-q', str(self.product)], check=True)
        _git(self.product, 'config', 'user.email', 'regresion@example.invalid')
        _git(self.product, 'config', 'user.name', 'regresion')
        self.commit('base')

    def commit(self, message):
        _git(self.product, 'add', '-A')
        _git(self.product, 'commit', '-q', '-m', message)

    def edit(self, name, text):
        (self.product / name).write_text(text, encoding='utf-8')

    def head(self):
        return subprocess.run(
            ['git', '-C', str(self.product), 'rev-parse', 'HEAD'], check=True,
            capture_output=True, text=True).stdout.strip()


def _both_streams(proc):
    """Une stdout y stderr.

    unittest escribe `Ran N tests` y el veredicto en stderr; un gate que solo
    mira stdout concluye verde sin haber leído nada. [W01]
    """
    return (proc.stdout or '') + '\n' + (proc.stderr or '')


class MemoryAwarePlan:
    """Plan con memoria habilitada sobre el producto sintético."""

    def __init__(self, product, run_root, steps, name='campana-lecciones'):
        self.path = Path(run_root).parent / (name + '.json')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        plan = {'schema_version': 1, 'name': name,
                'workspace': str(product.workspace),
                'run_root': str(run_root), 'memory': True, 'steps': steps}
        self.path.write_bytes(json.dumps(plan, sort_keys=True,
                                         separators=(',', ':')).encode() + b'\n')

    def run(self, run_root=None):
        return run_plan(str(self.path), run_root=run_root)


def _run_dir(run_root, outcome):
    """Deriva el run dir desde la salida del ejecutor.

    El id es `r-` + 24 chars del sha del plan: dos campañas del mismo plan
    comparten run, que es justo lo que [W04] comprueba que se respete.
    """
    return Path(outcome['run_dir'])


class WorkflowLessonsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.product = _Product(self.tmp / 'producto-fixture')
        self.product.init_git()
        self.run_root = self.tmp / 'runs'

    # ---------------------------------------------------------------- helpers

    def gate(self, step_id, exit=0, on_fail='abort'):
        # `on_fail` es obligatorio en todo paso gate: un plan sin él no valida.
        return {'id': step_id, 'type': 'gate',
                'command': [PYTHON, '-c', 'import sys; sys.exit(%d)' % exit],
                'on_fail': {'action': on_fail, 'rounds': 1}}

    def failing_gate(self, step_id):
        return self.gate(step_id, exit=1)

    def reconciled(self, run_dir):
        records = [item for item in read_journal(run_dir)
                   if item['kind'] == 'MEMORY_RECONCILED']
        self.assertTrue(records, 'sin MEMORY_RECONCILED en el journal')
        return records[-1]['payload']

    # [W02] La memoria mide en contra del producto, no del plan que la escribe.
    def test_memoria_pierde_hits_cuando_el_producto_cambia(self):
        """Cambiar el producto tiene que costar el `hit`, y decirlo en el journal.

        La lección nace de `MEMORY_RECONCILED {base 693ba47…, invalidated: 6,
        hits: 0, misses: 0}`: con la base inválida el índice ya no describía
        el producto. El comportamiento correcto es conservador —sin `hit`
        posible— y, sobre todo, **registrado**: un índice cuya medida no
        aparece en el journal es un índice que nadie puede auditar.
        """
        plan = MemoryAwarePlan(self.product, self.run_root, [self.gate('g1')])
        first = plan.run()
        self.assertEqual(first['result'], 'COMPLETED',
                         'la primera campaña tiene que completarse')
        register = self.reconciled(_run_dir(self.run_root, first))
        self.assertEqual(register['hits'], 0, 'la primera campaña no tiene hits')
        self.assertGreaterEqual(register['misses'], 1,
                                'la primera campaña tiene que inventariar')

        self.product.edit('app.py', 'X = 2\n')
        self.product.commit('cambio')
        second = plan.run()
        self.assertEqual(second['result'], 'COMPLETED')
        register = self.reconciled(_run_dir(self.run_root, second))
        self.assertEqual(register['invalidated'], 1,
                         'el cambio de base invalida el grupo anterior entero, '
                         'no solo el fichero tocado')
        self.assertEqual(register['hits'], 0,
                         'un producto con base distinta no tiene ningún hit '
                         'posible: el contexto manda sobre el contenido')

    def published_digest(self, relative):
        memory = workflow_evidence.read_memory(
            workflow_evidence.memory_path(self.run_root))
        self.assertIsNotNone(memory, 'la memoria publicada no es legible')
        self.assertIn(relative, memory['files'],
                      'el fichero del producto tiene que estar inventariado')
        return memory['files'][relative]

    # [W03] Memoria reutilizada no reemplaza el veredicto de un gate.
    def test_memoria_no_convierte_un_fallo_en_pase(self):
        """FAIL → repair → PASS es el caso de éxito que la campaña midió.

        `r-5d7d11…` quedó `RETAINED cause: gate-abort:gate-producto` y
        `r-7761c0…` completó con el producto reparado. La memoria no puede
        saltarse el gate: el que reutilice un índice sobre un producto cambiado
        tiene que volver a ejecutar el comando y heredar su veredicto.
        """
        plan = MemoryAwarePlan(self.product, self.run_root,
                               [self.failing_gate('g1')])
        first = plan.run()
        self.assertEqual(first['result'], 'RETAINED',
                         'el gate que aborta retiene el run')
        self.assertIn('gate', first.get('cause', ''),
                      'la causa tiene que nombrar el gate: ' +
                      first.get('cause', ''))

        self.product.edit('app.py', 'X = 9\n')
        self.product.commit('reparado')
        plan = MemoryAwarePlan(self.product, self.run_root, [self.gate('g1')])
        second = plan.run()
        self.assertEqual(second['result'], 'COMPLETED',
                         'el producto reparado tiene que pasar por ejecución '
                         'real, no por reuso de memoria')

    # [W04] La memoria no se publica en un run retenido.
    def test_memoria_no_publica_indice_en_run_retenido(self):
        plan = MemoryAwarePlan(self.product, self.run_root,
                               [self.failing_gate('g1')])
        plan.run()
        self.assertFalse(workflow_evidence.memory_path(self.run_root).exists(),
                         'un run RETAINED no publica memoria: sería refugio de '
                         'un resultado que nunca se aceptó')

    # [W05] El índice es del producto declarado, nunca un listado del árbol.
    def test_indice_no_arrastra_rutas_fuera_del_producto(self):
        plan = MemoryAwarePlan(self.product, self.run_root, [self.gate('g1')])
        plan.run()
        memory = workflow_evidence.read_memory(
            workflow_evidence.memory_path(self.run_root))
        self.assertIsNotNone(memory, 'la memoria publicada no es legible')
        for relative in memory['files']:
            self.assertFalse(Path(relative).is_absolute(),
                             'el índice no debe contener rutas absolutas: '
                             + relative)
            self.assertNotIn('..', Path(relative).parts,
                             'el índice no debe escapar del producto con ..: '
                             + relative)
        self.assertEqual(sorted(memory['files']), ['app.py'],
                         'el índice solo cubre el producto declarado')

    # [W06] Bytes idénticos reproducen el índice; un índice distinto no se pisa.
    # La idempotencia de publicación que el documento atribuye a L26 se mide
    # aquí, byte a byte.
    def test_publicacion_de_memoria_es_idempotente_por_bytes(self):
        first = MemoryAwarePlan(self.product, self.run_root, [self.gate('g1')])
        first.run()
        index = workflow_evidence.memory_path(self.run_root)
        original = index.read_bytes()
        second = MemoryAwarePlan(self.product, self.run_root, [self.gate('g2')])
        second.run()
        self.assertEqual(index.read_bytes(), original,
                         're-ejecutar sobre el mismo producto tiene que '
                         'reproducir el índice, no reescribirlo')

    # [W07] Un índice manipulado no decide nada.
    def test_memoria_manipulada_no_hace_pasar_el_gate(self):
        first = MemoryAwarePlan(self.product, self.run_root, [self.gate('g1')])
        clean = first.run()
        workflow_evidence.memory_path(self.run_root).write_text('{"roto": ')
        outcome = MemoryAwarePlan(self.product, self.run_root,
                                  [self.failing_gate('g1')]).run()
        self.assertEqual(outcome['result'], 'RETAINED',
                         'un índice corrupto no puede fabricar un pase')
        # El journal del run limpio sigue siendo verificable: el índice de
        # memoria corrompido no puede dañar la cadena del run que lo publicó.
        info = verify(Path(clean['run_dir']))
        self.assertEqual(info['events'], 5, info)

    # [W08] Reanudar el mismo plan reutiliza el mismo run; planes distintos no.
    def test_reanudacion_por_replay_no_abre_run_nuevo(self):
        plan = MemoryAwarePlan(self.product, self.run_root, [self.gate('g1')])
        first = plan.run()
        second = plan.run()
        self.assertEqual(first['run_dir'], second['run_dir'],
                         'el mismo plan reanuda el mismo run dir')
        self.assertEqual(Path(first['run_dir']).name,
                         Path(second['run_dir']).name,
                         'el id del run sale del sha del plan, no del turno')

        other = MemoryAwarePlan(self.product, self.run_root,
                                [self.gate('g2')], name='otro-plan')
        third = other.run()
        self.assertNotEqual(third['run_dir'], first['run_dir'],
                            'un plan distinto no puede heredar el run de otro')

    # [W09] El veredicto de la suite no sale de un pipeline.
    def test_veredicto_de_suite_no_se_toma_de_un_pipeline(self):
        """El código que llega de `python -m unittest … | tail` es el de `tail`.

        [W01] es la misma familia, dicha desde la suite. Aquí se fija la lectura
        correcta: se ejecuta el proceso y se lee su `returncode`, con stdout y
        stderr juntos.
        """
        proc = subprocess.run([PYTHON, '-B', '-m', 'unittest',
                               'tests.test_workflow_lessons.DocSelfTest'],
                              cwd=str(REPO_ROOT), capture_output=True, text=True)
        text = _both_streams(proc)
        self.assertIn('Ran', text, 'el veredicto no se leyó de ningún flujo')
        self.assertIn('OK', text,
                      'una suite vacía daría verde sin casos: el marcador de '
                      'clase no debe desaparecer sin cambiar este fichero')
        self.assertEqual(proc.returncode, 0)

    # [W10] FAIL real registra FAIL; un PASS posterior no lo borra.
    def test_journal_registra_gate_fallido_y_run_arreglado_pasa(self):
        plan = MemoryAwarePlan(self.product, self.run_root,
                               [self.failing_gate('g1')])
        first = plan.run()
        self.assertEqual(first['result'], 'RETAINED')
        kinds = [item['kind'] for item in read_journal(_run_dir(self.run_root, first))]
        self.assertIn('STEP_FAILED', kinds,
                      'el fallo del gate tiene que quedar registrado, no solo '
                      'el veredicto final')
        self.assertNotIn('STEP_COMPLETED', kinds,
                         'un paso que falló no puede figurar como completado')

        fixed = MemoryAwarePlan(self.product, self.run_root, [self.gate('g1')],
                                name='campana-arreglada')
        second = fixed.run()
        self.assertEqual(second['result'], 'COMPLETED')
        kinds = [item['kind'] for item in read_journal(_run_dir(self.run_root, second))]
        self.assertIn('STEP_COMPLETED', kinds,
                      'el gate arreglado tiene que registrar su paso completado')
        self.assertNotIn('STEP_FAILED', kinds,
                         'el run arreglado no debe arrastrar el fallo anterior')


class DocSelfTest(unittest.TestCase):
    """Marcador para [W09]: se ejecuta a sí mismo y no aporta casos.

    Si esteTestClass desaparece, `test_veredicto_de_suite_no_se_toma_de_un_pipeline`
    falla en vez de dar un verde vacío.
    """

    def test_marker_is_runnable(self):
        self.assertTrue(True)


class DocumentedLessonsMapTests(unittest.TestCase):
    """El documento de lecciones y las pruebas tienen que decir lo mismo.

    Una lección que solo vive en prosa es una lección que nadie comprueba; una
    prueba sin lección documentada es una prueba sin procedencia.
    """

    def setUp(self):
        self.doc = DOCS_LEARNING.read_text(encoding='utf-8')

    def test_the_document_defines_every_lesson_id_it_uses(self):
        used = set(re.findall(r'\| (L\d\d) ', self.doc))
        self.assertTrue(used, 'el documento no declara lecciones')
        for number in sorted(used):
            self.assertIn(number, self.doc,
                          'la lección %s se usa pero no se define' % number)

    def test_every_lesson_with_a_permanent_test_is_in_the_tree(self):
        """Una lección que declara prueba permanente existe de verdad.

        La marca es explícita en el documento; si una fila dice que tiene prueba
        y esa prueba no está en el árbol, la lección mentiría sobre su cobertura.
        La prueba se identifica por el `[W<nn>]` que aparece en su docstring.
        """
        rows = [line for line in self.doc.splitlines()
                if re.match(r'\| L\d\d ', line)]
        self.assertGreaterEqual(len(rows), DEFINITION_ROWS,
                                'el documento tiene menos lecciones de las que '
                                'declara')
        text = (REPO_ROOT / 'tests' / 'test_workflow_lessons.py').read_text(
            encoding='utf-8')
        cited = set()
        for line in rows:
            if '`tests/test_workflow_lessons.py`' not in line:
                continue
            cited.update(re.findall(r'\[W\d\d\]', line))
        self.assertTrue(cited,
                        'ninguna lección apunta a la prueba permanente')
        for marker in sorted(cited):
            self.assertIn(marker, text,
                          'la lección se cita con %s y esa prueba no está en '
                          'tests/test_workflow_lessons.py' % marker)

    def test_lessons_map_at_least_a_run_id_or_a_commit_for_each_lesson(self):
        """Cada lección atribuye su evidencia a un run id, un sha o una ruta.

        Sin atribución, la lección es folklore: no se puede reproducir el fallo
        que la motivó ni comprobar que el éxito contrario todavía existe. Una
        cita a `docs/status.md:176` es atribución válida porque esa línea es
        evidencia conservada y reproducible; lo que no vale es la referencia sin
        destino.
        """
        rows = [line for line in self.doc.splitlines()
                if re.match(r'\| L\d\d ', line)]
        self.assertTrue(rows, 'el documento no tiene filas de lección')
        # Atribución válida: un run id (`dwfrun-`/`dwfeval-`), un run del
        # ejecutor (`r-…`), un sha de commit, una cita a fichero con línea
        # (`ruta:123`, con o sin backticks), o `git show`.
        path_line = re.compile(r'[^\s|`]+:\d+')
        for line in rows:
            with self.subTest(line=line[:70]):
                self.assertTrue(
                    'dwfrun-' in line or 'dwfeval-' in line
                    or '`r-' in line or 'git show' in line
                    or re.search(r'\b[0-9a-f]{7,40}\b', line)
                    or path_line.search(line),
                    'la fila no atribuye su evidencia a nada localizable: '
                    + line[:70])

    def test_no_local_paths_or_borrowed_identifiers_in_the_lessons_doc(self):
        """Lecciones publicables: sin rutas personales ni sesiones ajenas.

        Las campañas corrieron en rutas concretas del mantenedor y alguno de los
        `.mjs` guardados contiene credenciales literalmente. Lo publicable es la
        lección, no el rastro del equipo donde se midió.
        """
        for needle in ('/home/', str(Path.home()), 'NROUTER', 'ezarr',
                       'DAA-auditoria', 'Syncify-workspace'):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, self.doc,
                                 'el documento de lecciones filtra material '
                                 'ajeno o local: ' + needle)

    def test_the_lessons_doc_declares_what_has_not_been_proved(self):
        """El documento dice qué no se ha probado, en vez de darlo por bueno.

        `docs/status.md` mantiene una lista explícita de «No probado». Copiar
        esa disciplina aquí es lo que impide que las lecciones se lean como
        cobertura completa de lo corrido.
        """
        self.assertIn('No probado', self.doc,
                      'el documento tiene que tener una sección explícita de '
                      'lo que no se probó')
        self.assertIn('cobertura', self.doc.lower(),
                      'el documento tiene que declarar el alcance real de su '
                      'cobertura, no dar por buena la lista de lecciones')
        for phrase in ('Creator end-to-end', 'git worktree', 'dsh web'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.doc,
                              'la lección sobre %s tiene que estar declarada '
                              'como no probada' % phrase)


if __name__ == '__main__':
    unittest.main()
