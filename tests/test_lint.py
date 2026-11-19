import json
from datetime import timedelta
import unittest

from vault_support import VaultTestCase
from kblib.vault import today


class LintReportTests(VaultTestCase):
    def report(self, *flags):
        result = self.run_cli('lint', '--json', *flags)
        self.assertIn(result.returncode, (0, 1), result)
        return json.loads(result.stdout)

    def test_orphans_ignore_index_self_links_and_exempt_projects(self):
        data = self.report()
        orphans = {f['path'] for f in data['hints'] if f['code'] == 'orphan'}
        self.assertIn('wiki/pitfalls/example.md', orphans)
        self.assertNotIn('wiki/projects/example.md', orphans)
        path = self.root / 'wiki/pitfalls/example.md'
        path.write_text(path.read_text() + '\n[自己](example.md)\n', encoding='utf-8')
        self.assertIn('wiki/pitfalls/example.md',
                      {f['path'] for f in self.report()['hints'] if f['code'] == 'orphan'})
        other = self.root / 'wiki/tech/example.md'
        other.write_text(other.read_text() + '\n[坑](../pitfalls/example.md)\n', encoding='utf-8')
        self.assertNotIn('wiki/pitfalls/example.md',
                         {f['path'] for f in self.report()['hints'] if f['code'] == 'orphan'})

    def test_stale_boundary_status_and_cli_threshold(self):
        for kind, age in (('pitfalls', 180), ('tech', 181), ('patterns', 5)):
            self.replace('wiki/' + kind + '/example.md', 'updated: 2026-01-01',
                         'updated: ' + (today() - timedelta(days=age)).isoformat())
        self.replace('wiki/decisions/example.md', 'status: current',
                     'status: superseded\nsuperseded_by: wiki/tech/example.md')
        stale = {f['path'] for f in self.report()['hints'] if f['code'] == 'stale'}
        self.assertEqual(stale, {'wiki/tech/example.md', 'wiki/projects/example.md'})
        stale = {f['path'] for f in self.report('--stale-days', '181')['hints'] if f['code'] == 'stale'}
        self.assertNotIn('wiki/tech/example.md', stale)
        stale = {f['path'] for f in self.report('--stale-days', '4')['hints'] if f['code'] == 'stale'}
        self.assertIn('wiki/patterns/example.md', stale)

    def test_backlog_excludes_raw_references_and_paths_in_save_body_only(self):
        paths = ['inbox/2026-01-02-' + name + '.md' for name in
                 ('saved', 'pending', 'other-operation', 'absolute', 'longer', 'heading')]
        entry = (self.root / 'inbox/2026-01-01-example.md').read_text()
        for path in paths:
            (self.root / path).write_text(entry.replace('2026-01-01', '2026-01-02'), encoding='utf-8')
        log = self.root / 'log.md'
        log.write_text(log.read_text() + '\n## [2026-01-02] save | 没有新内容\n\n'
                       + '`' + paths[0] + '` 已处理。\n没有新内容，但未写路径。\n'
                       + str(self.root / paths[3]) + '\n' + paths[4] + '.backup\n'
                       + '\n## [2026-01-02] lint | 提示\n\n' + paths[2] + '\n'
                       + '\n## [2026-01-02] save | ' + paths[5] + '\n\n正文未写路径。\n', encoding='utf-8')
        backlog = {f['path'] for f in self.report()['hints'] if f['code'] == 'backlog'}
        self.assertEqual(backlog, set(paths[1:]))

    def test_group_order_metrics_and_hints_do_not_fail_check(self):
        result = self.run_cli('lint', '--json')
        self.assertEqual(result.returncode, 0, result)
        data = json.loads(result.stdout)
        self.assertEqual([g['name'] for g in data['groups']],
                         ['导航断裂', '内容可信度', '格式', '维护提示'])
        self.assertEqual(data['metrics']['wiki_pages'],
                         {'value': 5, 'threshold': 300, 'exceeded': False})
        self.assertEqual(data['metrics']['index_bytes'],
                         {'value': (self.root / 'index.md').stat().st_size,
                          'threshold': 40960, 'exceeded': False})
        self.assertIsNone(data['metrics']['ask_average_reads']['value'])
        self.assertTrue(data['metrics']['ask_average_reads']['reason'])
        self.assertEqual(data['fixable'], 0)
        text = self.run_cli('lint')
        self.assertEqual(text.returncode, 0, text)
        self.assertIn('暂无数据', text.stdout)
        self.assertIn('摘要', text.stdout)
        for group in data['groups']:
            self.assertIn(group['name'] + '（' + str(group['count']) + '）', text.stdout)
        self.assertEqual(self.run_cli('check', '--json').returncode, 0)

    def test_ac2_four_problem_types_and_all_check_findings_in_order(self):
        self.replace('wiki/pitfalls/example.md', '当前方法已经验证。',
                     '当前方法已经验证。[断链](missing.md)\n无出处的数值 55K。')
        self.replace('index.md', '- [合法示例](wiki/tech/example.md) — 当前方法示例 · 2026-01-01\n', '')
        result = self.run_cli('lint', '--json')
        self.assertEqual(result.returncode, 1, result)
        data = json.loads(result.stdout)
        found = [f for group in data['groups'][:3] for f in group['findings']]
        checked = json.loads(self.run_cli('check', '--json').stdout)['findings']
        self.assertCountEqual(found, checked)
        self.assertTrue({'link', 'index'} <= {f['code'] for f in data['groups'][0]['findings']})
        self.assertIn('evidence', {f['code'] for f in data['groups'][1]['findings']})
        self.assertIn('orphan', {f['code'] for f in data['groups'][3]['findings']})
        text = self.run_cli('lint').stdout
        positions = [text.index(name) for name in ('导航断裂', '内容可信度', '格式', '维护提示', '规模指标')]
        self.assertEqual(positions, sorted(positions))

    def test_report_preserves_all_files_config_and_git_state_clean_and_dirty(self):
        for dirty in (False, True):
            with self.subTest(dirty=dirty):
                if dirty:
                    self.replace('index.md', '# 知识库总目录', '# 修改的目录')
                    self.git('add', 'index.md')
                    (self.root / 'untracked.txt').write_text('未跟踪文件。', encoding='utf-8')
                status = self.git('status', '--porcelain=v1', '-z')
                before = {p.relative_to(self.root).as_posix(): p.read_bytes()
                          for p in self.root.rglob('*') if p.is_file()}
                config = self.config.read_bytes()
                for flags in ((), ('--json',)):
                    result = self.run_cli('lint', *flags)
                    self.assertIn(result.returncode, (0, 1), result)
                self.assertEqual({p.relative_to(self.root).as_posix(): p.read_bytes()
                                  for p in self.root.rglob('*') if p.is_file()}, before)
                self.assertEqual(self.git('status', '--porcelain=v1', '-z'), status)
                self.assertEqual(self.config.read_bytes(), config)

    def test_metrics_thresholds_and_exact_utf8_index_bytes(self):
        from kblib.lint import report
        template = (self.root / 'wiki/tech/example.md').read_text()
        for number in range(295):
            (self.root / f'wiki/tech/scale-{number}.md').write_text(template, encoding='utf-8')
        index = self.root / 'index.md'
        content = index.read_bytes()
        index.write_bytes(content + b' ' * (40960 - len(content)))
        data = report(self.vault())
        self.assertEqual(data['metrics']['wiki_pages'],
                         {'value': 300, 'threshold': 300, 'exceeded': False})
        self.assertEqual(data['metrics']['index_bytes'],
                         {'value': 40960, 'threshold': 40960, 'exceeded': False})
        (self.root / 'wiki/tech/scale-extra.md').write_text(template, encoding='utf-8')
        with index.open('ab') as stream:
            stream.write('中'.encode('utf-8'))
        data = report(self.vault())
        self.assertEqual(data['metrics']['wiki_pages']['value'], 301)
        self.assertTrue(data['metrics']['wiki_pages']['exceeded'])
        self.assertEqual(data['metrics']['index_bytes']['value'], 40963)
        self.assertTrue(data['metrics']['index_bytes']['exceeded'])

    def test_code_external_and_invalid_anchor_links_do_not_supply_backlinks(self):
        other = self.root / 'wiki/tech/example.md'
        other.write_text(other.read_text() + '\n```md\n[坑](../pitfalls/example.md)\n```\n'
                         '`[坑](../pitfalls/example.md)`\n'
                         '[外部](https://example.com/wiki/pitfalls/example.md)\n'
                         '[断锚点](../pitfalls/example.md#不存在)\n', encoding='utf-8')
        self.assertIn('wiki/pitfalls/example.md',
                      {f['path'] for f in self.report()['hints'] if f['code'] == 'orphan'})

    def test_invalid_metadata_reports_findings_without_stale_crash(self):
        for field, value in (('updated', '[bad]'), ('raw', 'true'), ('type', '[bad]')):
            path = 'wiki/tech/example.md'
            original = (self.root / path).read_text()
            import re
            (self.root / path).write_text(re.sub(r'^' + field + r':.*$', field + ': ' + value,
                                               original, flags=re.MULTILINE), encoding='utf-8')
            result = self.run_cli('lint', '--json')
            self.assertEqual(result.returncode, 1, result)
            self.assertNotIn('Traceback', result.stdout + result.stderr)
            (self.root / path).write_text(original, encoding='utf-8')

    def test_usage_and_configuration_errors_are_two(self):
        for args in (('--stale-days', '0'), ('--stale-days', '-1'), ('--stale-days', 'abc'),
                     ('--stale-days', '1.5'), ('fix',), ('fix', 'apply'),
                     ('fix', 'apply', '--confirm'), ('fix', 'unknown'), ('unknown',)):
            for flags in ((), ('--json',)):
                result = self.run_cli('lint', *args, *flags)
                self.assertEqual(result.returncode, 2, result)
                self.assertNotIn('Traceback', result.stdout + result.stderr)
                self.assertIn('用法', result.stdout + result.stderr)
        self.config.unlink()
        result = self.run_cli('lint', '--json')
        self.assertEqual(result.returncode, 2, result)
        self.assertIn('配置', result.stdout)
        self.assertFalse(json.loads(result.stdout)['ok'])


class LintFixTests(VaultTestCase):
    def setUp(self):
        super().setUp()
        self.git('config', 'user.name', 'Lint Tests')
        self.git('config', 'user.email', 'lint@example.invalid')
        self.git('config', 'core.hooksPath', '/dev/null')
        self.git('config', 'commit.gpgsign', 'false')

    def commit_fixture(self):
        self.git('add', '.')
        self.git('commit', '-qm', '构造体检修复样例')

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def remove_index_entry(self, path):
        index = self.root / 'index.md'
        index.write_text(''.join(line for line in index.read_text().splitlines(keepends=True)
                                 if '(' + path + ')' not in line), encoding='utf-8')

    def unique_link(self):
        old, new = 'wiki/tech/example.md', 'wiki/tech/unique.md'
        (self.root / old).rename(self.root / new)
        self.replace('index.md', old, new)
        page = self.root / 'wiki/pitfalls/example.md'
        page.write_text(page.read_text() + '\n[技术](../missing/unique.md#原理)\n', encoding='utf-8')
        return 'wiki/pitfalls/example.md'

    def preview(self):
        result = self.run_cli('lint', 'fix', 'preview', '--json')
        self.assertEqual(result.returncode, 0, result)
        return json.loads(result.stdout)

    def apply(self, token):
        return self.run_cli('lint', 'fix', 'apply', '--confirm', token, '--json')

    def assert_apply(self, count):
        before = self.snapshot()
        head = self.git('rev-parse', 'HEAD')
        preview = self.preview()
        self.assertEqual(preview['fixable'], count)
        self.assertRegex(preview['fingerprint'], r'^[0-9a-f]{16}$')
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertEqual(preview['fingerprint'], self.preview()['fingerprint'])
        result = self.apply(preview['fingerprint'])
        self.assertEqual(result.returncode, 0, result)
        data = json.loads(result.stdout)
        self.assertTrue(data['ok'])
        self.assertEqual(data['commit'], self.git('rev-parse', 'HEAD').strip())
        self.assertEqual(self.git('log', '-1', '--format=%s').strip(), f'lint: 安全修复 {count} 处')
        self.assertEqual(self.git('rev-parse', 'HEAD^'), head)
        changed = set(self.git('diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD').splitlines())
        self.assertEqual(changed, set(preview['modified']))
        self.assertIn('log.md', changed)
        self.assertTrue(changed <= {'index.md', 'log.md', 'wiki/pitfalls/example.md'})
        self.assertFalse(preview['created'])
        self.assertIn(f'## [{today().isoformat()}] lint | 安全修复 {count} 处',
                      (self.root / 'log.md').read_text())
        self.assertEqual(self.run_cli('check', '--json').returncode, 0)
        self.assertEqual(self.git('status', '--porcelain'), '')
        return preview

    def test_add_missing_index_entry_in_type_section(self):
        self.remove_index_entry('wiki/pitfalls/example.md')
        self.commit_fixture()
        preview = self.assert_apply(1)
        self.assertIn('- [合法示例](wiki/pitfalls/example.md) — （待补摘要） · 2026-01-01', preview['diff'])
        index = (self.root / 'index.md').read_text()
        self.assertLess(index.index('wiki/pitfalls/example.md'), index.index('## decision'))

    def test_delete_dangling_index_row(self):
        self.replace('index.md', '## tech\n', '## tech\n\n- [失效](wiki/tech/missing.md) — 旧条目 · 2026-01-01\n')
        self.commit_fixture()
        self.assert_apply(1)
        self.assertNotIn('missing.md', (self.root / 'index.md').read_text())

    def test_relocate_unique_basename_and_keep_anchor(self):
        page = self.unique_link()
        self.commit_fixture()
        self.assert_apply(1)
        self.assertIn('[技术](../tech/unique.md#原理)', (self.root / page).read_text())

    def test_three_repairs_and_log_are_one_commit(self):
        self.unique_link()
        self.remove_index_entry('wiki/pitfalls/example.md')
        self.replace('index.md', '## tech\n', '## tech\n\n- [失效](wiki/tech/missing.md) — 旧条目 · 2026-01-01\n')
        self.commit_fixture()
        self.assertEqual(json.loads(self.run_cli('lint', '--json').stdout)['fixable'], 3)
        self.assert_apply(3)

    def test_two_basename_candidates_are_not_repaired(self):
        self.unique_link()
        copy = self.root / 'wiki/patterns/unique.md'
        copy.write_text((self.root / 'wiki/patterns/example.md').read_text(), encoding='utf-8')
        self.replace('index.md', '## pattern\n', '## pattern\n\n- [合法示例](wiki/patterns/unique.md) — 当前方法示例 · 2026-01-01\n')
        self.commit_fixture()
        before = self.snapshot()
        preview = self.preview()
        self.assertEqual(preview['fixable'], 0)
        self.assertIn('无需修复', preview['message'])
        self.assertEqual(preview['diff'], '')
        text = self.run_cli('lint', 'fix', 'preview')
        self.assertEqual(text.returncode, 0, text)
        self.assertIn('无需修复', text.stdout)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.run_cli('lint').returncode, 1)

    def test_preview_with_no_repairs_succeeds_without_commit(self):
        before = self.snapshot()
        preview = self.preview()
        self.assertEqual(preview['fixable'], 0)
        self.assertIsNone(preview['fingerprint'])
        self.assertIn('无需修复', preview['message'])
        self.assertEqual(self.snapshot(), before)

    def test_mismatched_and_stale_fingerprints_return_three_without_writes(self):
        self.remove_index_entry('wiki/pitfalls/example.md')
        self.commit_fixture()
        token = self.preview()['fingerprint']
        for change in ('wrong', 'worktree', 'head'):
            with self.subTest(change=change):
                if change == 'worktree':
                    self.replace('log.md', '# 操作日志', '# 已改日志')
                    (self.root / 'untracked.txt').write_text('新文件。', encoding='utf-8')
                elif change == 'head':
                    self.commit_fixture()
                before = self.snapshot()
                status = self.git('status', '--porcelain=v1', '-z')
                result = self.apply('bad-token' if change == 'wrong' else token)
                self.assertEqual(result.returncode, 3, result)
                self.assertIn('指纹', result.stdout)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.git('status', '--porcelain=v1', '-z'), status)

    def test_full_overlay_validation_rejects_remaining_evidence_problem(self):
        self.remove_index_entry('wiki/pitfalls/example.md')
        self.replace('wiki/tech/example.md', '42K', '55K')
        self.commit_fixture()
        before = self.snapshot()
        result = self.run_cli('lint', 'fix', 'preview', '--json')
        self.assertEqual(result.returncode, 1, result)
        data = json.loads(result.stdout)
        self.assertFalse(data['ok'])
        self.assertIn('evidence', {f['code'] for f in data['findings']})
        self.assertIsNone(data['fingerprint'])
        self.assertEqual(self.snapshot(), before)

    def test_dirty_worktree_preview_is_rejected(self):
        self.remove_index_entry('wiki/pitfalls/example.md')
        before = self.snapshot()
        result = self.run_cli('lint', 'fix', 'preview', '--json')
        self.assertEqual(result.returncode, 1, result)
        self.assertIn('worktree', result.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_add_index_entries_for_all_types_and_chinese_headings(self):
        index = self.root / 'index.md'
        index.write_text('# 总目录\n\n## 踩坑\n\n## 决策\n\n## 技术\n\n## 模式\n\n## 项目\n', encoding='utf-8')
        self.commit_fixture()
        preview = self.preview()
        self.assertEqual(preview['fixable'], 5)
        applied = self.apply(preview['fingerprint'])
        self.assertEqual(applied.returncode, 0, applied)
        self.assertEqual(self.run_cli('check', '--json').returncode, 0)
        text = index.read_text()
        for heading, directory in (('踩坑', 'pitfalls'), ('决策', 'decisions'), ('技术', 'tech'),
                                   ('模式', 'patterns'), ('项目', 'projects')):
            section = text.split('## ' + heading + '\n')[1].split('\n## ')[0]
            self.assertIn('wiki/' + directory + '/example.md', section)

    def test_missing_section_is_not_invented_and_other_problems_are_not_fixed(self):
        self.remove_index_entry('wiki/pitfalls/example.md')
        self.replace('index.md', '## pitfall', '## 未知类型')
        self.replace('wiki/pitfalls/example.md', '## 症状', '## 错误章节')
        self.commit_fixture()
        before = self.snapshot()
        preview = self.preview()
        self.assertEqual(preview['fixable'], 0)
        self.assertEqual(self.snapshot(), before)

    def test_link_repair_preserves_titles_references_and_ignores_code_and_plain_text(self):
        page = self.unique_link()
        text = (self.root / page).read_text()
        text += ('\n[角括号](<../missing/unique.md#原理> "标题")\n'
                 '[参考][tech] 和 [另一引用][tech]\n'
                 '[tech]: ../missing/unique.md#原理 "参考标题"\n'
                 '普通文字 ../missing/unique.md#原理\n'
                 '`[代码](../missing/unique.md#原理)`\n'
                 '\\[转义](../missing/unique.md#原理)\n'
                 '```md\n[示例](../missing/unique.md#原理)\n```\n')
        (self.root / page).write_text(text, encoding='utf-8')
        self.commit_fixture()
        self.assert_apply(3)
        fixed = (self.root / page).read_text()
        self.assertIn('[角括号](<../tech/unique.md#原理> "标题")', fixed)
        self.assertIn('[tech]: ../tech/unique.md#原理 "参考标题"', fixed)
        self.assertIn('普通文字 ../missing/unique.md#原理', fixed)
        self.assertIn('`[代码](../missing/unique.md#原理)`', fixed)
        self.assertIn('\\[转义](../missing/unique.md#原理)', fixed)
        self.assertIn('```md\n[示例](../missing/unique.md#原理)\n```', fixed)

    def test_frontmatter_markdown_link_to_unique_file_is_repaired(self):
        page = self.unique_link()
        self.replace(page, 'tags: [示例]', 'related: "[技术](../missing/unique.md#原理)"\ntags: [示例]')
        self.commit_fixture()
        self.assert_apply(2)
        self.assertIn('related: "[技术](../tech/unique.md#原理)"', (self.root / page).read_text())

    def test_repair_whitelist_rejects_sources_new_files_and_symlinks(self):
        from kblib.lint import _validate_repairs
        from kblib.writer import WriteError
        for path in ('raw/example.md', 'inbox/2026-01-01-example.md', 'wiki/tech/new.md',
                     'SCHEMA.md', '../outside.md', 'wiki/tech/other.txt'):
            with self.subTest(path=path), self.assertRaises(WriteError):
                _validate_repairs(self.vault(), {path: '禁止写入。'})
        linked = self.root / 'wiki/tech/linked.md'
        linked.symlink_to(self.root / 'wiki/tech/example.md')
        with self.assertRaises(WriteError):
            _validate_repairs(self.vault(), {'wiki/tech/linked.md': '禁止写入。'})

    def test_existing_file_with_bad_anchor_and_non_wiki_links_are_not_repaired(self):
        page = self.root / 'wiki/pitfalls/example.md'
        page.write_text(page.read_text() + '\n[锚点](../tech/example.md#不存在)\n', encoding='utf-8')
        entry = self.root / 'inbox/2026-01-02-new.md'
        text = (self.root / 'inbox/2026-01-01-example.md').read_text().replace('2026-01-01', '2026-01-02')
        entry.write_text(text + '\n[断链](../wrong/example.md)\n', encoding='utf-8')
        self.commit_fixture()
        before = self.snapshot()
        self.assertEqual(self.preview()['fixable'], 0)
        self.assertEqual(self.snapshot(), before)

    def test_log_is_append_only_and_sources_remain_identical(self):
        log = self.root / 'log.md'
        log.write_text(log.read_text() + '\n\n\n', encoding='utf-8')
        self.remove_index_entry('wiki/pitfalls/example.md')
        self.commit_fixture()
        original_log = log.read_bytes()
        sources = {p: p.read_bytes() for scope in ('raw', 'inbox') for p in (self.root / scope).rglob('*') if p.is_file()}
        self.assert_apply(1)
        self.assertTrue(log.read_bytes().startswith(original_log))
        self.assertEqual({p: p.read_bytes() for p in sources}, sources)

    def test_shared_writer_rolls_back_failed_lint_write(self):
        import contextlib
        import io
        import os
        from unittest.mock import patch
        import kb
        self.unique_link()
        self.remove_index_entry('wiki/pitfalls/example.md')
        self.commit_fixture()
        token = self.preview()['fingerprint']
        before = self.snapshot()
        real_replace = os.replace
        calls = []

        def fail_once(source, target):
            calls.append(target)
            if len(calls) == 2:
                raise OSError('simulated replace failure')
            return real_replace(source, target)

        output = io.StringIO()
        with patch.dict(os.environ, self.env), patch('kblib.writer.os.replace', side_effect=fail_once):
            with contextlib.redirect_stdout(output):
                code = kb.main(['lint', 'fix', 'apply', '--confirm', token, '--json'])
        self.assertEqual(code, 1, output.getvalue())
        self.assertIn('回滚', output.getvalue())
        self.assertEqual(self.snapshot(), before)

    def test_commit_failure_keeps_repairs_and_masks_reason(self):
        self.remove_index_entry('wiki/pitfalls/example.md')
        self.commit_fixture()
        token = self.preview()['fingerprint']
        head = self.git('rev-parse', 'HEAD')
        secret = 'ghp_' + 'a2B' * 12
        hooks = self.base / 'hooks'
        hooks.mkdir()
        hook = hooks / 'pre-commit'
        hook.write_text('#!/bin/sh\necho "' + secret + '" >&2\nexit 1\n', encoding='utf-8')
        hook.chmod(0o755)
        self.git('config', 'core.hooksPath', str(hooks))
        applied = self.apply(token)
        self.assertEqual(applied.returncode, 1, applied)
        self.assertNotIn(secret, applied.stdout + applied.stderr)
        self.assertIn('提交失败', applied.stdout)
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertEqual(set(self.git('diff', '--cached', '--name-only').splitlines()), {'index.md', 'log.md'})

    def test_text_preview_and_apply_show_diff_fingerprint_and_commit(self):
        self.remove_index_entry('wiki/pitfalls/example.md')
        self.commit_fixture()
        text = self.run_cli('lint', 'fix', 'preview')
        self.assertEqual(text.returncode, 0, text)
        self.assertIn('预览指纹', text.stdout)
        self.assertIn('--- index.md', text.stdout)
        self.assertIn('确认', text.stdout)
        result = self.run_cli('lint', 'fix', 'apply', '--confirm', self.preview()['fingerprint'])
        self.assertEqual(result.returncode, 0, result)
        self.assertIn('提交', result.stdout)
        self.assertIn(self.git('rev-parse', 'HEAD').strip(), result.stdout)


if __name__ == '__main__':
    unittest.main()
