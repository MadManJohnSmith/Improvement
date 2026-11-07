#!/usr/bin/env python3
"""Deriva el recuento de la suite y reescribe la cifra viva de los README.

El recuento publicado es una afirmación sobre este repositorio, ahora mismo,
y editarla a mano cada ronda es la versión frágil: la retrospectiva del
2026-11-06 publicó 1295 cuando la suite tenía 1294, dos veces. Aquí el número
se descubre como lo descubre el gate
`test_the_published_suite_count_is_the_count_that_runs`
(tests/test_architecture_consistency.py), que importa los mismos patrones de
este módulo: una sola fuente para quien afirma y quien reescribe.

Uso:
    python3 -B scripts/suite_count.py            # reescribe los README
    python3 -B scripts/suite_count.py --check    # solo verifica; salida 1 si difiere
"""
import re
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Cada entrada es (fichero, marcador de cifra histórica, patrón de la cifra
# viva, patrón de la fecha de medida). Una línea con el marcador histórico es
# historia: se le permite estar vieja y no se reescribe.
LIVE_CLAIMS = (
    ("README.md", "at that point",
     re.compile(r"Framework suite: \*\*(\d+) tests green\*\*"),
     re.compile(r"measured (\d{4}-\d{2}-\d{2})")),
    ("README.es.md", "en ese punto",
     re.compile(r"Suite del (?:propio )?framework: \*\*(\d+) pruebas en verde\*\*"),
     re.compile(r"medida el (\d{4}-\d{2}-\d{2})")),
)


def discovered_count(root=ROOT):
    return unittest.TestLoader().discover(str(root / "tests")).countTestCases()


def rewrite(root=ROOT, write=True, today=None):
    """Ajusta las cifras vivas al total descubierto.

    Devuelve la lista de (fichero, línea vieja, línea nueva) que necesitó
    cambio. Con write=False solo informa. La fecha de medida se estampa solo
    en las líneas que se reescriben: un recuento sin cambios conserva su
    fecha, porque la medición es de ese día.
    """
    today = today or date.today().isoformat()
    count = discovered_count(root)
    changes = []
    for relative, historical, claim, measured in LIVE_CLAIMS:
        path = root / relative
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        changed = False
        for index, line in enumerate(lines):
            said = claim.search(line)
            if not said or historical in line or int(said.group(1)) == count:
                continue
            new = claim.sub(lambda m: m.group(0).replace(m.group(1), str(count)), line)
            if measured.search(new):
                new = measured.sub(lambda m: m.group(0).replace(m.group(1), today), new)
            changes.append((relative, line, new))
            lines[index] = new
            changed = True
        if changed and write:
            path.write_text("".join(lines), encoding="utf-8")
    return changes


def main(argv=None):
    check = "--check" in (argv if argv is not None else sys.argv[1:])
    changes = rewrite(write=not check)
    if not changes:
        print("La cifra viva de los README coincide con la suite.")
        return 0
    for relative, old, new in changes:
        print(f"{relative}:")
        print(f"  - {old.strip()}")
        print(f"  + {new.strip()}")
    if check:
        print("El recuento publicado difiere de la suite (salida 1).")
        return 1
    print("READMEs reescritos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
