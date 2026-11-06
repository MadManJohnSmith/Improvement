"""Fila del roster derivada del caso evaluado: costura offline del CLI.

Regresión (#16, spec #11): un caso sintético (facts.json + report.json
coherentes en un tempdir, sin datos reales) basta para que el CLI derive
la fila del roster con las columnas cerradas del spec y la escriba junto
al caso. La fila es una proyección cerrada: ningún campo de más del caso
(falsos secretos incluidos) pasa, y lo que el caso no registró se omite,
no se inventa. grade() y el modo --from-run no cambian.
"""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import creator_roster

GEN_ID = "gen-sintetico"
ROOT_IDENTITY = "c" * 64

# Las columnas del spec: la generación, la revisión del framework, la
# versión de prompt, el modelo, la identidad del producto, el presupuesto,
# el uso, los pasos, las llamadas de herramienta, las lecturas de schema,
# las llamadas al lector, el manifiesto, la prevalidación, el veredicto,
# el motivo, la parada, la duración y los eventos del journal; el journal
# referenciado cierra la fila y viaja como artefacto aparte (#11).
COLUMNS = frozenset({
    "generation_id", "framework_revision", "prompt_version", "model",
    "root_identity", "budget_tokens", "usage_tokens", "input_tokens",
    "cache_read_tokens", "output_tokens", "steps", "tool_calls",
    "schema_reads", "reader_calls", "manifest", "prevalidation_passed",
    "verdict", "reason", "stop_reason", "elapsed_seconds", "journal_events",
    "journal",
})


def _facts():
    """The facts a graded run leaves, plus two fields that must not pass."""
    return {
        "generation_id": GEN_ID,
        "project": {"name": "product", "root_identity": ROOT_IDENTITY},
        "framework_revision": "revision-sintetica",
        "budget": {"max_attempts": 3, "max_tokens": 500000, "max_seconds": 600},
        "prompt_version": "9.9.9",
        "model": "proveedor-prueba/modelo-prueba",
        "usage_input_tokens": 200,
        "usage_output_tokens": 100,
        "usage_cache_read_tokens": 700,
        "usage_tokens": 1000,
        "usage_steps": 4,
        "stop_reason": "TERMINAL_QUIESCENT",
        "terminal_turn": True,
        "journal_last_seq": 2,
        "turns_started": 1,
        "journal_event_count": 3,
        "manifest_present": True,
        "prevalidation_passed": True,
        # Campos que la proyección cerrada no deja pasar: un volcado de los
        # hechos sí lo haría, y con ellos viajan rutas y valores privados.
        "notas": "ruta y valor privados que no salen del caso",
        "provider_secret": "valor-sintetico-no-publicable",
    }


def _report(**counts_overrides):
    counts = {
        "tool_calls": {"read": 1},
        "schema_reads": {},
        "schema_read_events": {},
        "reader_calls": 0,
    }
    counts.update(counts_overrides)
    return {
        "verdict": "PASS",
        "reason": "criterios cumplidos",
        "case": "remote-creator-v1",
        "evidence": [{"criterion": "mechanism", "ok": True,
                      "detail": "sin lecturas completas de los schemas"}],
        "counts": counts,
        "descriptive": {"usage_tokens": 1000, "cache_read_tokens": 700,
                        "cache_share": 0.7, "steps": 4},
        "unknown_types": {},
        "malformed_events": 0,
        "seq_checked": True,
        "digests": {"facts": "0" * 64, "criteria": "1" * 64,
                    "journal": "2" * 64},
        "journal_file": "journal.jsonl",
        "entorno_del_run": {"clave_del_proveedor": "nombre-no-valor"},
    }


class CreatorRosterRowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="creator-roster-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _write_json(self, path, payload):
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _write_case(self, *, name="caso", facts=None, report=None,
                    with_journal=True):
        case = self.tmp / name
        case.mkdir()
        self._write_json(case / "facts.json",
                         _facts() if facts is None else facts)
        self._write_json(case / "report.json",
                         _report() if report is None else report)
        if with_journal:
            (case / "journal.jsonl").write_text(
                json.dumps({"type": "session", "version": 4}) + "\n",
                encoding="utf-8")
        return case

    def _derive(self, case, out):
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            code = creator_roster.main(
                ["--case", str(case), "--out", str(out)])
        return code, errors.getvalue()

    def test_the_row_is_derived_from_the_case_without_leaking_what_it_carries(self):
        """Every spec column maps from facts and report; nothing else passes.

        Un caso calificado deja facts.json y report.json con los campos que
        el constructor y el evaluador escriben. La fila los proyecta por
        nombre cerrado: las columnas del spec salen con su valor, y los
        campos de más que el caso pueda llevar (aquí dos falsos privados)
        no aparecen en la fila publicada, porque una fila que filtrara por
        omisión sería un volcado, no una proyección.
        """
        case = self._write_case()
        out = self.tmp / "fila.json"
        code, errors = self._derive(case, out)
        self.assertEqual(code, 0, errors)
        text = out.read_text(encoding="utf-8")
        row = json.loads(text)
        self.assertLessEqual(frozenset(row), COLUMNS,
                             "la fila tiene columnas fuera del spec")
        self.assertNotIn("valor-sintetico-no-publicable", text)
        self.assertNotIn("ruta y valor privados que no salen del caso", text)
        self.assertNotIn("nombre-no-valor", text)
        self.assertEqual(row["generation_id"], GEN_ID)
        self.assertEqual(row["framework_revision"], "revision-sintetica")
        self.assertEqual(row["prompt_version"], "9.9.9")
        self.assertEqual(row["model"], "proveedor-prueba/modelo-prueba")
        self.assertEqual(row["root_identity"], ROOT_IDENTITY)
        self.assertEqual(row["budget_tokens"], 500000)
        self.assertEqual(row["usage_tokens"], 1000)
        self.assertEqual(row["input_tokens"], 200)
        self.assertEqual(row["cache_read_tokens"], 700)
        self.assertEqual(row["output_tokens"], 100)
        self.assertEqual(row["steps"], 4)
        self.assertEqual(row["tool_calls"], {"read": 1})
        self.assertEqual(row["schema_reads"], {})
        self.assertEqual(row["reader_calls"], 0)
        self.assertIs(row["manifest"], True)
        self.assertIs(row["prevalidation_passed"], True)
        self.assertEqual(row["verdict"], "PASS")
        self.assertEqual(row["reason"], "criterios cumplidos")
        self.assertEqual(row["stop_reason"], "TERMINAL_QUIESCENT")
        self.assertEqual(row["journal_events"], 3)
        self.assertEqual(row["journal"], "journal.jsonl")
        # La duración no estaba en los hechos del caso: se omite, no se
        # inventa un cero.
        self.assertNotIn("elapsed_seconds", row)

    def test_an_unknowable_case_fails_closed_without_writing_a_row(self):
        """No graded case, no journal: exit 2 and nothing on disk.

        La fila solo sale de un caso que el evaluador calificó y cuyo
        journal está en el directorio: un reporte ausente o un journal que
        no viaja son fallos cerrados, nunca una fila con huecos rellenados
        o una referencia rota al artefacto que la sostiene.
        """
        out = self.tmp / "fila.json"
        without_report = self._write_case(name="sin-reporte")
        (without_report / "report.json").unlink()
        without_journal = self._write_case(name="sin-journal")
        (without_journal / "journal.jsonl").unlink()
        for label, case in (("sin reporte", without_report),
                            ("sin journal", without_journal)):
            with self.subTest(caso=label):
                code, errors = self._derive(case, out)
                self.assertEqual(code, 2, errors)
                self.assertFalse(out.exists(),
                                 "un caso indeterminable no escribe fila")


if __name__ == "__main__":
    unittest.main()
