import copy
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from vault_support import CLI, ROOT


TTL = 'wiki/pitfalls/fluxctl-cache-ttl.md'
POLICY = 'wiki/decisions/fluxctl-cache-policy.md'
RETRY = 'wiki/patterns/retry-backoff.md'
RETRY_POLICY = 'wiki/decisions/retry-policy.md'
PKGSYNC = 'wiki/tech/pkgsync.md'
RULE = 'wiki/pitfalls/never-force-push-shared.md'
FRIDAY = 'wiki/pitfalls/friday-release.md'
TODAY = date(2026, 11, 20)
REAL_QUOTE = '目前 fluxctl 0.9.3 是最新版本，以上行为在该版本上验证。'


class SemanticTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.root = self.base / '语义知识库 with spaces'
        shutil.copytree(ROOT / 'tests/fixtures/vaults/semantic', self.root)
        self.config = self.base / 'config.json'
        self.config.write_text(json.dumps({'version': 1, 'vault': str(self.root)}), encoding='utf-8')
        self.env = dict(os.environ, KB_CONFIG=str(self.config),
                        KB_STATE_DIR=str(self.base / 'state'),
                        KB_DELEGATE_DIR=str(self.base / 'delegate'))
        (self.base / 'delegate').mkdir()
        self.environ = patch.dict(os.environ, self.env)
        self.environ.start()
        self.addCleanup(self.environ.stop)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Semantic Tests')
        self.git('config', 'user.email', 'semantic@example.invalid')
        self.git('config', 'core.hooksPath', '/dev/null')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('add', '.')
        self.git('commit', '-qm', '构造语义体检样例')

    def git(self, *args):
        result = subprocess.run(['git', '-C', str(self.root), *args], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def vault(self):
        from kblib.vault import Vault
        return Vault.load(environ=self.env)

    def run_cli(self, *args, input=None):
        return subprocess.run([sys.executable, '-B', str(CLI), *args], env=self.env,
                              cwd=self.base, input=input, capture_output=True, text=True)

    def pack(self):
        from kblib.semantic import pack
        return pack(self.vault(), TODAY)

    def finding(self, **changes):
        return dict(category='stale', pages=[TTL], quotes=[{'page': TTL, 'text': REAL_QUOTE}],
                    reason='版本结论需要重新核实。', action='核实后更新日期。', **changes)

    def verify(self, *findings):
        from kblib.semantic import verify
        return verify(self.vault(), {'version': 1, 'findings': list(findings)})

    def write_page(self, path, body, tags='[shared]', updated='2026-01-01', title=None):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('---\ntype: tech\ntitle: ' + (title or target.stem)
                          + '\ntags: ' + tags + '\ncreated: 2025-01-01\nupdated: '
                          + updated + '\n---\n# 页面\n\n' + body, encoding='utf-8')

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.rglob('*') if p.is_file()}

    def test_fixture_passes_check_and_pack_contains_metadata_links_and_four_clues(self):
        self.assertEqual(self.run_cli('check', '--json').returncode, 0)
        data = self.pack()
        self.assertTrue(data['ok'])
        self.assertFalse(data['truncated'])
        self.assertEqual(len(data['pages']), 8)
        pages = {p['path']: p for p in data['pages']}
        self.assertEqual(pages[TTL]['type'], 'pitfall')
        self.assertEqual(pages[TTL]['created'], '2025-03-01')
        self.assertEqual(pages[TTL]['updated_days'], (TODAY - date(2025, 3, 1)).days)
        self.assertEqual(pages[TTL]['tags'], ['fluxctl', 'cache'])
        self.assertIn(RULE, pages[TTL]['related'])
        self.assertIn(RULE, pages[POLICY]['links'])
        clues = data['candidates']
        pairs = {frozenset(c['pages']) for c in clues['contradiction']}
        self.assertIn(frozenset((TTL, POLICY)), pairs)
        self.assertNotIn(frozenset((RETRY, RETRY_POLICY)), pairs)
        self.assertIn(frozenset((PKGSYNC, 'wiki/pitfalls/pkgsync-lockfile-comments.md')), pairs)
        self.assertTrue(any(c['page'] == TTL and '0.9.3' in c['sentence'] for c in clues['stale']))
        self.assertFalse(any('1.4.2' in c['sentence'] for c in clues['stale']))
        missing = {c['term'].casefold(): c for c in clues['missing-page']}
        self.assertEqual(set(missing['relayd']['pages']), {TTL, RETRY, RETRY_POLICY})
        self.assertNotIn('pkgsync', missing)
        promote = {c['page']: c for c in clues['promote']}
        self.assertEqual({s['kind'] for s in promote[RULE]['signals']},
                         {'incoming-links', 'log-updates', 'imperative'})
        self.assertEqual(next(s['count'] for s in promote[RULE]['signals']
                              if s['kind'] == 'log-updates'), 3)
        self.assertEqual([s['kind'] for s in promote[FRIDAY]['signals']], ['imperative'])

    def test_all_callout_kinds_are_removed_from_current_body_and_clues(self):
        path = self.root / TTL
        path.write_text(path.read_text() + '\n> [!note] 旧提示\n> 最新 v999 `hidden-term`\n'
                        '>\n> ```text\n> 被围栏包住的块内容\n> ```\n'
                        '\n现行尾句。\n', encoding='utf-8')
        data = self.pack()
        body = {p['path']: p['body'] for p in data['pages']}
        self.assertIn('现行尾句。', body[TTL])
        for old in ('旧提示', 'v999', 'hidden-term', '被围栏包住的块内容'):
            self.assertNotIn(old, body[TTL])
        self.assertNotIn('1.4.2', body[PKGSYNC])
        self.assertNotIn('本页实践用 5 次', body[RETRY])
        self.assertNotIn('v999', json.dumps(data['candidates'], ensure_ascii=False))

    def test_clues_use_full_current_body_before_page_excerpt_truncation(self):
        tail = '\n目前 tailtool v5 必须重新核实。使用 `TailTerm`。\n'
        for number in range(2):
            self.write_page(f'wiki/tech/tail-{number}.md', '普通现行结论。' * 800 + tail,
                            tags='[]')
        data = self.pack()
        self.assertTrue(any(c['sentence'].startswith('目前 tailtool v5')
                            for c in data['candidates']['stale']))
        self.assertIn('tailterm', {c['term'] for c in data['candidates']['missing-page']})
        self.assertTrue(all('tailtool' not in p['body'] for p in data['pages']
                            if '/tail-' in p['path']))

    def test_stale_version_date_and_time_word_variants(self):
        sentences = ['工具 v5 有此行为。', '适用于工具 1.x。', '版本 0.166.0 已验证。',
                     '核实于 2025-03。', '核实于 2025-03-01。', '核实于 2025年3月。',
                     'Currently supported.', 'The latest behavior.', 'Use this now.',
                     'Use tool v5.']
        path = 'wiki/tech/time-signals.md'
        self.write_page(path, '\n'.join(sentences), tags='[]', updated='2025-01-01')
        clues = [c for c in self.pack()['candidates']['stale'] if c['page'] == path]
        self.assertEqual({c['sentence'] for c in clues}, set(sentences))
        self.assertTrue(all(c['updated_days'] == (TODAY - date(2025, 1, 1)).days for c in clues))

    def test_related_reference_links_resolve_definitions_outside_the_section(self):
        target = self.root / TTL
        target.write_text(target.read_text().replace('## 原因\n',
                          '## 原因\n\n[policy]: ../decisions/fluxctl-cache-policy.md\n')
                          + '\n[缓存政策][policy]\n', encoding='utf-8')
        page = next(p for p in self.pack()['pages'] if p['path'] == TTL)
        self.assertIn(POLICY, page['links'])
        self.assertIn(POLICY, page['related'])

    def test_pack_is_read_only_with_clean_and_dirty_worktrees(self):
        for dirty in (False, True):
            with self.subTest(dirty=dirty):
                if dirty:
                    (self.root / TTL).write_text((self.root / TTL).read_text() + '\n新句。\n')
                    self.git('add', TTL)
                    (self.root / 'untracked.txt').write_text('未跟踪')
                status = self.git('status', '--porcelain=v1', '-z')
                before = self.snapshot()
                head = self.git('rev-parse', 'HEAD')
                for flags in ((), ('--json',)):
                    result = self.run_cli('lint', 'semantic-pack', '--today', TODAY.isoformat(), *flags)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout), self.pack())
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.git('status', '--porcelain=v1', '-z'), status)
                self.assertEqual(self.git('rev-parse', 'HEAD'), head)

    def test_contradiction_pairs_are_capped_and_ranked_by_shared_tags_and_terms(self):
        for number in range(14):
            self.write_page(f'wiki/tech/pair-{number}.md', '`shared-term`', tags='[shared]')
        self.write_page('wiki/tech/top-a.md', '`shared-term` `extra-term`', tags='[shared, extra]')
        self.write_page('wiki/tech/top-b.md', '`shared-term` `extra-term`', tags='[shared, extra]')
        clues = self.pack()['candidates']['contradiction']
        self.assertEqual(len(clues), 30)
        self.assertEqual(set(clues[0]['pages']), {'wiki/tech/top-a.md', 'wiki/tech/top-b.md'})
        scores = [len(c['shared_tags']) + len(c['shared_terms']) for c in clues]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_pack_size_and_body_truncation_prioritize_older_pages(self):
        self.write_page('wiki/tech/oldest.md', '最旧正文。' * 3000, updated='2020-01-01')
        for number in range(50):
            self.write_page(f'wiki/tech/large-{number:02}.md', '较新正文。' * 3000,
                            tags='[]', updated='2026-11-01')
        data = self.pack()
        self.assertTrue(data['truncated'])
        self.assertTrue(data['truncated_pages'])
        self.assertLessEqual(len(json.dumps(data, ensure_ascii=False).encode('utf-8')), 60000)
        self.assertEqual(data['pages'][0]['path'], 'wiki/tech/oldest.md')
        self.assertIn('最旧正文。' * 100, data['pages'][0]['body'])
        self.assertTrue(any(len(p['body']) < 4000 for p in data['pages'][1:]))
        result = self.run_cli('lint', 'semantic-pack', '--today', TODAY.isoformat())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLessEqual(len(result.stdout.encode('utf-8')), 60000)

    def test_oversized_metadata_omits_newer_page_and_names_it_as_truncated(self):
        path = 'wiki/tech/oversized-metadata.md'
        self.write_page(path, '现行正文。', tags='[]', title='很长的标题' * 15000,
                        updated='2026-11-19')
        data = self.pack()
        self.assertTrue(data['truncated'])
        self.assertIn(path, data['truncated_pages'])
        self.assertEqual(data['omitted_page_count'], 1)
        self.assertEqual(len(data['pages']), 8)
        self.assertLessEqual(len(json.dumps(data, ensure_ascii=False).encode('utf-8')), 60000)

    def test_promote_backlink_signal_survives_omitting_newer_source_pages(self):
        rule = 'wiki/pitfalls/linked-rule.md'
        self.write_page(rule, '已验证的惯例。', tags='[]', updated='2020-01-01')
        target = self.root / rule
        target.write_text(target.read_text().replace('type: tech', 'type: pitfall'), encoding='utf-8')
        sources = []
        for number in range(2):
            path = f'wiki/tech/new-source-{number}.md'
            sources.append(path)
            self.write_page(path, '[惯例](../pitfalls/linked-rule.md)', tags='[]',
                            updated='2026-11-19', title=str(number) + '很长的标题' * 15000)
        data = self.pack()
        signal = next(c for c in data['candidates']['promote'] if c['page'] == rule)
        self.assertEqual(signal['signals'], [{'kind': 'incoming-links', 'pages': sources}])

    def test_missing_terms_are_case_insensitive_count_pages_and_exclude_commands(self):
        for number in range(3):
            self.write_page(f'wiki/tech/terms-{number}.md',
                            '`NoPage` `NoPage` `git push --force` `PKGSYNC` `Exists` `By Title`',
                            tags='[TagOnly, pkgsync, Exact Title]')
        self.write_page('wiki/tech/exists.md', '存在。', tags='[]', title='Exact Title')
        terms = {c['term'].casefold(): c for c in self.pack()['candidates']['missing-page']}
        self.assertEqual(len(terms['nopage']['pages']), 3)
        self.assertEqual(len(terms['tagonly']['pages']), 3)
        for excluded in ('pkgsync', 'exists', 'exact title', 'git push --force', 'by title'):
            self.assertNotIn(excluded, terms)

    def test_verify_accepts_literal_and_normalized_whitespace_quotes(self):
        finding = self.finding()
        finding['quotes'].append({'page': TTL, 'text': '目前 fluxctl 0.9.3 是最新版本，以上行为在该版本上验证。\n'})
        result = self.verify(finding)
        self.assertTrue(result['ok'])
        self.assertEqual(result['accepted'], [finding])
        self.assertEqual(result['rejected'], [])

    def test_verify_does_not_use_truncated_pack_or_frontmatter_as_quote_source(self):
        path = self.root / TTL
        path.write_text(path.read_text() + '\n' + '填充。' * 3000 + '\n正文末尾的有效证据。\n',
                        encoding='utf-8')
        good = self.finding()
        good['quotes'] = [{'page': TTL, 'text': '正文末尾的有效证据。'}]
        bad = self.finding()
        bad['quotes'] = [{'page': TTL, 'text': 'updated: 2025-03-01'}]
        result = self.verify(good, bad)
        self.assertEqual(result['accepted'], [good])
        self.assertEqual(len(result['rejected']), 1)

    def test_verify_read_only_and_disputed_note_quotes_are_rejected(self):
        findings = []
        for page, quote in ((RETRY, '重试次数：本页实践用 5 次；'),
                            (TTL, '专有提示文字。')):
            item = self.finding()
            item.update(pages=[page], quotes=[{'page': page, 'text': quote}])
            findings.append(item)
        target = self.root / TTL
        target.write_text(target.read_text() + '\n> [!tip]\n> 专有提示文字。\n', encoding='utf-8')
        before, status = self.snapshot(), self.git('status', '--porcelain=v1', '-z')
        result = self.verify(*findings)
        self.assertEqual(len(result['rejected']), 2)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.git('status', '--porcelain=v1', '-z'), status)

    def test_verify_rejects_changed_callout_missing_and_unsafe_page_quotes(self):
        good = self.finding()
        bad = []
        changed = copy.deepcopy(good)
        changed['quotes'][0]['text'] = REAL_QUOTE.replace('目前', '以前')
        bad.append(changed)
        outdated = copy.deepcopy(good)
        outdated.update(pages=[PKGSYNC], quotes=[{'page': PKGSYNC, 'text': '目前 pkgsync 1.4.2 是最新版本，写锁文件会丢注释。'}])
        bad.append(outdated)
        for path in ('../outside.md', '/wiki/tech/pkgsync.md', 'raw/anything.md',
                     'wiki/tech/../tech/pkgsync.md', 'wiki/tech/missing.md',
                     'wiki\\tech\\pkgsync.md'):
            item = copy.deepcopy(good)
            item.update(pages=[path], quotes=[{'page': path, 'text': REAL_QUOTE}])
            bad.append(item)
        result = self.verify(good, *bad)
        self.assertEqual(result['accepted'], [good])
        self.assertEqual(len(result['rejected']), len(bad))
        self.assertFalse(result['ok'])
        self.assertTrue(all(item['errors'] for item in result['rejected']))

    def test_verify_rejects_invalid_category_missing_fields_and_empty_evidence(self):
        variants = []
        for field in ('category', 'pages', 'quotes', 'reason', 'action'):
            finding = self.finding()
            del finding[field]
            variants.append(finding)
        for field, value in (('category', 'unknown'), ('category', []), ('pages', []),
                             ('quotes', []), ('reason', '  '), ('action', None),
                             ('quotes', [{'page': TTL, 'text': ''}])):
            finding = self.finding()
            finding[field] = value
            variants.append(finding)
        result = self.verify(*variants)
        self.assertFalse(result['ok'])
        self.assertFalse(result['accepted'])
        self.assertEqual(len(result['rejected']), len(variants))

    def test_verify_cli_file_stdin_and_grouped_text_report(self):
        findings = []
        for category in ('contradiction', 'stale', 'missing-page', 'promote'):
            item = self.finding()
            item['category'] = category
            findings.append(item)
        payload = json.dumps({'version': 1, 'findings': findings}, ensure_ascii=False)
        path = self.base / 'findings.json'
        path.write_text(payload, encoding='utf-8')
        for source in (str(path), '-'):
            result = self.run_cli('lint', 'semantic-verify', source, '--json', input=payload)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(json.loads(result.stdout)['accepted']), 4)
        text = self.run_cli('lint', 'semantic-verify', '-', input=payload)
        self.assertEqual(text.returncode, 0, text.stderr)
        positions = [text.stdout.index(label) for label in
                     ('疑似矛盾', '疑似过期', '缺页概念', '建议升级为规则', '引文核对失败，已剔除')]
        self.assertEqual(positions, sorted(positions))
        self.assertIn(REAL_QUOTE, text.stdout)

    def test_cli_reports_bad_json_schema_and_findings_in_chinese_without_traceback(self):
        for payload in ('{', '[]', '{}', '{"version": true, "findings": []}',
                        '{"version": 1, "findings": [], "extra": NaN}',
                        '{"version": 2, "findings": []}', '{"version": 1}',
                        json.dumps({'version': 1, 'findings': [{}]}),
                        json.dumps({'version': 1, 'findings': [dict(self.finding(), category='unknown')]})):
            for flags in ((), ('--json',)):
                result = self.run_cli('lint', 'semantic-verify', '-', *flags, input=payload)
                self.assertNotEqual(result.returncode, 0, result)
                self.assertNotIn('Traceback', result.stdout + result.stderr)
                self.assertRegex(result.stdout + result.stderr, '[\u4e00-\u9fff]')

    def test_cli_invalid_date_and_unreadable_findings_are_usage_errors(self):
        for args in (('semantic-pack', '--today', '2026-02-30'),
                     ('semantic-pack', '--today', '20261120'),
                     ('semantic-verify', str(self.base / 'missing.json')),
                     ('semantic-verify',)):
            result = self.run_cli('lint', *args, '--json')
            self.assertEqual(result.returncode, 2, result)
            self.assertFalse(json.loads(result.stdout)['ok'])
            self.assertNotIn('Traceback', result.stdout + result.stderr)

    def test_verify_honors_vault_local_blocklist_without_masking_schema_keys(self):
        (self.base / 'blocklist.txt').write_text('fluxctl\npage\nstale\n', encoding='utf-8')
        result = self.verify(self.finding())
        self.assertTrue(result['ok'])
        self.assertEqual(len(result['accepted']), 1)
        self.assertEqual(result['accepted'][0]['category'], 'stale')
        self.assertNotIn('fluxctl', json.dumps(result))
        output = self.run_cli('lint', 'semantic-verify', '-', input=json.dumps(
            {'version': 1, 'findings': [self.finding()]}))
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertIn('疑似过期（1）', output.stdout)
        self.assertNotIn('fluxctl', output.stdout)

    def test_verify_snapshot_without_config_uses_isolated_environment_blocklist(self):
        from dataclasses import replace
        from kblib.semantic import verify
        (self.base / 'blocklist.txt').write_text('fluxctl\n', encoding='utf-8')
        result = verify(replace(self.vault(), config_file=None),
                        {'version': 1, 'findings': [self.finding()]})
        self.assertNotIn('fluxctl', json.dumps(result))

    def test_verify_masks_all_report_fields_after_matching_raw_quotes(self):
        secret = 'ghp_' + 'Ab3' * 12
        path = self.root / TTL
        path.write_text(path.read_text() + '\n凭据 ' + secret + '。\n', encoding='utf-8')
        finding = self.finding()
        finding.update(reason='核实 ' + secret, action='删除 ' + secret,
                       verified_by='本机读取 ' + secret,
                       quotes=[{'page': TTL, 'text': '凭据 ' + secret + '。'}])
        bad = copy.deepcopy(finding)
        bad['quotes'][0]['page'] = 'wiki/' + secret + '.md'
        payload = json.dumps({'version': 1, 'findings': [finding, bad]})
        result = self.verify(finding, bad)
        self.assertEqual(len(result['accepted']), 1)
        self.assertNotIn(secret, json.dumps(result))
        for flags in ((), ('--json',)):
            output = self.run_cli('lint', 'semantic-verify', '-', *flags, input=payload)
            self.assertNotIn(secret, output.stdout + output.stderr)
            self.assertIn('****', output.stdout)


if __name__ == '__main__':
    unittest.main()
