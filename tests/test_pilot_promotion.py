import json
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pilot
import promotion

class PilotPromotionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.project = self.root / "project"; self.project.mkdir()

    def test_plan_python_and_multipart(self):
        for kind in ("python-backend", "multipart"):
            plan = pilot.create_plan(self.project, self.root / kind, kind)
            self.assertEqual(plan["kind"], kind)

    def test_feedback_rejects_secrets(self):
        with self.assertRaises(ValueError):
            pilot.record(self.root / "feedback.json", "note", note="api_key leaked")

    def test_promotion_requires_clean_git(self):
        subprocess.run(["git", "init", str(self.root / "repo")], capture_output=True, check=True)
        with self.assertRaises(ValueError):
            promotion.prepare(self.root / "repo")

    def test_publish_requires_authorization(self):
        with self.assertRaises(PermissionError):
            promotion.publish({"published": False})

if __name__ == "__main__":
    unittest.main()
