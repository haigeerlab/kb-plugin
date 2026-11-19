import json
import contextlib
import io
import os
import shutil
import unittest
from unittest.mock import patch

from vault_support import ROOT, VaultTestCase
from kblib.vault import today


class SaveTests(VaultTestCase):
    def setUp(self):
        super().setUp()
        self.draft = self.base / '草稿 with spaces'
        self.draft.mkdir()
        self.entry = 'inbox/2026-01-02-save-example.md'
        self.page = 'wiki/pitfalls/save-example.md'
        self.write_draft(self.entry, '---\ncaptured: 2026-01-02\nsource: session\n'
                         'host: codex\ntitle: 保存示例\n---\n# 摘录\n\n当前方法已经验证。\n')
        page = (self.root / 'wiki/pitfalls/example.md').read_text(encoding='utf-8')
        page = page.replace('合法示例', '保存示例').replace(
            'raw: [inbox/2026-01-01-example.md, raw/example.md]', 'raw: [' + self.entry + ']')
        self.write_draft(self.page, page)
        index = (self.root / 'index.md').read_text(encoding='utf-8')
        self.write_draft('index.md', index.replace('## pitfall\n', '## pitfall\n\n'
                         '- [保存示例](' + self.page + ') — 保存经验 · 2026-01-02\n'))
        self.write_draft('log.md', (self.root / 'log.md').read_text(encoding='utf-8')
                         + '\n## [2026-01-02] save | 保存示例\n\n保存一条经验。\n')
        self.git('config', 'user.name', 'Save Tests')
        self.git('config', 'user.email', 'save@example.invalid')
        self.git('config', 'core.hooksPath', '/dev/null')
        self.git('config', 'commit.gpgsign', 'false')

    def write_draft(self, path, text):
        target = self.draft / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')

    def preview(self, *flags, draft=None):
        return self.run_cli('save', 'preview', str(draft or self.draft), *flags)

    def apply(self, fingerprint, *flags):
        return self.run_cli('save', 'apply', str(self.draft), '--confirm', fingerprint, *flags)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file() and '.git' not in p.relative_to(self.root).parts}

    def test_preview_valid_draft_is_read_only_and_has_relative_unified_diff(self):
        before = self.snapshot()
        result = self.preview('--json')
        self.assertEqual(result.returncode, 0, result)
        data = json.loads(result.stdout)
        self.assertEqual(set(data), {'ok', 'fingerprint', 'created', 'modified', 'diff',
                                     'replaced_aliases', 'findings'})
        self.assertTrue(data['ok'])
        self.assertRegex(data['fingerprint'], r'^[0-9a-f]{16}$')
        self.assertEqual(data['created'], [self.entry, self.page])
        self.assertEqual(data['modified'], ['index.md', 'log.md'])
        self.assertIn('+++ ' + self.page, data['diff'])
        self.assertIn('+当前方法已经验证。', data['diff'])
        self.assertIn('--- index.md', data['diff'])
        self.assertEqual(data['findings'], [])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertEqual(json.loads(self.preview('--json').stdout)['fingerprint'], data['fingerprint'])

    def assert_rejected(self, code='path', draft=None):
        before = self.snapshot()
        result = self.preview('--json', draft=draft)
        self.assertEqual(result.returncode, 1, result)
        data = json.loads(result.stdout)
        self.assertFalse(data['ok'])
        self.assertIn(code, [f['code'] for f in data['findings']])
        self.assertEqual(self.snapshot(), before)
        result = self.apply('0' * 16, '--json')
        self.assertNotEqual(result.returncode, 0, result)
        self.assertEqual(self.snapshot(), before)
        return data

    def test_existing_inbox_is_rejected(self):
        self.write_draft('inbox/2026-01-01-example.md', '禁止改写。')
        self.assert_rejected()

    def test_raw_and_other_paths_are_rejected(self):
        for path in ('raw/new.md', 'raw/example.md', 'SCHEMA.md', 'delete.json'):
            with self.subTest(path=path):
                self.write_draft(path, '禁止写入。')
                self.assert_rejected()
                (self.draft / path).unlink()
                if path.startswith('raw/'):
                    (self.draft / 'raw').rmdir()

    def test_parent_traversal_in_draft_argument_is_rejected(self):
        self.assert_rejected(draft=str(self.draft / '..' / self.draft.name))

    def test_symlink_file_and_directory_are_rejected(self):
        for directory in (False, True):
            with self.subTest(directory=directory):
                target = self.draft / ('wiki/escape' if directory else 'wiki/escape.md')
                target.symlink_to(self.base if directory else self.root / 'index.md',
                                  target_is_directory=directory)
                self.assert_rejected()
                target.unlink()

    def test_target_outside_vault_is_rejected(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (self.root / 'wiki/escape').symlink_to(outside, target_is_directory=True)
        self.git('add', 'wiki/escape')
        self.git('commit', '-qm', '库外路径测试')
        self.write_draft('wiki/escape/new.md', '禁止写到库外。')
        self.assert_rejected()
        self.assertEqual(list(outside.iterdir()), [])

    def test_two_inbox_entries_are_rejected(self):
        self.write_draft('inbox/2026-01-02-second.md', '第二条。')
        self.assert_rejected()

    def test_zero_inbox_entries_are_rejected(self):
        (self.draft / self.entry).unlink()
        self.assert_rejected()

    def test_redaction_failure_is_masked_and_never_written(self):
        secret = 'ghp_' + 'a2B' * 12
        self.write_draft(self.entry, (self.draft / self.entry).read_text() + secret + '\n')
        data = self.assert_rejected('redaction')
        self.assertNotIn(secret, json.dumps(data))
        self.assertEqual(data['diff'], '')
        result = self.preview()
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_missing_index_entry_reports_index(self):
        (self.draft / 'index.md').unlink()
        self.assert_rejected('index')

    def test_redaction_and_contract_findings_are_all_reported(self):
        secret = 'ghp_' + 'a2B' * 12
        self.write_draft(self.entry, (self.draft / self.entry).read_text() + secret + '\n')
        (self.draft / 'index.md').unlink()
        data = self.assert_rejected('redaction')
        self.assertIn('index', [f['code'] for f in data['findings']])
        self.assertNotIn(secret, json.dumps(data))
        self.assertEqual(data['diff'], '')

    def test_diff_includes_change_to_final_newline(self):
        text = (self.root / 'log.md').read_text(encoding='utf-8')
        self.assertTrue(text.endswith('\n'))
        self.write_draft('log.md', text.rstrip('\n'))
        result = self.preview('--json')
        self.assertEqual(result.returncode, 0, result)
        data = json.loads(result.stdout)
        self.assertIn('--- log.md', data['diff'])
        self.assertIn('No newline at end of file', data['diff'])

    def test_alias_replacement_precedes_scan_and_is_used_in_diff(self):
        (self.config.parent / 'aliases.json').write_text('{"项目真名": "proj-test"}', encoding='utf-8')
        (self.config.parent / 'blocklist.txt').write_text('项目真名\n', encoding='utf-8')
        self.write_draft(self.entry, (self.draft / self.entry).read_text() + '项目真名\n')
        result = self.preview('--json')
        self.assertEqual(result.returncode, 0, result)
        data = json.loads(result.stdout)
        self.assertEqual(data['replaced_aliases'], 1)
        self.assertIn('+proj-test', data['diff'])
        self.assertNotIn('项目真名', data['diff'])
        self.assertIn('项目真名', (self.draft / self.entry).read_text())

    def test_full_check_uses_real_blocklist_and_git_history(self):
        (self.config.parent / 'blocklist.txt').write_text('当前方法\n', encoding='utf-8')
        self.assert_rejected('redaction')
        (self.config.parent / 'blocklist.txt').unlink()
        self.replace('raw/example.md', '当前方法', '改写方法')
        self.git('add', 'raw/example.md')
        self.git('commit', '-qm', '错误改写原文')
        self.assert_rejected('immutable')

    def test_overlay_check_reads_blocklist_for_unchanged_files(self):
        (self.config.parent / 'blocklist.txt').write_text('外部资料\n', encoding='utf-8')
        data = self.assert_rejected('redaction')
        self.assertTrue(any(f['path'] == 'raw/example.md' for f in data['findings']))

    def test_omitted_existing_files_are_preserved_not_deleted(self):
        old = self.snapshot()
        result = self.apply(self.fingerprint(), '--json')
        self.assertEqual(result.returncode, 0, result)
        for path, data in old.items():
            if path not in ('index.md', 'log.md'):
                self.assertEqual((self.root / path).read_bytes(), data)

    def test_directory_cannot_replace_existing_file_as_deletion(self):
        (self.draft / self.page).unlink()
        (self.draft / 'wiki/pitfalls/example.md').mkdir()
        self.assert_rejected()

    def test_invalid_utf8_and_special_files_are_rejected(self):
        path = self.draft / 'wiki/unreadable.txt'
        path.write_bytes(b'\xff')
        self.assert_rejected()
        path.unlink()
        os.mkfifo(path)
        self.assert_rejected()

    def test_draft_root_symlink_is_rejected(self):
        linked = self.base / 'linked-draft'
        linked.symlink_to(self.draft, target_is_directory=True)
        self.assert_rejected(draft=linked)

    def test_modified_wiki_and_noop_files_are_reported_correctly(self):
        self.page = 'wiki/pitfalls/example.md'
        (self.draft / 'wiki/pitfalls/save-example.md').unlink()
        self.write_draft(self.page, (self.root / self.page).read_text() + '\n补充经验。\n')
        self.write_draft('index.md', (self.root / 'index.md').read_text())
        result = self.preview('--json')
        self.assertEqual(result.returncode, 0, result)
        data = json.loads(result.stdout)
        self.assertEqual(data['created'], [self.entry])
        self.assertEqual(data['modified'], ['log.md', self.page])
        self.assertIn('--- ' + self.page, data['diff'])
        self.assertNotIn('--- index.md', data['diff'])

    def test_main_wiki_title_wins_over_project_hub(self):
        page = (self.root / 'wiki/projects/example.md').read_text(encoding='utf-8')
        self.write_draft('wiki/projects/example.md', page.replace('合法示例', '项目枢纽'))
        result = self.apply(self.fingerprint(), '--json')
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(self.git('log', '-1', '--format=%s').strip(), 'save: 保存示例')

    def test_project_only_save_uses_its_wiki_title(self):
        (self.draft / self.page).unlink()
        (self.draft / 'index.md').unlink()
        page = (self.root / 'wiki/projects/example.md').read_text(encoding='utf-8')
        self.write_draft('wiki/projects/example.md', page.replace('合法示例', '项目经验'))
        result = self.apply(self.fingerprint(), '--json')
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(self.git('log', '-1', '--format=%s').strip(), 'save: 项目经验')

    def test_dirty_worktree_preview_is_rejected(self):
        for staged in (False, True):
            with self.subTest(staged=staged):
                (self.root / 'unrelated.md').write_text('他人的改动。', encoding='utf-8')
                if staged:
                    self.git('add', 'unrelated.md')
                data = self.assert_rejected('worktree')
                self.assertIn('未提交改动', str(data))

    def fingerprint(self):
        result = self.preview('--json')
        self.assertEqual(result.returncode, 0, result)
        return json.loads(result.stdout)['fingerprint']

    def test_apply_success_commits_only_save_files_and_passes_check(self):
        fingerprint = self.fingerprint()
        before_count = int(self.git('rev-list', '--count', 'HEAD'))
        old_entry = (self.root / 'inbox/2026-01-01-example.md').read_bytes()
        result = self.apply(fingerprint, '--json')
        self.assertEqual(result.returncode, 0, result)
        data = json.loads(result.stdout)
        self.assertEqual(set(data), {'ok', 'commit', 'created', 'modified', 'findings'})
        self.assertEqual(data['commit'], self.git('rev-parse', 'HEAD').strip())
        self.assertEqual(data['created'], [self.entry, self.page])
        self.assertEqual(data['modified'], ['index.md', 'log.md'])
        self.assertEqual(data['findings'], [])
        self.assertEqual(int(self.git('rev-list', '--count', 'HEAD')), before_count + 1)
        self.assertEqual(self.git('log', '-1', '--format=%s').strip(), 'save: 保存示例')
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertEqual((self.root / 'inbox/2026-01-01-example.md').read_bytes(), old_entry)
        self.assertEqual(self.run_cli('check', '--json').returncode, 0)

    def test_alias_replacement_is_written_and_draft_is_preserved(self):
        (self.config.parent / 'aliases.json').write_text('{"项目真名": "proj-test"}', encoding='utf-8')
        (self.config.parent / 'blocklist.txt').write_text('项目真名\n', encoding='utf-8')
        self.write_draft(self.entry, (self.draft / self.entry).read_text() + '项目真名\n')
        result = self.apply(self.fingerprint(), '--json')
        self.assertEqual(result.returncode, 0, result)
        self.assertIn('proj-test', (self.root / self.entry).read_text())
        self.assertNotIn('项目真名', (self.root / self.entry).read_text())
        self.assertIn('项目真名', (self.draft / self.entry).read_text())

    def test_draft_change_after_preview_returns_three_without_writing(self):
        fingerprint = self.fingerprint()
        self.write_draft(self.entry, (self.draft / self.entry).read_text() + '补充。\n')
        before = self.snapshot()
        result = self.apply(fingerprint, '--json')
        self.assertEqual(result.returncode, 3, result)
        self.assertIn('fingerprint', result.stdout)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_new_commit_after_preview_returns_three_without_writing(self):
        fingerprint = self.fingerprint()
        (self.root / 'unrelated.txt').write_text('另一个提交。', encoding='utf-8')
        self.git('add', 'unrelated.txt')
        self.git('commit', '-qm', '另一个提交')
        before = self.snapshot()
        result = self.apply(fingerprint, '--json')
        self.assertEqual(result.returncode, 3, result)
        self.assertEqual(self.snapshot(), before)

    def test_worktree_change_after_preview_returns_three_without_writing(self):
        fingerprint = self.fingerprint()
        self.replace('index.md', '# 知识库总目录', '# 已修改的总目录')
        before = self.snapshot()
        status = self.git('status', '--porcelain')
        result = self.apply(fingerprint, '--json')
        self.assertEqual(result.returncode, 3, result)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.git('status', '--porcelain'), status)

    def test_alias_configuration_change_invalidates_fingerprint(self):
        self.write_draft(self.entry, (self.draft / self.entry).read_text() + '项目真名\n')
        fingerprint = self.fingerprint()
        (self.config.parent / 'aliases.json').write_text('{"项目真名": "proj-test"}', encoding='utf-8')
        before = self.snapshot()
        result = self.apply(fingerprint, '--json')
        self.assertEqual(result.returncode, 3, result)
        self.assertEqual(self.snapshot(), before)

    def test_write_failure_rolls_back_existing_and_new_files(self):
        import kb
        fingerprint = self.fingerprint()
        before = self.snapshot()
        head = self.git('rev-parse', 'HEAD')
        real_replace = os.replace
        calls = []

        def fail_once(source, target):
            calls.append(target)
            if len(calls) == 4:
                raise OSError('simulated replace failure')
            return real_replace(source, target)

        with patch.dict(os.environ, self.env), patch('kblib.save.os.replace', side_effect=fail_once):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = kb.main(['save', 'apply', str(self.draft), '--confirm', fingerprint, '--json'])
        self.assertEqual(code, 1, output.getvalue())
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertIn('回滚', output.getvalue())
        self.assertEqual(list(self.root.rglob('.kb-save-*')), [])

    def test_prepare_failure_does_not_write_any_target(self):
        import kb
        fingerprint = self.fingerprint()
        before = self.snapshot()
        real_fsync = os.fsync
        calls = []

        def fail_once(descriptor):
            calls.append(descriptor)
            if len(calls) == 3:
                raise OSError('simulated temporary write failure')
            return real_fsync(descriptor)

        with patch.dict(os.environ, self.env), patch('kblib.save.os.fsync', side_effect=fail_once):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = kb.main(['save', 'apply', str(self.draft), '--confirm', fingerprint, '--json'])
        self.assertEqual(code, 1, output.getvalue())
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertEqual(list(self.root.rglob('.kb-save-*')), [])

    def test_commit_failure_keeps_written_files_and_reports_masked_reason(self):
        fingerprint = self.fingerprint()
        head = self.git('rev-parse', 'HEAD')
        hooks = self.base / 'hooks'
        hooks.mkdir()
        secret = 'ghp_' + 'a2B' * 12
        hook = hooks / 'pre-commit'
        hook.write_text('#!/bin/sh\necho "' + secret + '" >&2\nexit 1\n', encoding='utf-8')
        hook.chmod(0o755)
        self.git('config', 'core.hooksPath', str(hooks))
        result = self.apply(fingerprint, '--json')
        self.assertEqual(result.returncode, 1, result)
        self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertIn('提交失败', result.stdout)
        self.assertIn('保留', result.stdout)
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertTrue((self.root / self.entry).exists())
        self.assertEqual((self.root / self.page).read_bytes(), (self.draft / self.page).read_bytes())
        self.assertIn(self.entry, self.git('diff', '--cached', '--name-only'))

    def test_no_new_content_uses_inbox_title_then_filename(self):
        for title in ('保存示例', None):
            with self.subTest(title=title):
                if title is None:
                    self.entry = 'inbox/2026-01-02-another.md'
                    (self.draft / 'inbox/2026-01-02-save-example.md').unlink()
                    self.write_draft(self.entry, '---\ncaptured: 2026-01-02\nsource: session\n'
                                     'host: codex\n---\n没有新内容。\n')
                if (self.draft / self.page).exists():
                    (self.draft / self.page).unlink()
                    (self.draft / 'index.md').unlink()
                result = self.apply(self.fingerprint(), '--json')
                self.assertEqual(result.returncode, 0, result)
                self.assertEqual(self.git('log', '-1', '--format=%s').strip(),
                                 'save: ' + (title or self.entry.split('/')[-1]))
                self.assertEqual(self.run_cli('check', '--json').returncode, 0)

    def test_usage_and_configuration_errors_return_two(self):
        for args in (('save',), ('save', 'apply', str(self.draft)),
                     ('save', 'apply', str(self.draft), '--confirm'),
                     ('save', 'preview'), ('save', 'preview', str(self.base / 'missing'))):
            with self.subTest(args=args):
                result = self.run_cli(*args, '--json')
                self.assertEqual(result.returncode, 2, result)
                self.assertFalse(json.loads(result.stdout)['ok'])
                self.assertNotIn('Traceback', result.stdout + result.stderr)
        self.config.unlink()
        result = self.preview('--json')
        self.assertEqual(result.returncode, 2, result)
        self.assertIn('配置', result.stdout)

    def test_text_output_exposes_preview_and_commit_in_chinese(self):
        result = self.preview()
        self.assertEqual(result.returncode, 0, result)
        self.assertIn('预览指纹', result.stdout)
        self.assertIn('新建', result.stdout)
        self.assertIn('确认', result.stdout)
        result = self.apply(self.fingerprint())
        self.assertEqual(result.returncode, 0, result)
        self.assertIn('提交', result.stdout)
        self.assertIn(self.git('rev-parse', 'HEAD').strip(), result.stdout)


class SaveEndToEndTests(VaultTestCase):
    def test_three_sources_save_conflict_with_immutable_inbox_history(self):
        shutil.rmtree(self.root)
        self.root.mkdir()
        initialized = self.run_cli('init', '--confirm', '--json')
        self.assertEqual(initialized.returncode, 0, initialized)
        self.git('config', 'user.name', 'Save Tests')
        self.git('config', 'user.email', 'save@example.invalid')
        self.git('config', 'core.hooksPath', '/dev/null')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('add', '.')
        self.git('commit', '-qm', '初始化知识库')
        fixtures = ROOT / 'tests/fixtures/vaults/dispatch'
        date = today().isoformat()
        pitfall_path = 'wiki/pitfalls/codex-exec.md'
        decision_path = 'wiki/decisions/dispatch-cost.md'
        pitfall = (fixtures / pitfall_path).read_text(encoding='utf-8')
        pitfall = pitfall[:pitfall.index('相关决策：')]
        first_decision = (
            '---\ntype: decision\ntitle: 派活成本与判据\nstatus: current\n'
            'created: 2026-08-28\nupdated: 2026-08-28\n'
            'raw: [inbox/2026-08-28-dispatch-claim.md]\n---\n# 派活成本与判据\n\n'
            '## 背景\n\n主会话输出 40.26M token，平均每条消息读 263k 缓存。\n\n'
            '## 选项\n\n留在主会话，或把机械活派给子代理。\n\n'
            '## 决定\n\n默认把机械活派给子代理。\n\n'
            '## 理由\n\n子代理自带独立短上下文，推断成本较低。\n\n'
            '## 后果\n\n需要通过后续实测核对成本。\n\n'
            '## 现行判据\n\n机械活优先派出去。\n')
        cases = [
            ('s1-codex-exec-pitfalls.md', '2026-08-29-codex-exec.md',
             pitfall_path, pitfall, '从代理调用 codex exec 的坑', 'pitfall'),
            ('s2-subagent-cheaper-claim.md', '2026-08-28-dispatch-claim.md',
             decision_path, first_decision, '派活成本与判据', 'decision'),
            ('s3-dispatch-verdict.md', '2026-10-06-dispatch-verdict.md',
             decision_path, (fixtures / decision_path).read_text(encoding='utf-8'),
             '派活成本与判据', 'decision'),
        ]
        original_entries = {}
        save_commits = []
        for number, (source, name, page, text, title, kind) in enumerate(cases, 1):
            with self.subTest(save=number):
                draft = self.base / ('草稿-' + str(number))
                (draft / 'inbox').mkdir(parents=True)
                (draft / page).parent.mkdir(parents=True)
                source_text = (ROOT / 'tests/fixtures/sources' / source).read_text(encoding='utf-8')
                entry_text = ('---\ncaptured: ' + name[:10] + '\nsource: session\n'
                              'host: claude-code\nproject: proj-example\n---\n' + source_text)
                (draft / 'inbox' / name).write_text(entry_text, encoding='utf-8')
                (draft / page).write_text(text, encoding='utf-8')
                index = (self.root / 'index.md').read_text(encoding='utf-8')
                if number < 3:
                    index = index.replace('## ' + kind + '\n', '## ' + kind + '\n\n'
                                          '- [' + title + '](' + page + ') — 会话经验 · ' + date + '\n')
                    (draft / 'index.md').write_text(index, encoding='utf-8')
                log = (self.root / 'log.md').read_text(encoding='utf-8')
                (draft / 'log.md').write_text(log + '\n## [' + date + '] save | ' + title
                                            + '\n\n保存会话经验。\n', encoding='utf-8')
                preview = self.run_cli('save', 'preview', str(draft), '--json')
                self.assertEqual(preview.returncode, 0, preview)
                data = json.loads(preview.stdout)
                self.assertEqual(data['findings'], [])
                applied = self.run_cli('save', 'apply', str(draft), '--confirm',
                                       data['fingerprint'], '--json')
                self.assertEqual(applied.returncode, 0, applied)
                save_commits.append(json.loads(applied.stdout)['commit'])
                self.assertEqual(self.git('log', '-1', '--format=%s').strip(), 'save: ' + title)
                check = self.run_cli('check', '--json')
                self.assertEqual(check.returncode, 0, check)
                self.assertEqual(json.loads(check.stdout), {'ok': True, 'findings': []})
                self.assertEqual(int(self.git('rev-list', '--count', 'HEAD')), number + 1)
                original_entries['inbox/' + name] = entry_text.encode('utf-8')
                for entry, expected in original_entries.items():
                    self.assertEqual((self.root / entry).read_bytes(), expected)
                    self.assertEqual(len(self.git('log', '--format=%H', '--', entry).splitlines()), 1)
                self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertEqual(len(set(save_commits)), 3)
        final_decision = (self.root / decision_path).read_text(encoding='utf-8')
        self.assertIn('[!outdated]', final_decision)
        self.assertIn('40.26M', final_decision)
        self.assertIn('15%～54%', final_decision)
        self.assertIn('inbox/2026-08-28-dispatch-claim.md', final_decision)
        self.assertIn('inbox/2026-10-06-dispatch-verdict.md', final_decision)
        self.assertEqual(len(self.git('log', '--format=%s', '--grep=^save:').splitlines()), 3)


if __name__ == '__main__':
    unittest.main()
