import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "plugins/kb/references/locate-plugin-root.md"
SKILL = ROOT / "plugins/kb/skills/doctor/SKILL.md"


def bash_blocks(path):
    return re.findall(r"```bash\n(.*?)\n```", path.read_text(encoding="utf-8"), re.DOTALL)


class PluginRootTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.first = self.base / "Claude 插件"
        self.second = self.base / "Codex 插件"
        self.first.mkdir()
        self.second.mkdir()
        self.env = dict(os.environ, KB_CONFIG=str(self.base / "config.json"))
        self.env.pop("CLAUDE_PLUGIN_ROOT", None)
        self.env.pop("PLUGIN_ROOT", None)
        self.env["PATH"] = str(self.bin) + os.pathsep + self.env.get("PATH", "")
        self.fake_codex({"installed": []})

    def fake_codex(self, data, exit_code=0):
        script = self.bin / "codex"
        script.write_text(
            f"#!{sys.executable}\nimport json, sys\n"
            "assert sys.argv[1:] == ['plugin', 'list', '--available', '--json']\n"
            f"print({json.dumps(data, ensure_ascii=False)!r})\n"
            f"sys.exit({exit_code})\n", encoding="utf-8",
        )
        script.chmod(0o755)

    def locate(self):
        blocks = bash_blocks(REFERENCE)
        self.assertEqual(len(blocks), 1)
        return subprocess.run(
            ["/bin/bash", "-c", blocks[0] + '\nprintf "%s\\n" "$ROOT"'],
            env=self.env, cwd=self.base, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def test_claude_root_takes_priority(self):
        self.env.update(CLAUDE_PLUGIN_ROOT=str(self.first), PLUGIN_ROOT=str(self.second))
        result = self.locate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.first))

    def test_plugin_root_fallback(self):
        self.env.update(CLAUDE_PLUGIN_ROOT="", PLUGIN_ROOT=str(self.second))
        result = self.locate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.second))

    def test_fake_codex_selects_installed_enabled_kb(self):
        self.fake_codex({"installed": [
            {"name": "other", "installed": True, "enabled": True, "source": {"path": str(self.first)}},
            {"name": "kb", "installed": False, "enabled": True, "source": {"path": str(self.first)}},
            {"name": "kb", "installed": True, "enabled": False, "source": {"path": str(self.first)}},
            {"name": "kb", "installed": True, "enabled": True, "source": "invalid"},
            {"name": "kb", "installed": True, "enabled": True, "source": {"path": str(self.second)}},
        ]})
        result = self.locate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.second))

    def test_all_sources_fail(self):
        result = self.locate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("kb 无法定位插件根目录", result.stderr)
        self.assertIn("没有列出已启用且带路径的 kb", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_no_codex_executable_fails(self):
        (self.bin / "codex").unlink()
        self.env["PATH"] = str(self.bin)
        result = self.locate()
        self.assertEqual(result.returncode, 2)
        self.assertIn("也没有 codex 可查询", result.stderr)

    def test_malformed_codex_output_fails(self):
        script = self.bin / "codex"
        script.write_text("#!/bin/sh\nprintf '%s' '{broken'\nexit 1\n", encoding="utf-8")
        script.chmod(0o755)
        result = self.locate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("无法解析", result.stderr)

    def test_nonexistent_environment_root_fails(self):
        self.env["CLAUDE_PLUGIN_ROOT"] = str(self.base / "missing")
        result = self.locate()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("插件根目录不存在", result.stderr)

    def test_skill_inlines_identical_resolver(self):
        self.assertEqual(bash_blocks(SKILL)[0], bash_blocks(REFERENCE)[0])
        frontmatter = SKILL.read_text(encoding="utf-8").split("---", 2)[1]
        fields = re.findall(r"^(\w+):", frontmatter, re.MULTILINE)
        self.assertEqual(fields, ["name", "description"])
        self.assertIn('python3 -B "$ROOT/scripts/kb.py" doctor', SKILL.read_text(encoding="utf-8"))

    def test_every_skill_uses_identical_resolver_and_portable_frontmatter(self):
        resolver = bash_blocks(REFERENCE)[0]
        skills = sorted((ROOT / "plugins/kb/skills").glob("*/SKILL.md"))
        self.assertTrue(skills)
        for skill in skills:
            with self.subTest(skill=skill.parent.name):
                text = skill.read_text(encoding="utf-8")
                fields = re.findall(r"^(\w+):", text.split("---", 2)[1], re.MULTILINE)
                self.assertEqual(fields, ["name", "description"])
                if 'ROOT="${CLAUDE_PLUGIN_ROOT}"' in text:
                    self.assertEqual(bash_blocks(skill)[0], resolver)

    def test_skill_blocks_run_doctor(self):
        config = Path(self.env["KB_CONFIG"])
        config.write_text(json.dumps({"version": 1, "vault": str(self.base)}), encoding="utf-8")
        self.env["CLAUDE_PLUGIN_ROOT"] = str(ROOT / "plugins/kb")
        result = subprocess.run(
            ["/bin/bash", "-c", "\n".join(bash_blocks(SKILL))],
            env=self.env, cwd=self.base, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.base), result.stdout)
        self.assertIn("自检通过", result.stdout)


if __name__ == "__main__":
    unittest.main()
