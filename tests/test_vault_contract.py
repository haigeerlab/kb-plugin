import json
import re
import shutil
import unittest

from vault_support import ROOT, VaultTestCase
from kblib import checks


class ContractTests(VaultTestCase):
    def test_valid_fixture_has_no_findings(self):
        self.assertEqual(checks.check(self.vault()), [])

    def test_each_check_code_reports_exact_path_and_line(self):
        cases = json.loads((ROOT / 'tests/fixtures/vaults/violations.json').read_text())
        for case in cases:
            with self.subTest(code=case['code']):
                if case['code'] == 'filename':
                    old_path = self.root / 'wiki/pitfalls/example.md'
                    old_path.rename(self.root / case['path'])
                else:
                    original = (self.root / case['path']).read_bytes()
                    self.replace(case['path'], case['old'], case['new'])
                findings = checks.check(self.vault())
                self.assertIn((case['code'], case['path'], case['line']),
                              [(f.code, f.path, f.line) for f in findings], findings)
                if case['code'] == 'filename':
                    (self.root / case['path']).rename(old_path)
                else:
                    (self.root / case['path']).write_bytes(original)

    def test_nested_frontmatter_is_finding_not_crash(self):
        self.replace('wiki/pitfalls/example.md', 'tags: [示例]', 'tags:\n  nested:\n    value: example')
        found = checks.check_frontmatter(self.vault())
        self.assertTrue(any(f.code == 'frontmatter' and f.line == 9 for f in found), found)

    def test_wikilink_is_link_error_but_code_is_ignored(self):
        path = 'wiki/pitfalls/example.md'
        self.replace(path, '当前方法已经验证。', '[[非法]] `[[代码]]`\n```\n[[代码块]]\n```')
        found = checks.check_link(self.vault())
        self.assertEqual([(f.code, f.path, f.line) for f in found], [('link', path, 15)])

    def test_callout_bad_number_and_corner_quote_are_evidence(self):
        path = 'wiki/decisions/example.md'
        self.replace(path, '> 旧方法需要复查。', '> 旧方法需要复查，用户数为 55K。')
        self.assertTrue(any(f.code == 'evidence' and f.path == path and f.line == 38
                            for f in checks.check_evidence(self.vault())))
        self.replace(path, '> 旧方法需要复查，用户数为 55K。', '> 他说「这是一段足够长但没有任何出处支持的引用内容」。')
        self.assertTrue(any(f.code == 'evidence' and f.line == 38 for f in checks.check_evidence(self.vault())))

    def test_immutable_modified_deleted_staged_and_untracked(self):
        path = 'inbox/2026-01-01-example.md'
        original = (self.root / path).read_bytes()
        self.replace(path, '当前方法已经验证。', '改动。')
        self.git('add', path)
        self.assertEqual([(f.code, f.path, f.line) for f in checks.check_immutable(self.vault())],
                         [('immutable', path, 1)])
        (self.root / path).unlink()
        self.assertTrue(checks.check_immutable(self.vault()))
        (self.root / path).write_bytes(original)
        self.git('add', path)
        (self.root / 'raw/new.md').write_text('新原文。')
        self.git('add', 'raw/new.md')
        self.assertEqual(checks.check_immutable(self.vault()), [])
        (self.root / 'raw/newer.md').write_text('未跟踪原文。')
        self.assertEqual(checks.check_immutable(self.vault()), [])
        (self.root / 'raw/example.md').unlink()
        self.assertEqual(checks.check_immutable(self.vault())[0].path, 'raw/example.md')

    def test_immutable_catches_modification_already_committed(self):
        path = 'inbox/2026-01-01-example.md'
        self.replace(path, '当前方法已经验证。', '提交过的改动。')
        self.git('add', path)
        self.git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'rewrite source')
        self.assertEqual([(f.code, f.path) for f in checks.check_immutable(self.vault())],
                         [('immutable', path)])

    def test_not_git_reports_one_immutable_explanation(self):
        shutil.rmtree(self.root / '.git')
        found = checks.check_immutable(self.vault())
        self.assertEqual([(f.code, f.path, f.line) for f in found], [('immutable', '.', 1)])
        self.assertIn('init', found[0].message)

    def test_global_index_log_immutable_still_checked_for_one_page(self):
        self.replace('index.md', '(wiki/tech/example.md)', '(wiki/tech/missing.md)')
        self.replace('log.md', '] init |', '] invalid |')
        self.replace('raw/example.md', '当前方法', '旧方法')
        found = checks.check(self.vault(['wiki/pitfalls/example.md']))
        self.assertTrue({'index', 'log', 'immutable'} <= {f.code for f in found}, found)

    def test_frontmatter_links_include_user_metadata(self):
        path = 'wiki/pitfalls/example.md'
        self.replace(path, 'title: 合法示例', 'title: "中文 [[非法]]"')
        self.assertIn(('link', path, 3), [(f.code, f.path, f.line) for f in checks.check_link(self.vault())])
        self.replace(path, 'title: "中文 [[非法]]"', 'title: "中文 [断链](missing.md)"')
        self.assertIn(('link', path, 3), [(f.code, f.path, f.line) for f in checks.check_link(self.vault())])

    def test_outdated_wikilink_does_not_satisfy_replacement_link(self):
        path = 'wiki/decisions/example.md'
        self.replace(path, '[现行判据](#现行判据)', '[[现行判据]]')
        self.assertEqual([(f.code, f.path, f.line) for f in checks.check_callout(self.vault())],
                         [('callout', path, 37)])

    def test_block_source_errors_point_to_item_line(self):
        path = 'wiki/pitfalls/example.md'
        self.replace(path, 'raw: [inbox/2026-01-01-example.md, raw/example.md]',
                     'raw:\n  - inbox/2026-01-01-example.md\n  - raw/missing.md')
        for function in (checks.check_raw_ref, checks.check_link):
            found = function(self.vault())
            self.assertTrue(any(f.path == path and f.line == 9 for f in found), found)

    def test_valid_superseded_page_and_empty_replacement(self):
        path = 'wiki/pitfalls/example.md'
        self.replace(path, 'status: current', 'status: superseded\nsuperseded_by: wiki/tech/example.md')
        self.assertEqual(checks.check_frontmatter(self.vault()), [])
        self.assertEqual(checks.check_link(self.vault()), [])
        self.replace(path, 'superseded_by: wiki/tech/example.md', 'superseded_by: ""')
        self.assertTrue(any('superseded_by' in f.message for f in checks.check_frontmatter(self.vault())))

    def test_uppercase_markdown_extension_is_invalid_filename(self):
        path = 'wiki/pitfalls/example.MD'
        (self.root / 'wiki/pitfalls/example.md').rename(self.root / path)
        self.assertEqual([(f.code, f.path, f.line) for f in checks.check_filename(self.vault())],
                         [('filename', path, 1)])

    def test_links_resolve_chinese_encoded_anchors_and_duplicates(self):
        path = 'wiki/pitfalls/example.md'
        self.replace(path, '当前方法已经验证。',
                     '[中文](#%E7%97%87%E7%8A%B6) [另一页](../tech/example.md#原理)\n'
                     '[重复](#症状-1)\n\n## 症状\n')
        self.assertEqual(checks.check_link(self.vault()), [])
        self.replace(path, '[重复](#症状-1)', '[断锚点](#症状-2)')
        found = checks.check_link(self.vault())
        self.assertEqual([(f.code, f.path, f.line) for f in found], [('link', path, 16)])

    def test_log_future_invalid_and_reverse_dates(self):
        path = 'log.md'
        (self.root / path).write_text('# 日志\n\n## [2026-01-02] save | 保存\n\n'
                                      '## [2026-01-01] save | 逆序\n\n'
                                      '## [2999-01-01] save | 未来\n\n'
                                      '## [2026-02-30] save | 非法日期\n')
        self.assertEqual([(f.code, f.path, f.line) for f in checks.check_log(self.vault())],
                         [('log', path, 5), ('log', path, 7), ('log', path, 9)])

    def test_invalid_field_shapes_report_without_crash(self):
        path = 'wiki/pitfalls/example.md'
        original = (self.root / path).read_text()
        for field, value in (('type', '[pitfall]'), ('title', 'false'), ('status', '[current]'),
                             ('created', '42'), ('raw', 'true'), ('tags', 'plain'),
                             ('projects', '[nested, [list]]')):
            with self.subTest(field=field):
                text = re.sub(r'^' + field + r':.*$', field + ': ' + value,
                                            original, flags=re.MULTILINE)
                (self.root / path).write_text(text)
                self.assertTrue(any(f.code == 'frontmatter' for f in checks.check(self.vault())))
        (self.root / path).write_text(original)

    def test_inbox_rejects_non_markdown_entries(self):
        path = 'inbox/memo.txt'
        (self.root / path).write_text('未按契约保存的条目。')
        self.assertIn(('inbox', path, 1),
                      [(f.code, f.path, f.line) for f in checks.check_inbox(self.vault())])

    def test_dates_status_raw_and_sections(self):
        path = 'wiki/pitfalls/example.md'
        self.replace(path, 'updated: 2026-01-01', 'updated: 2025-12-31')
        self.assertTrue(any(f.line == 6 for f in checks.check_frontmatter(self.vault())))
        self.replace(path, 'updated: 2025-12-31', 'updated: 2999-01-01')
        self.assertTrue(any(f.line == 6 for f in checks.check_frontmatter(self.vault())))
        self.replace(path, 'status: current', 'status: superseded')
        self.assertTrue(any('superseded_by' in f.message for f in checks.check_frontmatter(self.vault())))

    def test_outdated_missing_link_disputed_empty_unknown_type(self):
        path = 'wiki/decisions/example.md'
        self.replace(path, '> [!outdated] 2026-01-01 → [现行判据](#现行判据)', '> [!outdated] 2026-01-01')
        self.replace(path, '> 争议双方都有依据。', '>')
        self.replace(path, '## 背景', '> [!custom]\n> 内容\n\n## 背景')
        found = checks.check_callout(self.vault())
        self.assertEqual(len(found), 3, found)


if __name__ == '__main__':
    unittest.main()
