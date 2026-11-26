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
        self.env = dict(os.environ, KB_CONFIG=str(self.config),
                        KB_STATE_DIR=str(self.base / 'state'),
                        KB_DELEGATE_DIR=str(self.base / 'delegate'))

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

    def test_redaction_preview_does_not_write(self):
        result = self.run_cli('config', 'init-redaction', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload['ok'])
        self.assertFalse(payload['written'])
        self.assertEqual(payload['create'], ['blocklist.txt', 'aliases.json'])
        self.assertEqual(payload['skip'], [])
        self.assertFalse(self.config.parent.exists())
        result = self.run_cli('config', 'init-redaction')
        self.assertIn('--confirm', result.stdout)
        self.assertIn('{"真实名称": "proj-xxx"}', result.stdout)
        self.assertFalse(self.config.parent.exists())

    def test_redaction_confirm_creates_private_empty_rules(self):
        self.config = self.base / 'nested' / 'config dir' / 'config.json'
        self.env['KB_CONFIG'] = str(self.config)
        result = self.run_cli('config', 'init-redaction', '--confirm', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload['written'])
        self.assertEqual(payload['create'], ['blocklist.txt', 'aliases.json'])
        for path in (self.config.parent, self.config.parent.parent):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        for name in payload['create']:
            self.assertEqual((self.config.parent / name).stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.config.exists())
        blocklist = (self.config.parent / 'blocklist.txt').read_text(encoding='utf-8')
        self.assertTrue(all(line.startswith('#') for line in blocklist.splitlines()))
        self.assertEqual((self.config.parent / 'aliases.json').read_bytes(), b'{}\n')
        code = (
            f'import sys; sys.path.insert(0, {str(CLI.parent)!r}); '
            'from kblib.config import load_blocklist, load_aliases; '
            'assert load_blocklist() == []; assert load_aliases() == {}'
        )
        loaded = subprocess.run([sys.executable, '-B', '-c', code], env=self.env,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(loaded.returncode, 0, loaded.stderr)

    def test_redaction_existing_files_are_never_read_or_modified(self):
        self.config.parent.mkdir()
        contents = {'blocklist.txt': b'Fictional Brand\n', 'aliases.json': b'not JSON\xff'}
        for name, content in contents.items():
            path = self.config.parent / name
            path.write_bytes(content)
            path.chmod(0o000)
            self.addCleanup(path.chmod, 0o600)
        for flags in ((), ('--confirm',)):
            result = self.run_cli('config', 'init-redaction', *flags, '--json')
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload['create'], [])
            self.assertEqual(payload['skip'], list(contents))
            for name in contents:
                self.assertEqual((self.config.parent / name).stat().st_mode & 0o777, 0)
        for name, content in contents.items():
            path = self.config.parent / name
            path.chmod(0o600)
            self.assertEqual(path.read_bytes(), content)

    def test_redaction_skips_symlinks_including_dangling_links(self):
        self.config.parent.mkdir()
        target = self.base / 'fictional-target'
        target.write_bytes(b'unchanged')
        (self.config.parent / 'blocklist.txt').symlink_to(target)
        missing = self.base / 'missing-target'
        (self.config.parent / 'aliases.json').symlink_to(missing)
        result = self.run_cli('config', 'init-redaction', '--confirm', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['skip'], ['blocklist.txt', 'aliases.json'])
        self.assertEqual(target.read_bytes(), b'unchanged')
        self.assertFalse(missing.exists())
        self.assertTrue((self.config.parent / 'aliases.json').is_symlink())

    def test_redaction_creates_only_missing_file(self):
        self.write_config({'version': 1, 'vault': str(self.vault)})
        blocklist = self.config.parent / 'blocklist.txt'
        blocklist.write_bytes(b'Fictional Customer\n')
        config_bytes = self.config.read_bytes()
        for flags in ((), ('--confirm',)):
            result = self.run_cli('config', 'init-redaction', *flags, '--json')
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload['create'], ['aliases.json'])
            self.assertEqual(payload['skip'], ['blocklist.txt'])
            self.assertEqual(blocklist.read_bytes(), b'Fictional Customer\n')
            self.assertEqual(self.config.read_bytes(), config_bytes)
            self.assertEqual((self.config.parent / 'aliases.json').exists(), bool(flags))

    def test_redaction_concurrent_creation_is_skipped_exclusively(self):
        code = (
            'import os, sys; from pathlib import Path; from unittest.mock import patch\n'
            f'sys.path.insert(0, {str(CLI.parent)!r})\n'
            'import kb\n'
            'original = os.open\n'
            'def concurrent_open(path, flags, mode):\n'
            '    assert flags & os.O_CREAT and flags & os.O_EXCL\n'
            '    if path.name == "blocklist.txt":\n'
            '        path.write_bytes(b"concurrent fictional rule\\n")\n'
            '    return original(path, flags, mode)\n'
            'with patch("kblib.config.os.open", side_effect=concurrent_open):\n'
            '    sys.exit(kb.main(["config", "init-redaction", "--confirm", "--json"]))\n'
        )
        result = subprocess.run([sys.executable, '-B', '-c', code], env=self.env,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['create'], ['aliases.json'])
        self.assertEqual(payload['skip'], ['blocklist.txt'])
        self.assertEqual((self.config.parent / 'blocklist.txt').read_bytes(),
                         b'concurrent fictional rule\n')

    def test_redaction_write_and_usage_errors_have_stable_shape(self):
        self.config.parent.write_text('blocked directory', encoding='utf-8')
        for flags in (('--confirm',), ('--unknown',)):
            result = self.run_cli('config', 'init-redaction', *flags, '--json')
            self.assertEqual(result.returncode, 2, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(set(payload), {'ok', 'config', 'create', 'skip', 'written', 'error'})
            self.assertFalse(payload['ok'])
            self.assertFalse(payload['written'])
            self.assertNotIn('Traceback', result.stdout + result.stderr)
        self.assertIn('config init-redaction', payload['error'])

    def test_doctor_warns_about_missing_redaction_files_without_failing(self):
        self.write_config({'version': 1, 'vault': str(self.vault)})
        result = self.run_cli('doctor', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload['ok'])
        warnings = [check for check in payload['checks'] if check.get('level') == 'warn']
        self.assertEqual([check['name'] for check in warnings], ['blocklist', 'aliases'])
        for check, filename in zip(warnings, ('blocklist.txt', 'aliases.json')):
            self.assertTrue(check['ok'])
            self.assertIn(filename, check['message'])
            self.assertIn('config init-redaction', check['message'])
        result = self.run_cli('doctor')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count('提醒：'), 2)
        self.assertNotIn('失败：', result.stdout)

    def test_doctor_warns_about_dangling_redaction_symlink(self):
        self.write_config({'version': 1, 'vault': str(self.vault)})
        (self.config.parent / 'blocklist.txt').symlink_to(self.base / 'gone.txt')
        result = self.run_cli('doctor', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload['ok'])
        check = next(check for check in payload['checks'] if check['name'] == 'blocklist')
        self.assertEqual(check['level'], 'warn')
        self.assertTrue(check['ok'])
        self.assertIn('符号链接', check['message'])

    def test_doctor_only_checks_redaction_file_existence(self):
        self.write_config({'version': 1, 'vault': str(self.vault)})
        for filename in ('blocklist.txt', 'aliases.json'):
            path = self.config.parent / filename
            path.write_bytes(b'invalid JSON and UTF-8\xff')
            path.chmod(0o000)
            self.addCleanup(path.chmod, 0o600)
        code = (
            'import sys; from pathlib import Path; from unittest.mock import patch; '
            f'sys.path.insert(0, {str(CLI.parent)!r}); import kb; '
            'original = Path.read_text; '
            'guard = lambda path, *a, **kw: original(path, *a, **kw) '
            'if path.name == "config.json" else (_ for _ in ()).throw(AssertionError("rule read")); '
            'patcher = patch.object(Path, "read_text", guard); patcher.start(); '
            'sys.exit(kb.main(["doctor", "--json"]))'
        )
        result = subprocess.run([sys.executable, '-B', '-c', code], env=self.env,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)
        checks = {check['name']: check for check in json.loads(result.stdout)['checks']}
        for name in ('blocklist', 'aliases'):
            self.assertTrue(checks[name]['ok'])
            self.assertNotEqual(checks[name].get('level'), 'warn')
        result = self.run_cli('doctor')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('提醒：', result.stdout)
        for filename in ('blocklist.txt', 'aliases.json'):
            self.assertTrue(any(line.startswith('通过：') and filename in line
                                for line in result.stdout.splitlines()))


if __name__ == "__main__":
    unittest.main()
