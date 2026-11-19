import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
from unittest.mock import patch

from vault_support import ROOT, VaultTestCase
import kb
from kblib import writer


class CompileTests(VaultTestCase):
    def setUp(self):
        super().setUp()
        self.env['KB_STATE_DIR'] = str(self.base / 'state')
        self.git('config', 'user.name', 'Compile Tests')
        self.git('config', 'user.email', 'compile@example.invalid')
        self.git('config', 'core.hooksPath', '/dev/null')
        self.git('config', 'commit.gpgsign', 'false')
        self.entry = 'inbox/2026-01-02-compile-example.md'
        self.page = 'wiki/pitfalls/compile-example.md'
        self.draft = self.base / '编译草稿'
        self.draft.mkdir()
        self.make_draft()

    def write_draft(self, path, text, draft=None):
        target = (draft or self.draft) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')

    def make_draft(self, source=None):
        if source is None:
            self.write_draft(self.entry, '---\ncaptured: 2026-01-02\nsource: session\n'
                             'host: claude-code\ntitle: 编译摘录\n---\n# 摘录\n\n当前方法已经验证。\n')
        source = source or self.entry
        text = (self.root / 'wiki/pitfalls/example.md').read_text(encoding='utf-8')
        self.write_draft(self.page, text.replace('合法示例', '编译示例').replace(
            'raw: [inbox/2026-01-01-example.md, raw/example.md]', 'raw: [' + source + ']'))
        index = (self.root / 'index.md').read_text(encoding='utf-8')
        self.write_draft('index.md', index.replace('## pitfall\n', '## pitfall\n\n'
                         '- [编译示例](' + self.page + ') — 编译经验 · 2026-01-02\n'))
        self.write_draft('log.md', (self.root / 'log.md').read_text(encoding='utf-8')
                         + '\n## [2026-01-02] compile | 编译示例\n\n整理经验。\n')

    def preview(self, draft=None, json_output=True):
        flags = ('--json',) if json_output else ()
        return self.run_cli('compile', 'preview', str(draft or self.draft), *flags)

    def fingerprint(self, draft=None):
        result = self.preview(draft)
        self.assertEqual(result.returncode, 0, result)
        return json.loads(result.stdout)['fingerprint']

    def apply(self, fingerprint, draft=None):
        return self.run_cli('compile', 'apply', str(draft or self.draft), '--confirm', fingerprint, '--json')

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file() and '.git' not in p.relative_to(self.root).parts}

    def assert_rejected(self, code='path', draft=None):
        before = self.snapshot()
        result = self.preview(draft)
        self.assertEqual(result.returncode, 1, result)
        data = json.loads(result.stdout)
        self.assertIn(code, [f['code'] for f in data['findings']])
        self.assertEqual(self.snapshot(), before)
        self.assertNotEqual(self.apply('0' * 16, draft).returncode, 0)
        self.assertEqual(self.snapshot(), before)
        return data

    def invoke(self, *args):
        output = io.StringIO()
        with patch.dict(os.environ, self.env), contextlib.redirect_stdout(output):
            code = kb.main([*args, '--json'])
        return code, json.loads(output.getvalue())

    def test_one_inbox_preview_is_read_only_with_save_result_contract(self):
        before = self.snapshot()
        result = self.preview()
        self.assertEqual(result.returncode, 0, result)
        data = json.loads(result.stdout)
        self.assertEqual(set(data), {'ok', 'fingerprint', 'created', 'modified', 'diff', 'replaced_aliases', 'findings'})
        self.assertEqual(data['created'], [self.entry, self.page])
        self.assertEqual(data['modified'], ['index.md', 'log.md'])
        self.assertEqual(data['findings'], [])
        self.assertIn('+++ ' + self.page, data['diff'])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.git('status', '--porcelain'), '')
        text = self.preview(json_output=False)
        self.assertEqual(text.returncode, 0, text)
        self.assertIn('compile apply', text.stdout)
        self.assertIn(data['fingerprint'], text.stdout)

    def test_zero_inbox_references_existing_backlog_and_uses_wiki_title(self):
        (self.draft / self.entry).unlink()
        source = 'inbox/2026-01-02-backlog.md'
        (self.root / source).write_text((self.root / 'inbox/2026-01-01-example.md').read_text().replace(
            '2026-01-01', '2026-01-02'), encoding='utf-8')
        self.git('add', source)
        self.git('commit', '-qm', '加入待编译摘录')
        self.make_draft(source)
        original = (self.root / source).read_bytes()
        result = self.apply(self.fingerprint())
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(json.loads(result.stdout)['created'], [self.page])
        self.assertEqual((self.root / source).read_bytes(), original)
        self.assertEqual(self.git('log', '-1', '--format=%s').strip(), 'compile: 编译示例')
        self.assertEqual(self.run_cli('check', '--json').returncode, 0)
        self.assertNotIn(source, {f['path'] for f in json.loads(self.run_cli('lint', '--json').stdout)['hints']
                                  if f['code'] == 'backlog'})

    def test_two_inbox_entries_and_existing_inbox_or_raw_are_rejected(self):
        for path in ('inbox/2026-01-02-second.md', 'inbox/2026-01-01-example.md',
                     'raw/example.md', 'raw/new.md', 'SCHEMA.md'):
            with self.subTest(path=path):
                self.write_draft(path, '禁止写入。')
                self.assert_rejected()
                (self.draft / path).unlink()
                if path.startswith('raw/'):
                    (self.draft / 'raw').rmdir()

    def test_zero_inbox_without_changed_wiki_is_rejected_even_with_log_or_noop_wiki(self):
        (self.draft / self.entry).unlink()
        (self.draft / self.page).unlink()
        (self.draft / 'index.md').unlink()
        for noop in (False, True):
            if noop:
                self.write_draft('wiki/pitfalls/example.md', (self.root / 'wiki/pitfalls/example.md').read_text())
            data = self.assert_rejected('compile')
            self.assertIn('没有可写入的内容', str(data))
        shutil.rmtree(self.draft)
        self.draft.mkdir()
        self.assert_rejected('compile')

    def test_main_wiki_title_wins_over_project_hub(self):
        self.write_draft('wiki/projects/example.md', (self.root / 'wiki/projects/example.md').read_text().replace(
            '合法示例', '项目枢纽'))
        result = self.apply(self.fingerprint())
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(self.git('log', '-1', '--format=%s').strip(), 'compile: 编译示例')

    def test_title_falls_back_to_inbox_title_or_filename_without_wiki(self):
        (self.draft / self.page).unlink()
        (self.draft / 'index.md').unlink()
        result = self.apply(self.fingerprint())
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(self.git('log', '-1', '--format=%s').strip(), 'compile: 编译摘录')
        (self.draft / self.entry).unlink()
        self.entry = 'inbox/2026-01-02-no-title.md'
        self.write_draft(self.entry, '---\ncaptured: 2026-01-02\nsource: session\nhost: claude-code\n---\n无新内容。\n')
        self.write_draft('log.md', (self.root / 'log.md').read_text() + '\n## [2026-01-02] compile | 没有新内容\n\n已检查。\n')
        result = self.apply(self.fingerprint())
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(self.git('log', '-1', '--format=%s').strip(), 'compile: ' + Path(self.entry).name)

    def test_log_compile_operation_commits_and_passes_check(self):
        count = int(self.git('rev-list', '--count', 'HEAD'))
        result = self.apply(self.fingerprint())
        self.assertEqual(result.returncode, 0, result)
        data = json.loads(result.stdout)
        self.assertEqual(set(data), {'ok', 'commit', 'created', 'modified', 'findings'})
        self.assertEqual(data['commit'], self.git('rev-parse', 'HEAD').strip())
        self.assertEqual(int(self.git('rev-list', '--count', 'HEAD')), count + 1)
        self.assertEqual(self.git('log', '-1', '--format=%s').strip(), 'compile: 编译示例')
        self.assertIn('] compile |', (self.root / 'log.md').read_text())
        self.assertEqual(self.run_cli('check', '--json').returncode, 0)
        self.assertEqual(self.git('status', '--porcelain'), '')

    def test_fingerprint_changes_for_draft_head_or_worktree(self):
        for change in ('draft', 'head', 'worktree'):
            with self.subTest(change=change):
                fingerprint = self.fingerprint()
                if change == 'draft':
                    self.write_draft(self.entry, (self.draft / self.entry).read_text() + '\n补充事实。\n')
                elif change == 'head':
                    self.git('commit', '--allow-empty', '-qm', '新增基线提交')
                else:
                    self.replace('index.md', '# 知识库总目录', '# 修改目录')
                before = self.snapshot()
                result = self.apply(fingerprint)
                self.assertEqual(result.returncode, 3, result)
                self.assertEqual(self.snapshot(), before)

    def test_dirty_worktree_rejected_before_preview(self):
        (self.root / 'untracked.txt').write_text('其他工作。', encoding='utf-8')
        self.assert_rejected('worktree')

    def test_redaction_aliases_and_full_overlay_validation(self):
        secret = 'ghp_' + 'a2B' * 12
        original = (self.draft / self.entry).read_text()
        self.write_draft(self.entry, original + secret + '\n')
        data = self.assert_rejected('redaction')
        self.assertNotIn(secret, str(data))
        self.write_draft(self.entry, original + '项目真名\n')
        (self.config.parent / 'blocklist.txt').write_text('项目真名\n', encoding='utf-8')
        (self.config.parent / 'aliases.json').write_text('{"项目真名": "proj-test"}', encoding='utf-8')
        preview = json.loads(self.preview().stdout)
        self.assertTrue(preview['ok'], preview)
        self.assertEqual(preview['replaced_aliases'], 1)
        self.assertIn('proj-test', preview['diff'])
        (self.draft / 'index.md').unlink()
        self.assert_rejected('index')
        self.make_draft()
        self.replace('raw/example.md', '当前方法', '改写方法')
        self.git('add', 'raw/example.md')
        self.git('commit', '-qm', '错误改写原文')
        self.assert_rejected('immutable')

    def test_draft_path_symlinks_traversal_and_invalid_utf8_are_rejected(self):
        self.write_draft('wiki/escape.md', '临时内容')
        target = self.draft / 'wiki/escape.md'
        target.unlink()
        target.symlink_to(self.root / 'index.md')
        self.assert_rejected()
        target.unlink()
        target.write_bytes(b'\xff')
        self.assert_rejected()
        target.unlink()
        self.assert_rejected(draft=str(self.draft / '..' / self.draft.name))

    def test_atomic_write_failure_rolls_back_and_leaves_no_pending_record(self):
        fingerprint = self.fingerprint()
        before = self.snapshot()
        real_replace = os.replace
        calls = []

        def fail_once(source, target):
            calls.append(target)
            if len(calls) == 3:
                raise OSError('simulated failure')
            return real_replace(source, target)

        with patch('kblib.writer.os.replace', side_effect=fail_once):
            code, data = self.invoke('compile', 'apply', str(self.draft), '--confirm', fingerprint)
        self.assertEqual(code, 1, data)
        self.assertIn('回滚', str(data))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertEqual(list(self.root.rglob('.kb-save-*')), [])

    def test_commit_failure_records_compile_and_commit_pending_recovers(self):
        for stage in ('add', 'commit'):
            with self.subTest(stage=stage):
                fingerprint = self.fingerprint()
                real_git = writer.git

                def fail_git(root, *args):
                    if stage in args:
                        return subprocess.CompletedProcess(args, 1, b'', b'simulated failure')
                    return real_git(root, *args)

                with patch('kblib.writer.git', side_effect=fail_git):
                    code, data = self.invoke('compile', 'apply', str(self.draft), '--confirm', fingerprint)
                self.assertEqual(code, 1, data)
                pending = self.root / '.kb-pending.json'
                record = json.loads(pending.read_text())
                self.assertEqual(record['operation'], 'compile')
                self.assertEqual(record['message'], 'compile: 编译示例')
                self.assertEqual(record['fingerprint'], fingerprint)
                for path, digest in record['files'].items():
                    self.assertEqual(hashlib.sha256((self.root / path).read_bytes()).hexdigest(), digest)
                self.assert_rejected('pending')
                self.assertEqual(self.run_cli('save', 'preview', str(self.draft), '--json').returncode, 1)
                self.assertEqual(self.run_cli('lint', 'fix', 'preview', '--json').returncode, 1)
                recovered = self.run_cli('commit-pending', '--json')
                self.assertEqual(recovered.returncode, 0, recovered)
                self.assertFalse(pending.exists())
                self.assertEqual(self.git('log', '-1', '--format=%s').strip(), 'compile: 编译示例')
                self.assertEqual(self.run_cli('check', '--json').returncode, 0)
                if stage == 'add':
                    (self.draft / self.entry).unlink()
                    self.entry = 'inbox/2026-01-02-second.md'
                    self.page = 'wiki/pitfalls/second-example.md'
                    self.make_draft()

    def test_plain_apply_reports_compile_success(self):
        result = self.run_cli('compile', 'apply', str(self.draft), '--confirm', self.fingerprint())
        self.assertEqual(result.returncode, 0, result)
        self.assertIn('编译成功，已本地提交', result.stdout)

    def test_usage_and_configuration_errors_are_two(self):
        self.assertEqual(self.run_cli('compile', 'apply', str(self.draft)).returncode, 2)
        self.assertEqual(self.run_cli('compile', 'preview').returncode, 2)
        self.config.write_text('{}', encoding='utf-8')
        result = self.preview()
        self.assertEqual(result.returncode, 2, result)
        self.assertFalse(json.loads(result.stdout)['ok'])
        self.assertEqual(self.preview(json_output=False).returncode, 2)

    def test_end_to_end_backlog_and_session_two_drafts_two_compile_commits(self):
        source = 'inbox/2026-01-02-backlog.md'
        (self.root / source).write_text((self.root / 'inbox/2026-01-01-example.md').read_text().replace(
            '2026-01-01', '2026-01-02'), encoding='utf-8')
        self.git('add', source)
        self.git('commit', '-qm', '加入积压摘录')
        transcript = self.base / 'session.jsonl'
        transcript.write_text((ROOT / 'tests/fixtures/transcripts/basic.jsonl').read_text(), encoding='utf-8')
        added = self.run_cli('candidates', 'add', '--session-id', 'end-to-end', '--transcript', str(transcript),
                             '--cwd', str(self.base), '--reason', '编译候选')
        self.assertEqual(added.returncode, 0, added)
        identifier = hashlib.sha256(b'end-to-end').hexdigest()[:12]
        listing = self.run_cli('candidates', 'list', '--json')
        self.assertEqual(listing.returncode, 0, listing)
        self.assertEqual(len(json.loads(listing.stdout)['items']), 2)
        self.assertEqual(self.run_cli('candidates', 'show', identifier).returncode, 0)
        (self.draft / self.entry).unlink()
        self.make_draft(source)
        first = self.draft
        second = self.base / '候选会话草稿'
        second.mkdir()
        self.draft = second
        self.page = 'wiki/pitfalls/session-example.md'
        self.make_draft()
        # Both drafts are reviewable before any write; each later apply needs a fresh fingerprint after HEAD changes.
        self.fingerprint(first)
        self.fingerprint(second)
        count = int(self.git('rev-list', '--count', 'HEAD'))
        first_result = self.apply(self.fingerprint(first), first)
        self.assertEqual(first_result.returncode, 0, first_result)
        # Carry forward the first transaction's navigation and log into the second draft.
        self.make_draft()
        second_result = self.apply(self.fingerprint(second), second)
        self.assertEqual(second_result.returncode, 0, second_result)
        self.assertEqual(int(self.git('rev-list', '--count', 'HEAD')), count + 2)
        self.assertEqual(self.git('log', '-2', '--format=%s').splitlines(), ['compile: 编译示例'] * 2)
        marked = self.run_cli('candidates', 'mark', identifier, '--status', 'compiled')
        self.assertEqual(marked.returncode, 0, marked)
        records = [json.loads(line) for line in (self.base / 'state/candidates.jsonl').read_text().splitlines()]
        self.assertEqual(records[0]['status'], 'compiled')
        checked = self.run_cli('check', '--json')
        self.assertEqual(checked.returncode, 0, checked)
        self.assertEqual(json.loads(checked.stdout)['findings'], [])
        linted = self.run_cli('lint', '--json')
        self.assertEqual(linted.returncode, 0, linted)
        self.assertNotIn(source, {f['path'] for f in json.loads(linted.stdout)['hints'] if f['code'] == 'backlog'})
        self.assertEqual(json.loads(self.run_cli('candidates', 'list', '--json').stdout)['items'], [])
