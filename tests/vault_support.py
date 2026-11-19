import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'plugins/kb/scripts/kb.py'
sys.path.insert(0, str(CLI.parent))


class VaultTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / '知识库 with spaces'
        shutil.copytree(ROOT / 'tests/fixtures/vaults/valid', self.root)
        self.config = self.base / 'config.json'
        self.config.write_text(json.dumps({'version': 1, 'vault': str(self.root)}), encoding='utf-8')
        self.env = dict(os.environ, KB_CONFIG=str(self.config))
        self.git('init', '-q')
        self.git('add', '.')
        self.git('commit', '-qm', '测试知识库基线')

    def git(self, *args):
        result = subprocess.run(['git', '-C', str(self.root),
                                 '-c', 'user.name=Vault Tests', '-c', 'user.email=vault@example.invalid',
                                 '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false', *args],
                                env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def vault(self, paths=()):
        from kblib.vault import Vault
        return Vault.load(paths, self.env)

    def run_cli(self, *args, cwd=None):
        return subprocess.run([sys.executable, '-B', str(CLI), *args],
                              env=self.env, cwd=cwd or self.base, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def replace(self, path, old, new):
        target = self.root / path
        target.write_text(target.read_text(encoding='utf-8').replace(old, new, 1), encoding='utf-8')
