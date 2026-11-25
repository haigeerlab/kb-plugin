import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('select_tests', ROOT / 'scripts/select_tests.py')
select_tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(select_tests)


class SelectTestsTest(unittest.TestCase):
    def select(self, *files):
        return select_tests.select(list(files))[0]

    def test_docs_only_needs_no_tests(self):
        self.assertEqual(self.select('README.md', 'spec/lint.md', '.github/workflows/ci.yml', 'LICENSE'), [])

    def test_changed_test_file_runs_itself(self):
        self.assertEqual(self.select('tests/test_markdown.py'), ['test_markdown'])

    def test_script_maps_to_its_test(self):
        self.assertEqual(self.select('scripts/check_local_paths.py'), ['test_local_paths'])
        self.assertEqual(self.select('scripts/select_tests.py'), ['test_select_tests'])

    def test_leaf_module_runs_its_test_plus_cli_and_acceptance(self):
        self.assertEqual(self.select('plugins/kb/scripts/kblib/semantic.py'),
                         ['test_acceptance', 'test_cli', 'test_semantic'])

    def test_module_with_tested_users_includes_them(self):
        # candidates 被 capture、delegate_lessons 导入，它们的测试也要跑。
        selected = self.select('plugins/kb/scripts/kblib/candidates.py')
        for name in ('test_candidates', 'test_capture', 'test_delegate_lessons'):
            self.assertIn(name, selected)

    def test_unmapped_changes_fall_back_to_all(self):
        for f in ('plugins/kb/scripts/kb.py',
                  'plugins/kb/scripts/kblib/config.py',
                  'plugins/kb/scripts/kblib/markdown.py',   # checks 导入它，checks 没有专门测试
                  'plugins/kb/skills/lint/SKILL.md',
                  'plugins/kb/hooks/hooks.json',
                  'tests/fixtures/vaults/valid/index.md',
                  'tests/vault_support.py',
                  'scripts/validate.sh'):
            with self.subTest(f=f):
                self.assertIsNone(self.select('README.md', f))


if __name__ == '__main__':
    unittest.main()
