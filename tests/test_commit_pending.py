import contextlib
from datetime import datetime
import hashlib
import io
import json
import os
import subprocess
import unittest
from unittest.mock import patch

from vault_support import CLI, VaultTestCase
import kb
from kblib import writer


class CommitPendingTests(VaultTestCase):
    def setUp(self):
        super().setUp()
        self.git('config', 'user.name', 'Pending Tests')
        self.git('config', 'user.email', 'pending@example.invalid')
        self.git('config', 'core.hooksPath', '/dev/null')
        self.git('config', 'commit.gpgsign', 'false')
        self.pending = self.root / '.kb-pending.json'
        self.entry = 'inbox/2026-01-02-pending.md'
        self.draft = self.base / '待提交草稿'
        (self.draft / 'inbox').mkdir(parents=True)
        (self.draft / self.entry).write_text(
            '---\ncaptured: 2026-01-02\nsource: session\nhost: codex\n'
            'title: 待提交经验\n---\n已经验证的经验。\n', encoding='utf-8')
        (self.draft / 'log.md').write_text(
            (self.root / 'log.md').read_text(encoding='utf-8')
            + '\n## [2026-01-02] save | 待提交经验\n\n'
            + self.entry + ' 已处理。\n', encoding='utf-8')

    def invoke(self, *args):
        output = io.StringIO()
        with patch.dict(os.environ, self.env), contextlib.redirect_stdout(output):
            code = kb.main([*args, '--json'])
        return code, json.loads(output.getvalue())

    def fail_save(self, stage='commit'):
        preview = self.run_cli('save', 'preview', str(self.draft), '--json')
        self.assertEqual(preview.returncode, 0, preview)
        token = json.loads(preview.stdout)['fingerprint']
        real_git = writer.git
        secret = 'ghp_' + 'a2B' * 12

        def failing_git(root, *args):
            if stage in args:
                return subprocess.CompletedProcess(args, 1, b'', secret.encode('utf-8'))
            return real_git(root, *args)

        with patch('kblib.writer.git', side_effect=failing_git):
            code, data = self.invoke('save', 'apply', str(self.draft), '--confirm', token)
        self.assertEqual(code, 1, data)
        self.assertIn('commit-pending', str(data))
        self.assertNotIn(secret, str(data))
        return token, data

    def read_record(self):
        return json.loads(self.pending.read_text(encoding='utf-8'))

    def assert_refused(self, expected=1):
        head = self.git('rev-parse', 'HEAD')
        record = self.pending.read_bytes()
        status = self.git('status', '--porcelain=v1', '-z')
        result = self.run_cli('commit-pending', '--json')
        self.assertEqual(result.returncode, expected, result)
        data = json.loads(result.stdout)
        self.assertEqual(set(data), {'ok', 'commit', 'files', 'findings', 'error'})
        self.assertFalse(data['ok'])
        self.assertIsNone(data['commit'])
        self.assertTrue(data['error'])
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertEqual(self.pending.read_bytes(), record)
        self.assertEqual(self.git('status', '--porcelain=v1', '-z'), status)
        self.assertNotIn('Traceback', result.stdout + result.stderr)
        return data

    def test_ac8_add_and_commit_failures_record_written_hashes(self):
        for stage in ('add', 'commit'):
            with self.subTest(stage=stage):
                token, data = self.fail_save(stage)
                record = self.read_record()
                self.assertEqual(set(record), {'schema', 'operation', 'message', 'files',
                                               'fingerprint', 'created'})
                self.assertEqual(record['schema'], 1)
                self.assertEqual(record['operation'], 'save')
                self.assertEqual(record['message'], 'save: 待提交经验')
                self.assertEqual(record['fingerprint'], token)
                self.assertIsNotNone(datetime.fromisoformat(record['created']).tzinfo)
                self.assertEqual(set(record['files']), {self.entry, 'log.md'})
                for path, digest in record['files'].items():
                    self.assertEqual((self.root / path).read_bytes(), (self.draft / path).read_bytes())
                    self.assertEqual(digest, hashlib.sha256((self.root / path).read_bytes()).hexdigest())
                self.assertIn('python3 -B ' + str(CLI) + ' commit-pending', str(data))
                self.assertEqual(self.run_cli('commit-pending').returncode, 0)
                if stage == 'add':
                    self.entry = 'inbox/2026-01-02-second.md'
                    (self.draft / 'inbox/2026-01-02-pending.md').rename(self.draft / self.entry)
                    log = self.draft / 'log.md'
                    log.write_text(log.read_text() + '\n补充经验。\n', encoding='utf-8')

    def test_ac9_success_commits_only_recorded_files_and_removes_record(self):
        self.fail_save()
        record = self.read_record()
        head = self.git('rev-parse', 'HEAD').strip()
        result = self.run_cli('commit-pending', '--json')
        self.assertEqual(result.returncode, 0, result)
        data = json.loads(result.stdout)
        self.assertEqual(set(data), {'ok', 'commit', 'files', 'findings', 'error'})
        self.assertTrue(data['ok'])
        self.assertIsNone(data['error'])
        self.assertEqual(data['findings'], [])
        self.assertEqual(data['files'], sorted(record['files']))
        self.assertEqual(data['commit'], self.git('rev-parse', 'HEAD').strip())
        self.assertEqual(self.git('rev-parse', 'HEAD^').strip(), head)
        self.assertEqual(self.git('log', '-1', '--format=%s').strip(), record['message'])
        self.assertEqual(set(self.git('diff-tree', '--no-commit-id', '--name-only', '-r',
                                      'HEAD').splitlines()), set(record['files']))
        self.assertFalse(self.pending.exists())
        self.assertEqual(self.git('status', '--porcelain'), '')
        checked = self.run_cli('check', '--json')
        self.assertEqual(checked.returncode, 0, checked)
        self.assertEqual(json.loads(checked.stdout)['findings'], [])

    def test_ac9_changed_or_missing_file_is_refused(self):
        self.fail_save()
        path = self.root / self.entry
        original = path.read_bytes()
        path.write_bytes(original + b'!')
        self.assert_refused()
        path.unlink()
        self.assert_refused()

    def test_ac9_unrecorded_staged_unstaged_and_untracked_changes_are_refused(self):
        self.fail_save()
        path = self.root / 'wiki/tech/example.md'
        original = path.read_bytes()
        path.write_bytes(original + '\n额外改动。\n'.encode('utf-8'))
        self.assert_refused()
        self.git('add', 'wiki/tech/example.md')
        self.assert_refused()
        path.write_bytes(original)
        self.git('add', 'wiki/tech/example.md')
        extra = self.root / 'new directory/额外文件.txt'
        extra.parent.mkdir()
        extra.write_text('未跟踪改动。', encoding='utf-8')
        self.assert_refused()

    def test_ac9_full_check_failure_is_refused(self):
        self.fail_save()
        self.config.with_name('blocklist.txt').write_text('已经验证的经验\n', encoding='utf-8')
        data = self.assert_refused()
        self.assertIn('redaction', {f['code'] for f in data['findings']})

    def test_missing_record_is_two_in_text_and_json(self):
        for flags in ((), ('--json',)):
            result = self.run_cli('commit-pending', *flags)
            self.assertEqual(result.returncode, 2, result)
            self.assertIn('没有待提交记录', result.stdout + result.stderr)
            self.assertFalse(self.pending.exists())

    def test_corrupt_json_and_invalid_record_shapes_are_two(self):
        self.fail_save()
        record = self.read_record()
        invalid = ['{broken', '[]', 'null', json.dumps({**record, 'schema': 2}),
                   json.dumps({**record, 'schema': True}),
                   json.dumps({**record, 'files': []}),
                   json.dumps({**record, 'files': {}}),
                   json.dumps({**record, 'message': 1}),
                   json.dumps({**record, 'files': {'../outside': 'a' * 64}}),
                   json.dumps({**record, 'files': {'.kb-pending.json': 'a' * 64}}),
                   json.dumps({**record, 'files': {'.git/config': 'a' * 64}})]
        for value in invalid:
            with self.subTest(value=value):
                self.pending.write_text(value, encoding='utf-8')
                self.assert_refused(2)

    def test_ac10_pending_blocks_save_and_lint_fix_preview_and_apply(self):
        token, _ = self.fail_save()
        for args in (('save', 'preview', str(self.draft)),
                     ('save', 'apply', str(self.draft), '--confirm', token),
                     ('lint', 'fix', 'preview'),
                     ('lint', 'fix', 'apply', '--confirm', token)):
            with self.subTest(args=args):
                before = self.pending.read_bytes()
                result = self.run_cli(*args, '--json')
                self.assertEqual(result.returncode, 1, result)
                data = json.loads(result.stdout)
                self.assertEqual(data['findings'][0]['code'], 'pending')
                self.assertIn('commit-pending', data['findings'][0]['message'])
                self.assertEqual(self.pending.read_bytes(), before)

    def test_lint_commit_failure_records_lint_operation_and_can_resume(self):
        self.replace('index.md', '- [合法示例](wiki/tech/example.md) — 当前方法示例 · 2026-01-01\n', '')
        self.git('add', 'index.md')
        self.git('commit', '-qm', '构造缺失目录条目')
        preview = self.run_cli('lint', 'fix', 'preview', '--json')
        self.assertEqual(preview.returncode, 0, preview)
        token = json.loads(preview.stdout)['fingerprint']
        with patch('kblib.writer.commit', side_effect=writer.WriteError('模拟提交失败')):
            code, data = self.invoke('lint', 'fix', 'apply', '--confirm', token)
        self.assertEqual(code, 1, data)
        self.assertIn('commit-pending', str(data))
        record = self.read_record()
        self.assertEqual(record['operation'], 'lint')
        self.assertEqual(record['message'], 'lint: 安全修复 1 处')
        self.assertEqual(record['fingerprint'], token)
        self.assertEqual(set(record['files']), {'index.md', 'log.md'})
        for path, digest in record['files'].items():
            self.assertEqual(digest, hashlib.sha256((self.root / path).read_bytes()).hexdigest())
        result = self.run_cli('commit-pending')
        self.assertEqual(result.returncode, 0, result)
        self.assertIn(self.git('rev-parse', 'HEAD').strip(), result.stdout)
        self.assertFalse(self.pending.exists())

    def test_check_and_lint_ignore_even_unreadable_pending_content(self):
        before = json.loads(self.run_cli('lint', '--json').stdout)
        self.pending.write_bytes(b'\xff\x00[[invalid]]')
        self.assertNotIn('.kb-pending.json', self.vault().files)
        for paths in ((), ('.kb-pending.json',)):
            result = self.run_cli('check', '--json', *paths)
            self.assertEqual(result.returncode, 0, result)
            self.assertEqual(json.loads(result.stdout)['findings'], [])
        result = self.run_cli('lint', '--json')
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(json.loads(result.stdout), before)

    def test_retry_commit_failure_keeps_record_and_masks_reason(self):
        self.fail_save()
        secret = 'ghp_' + 'b3C' * 12
        hooks = self.base / 'hooks'
        hooks.mkdir()
        hook = hooks / 'pre-commit'
        hook.write_text('#!/bin/sh\necho "' + secret + '" >&2\nexit 1\n', encoding='utf-8')
        hook.chmod(0o755)
        self.git('config', 'core.hooksPath', str(hooks))
        data = self.assert_refused()
        self.assertNotIn(secret, str(data))
        self.assertIn('提交失败', data['error'])

    def test_pending_record_write_failure_preserves_original_error(self):
        preview = self.run_cli('save', 'preview', str(self.draft), '--json')
        token = json.loads(preview.stdout)['fingerprint']
        real_write = writer.atomic_write

        def fail_pending(root, content):
            if '.kb-pending.json' in content:
                raise writer.WriteError('模拟记录写入失败')
            return real_write(root, content)

        with patch('kblib.writer.atomic_write', side_effect=fail_pending), patch(
                'kblib.writer.commit', side_effect=writer.WriteError('原始提交失败原因')):
            code, data = self.invoke('save', 'apply', str(self.draft), '--confirm', token)
        self.assertEqual(code, 1, data)
        self.assertIn('原始提交失败原因', str(data))
        self.assertNotIn('已记录待提交', str(data))
        self.assertFalse(self.pending.exists())
        self.assertTrue((self.root / self.entry).exists())


if __name__ == '__main__':
    unittest.main()
