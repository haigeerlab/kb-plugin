import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "plugins/kb/scripts/kb.py"


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.config = self.base / "config dir/config.json"
        self.vault = self.base / "知识库 with spaces"
        self.vault.mkdir()
        self.env = dict(os.environ, KB_CONFIG=str(self.config))

    def run_cli(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, "-B", str(CLI), *args],
            env=self.env, cwd=cwd or self.base, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def write_config(self, content):
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(json.dumps(content), encoding="utf-8")

    def assert_config_error(self, reason):
        for flags in ((), ("--json",)):
            with self.subTest(flags=flags):
                result = self.run_cli("doctor", *flags)
                self.assertEqual(result.returncode, 2, result)
                output = result.stdout + result.stderr
                self.assertIn(str(self.config), output)
                self.assertIn("config set-vault", output)
                self.assertIn(reason, output)
                self.assertNotIn("Traceback", output)
                if flags:
                    payload = json.loads(result.stdout)
                    self.assertFalse(payload["ok"])
                    self.assertIsNone(payload["vault"])
                    self.assertEqual(payload["config"], str(self.config))
                    self.assertEqual(set(payload), {"ok", "config", "vault", "checks", "error"})

    def test_missing_config(self):
        self.assert_config_error("未找到配置")
        self.assertFalse(self.config.parent.exists())

    def test_corrupt_json(self):
        self.config.parent.mkdir()
        self.config.write_text("{broken", encoding="utf-8")
        self.assert_config_error("JSON")

    def test_unsupported_version(self):
        self.write_config({"version": 2, "vault": str(self.vault)})
        self.assert_config_error("version")

    def test_nonexistent_vault(self):
        self.write_config({"version": 1, "vault": str(self.base / "missing")})
        self.assert_config_error("不存在")

    def test_vault_is_file(self):
        path = self.base / "file"
        path.touch()
        self.write_config({"version": 1, "vault": str(path)})
        self.assert_config_error("不是目录")

    def test_relative_vault(self):
        self.write_config({"version": 1, "vault": self.vault.name})
        self.assert_config_error("绝对路径")

    def test_invalid_config_shapes(self):
        for content in ([], None, {}, {"version": True, "vault": str(self.vault)},
                        {"version": 1, "vault": 7}, {"version": 1, "vault": ""}):
            with self.subTest(content=content):
                self.write_config(content)
                self.assert_config_error("配置")

    def test_invalid_encoding(self):
        self.config.parent.mkdir()
        self.config.write_bytes(b"\xff")
        self.assert_config_error("读取")

    def test_preview_does_not_create_config_directory(self):
        result = self.run_cli("config", "set-vault", self.vault.name)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.config), result.stdout)
        self.assertIn(str(self.vault), result.stdout)
        self.assertIn('"version": 1', result.stdout)
        self.assertIn("--confirm", result.stdout)
        self.assertFalse(self.config.parent.exists())

    def test_preview_preserves_existing_config(self):
        self.write_config({"version": 1, "vault": str(self.base)})
        previous = self.config.read_bytes()
        result = self.run_cli("config", "set-vault", str(self.vault), "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["content"], {"version": 1, "vault": str(self.vault)})
        self.assertFalse(payload["written"])
        self.assertEqual(self.config.read_bytes(), previous)

    def test_confirm_then_doctor(self):
        result = self.run_cli("config", "set-vault", self.vault.name, "--confirm", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["written"])
        self.assertEqual(json.loads(self.config.read_text()), {"version": 1, "vault": str(self.vault)})
        result = self.run_cli("doctor")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.vault), result.stdout)
        self.assertIn("通过", result.stdout)

    def test_doctor_independent_of_cwd(self):
        self.write_config({"version": 1, "vault": str(self.vault)})
        other = self.base / "unrelated project"
        other.mkdir()
        vaults = []
        for cwd in (ROOT, other, self.base):
            result = self.run_cli("doctor", "--json", cwd=cwd)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(set(payload), {"ok", "config", "vault", "checks", "error"})
            vaults.append(payload["vault"])
        self.assertEqual(vaults, [str(self.vault)] * 3)

    def test_set_vault_rejects_invalid_path(self):
        file_path = self.base / "file"
        file_path.touch()
        for path in (file_path, self.base / "missing"):
            with self.subTest(path=path):
                result = self.run_cli("config", "set-vault", str(path), "--confirm", "--json")
                self.assertEqual(result.returncode, 2, result)
                self.assertFalse(json.loads(result.stdout)["ok"])
                self.assertFalse(self.config.exists())

    def test_write_error_is_configuration_error(self):
        self.config.parent.write_text("blocks parent directory", encoding="utf-8")
        result = self.run_cli("config", "set-vault", str(self.vault), "--confirm")
        self.assertEqual(result.returncode, 2, result)
        self.assertIn(str(self.config), result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_doctor_check_problem_exits_one(self):
        self.write_config({"version": 1, "vault": str(self.vault)})
        code = (
            "import sys; from unittest.mock import patch; "
            f"sys.path.insert(0, {str(CLI.parent)!r}); import kb; "
            "patcher = patch('kblib.doctor.os.access', return_value=False); "
            "patcher.start(); sys.exit(kb.main(['doctor', '--json']))"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", code], env=self.env, cwd=self.base,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 1, result)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["vault"], str(self.vault))
        self.assertTrue(any(not check["ok"] for check in payload["checks"]))

    def test_usage_errors_and_help_are_chinese(self):
        for args in ((), ("unknown",), ("config",), ("config", "set-vault"), ("doctor", "--unknown")):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2, result)
                self.assertIn("用法", result.stderr)
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("用法", result.stdout)


if __name__ == "__main__":
    unittest.main()
