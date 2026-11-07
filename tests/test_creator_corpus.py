"""El comando de corpus: puntaje determinista y fail-closed del índice.

El índice vive junto a los casos (`eval/cases/index.json`); los journals son
evidencia externa referida por nombre y digest: el comando los verifica antes
de calificar y un digest que no cuadra es error, no un caso silenciosamente
saltado. El puntaje es una lectura: no escribe nada y los campos que no puede
medir los omite, nunca los inventa.
"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import creator_eval


def _facts(**overrides):
    facts = {
        "generation_id": "gen-test",
        "model": "provider/model",
        "project": {"root_identity": "a" * 64},
        "manifest_present": True,
        "prevalidation_passed": True,
        "journal_event_count": 2,
        "journal_last_seq": 1,
        "usage_tokens": 1000,
        "usage_input_tokens": 200,
        "usage_cache_read_tokens": 700,
        "usage_output_tokens": 100,
        "usage_steps": 4,
        "elapsed_seconds": 12.5,
    }
    facts.update(overrides)
    return facts


def _criteria(**overrides):
    criteria = {
        "id": "case",
        "forbidden_schema_reads": ["modes.schema.json", "skills.schema.json"],
        "require_manifest": True,
        "require_prevalidation": True,
    }
    criteria.update(overrides)
    return criteria


def _events():
    return [
        {"type": "tool/call", "seq": 0,
         "data": {"name": "read",
                  "arguments": json.dumps({"path": "product/src/main.py"})}},
        {"type": "tool/call", "seq": 1,
         "data": {"name": "bash", "arguments": json.dumps({"command": "ls generated"})}},
    ]


class CorpusTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cases = self.root / "cases"
        self.evidence = self.root / "evidence"

    def _case(self, cid, facts, criteria=None, events=None, digest=None):
        """Escribe un caso en `cases/<id>` y su journal en la evidencia externa."""
        self.cases.mkdir(parents=True, exist_ok=True)
        self.evidence.mkdir(parents=True, exist_ok=True)
        case = self.cases / cid
        case.mkdir()
        (case / "facts.json").write_text(
            json.dumps(facts, ensure_ascii=False), encoding="utf-8")
        (case / "criteria.json").write_text(
            json.dumps(criteria or _criteria(), ensure_ascii=False), encoding="utf-8")
        raw = "".join(json.dumps(event) + "\n"
                      for event in (events or _events())).encode("utf-8")
        journal = self.evidence / f"{cid}.journal.jsonl"
        journal.write_bytes(raw)
        return {
            "id": cid,
            "expected_verdict": "PASS",
            "prompt_version": "1.11.0",
            "run_id": f"run-{cid}",
            "journal": journal.name,
            "journal_sha256": digest or hashlib.sha256(raw).hexdigest(),
        }

    def _write_index(self, entries):
        self.cases.mkdir(parents=True, exist_ok=True)
        path = self.cases / "index.json"
        path.write_text(json.dumps({"cases": entries}, ensure_ascii=False),
                        encoding="utf-8")
        return path


class CorpusScoreTest(CorpusTestBase):
    def test_score_agrees_with_expected_verdicts(self):
        """Dos casos coherentes: puntaje 2/2, sin desvíos, lectura pura."""
        green = self._case("verde", _facts())
        red_events = _events()
        red = self._case("rojo", _facts(prevalidation_passed=False,
                                        journal_event_count=2),
                         events=red_events)
        red["expected_verdict"] = "FAIL_COMPLETION"
        index = self._write_index([green, red])
        score = creator_eval.score_corpus(index, evidence_root=self.evidence)
        self.assertEqual(score["cases"], 2)
        self.assertEqual(score["correct"], 2)
        self.assertEqual(score["abstain"], 0)
        self.assertEqual(score["mismatches"], [])
        self.assertEqual(score["errors"], [])
        self.assertEqual(score["prompt_versions"], ["1.11.0"])
        self.assertNotIn("prompt_bytes", score,
                         "sin fichero de prompt, los bytes se omiten, no se inventan")
        details = {item["id"]: item for item in score["details"]}
        self.assertEqual(details["verde"]["actual"], "PASS")
        self.assertEqual(details["rojo"]["actual"], "FAIL_COMPLETION")

    def test_score_flags_a_mismatch_against_the_expected_verdict(self):
        entry = self._case("desviado", _facts())
        entry["expected_verdict"] = "ABSTAIN"
        index = self._write_index([entry])
        score = creator_eval.score_corpus(index, evidence_root=self.evidence)
        self.assertEqual(score["correct"], 0)
        self.assertEqual(score["mismatches"],
                         ["desviado"], "el desvío es dato del puntaje, no error")

    def test_score_counts_abstain(self):
        facts = _facts()
        del facts["model"]
        entry = self._case("incompleto", facts)
        index = self._write_index([entry])
        score = creator_eval.score_corpus(index, evidence_root=self.evidence)
        self.assertEqual(score["abstain"], 1)
        self.assertNotIn(score["details"][0]["actual"], ("PASS", "FAIL_COMPLETION"))

    def test_prompt_bytes_only_with_an_explicit_file(self):
        entry = self._case("verde", _facts())
        index = self._write_index([entry])
        prompt = self.root / "prompt.txt"
        prompt.write_text("x" * 1234, encoding="utf-8")
        score = creator_eval.score_corpus(index, evidence_root=self.evidence,
                                          prompt_path=prompt)
        self.assertEqual(score["prompt_bytes"], 1234)


class CorpusFailClosedTest(CorpusTestBase):
    def test_a_digest_that_disagrees_is_an_error_not_a_skip(self):
        entry = self._case("manipulado", _facts(), digest="0" * 64)
        index = self._write_index([entry])
        score = creator_eval.score_corpus(index, evidence_root=self.evidence)
        self.assertEqual([error["id"] for error in score["errors"]], ["manipulado"])
        self.assertNotIn("correct", score,
                         "un corpus con errores no emite puntaje parcial como si fuera sano")

    def test_a_missing_journal_is_an_error(self):
        entry = self._case("sin-evidencia", _facts())
        (self.evidence / entry["journal"]).unlink()
        index = self._write_index([entry])
        score = creator_eval.score_corpus(index, evidence_root=self.evidence)
        self.assertEqual(len(score["errors"]), 1)
        self.assertIn("journal", score["errors"][0]["reason"].lower())

    def test_a_missing_case_directory_is_an_error(self):
        entry = self._case("fantasma", _facts())
        import shutil
        shutil.rmtree(self.cases / "fantasma")
        index = self._write_index([entry])
        score = creator_eval.score_corpus(index, evidence_root=self.evidence)
        self.assertEqual(len(score["errors"]), 1)

    def test_errors_fail_the_command(self):
        entry = self._case("manipulado", _facts(), digest="0" * 64)
        index = self._write_index([entry])
        code = creator_eval.main(["--corpus", str(index),
                                  "--evidence", str(self.evidence)])
        self.assertEqual(code, 1, "errores de integridad: salida 1, no 0")

    def test_main_scores_a_healthy_corpus(self):
        entry = self._case("verde", _facts())
        index = self._write_index([entry])
        code = creator_eval.main(["--corpus", str(index),
                                  "--evidence", str(self.evidence)])
        self.assertEqual(code, 0)


class CorpusIndexValidationTest(CorpusTestBase):
    def test_duplicate_ids_are_rejected(self):
        entry = self._case("duplicado", _facts())
        index = self._write_index([entry, dict(entry)])
        with self.assertRaises(ValueError):
            creator_eval.validate_index(index)

    def test_a_bad_digest_shape_is_rejected(self):
        entry = self._case("mal-digest", _facts())
        entry["journal_sha256"] = "no-es-hex"
        index = self._write_index([entry])
        with self.assertRaises(ValueError):
            creator_eval.validate_index(index)

    def test_a_missing_key_is_rejected(self):
        entry = self._case("incompleto", _facts())
        del entry["prompt_version"]
        index = self._write_index([entry])
        with self.assertRaises(ValueError):
            creator_eval.validate_index(index)

    def test_an_empty_corpus_is_rejected(self):
        index = self._write_index([])
        with self.assertRaises(ValueError):
            creator_eval.validate_index(index)


if __name__ == "__main__":
    unittest.main()
