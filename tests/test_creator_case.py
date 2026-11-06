"""Constructor del caso Creator desde el run terminado: costura --from-run.

Regresión (#12): un run sintético y un journal comprimido bajo un home DSH
temporal bastan para derivar hechos, escribir el caso y calificarlo con el
núcleo puro, sin modelo ni red. El journal indescubrible es un fallo cerrado
(sin caso) y la inconsistencia entre el cursor de la sesión y el journal
abstiene con el veredicto cerrado intacto.
"""
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import creator_case
import creator_eval

SESSION_ID = "session-creator-" + "a" * 32
GEN_ID = "gen-sintetico"
ROOT_IDENTITY = "c" * 64


def _events():
    """A synthetic DSH journal: header, one request, one turn, one tool call.

    Los frames con ``seq`` llevan ``time`` en ms de época: el intervalo del
    primero al último es la duración que el constructor deriva (1.34 s aquí).
    """
    return [
        {"type": "session", "version": 4, "id": SESSION_ID, "createdAt": 1,
         "cwd": "/tmp/producto", "isSeeded": False},
        {"type": "request/header", "seq": 0, "time": 1000,
         "data": {"header": {"config": {"provider": "proveedor-prueba",
                                        "model": "modelo-prueba",
                                        "maxTokens": 1000},
                             "adapterDefaults": {}, "tools": []}}},
        {"type": "turn/start", "seq": 1, "time": 1500, "data": {"turn": 1}},
        {"type": "tool/call", "seq": 2, "time": 2342,
         "data": {"name": "read",
                  "arguments": json.dumps({"path": "product/src/main.py"})}},
    ]


def _session(**overrides):
    state = {
        "schema_version": 1,
        "generation_id": GEN_ID,
        "session_id": SESSION_ID,
        "request_id": "creator-request-sintetico",
        "prompt_digest": "b" * 64,
        "deadline": 99.0,
        "max_tokens": 1000,
        "usage_by_seq": {"2": {"inputTokens": 200, "outputTokens": 100,
                               "cacheReadTokens": 700, "totalTokens": 1000}},
        "usage_steps": 4,
        "usage_input_tokens": 200,
        "usage_output_tokens": 100,
        "usage_cache_read_tokens": 700,
        "usage_tokens": 1000,
        "usage_accounted": True,
        "cursor": 2,
        "reason": "TERMINAL_QUIESCENT",
        "created_at": "2026-11-06T00:00:00+00:00",
        "terminal": True,
    }
    state.update(overrides)
    return state


def _run_doc():
    return {
        "schema_version": 1,
        "generation_id": GEN_ID,
        "status": "GENERATED",
        "created_at": "2026-11-06T00:00:00+00:00",
        "project": {"name": "product", "root_identity": ROOT_IDENTITY},
        "framework_revision": "revision-sintetica",
        "budget": {"max_attempts": 3, "max_tokens": 1000, "max_seconds": 60},
        "updated_at": "2026-11-06T00:01:00+00:00",
    }


def _request_doc():
    return {
        "schema_version": 1,
        "generation_id": GEN_ID,
        "prompt_version": "9.9.9",
        "prompt_digest": "b" * 64,
        "project_name": "product",
        "budget": {"max_attempts": 3, "max_tokens": 1000, "max_seconds": 60},
        "timestamp": "2026-11-06T00:00:01+00:00",
    }


def _criteria(**overrides):
    criteria = {
        "id": "caso-sintetico",
        "forbidden_schema_reads": ["modes.schema.json", "skills.schema.json"],
        "require_manifest": True,
        "require_prevalidation": True,
    }
    criteria.update(overrides)
    return criteria


class CreatorCaseFromRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="creator-case-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _write_json(self, path, payload):
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _write_run(self, *, session=None, with_manifest=True):
        """A synthetic finished run: run documents plus optional package."""
        run_dir = self.tmp / "creator-runs" / GEN_ID
        run_dir.mkdir(parents=True)
        self._write_json(run_dir / "run.json", _run_doc())
        self._write_json(run_dir / "generation-request.json", _request_doc())
        self._write_json(run_dir / "creator-session.json",
                         _session() if session is None else session)
        if with_manifest:
            generated = run_dir / "generated"
            generated.mkdir()
            (generated / "generation-manifest.json").write_text(
                json.dumps({"generation_id": GEN_ID}) + "\n", encoding="utf-8")
        return run_dir

    def _write_dsh_home(self, *, compressed=True, session_id=SESSION_ID):
        """A temp DSH home whose sessions hold the synthetic journal."""
        home = self.tmp / "dsh-home"
        session_dir = home / "sessions" / "--tmp-producto--" / session_id
        session_dir.mkdir(parents=True)
        journal = session_dir / "session.v4.jsonl.zstd"
        plain = self.tmp / "journal.jsonl"
        plain.write_text("".join(json.dumps(event) + "\n" for event in _events()),
                         encoding="utf-8")
        if compressed:
            subprocess.run(["zstd", "-q", "-o", str(journal), str(plain)],
                           check=True)
            plain.unlink()
        else:
            shutil.move(str(plain), str(journal))
        return home

    def _write_criteria(self):
        path = self.tmp / "criteria-source.json"
        self._write_json(path, _criteria())
        return path

    def _from_run(self, run_dir, home, case=None, extra=()):
        case = case or self.tmp / "caso"
        argv = ["--from-run", str(run_dir), "--case", str(case),
                "--criteria", str(self._write_criteria()),
                "--dsh-home", str(home)] + list(extra)
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            code = creator_eval.main(argv)
        return code, errors.getvalue(), Path(case)

    def _stub_report(self, passed=True):
        import types
        return types.SimpleNamespace(passed=passed,
                                     verdict="READY_FOR_ACCEPTANCE" if passed
                                     else "RETAINED")

    def test_from_run_derives_the_facts_writes_the_case_and_grades_it(self):
        """Run + compressed journal in: derived case and a PASS out."""
        if not shutil.which("zstd"):
            self.skipTest("zstd no disponible")
        run_dir = self._write_run()
        home = self._write_dsh_home()
        case = self.tmp / "caso"
        source_journal = (home / "sessions" / "--tmp-producto--" /
                          SESSION_ID / "session.v4.jsonl.zstd")
        with unittest.mock.patch.object(
                creator_case, "validate_package",
                return_value=self._stub_report(True)):
            code, errors, case = self._from_run(run_dir, home, case=case)
        self.assertEqual(code, 0, errors)

        facts = json.loads((case / "facts.json").read_text(encoding="utf-8"))
        self.assertEqual(facts["model"], "proveedor-prueba/modelo-prueba")
        self.assertEqual(facts["usage_input_tokens"], 200)
        self.assertEqual(facts["usage_output_tokens"], 100)
        self.assertEqual(facts["usage_tokens"], 1000)
        self.assertEqual(facts["usage_cache_read_tokens"], 700)
        self.assertEqual(facts["usage_steps"], 4)
        self.assertEqual(facts["stop_reason"], "TERMINAL_QUIESCENT")
        self.assertIs(facts["terminal_turn"], True)
        self.assertEqual(facts["turns_started"], 1)
        self.assertEqual(facts["elapsed_seconds"], 1.34)
        self.assertEqual(facts["journal_event_count"], 3)
        self.assertEqual(facts["journal_last_seq"], 2)
        self.assertIs(facts["manifest_present"], True)
        self.assertIs(facts["prevalidation_passed"], True)
        self.assertEqual(facts["project"],
                         {"name": "product", "root_identity": ROOT_IDENTITY})
        self.assertEqual(facts["framework_revision"], "revision-sintetica")
        self.assertEqual(facts["budget"],
                         {"max_attempts": 3, "max_tokens": 1000,
                          "max_seconds": 60})
        self.assertEqual(facts["prompt_version"], "9.9.9")
        self.assertEqual(facts["generation_id"], GEN_ID)

        self.assertEqual(json.loads(
            (case / "criteria.json").read_text(encoding="utf-8")), _criteria())
        copied = case / "session.v4.jsonl.zstd"
        self.assertEqual(copied.read_bytes(), source_journal.read_bytes())

        report = json.loads((case / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["case"], "caso-sintetico")
        self.assertEqual(report["journal_file"], "session.v4.jsonl.zstd")
        self.assertEqual(report["digests"]["journal"],
                         hashlib.sha256(copied.read_bytes()).hexdigest())

    def test_from_run_reruns_the_host_prevalidation_on_the_package(self):
        """The verdict is observed again, not trusted from the run documents."""
        if not shutil.which("zstd"):
            self.skipTest("zstd no disponible")
        run_dir = self._write_run(with_manifest=False)
        home = self._write_dsh_home()
        code, errors, case = self._from_run(run_dir, home)
        self.assertEqual(code, 0, errors)
        facts = json.loads((case / "facts.json").read_text(encoding="utf-8"))
        self.assertIs(facts["manifest_present"], False)
        self.assertIs(facts["prevalidation_passed"], False)
        report = json.loads((case / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["verdict"], "FAIL_COMPLETION")

    def test_from_run_abstains_when_the_session_disagrees_with_the_journal(self):
        """A cursor that the journal cannot confirm is incomplete evidence."""
        if not shutil.which("zstd"):
            self.skipTest("zstd no disponible")
        run_dir = self._write_run(session=_session(cursor=9))
        home = self._write_dsh_home()
        with unittest.mock.patch.object(
                creator_case, "validate_package",
                return_value=self._stub_report(True)):
            code, errors, case = self._from_run(run_dir, home)
        self.assertEqual(code, 0, errors)
        report = json.loads((case / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["verdict"], "ABSTAIN")
        self.assertIn("last_seq", report["reason"])

    def test_from_run_fails_closed_when_the_journal_is_not_discoverable(self):
        """No journal, no case: the error names the session and writes nothing."""
        if not shutil.which("zstd"):
            self.skipTest("zstd no disponible")
        run_dir = self._write_run()
        home = self._write_dsh_home(session_id="session-creator-" + "f" * 32)
        case = self.tmp / "caso"
        code, errors, case = self._from_run(run_dir, home, case=case)
        self.assertEqual(code, 2)
        self.assertIn(SESSION_ID, errors)
        self.assertFalse(case.exists())

    def test_from_run_derives_the_comparable_product_digest_when_given_the_root(self):
        """--project-root yields the tree digest the fixture manifest registered.

        La root_identity de run.json es el sha256 del sha1 del commit del
        producto y en CI varía por corrida; el valor comparable con el
        registrado en project-manifest.json es el digest de árbol del
        producto en la convención del framework. Con la raíz del fixture
        (una copia basta: el digest no sigue ni mtimes ni metadatos) los
        hechos llevan el digest registrado; sin raíz el campo se omite, que
        no se inventa identidad.
        """
        if not shutil.which("zstd"):
            self.skipTest("zstd no disponible")
        registered = json.loads(
            (ROOT / "fixtures" / "libreta" / "project-manifest.json")
            .read_text(encoding="utf-8"))["root_identity"]
        product = self.tmp / "producto"
        shutil.copytree(ROOT / "fixtures" / "libreta" / "product", product)
        run_dir = self._write_run()
        home = self._write_dsh_home()
        with unittest.mock.patch.object(
                creator_case, "validate_package",
                return_value=self._stub_report(True)):
            code, errors, case = self._from_run(
                run_dir, home, extra=["--project-root", str(product)])
        self.assertEqual(code, 0, errors)
        facts = json.loads((case / "facts.json").read_text(encoding="utf-8"))
        self.assertEqual(facts["product_tree_digest"], registered)

        without = self.tmp / "caso-sin-raiz"
        with unittest.mock.patch.object(
                creator_case, "validate_package",
                return_value=self._stub_report(True)):
            code, errors, case = self._from_run(run_dir, home, case=without)
        self.assertEqual(code, 0, errors)
        facts = json.loads((case / "facts.json").read_text(encoding="utf-8"))
        self.assertNotIn("product_tree_digest", facts)

    def test_from_run_fails_closed_when_the_validator_breaks(self):
        """An unexpected validator exception is infrastructure: exit 2, no case.

        Colapsar el fallo del validador en prevalidation_passed=False
        puntuaría un problema de infraestructura como un defecto del prompt
        evaluado. La derivación aborta como fallo cerrado (exit 2, ningún
        caso escrito); solo un veredicto definitivo del validador produce
        True/False, y un run sin paquete sigue siendo prevalidación no
        superada, el veredicto del caso real.
        """
        if not shutil.which("zstd"):
            self.skipTest("zstd no disponible")
        run_dir = self._write_run()
        home = self._write_dsh_home()
        case = self.tmp / "caso"

        def broken(generated, run_dir=None):
            raise RuntimeError("infraestructura del validador rota")

        with unittest.mock.patch.object(creator_case, "validate_package",
                                        broken):
            code, errors, case = self._from_run(run_dir, home, case=case)
        self.assertEqual(code, 2)
        self.assertIn("prevalidación Host falló de forma inesperada", errors)
        self.assertFalse(case.exists())

    def test_derive_facts_omits_the_duration_without_timestamped_frames(self):
        """No frame with ``time``, no duration: omitted, never zero."""
        run_dir = self._write_run()
        events = []
        for event in _events():
            event.pop("time", None)
            events.append(event)
        facts = creator_case.derive_facts(
            run_dir, events, _session(),
            validate=lambda *args, **kwargs: self._stub_report(True))
        self.assertNotIn("elapsed_seconds", facts)

    def test_from_run_resolves_the_dsh_home_from_the_environment(self):
        """Without the flag the home follows the same order as the client."""
        if not shutil.which("zstd"):
            self.skipTest("zstd no disponible")
        run_dir = self._write_run()
        home = self._write_dsh_home()
        case = self.tmp / "caso"
        argv = ["--from-run", str(run_dir), "--case", str(case),
                "--criteria", str(self._write_criteria())]
        with unittest.mock.patch.object(
                creator_case, "validate_package",
                return_value=self._stub_report(True)), \
                unittest.mock.patch.dict(os.environ,
                                         {"DSH_HOME": str(home)}):
            with contextlib.redirect_stderr(io.StringIO()):
                code = creator_eval.main(argv)
        self.assertEqual(code, 0)
        report = json.loads((case / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["verdict"], "PASS")

    def test_from_run_requires_the_pre_registered_criteria(self):
        """A case is never derived against a criterion nobody registered."""
        if not shutil.which("zstd"):
            self.skipTest("zstd no disponible")
        run_dir = self._write_run()
        home = self._write_dsh_home()
        case = self.tmp / "caso"
        argv = ["--from-run", str(run_dir), "--case", str(case),
                "--dsh-home", str(home)]
        with contextlib.redirect_stderr(io.StringIO()) as errors:
            code = creator_eval.main(argv)
        self.assertEqual(code, 2)
        self.assertIn("--criteria", errors.getvalue())
        self.assertFalse(case.exists())


if __name__ == "__main__":
    unittest.main()
