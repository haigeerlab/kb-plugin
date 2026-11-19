import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from vault_support import ROOT, VaultTestCase


class AskTests(VaultTestCase):
    def write_page(self, name, body, title='检索示例', updated='2026-01-01',
                   status='current', superseded_by=None):
        path = 'wiki/tech/' + name + '.md'
        text = ('---\ntype: tech\ntitle: ' + title + '\nstatus: ' + status
                + '\ncreated: 2026-01-01\nupdated: ' + updated
                + '\nraw: [inbox/2026-01-01-example.md]\n')
        if superseded_by is not None:
            text += 'superseded_by: ' + superseded_by + '\n'
        (self.root / path).write_text(text + '---\n' + body, encoding='utf-8')
        return path

    def search(self, *terms, limit=10):
        from kblib.ask import search
        return search(self.vault(), terms, limit)

    def assert_contract(self, data):
        fields = {'schema': int, 'ok': bool, 'vault': str, 'terms': list,
                  'pages': list, 'truncated': bool}
        self.assertEqual(set(data), set(fields))
        for key, kind in fields.items():
            self.assertIs(type(data[key]), kind, key)
        self.assertEqual(data['schema'], 1)
        self.assertTrue(Path(data['vault']).is_absolute())
        self.assertTrue(all(isinstance(term, str) for term in data['terms']))
        page_fields = {'path': str, 'title': str, 'type': str, 'status': str,
                       'updated': str, 'raw': list, 'score': int,
                       'matched_terms': list, 'hits': list}
        for page in data['pages']:
            self.assertEqual(set(page), set(page_fields) | {'superseded_by'})
            for key, kind in page_fields.items():
                self.assertIs(type(page[key]), kind, key)
            self.assertTrue(page['superseded_by'] is None
                            or isinstance(page['superseded_by'], str))
            self.assertTrue(all(isinstance(path, str) for path in page['raw']))
            self.assertTrue(all(isinstance(term, str) for term in page['matched_terms']))
            self.assertGreater(len(page['hits']), 0)
            self.assertLessEqual(len(page['hits']), 20)
            for hit in page['hits']:
                self.assertEqual(set(hit), {'line', 'zone', 'text'})
                self.assertIs(type(hit['line']), int)
                self.assertGreater(hit['line'], 0)
                self.assertIn(hit['zone'], ('current', 'outdated', 'disputed'))
                self.assertIs(type(hit['text']), str)
                self.assertLessEqual(len(hit['text']), 200)

    def test_zones_include_code_and_ignore_frontmatter_and_fake_callouts(self):
        body = ('# 检索示例\nneedle 正文\n'
                '> [!OUTDATED] 旧结论\n> needle 旧记录\n'
                '> ```text\n> needle 旧代码\n> ```\n'
                '> [!disputed] 争议\n> needle 双方说法\n'
                '> ~~~text\n> needle 争议代码\n> ~~~\n'
                '```markdown\n> [!outdated] 伪标注\nneedle 正文代码\n```\n'
                'needle 现行记录\n')
        path = self.write_page('zones', body, title='needle 元数据标题')
        page = self.search('needle')['pages'][0]
        self.assertEqual(page['path'], path)
        self.assertEqual([hit['zone'] for hit in page['hits']],
                         ['current', 'outdated', 'outdated', 'disputed', 'disputed',
                          'current', 'current'])
        lines = (self.root / path).read_text(encoding='utf-8').splitlines()
        self.assertEqual([hit['text'] for hit in page['hits']],
                         [lines[hit['line'] - 1].strip() for hit in page['hits']])
        self.assertTrue(all(hit['line'] > 8 for hit in page['hits']))

    def test_superseded_page_overrides_all_zones_and_exposes_replacement(self):
        replacement = 'wiki/tech/example.md'
        self.write_page('superseded', 'needle\n> [!disputed]\n> needle\n'
                        '\n```\nneedle\n```\n', status='superseded',
                        superseded_by=replacement)
        data = self.search('needle')
        self.assert_contract(data)
        page = data['pages'][0]
        self.assertEqual(page['status'], 'superseded')
        self.assertEqual(page['superseded_by'], replacement)
        self.assertEqual([hit['zone'] for hit in page['hits']], ['outdated'] * 3)

    def test_any_term_case_insensitive_mixed_language_and_distinct_scoring(self):
        first = self.write_page('mixed', '缓存 CACHE Cache 缓存\n', title='缓存 Cache')
        second = self.write_page('second', '插件\n')
        data = self.search('缓存', 'cache', 'CACHE', '插件', '缺词')
        self.assertEqual([page['path'] for page in data['pages']], [first, second])
        self.assertEqual(data['pages'][0]['score'], 10)
        self.assertEqual(data['pages'][0]['matched_terms'], ['缓存', 'cache'])
        self.assertEqual(data['pages'][1]['matched_terms'], ['插件'])
        self.assertEqual(data['terms'], ['缓存', 'cache', '插件', '缺词'])
        self.assert_contract(data)

    def test_regex_metacharacters_are_literal(self):
        for number, term in enumerate(('a.b', '(x)', '[', 'a+b', '\\', '^$', '.*')):
            with self.subTest(term=term):
                path = self.write_page('literal-' + str(number), term + '\n')
                data = self.search(term)
                page = next(page for page in data['pages'] if page['path'] == path)
                self.assertEqual(page['matched_terms'], [term])
                self.assertEqual(page['hits'][0]['text'], term)
                (self.root / path).unlink()
        self.write_page('no-wildcard', 'axb\nx\n')
        self.assertEqual(self.search('a.b', '(x)')['pages'], [])

    def test_title_index_and_body_weights_then_date_and_path(self):
        body = self.write_page('body', 'needle\nneedle\n', updated='2026-03-01')
        title = self.write_page('title', '# needle\n', title='needle', updated='2026-01-01')
        indexed = self.write_page('indexed', 'needle\n', updated='2026-01-01')
        newer = self.write_page('newer', 'needle\n', updated='2026-02-01')
        older_a = self.write_page('a', 'needle\n')
        older_z = self.write_page('z', 'needle\n')
        (self.root / 'index.md').write_text('- [条目](' + indexed
                                           + '#标题) — needle needle\n', encoding='utf-8')
        pages = self.search('needle')['pages']
        self.assertEqual([page['path'] for page in pages],
                         [title, indexed, body, newer, older_a, older_z])
        self.assertEqual([page['score'] for page in pages], [5, 3, 2, 2, 2, 2])

    def test_index_and_frontmatter_only_matches_do_not_create_results(self):
        path = self.write_page('metadata', '无关正文\n', title='needle')
        (self.root / 'index.md').write_text('- [needle](' + path + ')\n', encoding='utf-8')
        for scope in ('inbox', 'raw', 'templates'):
            (self.root / scope).mkdir(exist_ok=True)
            (self.root / scope / 'needle.md').write_text('needle\n', encoding='utf-8')
        data = self.search('needle')
        self.assertEqual(data['pages'], [])
        self.assertFalse(data['truncated'])

    def test_index_bonus_counts_distinct_terms_on_corresponding_line(self):
        path = self.write_page('index', 'alpha\n')
        other = self.write_page('other', 'alpha\n')
        (self.root / 'index.md').write_text(
            '- [页面](' + path + ') alpha BETA beta\n'
            '- [另一页](' + other + ') alpha\n'
            'beta 无关行\n', encoding='utf-8')
        pages = self.search('alpha', 'beta')['pages']
        self.assertEqual([page['score'] for page in pages], [4, 3])
        self.assertEqual(pages[0]['matched_terms'], ['alpha'])

    def test_only_outdated_pages_follow_current_and_disputed_even_with_higher_score(self):
        outdated = self.write_page('outdated', '> [!outdated]\n> needle extra\n',
                                   title='needle extra', updated='2026-03-01')
        current = self.write_page('current', 'needle\n')
        disputed = self.write_page('disputed', '> [!disputed]\n> needle\n')
        mixed = self.write_page('mixed-many', '> [!outdated]\n' + '> needle\n' * 21
                               + '\nneedle extra\n')
        pages = self.search('needle', 'extra')['pages']
        self.assertEqual([page['path'] for page in pages], [mixed, current, disputed, outdated])
        self.assertTrue(all(hit['zone'] == 'outdated' for hit in pages[0]['hits']))
        self.assertEqual(pages[0]['matched_terms'], ['needle', 'extra'])

    def test_limit_default_truncation_and_hit_text_bounds(self):
        for number in range(12):
            self.write_page('many-' + str(number), 'needle\n')
        data = self.search('needle')
        self.assertEqual(len(data['pages']), 10)
        self.assertTrue(data['truncated'])
        result = self.run_cli('ask', 'search', 'needle', '--limit', '2', '--json')
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(len(json.loads(result.stdout)['pages']), 2)
        self.assertTrue(json.loads(result.stdout)['truncated'])
        self.assertFalse(self.search('needle', limit=12)['truncated'])
        self.write_page('bounds', '   bound ' + '中' * 250 + '  \n' + 'bound\n' * 24)
        page = self.search('bound')['pages'][0]
        self.assertEqual(len(page['hits']), 20)
        self.assertEqual(page['hits'][0]['text'], ('bound ' + '中' * 250)[:200])
        self.assertFalse(self.search('bound')['truncated'])

    def test_no_matches_exit_one_with_valid_json_and_successful_search_contract(self):
        for args in (('缺词',), ('缺词', '--json')):
            result = self.run_cli('ask', 'search', *args)
            self.assertEqual(result.returncode, 1, result)
            if '--json' in args:
                data = json.loads(result.stdout)
                self.assert_contract(data)
                self.assertTrue(data['ok'])
                self.assertEqual(data['pages'], [])
                self.assertEqual(data['terms'], ['缺词'])
            else:
                self.assertIn('没有', result.stdout)
        self.write_page('contract', 'needle\n')
        result = self.run_cli('ask', 'search', '--json', 'needle', cwd=Path('/'))
        self.assertEqual(result.returncode, 0, result)
        self.assert_contract(json.loads(result.stdout))
        self.assertEqual(json.loads(result.stdout)['vault'], str(self.root))

    def test_usage_and_configuration_errors_exit_two(self):
        for args in ((), ('search',), ('search', ''), ('search', '   '),
                     ('search', 'needle', '--limit', '0'),
                     ('search', 'needle', '--limit', '-1'),
                     ('search', 'needle', '--limit', '1.5'),
                     ('search', 'needle', '--limit', 'abc')):
            for flags in ((), ('--json',)):
                with self.subTest(args=args, flags=flags):
                    result = self.run_cli('ask', *args, *flags)
                    self.assertEqual(result.returncode, 2, result)
                    self.assertNotIn('Traceback', result.stdout + result.stderr)
                    self.assertIn('用法', result.stdout + result.stderr)
                    if flags:
                        self.assertFalse(json.loads(result.stdout)['ok'])
        self.config.unlink()
        result = self.run_cli('ask', 'search', 'needle', '--json')
        self.assertEqual(result.returncode, 2, result)
        self.assertIn('配置', result.stdout)
        self.assertFalse(json.loads(result.stdout)['ok'])

    def test_search_function_rejects_invalid_terms_and_limit(self):
        from kblib import KbError
        for terms, limit in (([], 10), ([''], 10), (['  '], 10), (['x'], 0),
                             (['x'], -1), (['x'], True), (['x'], 1.5)):
            with self.subTest(terms=terms, limit=limit), self.assertRaises(KbError):
                from kblib.ask import search
                search(self.vault(), terms, limit)

    def test_text_output_includes_title_path_status_score_and_zone(self):
        path = self.write_page('text', 'needle\n> [!outdated]\n> needle\n'
                               '> [!disputed]\n> needle\n')
        result = self.run_cli('ask', 'search', 'needle')
        self.assertEqual(result.returncode, 0, result)
        for value in ('检索示例', path, '状态', '得分', '现行', '过时', '争议'):
            self.assertIn(value, result.stdout)

    def test_dispatch_fixture_outdated_and_current_verdict(self):
        shutil.rmtree(self.root)
        shutil.copytree(ROOT / 'tests/fixtures/vaults/dispatch', self.root)
        self.git('init', '-q')
        result = self.run_cli('ask', 'search', '派活', '成本', '--json')
        self.assertEqual(result.returncode, 0, result)
        data = json.loads(result.stdout)
        self.assert_contract(data)
        self.assertTrue(any(hit['zone'] == 'current' for page in data['pages']
                            for hit in page['hits']))
        # The original outdated block says "机械活", not "派活" or "成本".
        data = self.search('派活', '成本', '机械活')
        page = next(page for page in data['pages']
                    if page['path'] == 'wiki/decisions/dispatch-cost.md')
        lines = (self.root / page['path']).read_text(encoding='utf-8').splitlines()
        old_start = next(i for i, line in enumerate(lines, 1) if '[!outdated]' in line)
        verdict = lines.index('## 现行判据') + 1
        outdated = [hit for hit in page['hits'] if old_start <= hit['line'] <= old_start + 2]
        current = [hit for hit in page['hits'] if hit['line'] > verdict]
        self.assertTrue(outdated)
        self.assertTrue(current)
        self.assertTrue(all(hit['zone'] == 'outdated' for hit in outdated))
        self.assertTrue(all(hit['zone'] == 'current' for hit in current))
        self.assert_contract(data)

        target = self.root / page['path']
        target.write_text(target.read_text(encoding='utf-8').replace(
            '> 早期主会话输出', '> 派活成本：早期主会话输出'), encoding='utf-8')
        result = self.run_cli('ask', 'search', '派活', '成本', '--json')
        self.assertEqual(result.returncode, 0, result)
        page = next(page for page in json.loads(result.stdout)['pages']
                    if page['path'] == 'wiki/decisions/dispatch-cost.md')
        self.assertTrue(any(hit['zone'] == 'outdated' for hit in page['hits']))
        self.assertTrue(any(hit['line'] > verdict and hit['zone'] == 'current'
                            for hit in page['hits']))

    def test_search_preserves_files_and_git_state_in_clean_and_dirty_vaults(self):
        def snapshot():
            return {p.relative_to(self.root).as_posix(): p.read_bytes()
                    for p in self.root.rglob('*') if p.is_file()}

        for dirty in (False, True):
            with self.subTest(dirty=dirty):
                if dirty:
                    (self.root / 'index.md').write_text('未暂存的修改\n', encoding='utf-8')
                    self.write_page('dirty', 'needle\n')
                    self.git('add', 'wiki/tech/dirty.md')
                    (self.root / 'untracked.txt').write_text('未跟踪\n', encoding='utf-8')
                status = self.git('status', '--porcelain=v1', '-z')
                before = snapshot()
                config = self.config.read_bytes()
                for term in ('当前', 'needle', '缺词'):
                    result = self.run_cli('ask', 'search', term, '--json')
                    self.assertIn(result.returncode, (0, 1), result)
                self.assertEqual(snapshot(), before)
                self.assertEqual(self.git('status', '--porcelain=v1', '-z'), status)
                self.assertEqual(self.config.read_bytes(), config)
        vault = self.vault()
        with patch('subprocess.run', side_effect=AssertionError('search must use the snapshot')):
            from kblib.ask import search
            search(vault, ['needle'])


if __name__ == '__main__':
    unittest.main()
