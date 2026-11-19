import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = (
    ".claude-plugin/marketplace.json",
    "plugins/kb/.claude-plugin/plugin.json",
    "plugins/kb/.codex-plugin/plugin.json",
)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.env = dict(os.environ, KB_CONFIG=str(self.base / "config.json"))
        self.copy = self.base / "plugin copy"
        for relative in (*MANIFESTS, "scripts/check-manifests.py"):
            target = self.copy / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        (self.copy / "plugins/kb/skills/doctor").mkdir(parents=True)

    def run_check(self, root):
        return subprocess.run(
            [sys.executable, "-B", str(root / "scripts/check-manifests.py")],
            cwd=self.base, env=self.env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def mutate(self, relative, key, value):
        path = self.copy / relative
        data = json.loads(path.read_text(encoding="utf-8"))
        if relative == MANIFESTS[0] and key in ("version", "source"):
            data["plugins"][0][key] = value
        else:
            data[key] = value
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_repository_manifests_pass(self):
        result = self.run_check(ROOT)
        self.assertEqual(result.returncode, 0, result)
        self.assertIn("通过", result.stdout)

    def test_changed_versions_fail_in_temporary_copy(self):
        for relative in MANIFESTS:
            with self.subTest(relative=relative):
                self.mutate(relative, "version", "9.9.9")
                result = self.run_check(self.copy)
                self.assertEqual(result.returncode, 1, result)
                self.assertIn("版本", result.stdout + result.stderr)
                self.mutate(relative, "version", "0.1.0")

    def test_changed_name_and_description_fail(self):
        for key, value, reason in (("name", "other", "名称"), ("description", "描述已改变。", "描述")):
            with self.subTest(key=key):
                path = self.copy / MANIFESTS[1]
                original = path.read_bytes()
                self.mutate(MANIFESTS[1], key, value)
                result = self.run_check(self.copy)
                self.assertEqual(result.returncode, 1, result)
                self.assertIn(reason, result.stdout + result.stderr)
                path.write_bytes(original)

    def test_missing_skills_directory_fails(self):
        shutil.rmtree(self.copy / "plugins/kb/skills")
        result = self.run_check(self.copy)
        self.assertEqual(result.returncode, 1, result)
        self.assertIn("skills", result.stdout + result.stderr)

    def test_invalid_json_fails_without_traceback(self):
        (self.copy / MANIFESTS[1]).write_text("{broken", encoding="utf-8")
        result = self.run_check(self.copy)
        self.assertEqual(result.returncode, 1, result)
        self.assertIn("JSON", result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
