"""Pruebas del almacén de la libreta.

Ejecutan las operaciones contra un directorio temporal propio; nada toca el
resto del equipo.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from libreta import storage


class PruebasAlmacen(unittest.TestCase):
    def setUp(self):
        self.datos = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.datos, ignore_errors=True)

    def test_anadir_y_listar(self):
        nota = storage.anadir_nota(self.datos, "Compra", "Pan y leche")
        guardadas = storage.listar_notas(self.datos)
        self.assertEqual([guardada["id"] for guardada in guardadas],
                         [nota["id"]])
        self.assertEqual(guardadas[0]["titulo"], "Compra")
        self.assertEqual(guardadas[0]["cuerpo"], "Pan y leche")
        self.assertTrue(guardadas[0]["creada"])

    def test_buscar_por_titulo_y_por_cuerpo(self):
        storage.anadir_nota(self.datos, "Compra", "Pan y leche")
        storage.anadir_nota(self.datos, "Cine", "Ver una película")
        por_cuerpo = storage.buscar_notas(self.datos, "leche")
        self.assertEqual([nota["titulo"] for nota in por_cuerpo], ["Compra"])
        por_titulo = storage.buscar_notas(self.datos, "cine")
        self.assertEqual([nota["titulo"] for nota in por_titulo], ["Cine"])
        self.assertEqual(storage.buscar_notas(self.datos, "silla de ruedas"),
                         [])

    def test_eliminar_nota_inexistente_falla(self):
        with self.assertRaises(storage.NotaInexistente):
            storage.eliminar_nota(self.datos, "no-existe")

    def test_eliminar_deja_el_almacen_vacio(self):
        nota = storage.anadir_nota(self.datos, "Compra", "Pan y leche")
        storage.eliminar_nota(self.datos, nota["id"])
        self.assertEqual(storage.listar_notas(self.datos), [])


if __name__ == "__main__":
    unittest.main()
