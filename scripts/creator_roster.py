"""Fila del roster derivada del caso evaluado del Creator.

Dado un directorio de caso (facts.json + report.json + el journal que el
evaluador calificó), proyecta la fila del roster con las columnas cerradas
del spec (#11, #16): la identidad comparable del producto
(``product_tree_digest`` cuando el caso la lleva) entra junto a la
identidad registrada del run. La fila es una proyección por nombre, nunca
un volcado: lo que el caso no registró se omite, no se inventa, y ningún
campo de más de los hechos o del reporte pasa a la fila publicada. El
workflow la sube como artefacto propio; versionar el roster sigue siendo
una decisión del mantenedor y el workflow no commitea nada.
"""

import argparse
import json
import sys
from pathlib import Path

FRAMEWORK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FRAMEWORK / "scripts"))

import creator_eval

ROW_FILE = "roster-row.json"


def derive_row(facts, report):
    """Project the roster row of one graded case from its facts and report.

    El veredicto, el motivo, el journal y los conteos vienen del reporte;
    el resto, de los hechos. Un campo ausente se omite para que la
    evidencia incompleta no se rellene con supuestos: los predicados
    "registrado u omitir" son los mismos del evaluador.
    """
    creator_eval.require_dict(facts, "facts.json")
    creator_eval.require_dict(report, "report.json")
    counts = report.get("counts")
    creator_eval.require_dict(counts, "Conteos del reporte")
    missing = [key for key in ("tool_calls", "schema_reads", "reader_calls")
               if key not in counts]
    missing += [key for key in ("verdict", "reason", "journal_file")
                if not isinstance(report.get(key), str) or not report[key]]
    if missing:
        raise ValueError(
            "report.json incompleto para la fila: %s" % ", ".join(missing))

    row = {}

    def take(key, value):
        if value is not None:
            row[key] = value

    take("generation_id", creator_eval.text_or_none(facts, "generation_id"))
    take("framework_revision",
         creator_eval.text_or_none(facts, "framework_revision"))
    take("prompt_version", creator_eval.text_or_none(facts, "prompt_version"))
    take("model", creator_eval.text_or_none(facts, "model"))
    project = facts.get("project")
    if isinstance(project, dict):
        take("root_identity", creator_eval.text_or_none(project, "root_identity"))
    take("product_tree_digest",
         creator_eval.text_or_none(facts, "product_tree_digest"))
    budget = facts.get("budget")
    if isinstance(budget, dict):
        take("budget_tokens", creator_eval.int_or_none(budget, "max_tokens"))
    take("usage_tokens", creator_eval.int_or_none(facts, "usage_tokens"))
    take("input_tokens", creator_eval.int_or_none(facts, "usage_input_tokens"))
    take("cache_read_tokens",
         creator_eval.int_or_none(facts, "usage_cache_read_tokens"))
    take("output_tokens", creator_eval.int_or_none(facts, "usage_output_tokens"))
    take("steps", creator_eval.int_or_none(facts, "usage_steps"))
    take("tool_calls", counts.get("tool_calls"))
    take("schema_reads", counts.get("schema_reads"))
    take("reader_calls", creator_eval.int_or_none(counts, "reader_calls"))
    if isinstance(facts.get("manifest_present"), bool):
        take("manifest", facts["manifest_present"])
    if isinstance(facts.get("prevalidation_passed"), bool):
        take("prevalidation_passed", facts["prevalidation_passed"])
    take("verdict", report["verdict"])
    take("reason", report["reason"])
    take("stop_reason", creator_eval.text_or_none(facts, "stop_reason"))
    elapsed = facts.get("elapsed_seconds")
    if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool):
        take("elapsed_seconds", elapsed)
    take("journal_events", creator_eval.int_or_none(facts, "journal_event_count"))
    take("journal", report["journal_file"])
    return row


def write_row(case_dir, out_path=None):
    """Derive the row of one case directory and write it as JSON.

    Por defecto la fila cae junto al caso. El journal que la fila
    referencia debe estar en el caso: una fila cuyo journal no viaja como
    artefacto aparte no se escribe.
    """
    case = Path(case_dir)
    facts, _ = creator_eval.read_json(case / "facts.json")
    report, _ = creator_eval.read_json(case / "report.json")
    row = derive_row(facts, report)
    if not (case / report["journal_file"]).is_file():
        raise ValueError(
            "El journal que la fila referencia no está en el caso: %s"
            % report["journal_file"])
    target = Path(out_path) if out_path else case / ROW_FILE
    creator_eval.write_report(target, json.dumps(
        row, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="creator_roster.py",
        description="Deriva la fila del roster de un caso evaluado del Creator.")
    parser.add_argument("--case", required=True,
                        help="Caso evaluado (facts.json + report.json + journal)")
    parser.add_argument("--out",
                        help="Fila a escribir; por defecto <case>/roster-row.json")
    args = parser.parse_args(argv)
    try:
        write_row(args.case, args.out)
    except (OSError, ValueError) as error:
        print(f"creator_roster: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
