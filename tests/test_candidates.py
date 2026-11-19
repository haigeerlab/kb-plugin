import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from vault_support import ROOT, VaultTestCase


class CandidatesTests(VaultTestCase):
    def setUp(self):
        super().setUp()
        self.git('config', 'user.name', 'Candidates Tests')
        self.git('config', 'user.email', 'candidates@example.invalid')
        self.state = self.base / 'state'
        self.env['KB_STATE_DIR'] = str(self.state)
        self.queue = self.state / 'candidates.jsonl'
        self.transcript = self.base / 'session.jsonl'
        self.secret = 'ghp_' + 'a2B' * 12
        text = (ROOT / 'tests/fixtures/transcripts/basic.jsonl').read_text(encoding='utf-8')
        self.transcript.write_text(text.replace('__SECRET_PLACEHOLDER__', self.secret), encoding='utf-8')

    def add(self, session='session-one', transcript=None, reason='待整理的经验'):
        result = self.run_cli('candidates', 'add', '--session-id', session,
                              '--transcript', str(transcript or self.transcript),
                              '--cwd', str(self.base), '--reason', reason)
        self.assertEqual(result.returncode, 0, result)
        return hashlib.sha256(session.encode('utf-8')).hexdigest()[:12]

    def records(self):
        return [json.loads(line) for line in self.queue.read_text(encoding='utf-8').splitlines()]

    def listing(self):
        result = self.run_cli('candidates', 'list', '--json')
        self.assertEqual(result.returncode, 0, result)
        return json.loads(result.stdout)

    def test_add_stable_id_local_timestamp_and_deduplication(self):
        identifier = self.add()
        first = self.records()[0]
        self.assertEqual(set(first), {'id', 'session_id', 'transcript_path', 'cwd', 'reason', 'ended_at', 'status'})
        self.assertEqual(first['id'], identifier)
        self.assertIsNotNone(datetime.fromisoformat(first['ended_at']).tzinfo)
        second = self.base / 'second.jsonl'
        second.write_text('', encoding='utf-8')
        self.add(transcript=second, reason='更新原因')
        records = self.records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['transcript_path'], str(second))
        self.assertEqual(records[0]['reason'], '更新原因')
        self.assertEqual(records[0]['cwd'], str(self.base))
        self.assertEqual(records[0]['status'], 'pending')

    def test_add_reactivates_expired_and_preserves_terminal_states(self):
        identifier = self.add()
        for status in ('pending', 'expired', 'compiled', 'dropped'):
            with self.subTest(status=status):
                record = self.records()[0]
                record['status'] = status
                self.queue.write_text(json.dumps(record) + '\n', encoding='utf-8')
                self.add(reason='重新入队')
                expected = 'pending' if status in ('pending', 'expired') else status
                self.assertEqual(self.records()[0]['status'], expected)
                self.assertEqual(self.records()[0]['id'], identifier)

    def test_mark_only_accepts_compiled_or_dropped_and_missing_is_business_error(self):
        identifier = self.add()
        for status in ('compiled', 'dropped'):
            result = self.run_cli('candidates', 'mark', identifier, '--status', status)
            self.assertEqual(result.returncode, 0, result)
            self.assertEqual(self.records()[0]['status'], status)
            self.assertEqual(self.listing()['items'], [])
        self.assertEqual(self.run_cli('candidates', 'mark', identifier, '--status', 'pending').returncode, 2)
        self.assertEqual(self.run_cli('candidates', 'mark', 'missing', '--status', 'compiled').returncode, 1)
        self.assertEqual(self.run_cli('candidates', 'show', 'missing').returncode, 1)

    def test_corrupt_queue_lines_are_reported_and_other_lines_preserved_on_write(self):
        identifier = self.add()
        original = self.queue.read_bytes()
        broken = b'{broken JSON\n'
        self.queue.write_bytes(broken + original + b'[]\n')
        result = self.listing()
        self.assertEqual(result['corrupt_lines'], [1, 3])
        self.assertEqual(len(result['items']), 1)
        result = self.run_cli('candidates', 'mark', identifier, '--status', 'compiled')
        self.assertEqual(result.returncode, 0, result)
        self.assertIn('1', result.stdout)
        self.assertIn('3', result.stdout)
        self.assertTrue(self.queue.read_bytes().startswith(broken))
        self.assertTrue(self.queue.read_bytes().endswith(b'[]\n'))
        self.add('another')
        self.assertEqual(self.listing()['corrupt_lines'], [1, 3])

    def test_atomic_queue_failure_preserves_original_and_cleans_temporary_file(self):
        from kblib import candidates, KbError
        self.add()
        before = self.queue.read_bytes()
        with patch.dict(os.environ, self.env), patch('kblib.candidates.os.replace', side_effect=OSError):
            with self.assertRaises(KbError):
                candidates.add('another', str(self.transcript), str(self.base), '经验')
        self.assertEqual(self.queue.read_bytes(), before)
        self.assertEqual([p.name for p in self.state.iterdir()], ['candidates.jsonl'])

    def test_list_reuses_lint_backlog_including_save_log_exclusion(self):
        paths = ['inbox/2026-01-02-' + name + '.md' for name in ('backlog', 'saved', 'longer', 'other')]
        text = (self.root / 'inbox/2026-01-01-example.md').read_text(encoding='utf-8')
        for path in paths:
            (self.root / path).write_text(text.replace('2026-01-01', '2026-01-02'), encoding='utf-8')
        log = self.root / 'log.md'
        log.write_text(log.read_text(encoding='utf-8') + '\n## [2026-01-02] save | 没有新内容\n\n'
                       + paths[1] + '\n' + paths[2] + '.backup\n'
                       + '\n## [2026-01-02] lint | 其他记录\n\n' + paths[3] + '\n', encoding='utf-8')
        identifier = self.add()
        data = self.listing()
        expected = {f['path'] for f in json.loads(self.run_cli('lint', '--json').stdout)['hints']
                    if f['code'] == 'backlog'}
        self.assertEqual(expected, {paths[0], paths[2], paths[3]})
        self.assertEqual({i['path'] for i in data['items'] if i['kind'] == 'inbox'}, expected)
        self.assertEqual([i['id'] for i in data['items'] if i['kind'] == 'candidate'], [identifier])
        self.assertIn('inbox 积压', self.run_cli('candidates', 'list').stdout)

    def test_missing_transcript_expires_and_show_returns_one(self):
        identifier = self.add()
        self.transcript.unlink()
        data = self.listing()
        self.assertEqual(data['items'], [])
        self.assertEqual([i['id'] for i in data['expired']], [identifier])
        self.assertEqual(self.records()[0]['status'], 'expired')
        self.assertIn('已过期', self.run_cli('candidates', 'list').stdout)
        result = self.run_cli('candidates', 'show', identifier)
        self.assertEqual(result.returncode, 1, result)
        self.assertIn('过期', result.stderr)

    def test_show_detects_missing_transcript_without_prior_list(self):
        identifier = self.add()
        self.transcript.unlink()
        self.assertEqual(self.run_cli('candidates', 'show', identifier).returncode, 1)
        self.assertEqual(self.records()[0]['status'], 'expired')

    def test_expiring_strict_twenty_five_day_boundary(self):
        from kblib import candidates
        self.add()
        now = datetime(2026, 11, 19, 12, tzinfo=timezone.utc)
        for age, expected in ((timedelta(days=25), False),
                              (timedelta(days=25, microseconds=1), True)):
            record = self.records()[0]
            record['ended_at'] = (now - age).isoformat()
            self.queue.write_text(json.dumps(record) + '\n', encoding='utf-8')
            with patch.dict(os.environ, self.env), patch('kblib.candidates.datetime') as clock:
                clock.now.return_value = now
                clock.fromisoformat = datetime.fromisoformat
                data = candidates.list_candidates(self.vault())
            self.assertEqual(data['items'][0]['expiring'], expected)
        record['ended_at'] = (datetime.now().astimezone() - timedelta(days=26)).isoformat()
        self.queue.write_text(json.dumps(record) + '\n', encoding='utf-8')
        self.assertIn('即将过期', self.run_cli('candidates', 'list').stdout)

    def test_show_fixture_retains_only_conversation_and_counts_one_broken_line(self):
        identifier = self.add()
        result = self.run_cli('candidates', 'show', identifier)
        self.assertEqual(result.returncode, 0, result)
        for marker in ('ATTACH', 'META', 'META2', 'REMINDER', 'THINKING', 'TOOLUSE', 'TOOLRESULT', 'SIDECHAIN'):
            self.assertNotIn(marker + '-MARKER', result.stdout)
        self.assertNotIn(self.secret, result.stdout)
        for body in ('【用户】', '【助手】', '构建时报错 TypeError: x is undefined，怎么回事？',
                     '原因是 vite 5.2.0 的配置里 define 没有声明 x。', '好了，测试通过了。'):
            self.assertIn(body, result.stdout)
        self.assertTrue(result.stdout.rstrip().endswith('跳过 1 条无法识别的记录。'))

    def test_show_masks_assistant_and_user_secrets_and_local_blocklist_in_context(self):
        identifier = self.add()
        with self.transcript.open('a', encoding='utf-8') as stream:
            for role, content in (('user', '前文 ' + self.secret + ' 后文'),
                                  ('assistant', [{'type': 'text', 'text': '助手前文 ' + self.secret + ' 客户名称 后文'}])):
                stream.write(json.dumps({'type': role, 'message': {'content': content}}) + '\n')
        (self.config.parent / 'blocklist.txt').write_text('客户名称\n', encoding='utf-8')
        result = self.run_cli('candidates', 'show', identifier)
        self.assertEqual(result.returncode, 0, result)
        self.assertNotIn(self.secret, result.stdout)
        self.assertNotIn('客户名称', result.stdout)
        self.assertIn('前文 ghp_' + '*' * 36 + ' 后文', result.stdout)
        self.assertIn('助手前文', result.stdout)
        self.assertIn('**** 后文', result.stdout)

    def test_only_unrecognized_conversation_records_are_counted(self):
        # Metadata record types (titles, API logs, snapshots, future types) are skipped
        # silently; only malformed user/assistant records and corrupt lines are counted.
        identifier = self.add()
        with self.transcript.open('a', encoding='utf-8') as stream:
            for record in ([], {'type': 'new-format'}, {'type': 'custom-title', 'title': 'x'},
                           {'type': 'api-request', 'body': {}}, {'type': 'user', 'message': None},
                           {'type': 'assistant', 'message': {'content': 'unsupported'}}):
                stream.write(json.dumps(record) + '\n')
        self.assertIn('跳过 4 条无法识别的记录。', self.run_cli('candidates', 'show', identifier).stdout)

    def test_host_injected_user_blocks_are_removed_and_entities_unescaped(self):
        identifier = self.add()
        with self.transcript.open('a', encoding='utf-8') as stream:
            for content in ('<task-notification>\n<status>completed</status> NOTIFY-MARKER\n</task-notification>',
                            '<side-sessions-event>SIDE-EVENT-MARKER</side-sessions-event>',
                            '<bash-input>git push</bash-input><bash-stdout>a -&gt; b &amp;&amp; c</bash-stdout>',
                            [{'type': 'text', 'text': '粘贴的文本块 USER-BLOCK'}, {'type': 'image', 'source': {}}]):
                stream.write(json.dumps({'type': 'user', 'message': {'role': 'user', 'content': content}},
                                        ensure_ascii=False) + '\n')
        output = self.run_cli('candidates', 'show', identifier).stdout
        self.assertNotIn('NOTIFY-MARKER', output)
        self.assertNotIn('SIDE-EVENT-MARKER', output)
        self.assertIn('<bash-input>git push</bash-input>', output)
        self.assertIn('a -> b && c', output)
        self.assertIn('粘贴的文本块 USER-BLOCK', output)
        self.assertTrue(output.rstrip().endswith('跳过 1 条无法识别的记录。'))

    def test_truncation_keeps_redacted_tail_with_exact_count_and_annotation(self):
        identifier = self.add()
        full = self.run_cli('candidates', 'show', identifier).stdout
        body, footer = full.rsplit('\n\n', 1)
        result = self.run_cli('candidates', 'show', identifier, '--max-chars', '30')
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(result.stdout, '已截断前 ' + str(len(body) - 30) + ' 字\n' + body[-30:] + '\n\n' + footer)
        self.assertIn('好了，测试通过了。', result.stdout)
        for value in ('0', '-1', 'abc'):
            self.assertEqual(self.run_cli('candidates', 'show', identifier, '--max-chars', value).returncode, 2)

    def test_empty_queue_is_read_only_and_configuration_errors_are_two(self):
        self.assertEqual(self.listing()['items'], [])
        self.assertFalse(self.state.exists())
        self.config.write_text('{}', encoding='utf-8')
        self.assertEqual(self.run_cli('candidates', 'list', '--json').returncode, 2)
        self.assertEqual(self.run_cli('candidates', 'add').returncode, 2)
