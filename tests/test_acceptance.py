import hashlib
import shutil
import unittest
from unittest.mock import patch

from vault_support import ROOT, VaultTestCase
from kblib import checks
from kblib.vault import today


class AcceptanceTests(VaultTestCase):
    def test_ac6_three_original_sources_form_valid_knowledge_base(self):
        shutil.rmtree(self.root)
        shutil.copytree(ROOT / 'tests/fixtures/vaults/dispatch', self.root)
        self.git('init', '-q')
        self.git('add', '.')
        self.git('commit', '-qm', '真实素材样例基线')
        pairs = [('s1-codex-exec-pitfalls.md', '2026-08-29-codex-exec.md'),
                 ('s2-subagent-cheaper-claim.md', '2026-08-28-dispatch-claim.md'),
                 ('s3-dispatch-verdict.md', '2026-10-06-dispatch-verdict.md')]
        for source, entry in pairs:
            self.assertTrue((self.root / 'inbox' / entry).read_text().endswith(
                (ROOT / 'tests/fixtures/sources' / source).read_text()))
        self.assertEqual(checks.check(self.vault()), [])
        result = self.run_cli('check', '--json')
        self.assertEqual(result.returncode, 0, result)

    def test_check_is_read_only_including_git_state(self):
        snapshot = lambda: {p.relative_to(self.root).as_posix(): p.read_bytes()
                            for p in self.root.rglob('*') if p.is_file()}
        before = snapshot()
        self.assertEqual(self.run_cli('check', '--json').returncode, 0)
        self.assertEqual(snapshot(), before)

    def test_vendor_original_hashes_unchanged(self):
        vendor = ROOT / 'plugins/kb/scripts/vendor/karpathy-llm-wiki'
        expected = {'check_evidence.py': '967298608a30f83f62616a40c0f68a64e300abd4a3299e24548ccee7722ee40e',
                    'test_check_evidence.py': 'baae13bc4a617e286a937d347b81cad630366fbf50891ee055e00bb63ffb27c4',
                    'LICENSE': 'ce1702d638e34829f490a6aee7c4bdf033cecf358e971df69ba758714d9f1d56'}
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256((vendor / name).read_bytes()).hexdigest(), digest)

    def test_today_uses_local_timezone(self):
        with patch('kblib.vault.datetime') as clock:
            clock.now.return_value.astimezone.return_value.date.return_value = 'local date'
            self.assertEqual(today(), 'local date')
            clock.now.assert_called_once_with()
            clock.now.return_value.astimezone.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
