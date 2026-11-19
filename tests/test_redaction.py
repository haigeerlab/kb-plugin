import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/kb/scripts'))
from kblib.redaction import apply_aliases, mask, parse_allowlist, scan
from vault_support import CLI, VaultTestCase


def github_token(letter='A'):
    return 'ghp_' + (letter + '2b') * 12


def secret_samples():
    boundary = '-' * 5
    private = boundary + 'BEGIN RSA PRIVATE KEY-----\n' + 'aB12' * 16
    private += '\n' + boundary + 'END RSA PRIVATE KEY-----'
    aws_prefix, bearer_prefix, password = 'AKIA', 'Bearer ', 'aB2' * 8
    cases = [private, aws_prefix + 'A2' * 8]
    cases += [prefix + 'A2b' * 12 for prefix in
              ('ghp_', 'gho_', 'ghu_', 'ghs_', 'ghr_', 'github_pat_')]
    cases += [prefix + 'A2b' * 16 for prefix in ('sk-', 'sk-ant-', 'sk-proj-')]
    cases += ['xox' + kind + '-' + 'A2b' * 12 for kind in 'abprs']
    cases += ['.'.join(('eyJ' + 'aB2' * 8, 'eyJ' + 'cD3' * 8, 'eF4' * 12)),
              bearer_prefix + 'aB2' * 12, 'postgres://alice:' + password + '@db.example.com']
    cases += [name + '=' + password for name in
              ('password', 'passwd', 'secret', 'token', 'api_key', 'apikey', 'access_key')]
    return cases


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]


class RedactionTests(unittest.TestCase):
    def test_each_secret_rule_detects_runtime_generated_values(self):
        for index, value in enumerate(secret_samples()):
            with self.subTest(index=index):
                findings = scan('前言\n```\n  ' + value + '\n```', 'inbox/a.md', [], set())
                self.assertEqual(len(findings), 1)
                finding = findings[0]
                self.assertEqual((finding.category, finding.path, finding.line, finding.column),
                                 ('secret', 'inbox/a.md', 3, 3))
                self.assertNotIn(value, repr(findings))
                self.assertEqual(finding.masked, mask(value))

    def test_secret_negative_cases_and_placeholders(self):
        values = ['', '<your-password>', '${PASSWORD}', '{{ password }}', 'xxx', 'XXX',
                  '********', 'your-password', 'placeholder', 'changeme', 'example', 'dummy']
        for name in ('password', 'passwd', 'secret', 'token', 'api_key', 'apikey', 'access_key'):
            for index, value in enumerate(values):
                with self.subTest(name=name, index=index):
                    for quoted in (value, '"' + value + '"', "'" + value + "'"):
                        self.assertEqual(scan(name + '=' + quoted, 'a.md', [], set()), [])
        negatives = ['-----' + 'BEGIN PUBLIC KEY-----', 'AKIA' + 'A' * 15,
                     'Bearer short', 'https://example.com', 'https://user@example.com',
                     '1.2.3', 'abcdefgh.ijklmnop', 'sk-xxx']
        negatives += [prefix + 'xxx' for prefix in
                      ('ghp_', 'gho_', 'ghu_', 'ghs_', 'ghr_', 'github_pat_', 'sk-ant-')]
        negatives += ['xox' + kind + '-xxx' for kind in 'abprs']
        for index, value in enumerate(negatives):
            with self.subTest(index=index):
                self.assertEqual(scan(value, 'a.md', [], set()), [])
        self.assertEqual(scan('api_key=' + 'sk-' + 'xxx', 'a.md', [], set()), [])
        self.assertEqual(scan('token=' + 'ghp_' + 'X' * 36, 'a.md', [], set()), [])

    def test_assignments_support_json_yaml_and_quoted_spaces(self):
        for index, text in enumerate(('"password": "' + 'aB2' * 8 + '"',
                                      "passwd: 'two private words'", 'API_KEY = ' + 'aB2' * 8)):
            with self.subTest(index=index):
                self.assertEqual([f.category for f in scan(text, 'a.md', [], set())], ['secret'])

    def test_network_rules_and_documentation_exclusions(self):
        for address in ('10.1.2.3', '172.16.0.1', '192.168.1.2', '8.8.8.8'):
            findings = scan('地址：' + address, 'a.md', [], set())
            self.assertEqual([(f.category, f.line, f.column) for f in findings], [('network', 1, 4)])
        for suffix in ('internal', 'local', 'corp', 'lan', 'intra'):
            self.assertEqual(len(scan('db.team.' + suffix, 'a.md', [], set())), 1)
            self.assertEqual(len(scan('db.team.' + suffix + '.', 'a.md', [], set())), 1)
            self.assertEqual(scan('db.' + suffix + '.example.com', 'a.md', [], set()), [])
        self.assertEqual([f.category for f in scan('server01.customerdata.internal', 'a.md', [], set())],
                         ['network'])
        self.assertEqual(scan('longservice.customerdata.examplecompany', 'a.md', [], set()), [])
        for address in ('127.0.0.1', '0.0.0.0', '192.0.2.1', '192.0.2.255',
                        '198.51.100.4', '203.0.113.8', '999.1.2.3', '10.0.0.1000',
                        'abc10.0.0.1', '10.0.0.1abc', '1.2.3', 'v2.1.80'):
            self.assertEqual(scan(address, 'a.md', [], set()), [])

    def test_emails_exclude_only_example_domains_and_subdomains(self):
        for domain in ('example.com', 'example.org', 'example.net', 'docs.EXAMPLE.com'):
            self.assertEqual(scan('alice@' + domain, 'a.md', [], set()), [])
        for domain in ('sample.io', 'notexample.com', 'example.com.evil.io'):
            self.assertEqual([f.category for f in scan('alice@' + domain, 'a.md', [], set())], ['email'])
            self.assertEqual([f.category for f in scan('联系 alice@' + domain + '.', 'a.md', [], set())], ['email'])

    def test_blocklist_is_case_insensitive_substring_with_literal_metacharacters(self):
        findings = scan('prefixACMEsuffix\nClient[One]', 'a.md', ['acme', 'client[one]'], set())
        self.assertEqual([(f.category, f.line, f.column) for f in findings],
                         [('blocklist', 1, 7), ('blocklist', 2, 1)])
        self.assertEqual(scan('acme', 'a.md', [], set()), [])

    def test_aliases_are_longest_first_literal_and_not_recursive(self):
        aliases = {'星图': 'proj-small', '星图SaaS': 'proj-large', 'A+B': '星图'}
        self.assertEqual(apply_aliases('星图SaaS、星图、A+B、星图SaaS', aliases),
                         ('proj-large、proj-small、星图、proj-large', 4))
        self.assertEqual(apply_aliases('无项目', {}), ('无项目', 0))
        text, count = apply_aliases('星图SaaS', {'星图SaaS': '星图'})
        self.assertEqual(count, 1)
        self.assertEqual([f.category for f in scan(text, 'a.md', ['星图'], set())], ['blocklist'])

    def test_allowlist_matches_exact_path_and_content(self):
        token = github_token()
        entries, errors = parse_allowlist('# 说明\n\ninbox/a.md ' + digest(token) + ' # 误报\n')
        self.assertEqual(errors, [])
        self.assertEqual(scan(token, 'inbox/a.md', [], entries), [])
        self.assertEqual(len(scan(token, 'inbox/b.md', [], entries)), 1)
        self.assertEqual(len(scan(github_token('B'), 'inbox/a.md', [], entries)), 1)

    def test_allowlist_invalid_records_report_line_without_source(self):
        token = github_token()
        entries, errors = parse_allowlist('# 说明\n' + token + '\na.md zzzz\n/abs.md ' + 'a' * 16
                                          + '\n../escape.md ' + 'b' * 16 + '\n')
        self.assertEqual(entries, set())
        self.assertEqual([(f.path, f.line) for f in errors], [('redaction-allow.txt', n) for n in (2, 3, 4, 5)])
        self.assertNotIn(token, repr(errors))

    def test_mask_and_scan_do_not_expose_raw_values(self):
        self.assertEqual(mask('abc'), '***')
        self.assertEqual(mask('abcde'), 'abcd*')
        self.assertEqual(mask(''), '')
        token = github_token()
        findings = scan('prefix\n' + token + '\n' + token, 'a.md', [], set())
        self.assertEqual([(f.line, f.column) for f in findings], [(2, 1), (3, 1)])
        self.assertNotIn(token, json.dumps([vars(f) for f in findings]))


class RedactionConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.env = {'KB_CONFIG': str(self.base / 'config.json')}

    def test_optional_files_are_empty_and_follow_config_directory(self):
        from kblib.config import load_aliases, load_blocklist
        self.assertEqual(load_aliases(self.env), {})
        self.assertEqual(load_blocklist(self.env), [])
        (self.base / 'blocklist.txt').write_text(' # 说明\n\n ACME \n客户名\n', encoding='utf-8')
        (self.base / 'aliases.json').write_text('{"项目真名": "proj-test"}', encoding='utf-8')
        self.assertEqual(load_blocklist(self.env), ['ACME', '客户名'])
        self.assertEqual(load_aliases(self.env), {'项目真名': 'proj-test'})

    def test_aliases_invalid_json_and_shapes_do_not_echo_contents(self):
        from kblib import KbError
        from kblib.config import load_aliases
        token = github_token()
        for index, value in enumerate(('{"' + token, '[]', '{"": "proj-test"}',
                                       '{"项目": 7}', '{"项目": ""}')):
            with self.subTest(index=index):
                (self.base / 'aliases.json').write_text(value, encoding='utf-8')
                with self.assertRaises(KbError) as error:
                    load_aliases(self.env)
                self.assertEqual(error.exception.exit_code, 2)
                self.assertNotIn(token, str(error.exception))


class RedactionCliTests(VaultTestCase):
    def run_redact(self, text, *flags, path='-'):
        return subprocess.run([sys.executable, '-B', str(CLI), 'redact', path, *flags],
                              env=self.env, cwd=self.base, input=text, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def write_local(self, name, text):
        (self.config.parent / name).write_text(text, encoding='utf-8')

    def assert_not_exposed(self, result, token):
        self.assertFalse(token in result.stdout, '标准输出泄露了完整敏感值')
        self.assertFalse(token in result.stderr, '标准错误泄露了完整敏感值')
        self.assertNotIn('Traceback', result.stdout + result.stderr)

    def test_redact_text_json_stdin_and_file_never_echo_secret(self):
        token = github_token()
        text = '记录\n```\n  ' + token + '\n```\n'
        draft = self.base / '草稿.md'
        draft.write_text(text, encoding='utf-8')
        for path in ('-', str(draft)):
            for flags in ((), ('--json',)):
                with self.subTest(path=path, flags=flags):
                    result = self.run_redact(text, *flags, path=path)
                    self.assertEqual(result.returncode, 1)
                    self.assert_not_exposed(result, token)
                    if flags:
                        data = json.loads(result.stdout)
                        self.assertEqual(set(data), {'ok', 'replaced', 'findings'})
                        self.assertFalse(data['ok'])
                        self.assertEqual(data['replaced'], 0)
                        self.assertEqual(data['findings'], [{'code': 'redaction', 'category': 'secret',
                                                            'path': '<stdin>' if path == '-' else path,
                                                            'line': 3, 'column': 3, 'masked': mask(token)}])
                    else:
                        self.assertIn('secret', result.stdout)
                        self.assertIn('第 3 列', result.stdout)
        self.assertEqual(draft.read_text(encoding='utf-8'), text)

    def test_clean_redact_works_without_vault_config_or_optional_files(self):
        self.config.unlink()
        result = self.run_redact('安全内容', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'ok': True, 'replaced': 0, 'findings': []})

    def test_every_secret_type_is_masked_in_all_cli_output_modes(self):
        samples = secret_samples()
        text = '\n'.join(samples)
        for flags in ((), ('--json',), ('--apply-aliases',)):
            with self.subTest(flags=flags):
                result = self.run_redact(text, *flags)
                self.assertEqual(result.returncode, 1)
                for value in samples:
                    self.assert_not_exposed(result, value)
                if flags == ('--json',):
                    self.assertEqual(len(json.loads(result.stdout)['findings']), len(samples))

    def test_alias_application_stdout_stderr_count_and_no_file_write(self):
        self.write_local('aliases.json', json.dumps({'星图': 'proj-one', '星图SaaS': 'proj-two'}))
        self.write_local('blocklist.txt', '星图\n')
        draft = self.base / 'draft.md'
        draft.write_text('星图SaaS、星图\n', encoding='utf-8')
        result = self.run_redact('', '--apply-aliases', path=str(draft))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'proj-two、proj-one\n')
        self.assertIn('2', result.stderr)
        self.assertEqual(draft.read_text(encoding='utf-8'), '星图SaaS、星图\n')
        clean = self.run_redact(result.stdout, '--json')
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertEqual(json.loads(clean.stdout)['findings'], [])

    def test_apply_aliases_with_remaining_secret_does_not_emit_unsafe_draft(self):
        token = github_token()
        self.write_local('aliases.json', '{"项目": "proj-test"}')
        result = self.run_redact('项目\n' + token, '--apply-aliases')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn('1', result.stderr)
        self.assertIn(mask(token), result.stderr)
        self.assert_not_exposed(result, token)

    def test_configuration_and_input_errors_exit_two_without_raw_content(self):
        token = github_token()
        self.write_local('aliases.json', '{"' + token)
        for flags in ((), ('--json',), ('--apply-aliases',)):
            result = self.run_redact('内容', *flags)
            self.assertEqual(result.returncode, 2)
            self.assert_not_exposed(result, token)
        (self.config.parent / 'aliases.json').unlink()
        missing = self.run_redact('', path=str(self.base / 'missing.md'))
        self.assertEqual(missing.returncode, 2)
        invalid = self.base / 'invalid.md'
        invalid.write_bytes(b'\xff')
        self.assertEqual(self.run_redact('', path=str(invalid)).returncode, 2)

    def test_configuration_error_masks_blocklisted_path(self):
        company = '星河公司'
        self.write_local('blocklist.txt', company)
        self.config.write_text(json.dumps({'version': 1, 'vault': str(self.base / company)}), encoding='utf-8')
        for flags in ((), ('--json',)):
            result = self.run_redact('内容', *flags)
            self.assertEqual(result.returncode, 2)
            self.assert_not_exposed(result, company)

    def test_allowlist_is_loaded_from_vault_and_path_is_vault_relative(self):
        token = github_token()
        path = 'raw/allowed.md'
        target = self.root / path
        target.write_text(token, encoding='utf-8')
        (self.root / 'redaction-allow.txt').write_text(path + ' ' + digest(token), encoding='utf-8')
        result = self.run_redact('', '--json', path=str(target))
        self.assertEqual(result.returncode, 0, result.stderr)
        target.write_text(github_token('B'), encoding='utf-8')
        self.assertEqual(self.run_redact('', '--json', path=str(target)).returncode, 1)
        result = self.run_redact(token, '--json')
        self.assertEqual(result.returncode, 1)
        self.assert_not_exposed(result, token)

    def test_ac6_session_has_three_hits_one_alias_and_exact_locations(self):
        token = github_token()
        self.write_local('aliases.json', '{"星图项目": "proj-star"}')
        self.write_local('blocklist.txt', '# 公司名\n 星河公司 \n')
        text = '会话摘录\n项目：星图项目\n凭证：' + token + '\n内网：10.20.30.40\n客户：星河公司\n'
        result = self.run_redact(text, '--json')
        self.assertEqual(result.returncode, 1)
        self.assert_not_exposed(result, token)
        data = json.loads(result.stdout)
        self.assertEqual(data['replaced'], 1)
        self.assertEqual([(f['category'], f['path'], f['line'], f['column']) for f in data['findings']],
                         [('secret', '<stdin>', 3, 4), ('network', '<stdin>', 4, 4),
                          ('blocklist', '<stdin>', 5, 4)])
        self.assertEqual([f['masked'] for f in data['findings']],
                         [mask(token), mask('10.20.30.40'), mask('星河公司')])

    def test_check_redaction_scans_all_scopes_and_code_without_alias_replacement(self):
        from kblib.checks import check_redaction
        token = github_token()
        self.write_local('aliases.json', '{"项目真名": "proj-test"}')
        self.write_local('blocklist.txt', '项目真名\n')
        paths = ('inbox/2026-01-02-secret.md', 'raw/source.txt', 'wiki/tech/new.txt', 'index.md', 'log.md')
        for path in paths:
            (self.root / path).write_text('```\n  ' + token + '\n```\n项目真名\n', encoding='utf-8')
        findings = check_redaction(self.vault())
        self.assertEqual(len(findings), 10)
        self.assertEqual({f.path for f in findings}, set(paths))
        self.assertTrue(all(f.code == 'redaction' for f in findings))
        self.assertNotIn(token, repr(findings))
        self.assertTrue(all('第 3 列' in f.message for f in findings if f.line == 2))

    def test_check_json_and_text_mask_inbox_secret_and_bad_allowlist(self):
        token = github_token()
        path = 'inbox/2026-01-02-secret.md'
        (self.root / path).write_text('---\ncaptured: 2026-01-02\nsource: manual\nhost: codex\n---\n'
                                     '```\n' + token + '\n```\n', encoding='utf-8')
        (self.root / 'redaction-allow.txt').write_text('# 说明\n' + token + '\n', encoding='utf-8')
        for flags in ((), ('--json',)):
            result = self.run_cli('check', *flags)
            self.assertEqual(result.returncode, 1)
            self.assert_not_exposed(result, token)
            if flags:
                findings = json.loads(result.stdout)['findings']
                self.assertEqual([(f['code'], f['path'], f['line']) for f in findings],
                                 [('redaction', 'redaction-allow.txt', 2), ('redaction', path, 7)])

    def test_check_other_diagnostics_and_paths_cannot_echo_secret(self):
        token = github_token()
        self.replace('wiki/tech/example.md', 'raw: [inbox/2026-01-01-example.md, raw/example.md]',
                     'raw: [' + token + ']')
        path = self.root / 'raw' / (token + '.txt')
        path.write_text(token, encoding='utf-8')
        for flags in ((), ('--json',)):
            result = self.run_cli('check', *flags)
            self.assertEqual(result.returncode, 1)
            self.assert_not_exposed(result, token)
        for flags in ((), ('--json',)):
            result = self.run_redact('', *flags, path=str(path))
            self.assertEqual(result.returncode, 1)
            self.assert_not_exposed(result, token)

    def test_valid_and_dispatch_fixtures_still_pass_check(self):
        for fixture in ('valid', 'dispatch'):
            with self.subTest(fixture=fixture):
                if fixture == 'dispatch':
                    shutil.rmtree(self.root)
                    shutil.copytree(ROOT / 'tests/fixtures/vaults' / fixture, self.root)
                    self.git('init', '-q')
                result = self.run_cli('check', '--json')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), {'ok': True, 'findings': []})


if __name__ == '__main__':
    unittest.main()
