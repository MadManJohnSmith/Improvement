"""Binding del manifest: effective_routing_digest liga el roster declarado.

    python3 -B -m unittest tests.test_routing_digest_binding -v

Regresión de la colina proxy (ronda 0, run gen-78901d1c44fa, 2026-11-11):
`_manifest_derived` alimentaba al campo el digest de la configuración DSH
instalada (`inputs/effective-routing.json`, escrito por bootstrap sobre
`pf["dsh"]`), mientras `host_validator` exige el digest del roster de
routing declarado en los contratos del paquete (`skill_router._digest`).
Con roster de instalación vacío, cualquier generación que declarara
routing fallaba siempre la capa `contracts`. La derivación del Host y la
verificación deben partir de la misma forma canónica.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "scripts"))

import creator_client as cc
import skill_router
from test_creator_and_validator import Base


class EffectiveRoutingDigestTests(unittest.TestCase):
    def test_sin_filas_devuelve_digest_de_lista_vacia(self):
        with tempfile.TemporaryDirectory() as tmp:
            generated = Path(tmp)
            (generated / "contracts").mkdir()
            self.assertEqual(
                cc.effective_routing_digest(generated),
                skill_router._digest([]))

    def test_filas_declaradas_ligan_forma_canonica(self):
        with tempfile.TemporaryDirectory() as tmp:
            generated = Path(tmp)
            contracts = generated / "contracts"
            contracts.mkdir()
            routing = {"modes": ["auditor"], "actions": ["audit"],
                       "capability_set": ["read_product", "report"]}
            doc = {"schema_version": 1, "kind": "skill", "name": "x",
                   "routing": routing}
            (contracts / "x.skill.json").write_text(
                json.dumps(doc) + "\n", encoding="utf-8")
            self.assertEqual(
                cc.effective_routing_digest(generated),
                skill_router._digest([("x", routing)]))


class ManifestBindingTests(Base):
    def test_manifest_derived_liga_roster_declarado(self):
        """El campo derivado coincide con la forma que el validador recomputa."""
        generated = self.run_dir / "generated"
        contracts = generated / "contracts"
        contracts.mkdir(exist_ok=True)
        routing = {"modes": ["auditor"], "actions": ["audit"],
                   "capability_set": ["read_product", "report"]}
        doc = {"schema_version": 1, "kind": "skill", "name": "x",
               "routing": routing}
        (contracts / "x.skill.json").write_text(
            json.dumps(doc) + "\n", encoding="utf-8")
        derived = cc._manifest_derived(self.run_dir, generated)
        esperado = skill_router._digest([("x", routing)])
        self.assertEqual(derived["effective_routing_digest"], esperado)
        # La trampa exacta de la ronda 0: el campo nunca debe ser el digest
        # de la configuración DSH instalada mientras el paquete declara rows.
        instalado = json.loads(
            (self.run_dir / "inputs" / "effective-routing.json")
            .read_text(encoding="utf-8"))["routing_digest"]
        self.assertNotEqual(derived["effective_routing_digest"], instalado)


if __name__ == "__main__":
    unittest.main()
