"""Adapted fidelity cases from karpathy-llm-wiki eafcc77 (MIT)."""

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/kb/scripts'))
from kblib.evidence import missing_candidates, raw_links_of, source_content


def article(body, raw='raw/t/src.md'):
    return '---\ntype: tech\nraw: [' + raw + ']\n---\n# 页面\n\n' + body


class EvidenceTests(unittest.TestCase):
    def misses(self, body, raw='No numeric facts here at all.'):
        return [c.value for c in missing_candidates(article(body), [source_content(raw)])]

    def test_reads_only_frontmatter_raw(self):
        text = article('> Raw: [fake](raw/fake.md)\n```\nraw: [raw/fake.md]\n```')
        self.assertEqual(raw_links_of(text), ['raw/t/src.md'])
        self.assertEqual(raw_links_of('# 页面\n> Raw: [fake](raw/fake.md)'), [])

    def test_verbatim_numbers_and_quotes_pass(self):
        raw = 'Ghostty reached 42K stars. Daily users reached 10,000. The terminal should feel invisible to users.'
        self.assertEqual(self.misses('42K stars, 10,000 users. "The terminal should feel invisible to users."', raw), [])
        self.assertEqual(self.misses('Forks grew to 3,020.'), ['3,020'])

    def test_numeric_boundaries_and_small_integers(self):
        self.assertEqual(self.misses('42K 5.5% 3,020', '142K 95.5% 13,020'), ['42K', '5.5%', '3,020'])
        self.assertEqual(self.misses('42 users; 3.14 ratio; founded 2026.'), ['3.14', '2026'])
        self.assertEqual(self.misses('42, then 17, finally 9 items.'), [])

    def test_dates_versions_and_sentence_final_values(self):
        self.assertEqual(self.misses('Released 2031-09-12.'), ['2031-09-12'])
        self.assertEqual(self.misses('Released 2026-03.', 'Released 2026-03-19.'), ['2026-03'])
        self.assertEqual(self.misses('After v2.1.80, things changed.'), ['2.1.80'])
        self.assertEqual(self.misses('v2.1.80', 'After v2.1.80, things changed.'), [])
        self.assertEqual(self.misses('42K and 99.9%. Released 2026-06-15.', '42K. Uptime 99.9%. Released 2026-06-15.'), [])

    def test_fences_inline_code_and_link_targets_ignored(self):
        self.assertEqual(self.misses('`9000`\n~~~text\n777K\n~~~\n````text\n888K\n````\n[链接](https://example.com/9999)'), [])
        self.assertEqual(self.misses('```text\n777K\n``` trailing text\n888K\n```'), [])
        self.assertIn('666K', self.misses('```lang`bad\n666K\n```'))
        self.assertIn('777K', self.misses('    ```\n    indented text\n\n777K'))

    def test_title_checked_and_candidate_deduplicated(self):
        text = article('88,123 and 88,123 elsewhere.').replace('# 页面', '# GPT 9.7')
        found = missing_candidates(text, ['nothing'])
        self.assertEqual([(c.value, c.line) for c in found], [('9.7', 5), ('88,123', 7)])

    def test_source_metadata_is_not_evidence_but_body_metadata_is(self):
        source = '# Source\n\n> Source: example\n> Collected: 2026-06-01\n\nFirst paragraph.\n> Updated: 999K users.'
        body = source_content(source)
        self.assertNotIn('2026-06-01', body)
        self.assertIn('999K', body)
        self.assertNotIn('2026-06-01', source_content('---\ncaptured: 2026-06-01\n---\nText.'))

    def test_multiline_quotes_and_short_quote_pairing(self):
        self.assertEqual(self.misses('The maintainer said "the terminal should\nfeel invisible to users".'), ['the terminal should feel invisible to users'])
        self.assertEqual(self.misses('Accuracy is "high" but reliability is "low".'), [])
        self.assertEqual(self.misses('> The [terminal](https://example.com) should feel invisible to users.', 'The terminal should feel invisible to users.'), [])
        self.assertEqual(self.misses('> 999K users'), ['999K'])
        self.assertIn('This fabricated quotation is definitely absent', self.misses('> This fabricated quotation is definitely absent.'))

    def test_spaced_suffixes_and_word_boundaries(self):
        self.assertEqual(self.misses('10 Million users and 42 Kilobytes.'), [])
        self.assertEqual(self.misses('99.9 %', '99.9 %'), [])
        self.assertEqual(self.misses('99.9 %', '99.9%'), ['99.9 %'])
        self.assertEqual(self.misses('42K', '42Kg'), ['42K'])

    def test_callout_wrong_numbers_checked_without_paraphrase_false_positive(self):
        for kind in ('outdated', 'disputed'):
            with self.subTest(kind=kind):
                found = missing_candidates(article('> [!' + kind + '] 2026-01-01\n> This is a paraphrased conclusion with 55K users.'), ['42K users'])
                self.assertEqual([(c.value, c.line) for c in found], [('55K', 8)])

    def test_corner_quotes_recognized(self):
        self.assertEqual(self.misses('他说「这是一段足够长但没有任何来源支持的引用内容」。'), ['这是一段足够长但没有任何来源支持的引用内容'])
        self.assertEqual(self.misses('他说「这是一段足够长且在来源中出现的引用内容」。', '这是一段足够长且在来源中出现的引用内容'), [])


if __name__ == '__main__':
    unittest.main()
