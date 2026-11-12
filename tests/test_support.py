"""Regresión de `scripts/support.py`: digest sha256 y escritura atómica canónica.

El contrato: vector conocido de sha256 (y entrada vacía), `digest_file` en
streaming con más de un trozo, roundtrip bytes/str publicado con `os.replace`
verificable por el inodo, permiso preservado en destino, y un fallo de
publicación que no corrompe el destino ni deja el temporal en el camino.
"""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import support  # noqa: E402


class DigestTests(unittest.TestCase):
    """El vector conocido fija que es sha256 hexdigest, no otra cosa."""

    def test_known_vector_and_empty_input(self):
        self.assertEqual(
            support.digest_bytes(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        self.assertEqual(
            support.digest_bytes(b""),
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855")

    def test_bytes_only_a_str_is_rejected(self):
        """El contrato es bytes: quien tiene str codifica explícitamente."""
        with self.assertRaises(TypeError):
            support.digest_bytes("texto")

    def test_digest_file_streams_content_bigger_than_one_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = bytes(range(256)) * 512  # 128 KiB, más de un trozo de 64 KiB
            path = Path(tmp) / "grande.bin"
            path.write_bytes(raw)
            self.assertEqual(support.digest_file(path),
                             hashlib.sha256(raw).hexdigest())
            empty = Path(tmp) / "vacio.bin"
            empty.write_bytes(b"")
            self.assertEqual(support.digest_file(empty),
                             hashlib.sha256(b"").hexdigest())


class AtomicWriteTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="support-atomic-")
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_roundtrip_bytes_and_str_replaces_the_inode(self):
        dest = self.dir / "artefacto.json"
        dest.write_bytes(b"viejo")
        old_inode = dest.stat().st_ino
        support.atomic_write(dest, b"nuevo-bytes")
        self.assertEqual(dest.read_bytes(), b"nuevo-bytes")
        self.assertNotEqual(dest.stat().st_ino, old_inode)
        support.atomic_write(dest, "texto utf-8: ñ\n")
        self.assertEqual(dest.read_bytes(), "texto utf-8: ñ\n".encode("utf-8"))
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()),
                         ["artefacto.json"])

    def test_mode_is_preserved(self):
        private = self.dir / "privado.txt"
        support.atomic_write(private, "x", mode=0o640)
        self.assertEqual(private.stat().st_mode & 0o777, 0o640)
        default = self.dir / "por-defecto.txt"
        support.atomic_write(default, "x")
        self.assertEqual(default.stat().st_mode & 0o777, 0o600)

    def test_failed_publish_leaves_destination_and_no_temp(self):
        dest = self.dir / "destino.json"
        dest.write_bytes(b"contenido-vigente")
        with mock.patch("os.replace", side_effect=OSError("replace roto")):
            with self.assertRaises(OSError):
                support.atomic_write(dest, "nuevo")
        self.assertEqual(dest.read_bytes(), b"contenido-vigente")
        self.assertEqual([p.name for p in self.dir.iterdir()], ["destino.json"])


if __name__ == "__main__":
    unittest.main()
