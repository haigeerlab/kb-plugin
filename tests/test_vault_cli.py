import json
from pathlib import Path
import shutil
import unittest

from vault_support import ROOT, VaultTestCase


class VaultCliTests(VaultTestCase):
    def empty_vault(self):
        shutil.rmtree(self.root)
        self.root.mkdir()

    def test_init_preview_never_writes_and_lists_git_init(self):
        self.empty_vault()
        result = self.run_cli('init', '--json')
        self.assertEqual(result.returncode, 0, result)
        data = json.loads(result.stdout)
        self.assertFalse(data['written'])
        self.assertTrue(data['git_init'])
        self.assertIn('SCHEMA.md', data['create'])
        self.assertIn('templates/pitfall.md', data['create'])
        self.assertEqual(data['skip'], [])
        self.assertEqual(list(self.root.iterdir()), [])
        result = self.run_cli('init')
        self.assertIn('git init', result.stdout)
        self.assertIn('--confirm', result.stdout)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_init_confirm_then_check_passes(self):
        self.empty_vault()
        result = self.run_cli('init', '--confirm', '--json')
        self.assertEqual(result.returncode, 0, result)
        self.assertTrue(json.loads(result.stdout)['written'])
        for directory in ('inbox', 'raw', 'wiki/pitfalls', 'wiki/decisions', 'wiki/tech',
                          'wiki/patterns', 'wiki/projects', 'templates', '.git'):
            self.assertTrue((self.root / directory).is_dir(), directory)
        for kind in ('pitfall', 'decision', 'tech', 'pattern', 'project'):
            template = (self.root / 'templates' / (kind + '.md')).read_text(encoding='utf-8')
            # Page templates are reused later, so they must keep a date placeholder.
            self.assertIn('created: YYYY-MM-DD', template)
            self.assertNotRegex(template, r'\d{4}-\d{2}-\d{2}')
        self.assertRegex((self.root / 'log.md').read_text(encoding='utf-8'), r'## \[\d{4}-\d{2}-\d{2}\] init')
        result = self.run_cli('check', '--json')
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(json.loads(result.stdout), {'ok': True, 'findings': []})

    def test_init_preserves_existing_files_and_skips_them(self):
        schema = (self.root / 'SCHEMA.md').read_bytes()
        (self.root / 'templates').mkdir()
        (self.root / 'templates/pitfall.md').write_text('已有模板，不许覆盖。')
        result = self.run_cli('init', '--json')
        data = json.loads(result.stdout)
        self.assertIn('SCHEMA.md', data['skip'])
        self.assertIn('templates/pitfall.md', data['skip'])
        self.assertFalse(data['git_init'])
        result = self.run_cli('init', '--confirm', '--json')
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual((self.root / 'SCHEMA.md').read_bytes(), schema)
        self.assertEqual((self.root / 'templates/pitfall.md').read_text(), '已有模板，不许覆盖。')
        self.assertEqual(self.run_cli('check').returncode, 0)

    def test_check_json_and_exit_codes(self):
        result = self.run_cli('check', '--json')
        self.assertEqual(result.returncode, 0, result)
        self.replace('wiki/tech/example.md', '42K', '55K')
        result = self.run_cli('check', '--json')
        data = json.loads(result.stdout)
        self.assertEqual(result.returncode, 1, result)
        self.assertFalse(data['ok'])
        self.assertEqual(set(data), {'ok', 'findings'})
        self.assertEqual(set(data['findings'][0]), {'code', 'path', 'line', 'message'})
        result = self.run_cli('check', '--json', '../outside.md')
        self.assertEqual(result.returncode, 2, result)
        self.assertEqual(set(json.loads(result.stdout)), {'ok', 'findings'})
        self.assertIn('知识库', result.stderr)
        self.config.unlink()
        result = self.run_cli('check', '--json')
        self.assertEqual(result.returncode, 2, result)
        self.assertFalse(json.loads(result.stdout)['ok'])
        self.assertIn('配置', result.stderr)

    def test_selected_paths_resolve_from_vault_and_validate_usage(self):
        self.replace('wiki/tech/example.md', '42K', '55K')
        result = self.run_cli('check', '--json', 'wiki/pitfalls/example.md', cwd=Path('/'))
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(self.run_cli('check', 'wiki/tech').returncode, 1)
        for args in (('check', 'missing.md'), ('check', '--unknown'), ('init', 'extra')):
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 2, result)
            self.assertNotIn('Traceback', result.stderr)

    def test_skill_inlines_resolver_and_requires_explicit_agreement(self):
        import re
        text = (ROOT / 'plugins/kb/skills/init/SKILL.md').read_text()
        reference = (ROOT / 'plugins/kb/references/locate-plugin-root.md').read_text()
        block = lambda s: re.findall(r'```bash\n(.*?)\n```', s, re.DOTALL)[0]
        self.assertEqual(block(text), block(reference))
        self.assertEqual(re.findall(r'^(\w+):', text.split('---', 2)[1], re.MULTILINE), ['name', 'description'])
        self.assertIn('明确同意', text)
        self.assertIn('原样转述', text)
        self.assertIn('init --confirm', text)


if __name__ == '__main__':
    unittest.main()
