import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/kb/scripts'))
from kblib.markdown import (parse_frontmatter, sections, links, callouts, anchors)


class MarkdownTests(unittest.TestCase):
    def test_flat_frontmatter_and_lists(self):
        result = parse_frontmatter('---\ntitle: 中文\nraw: [inbox/a.md, raw/b.md]\ntags:\n  - python\n  - "中文"\n---\n# 页面\n')
        self.assertEqual(result.errors, [])
        self.assertEqual(result.data['raw'], ['inbox/a.md', 'raw/b.md'])
        self.assertEqual(result.data['tags'], ['python', '中文'])
        self.assertEqual(result.lines['tags'], 4)
        self.assertEqual(result.end, 7)

    def test_unsupported_yaml_returns_line_errors(self):
        for value in ('raw:\n  nested: value', 'raw: {nested: value}',
                      'raw: [[nested]]', 'raw: &anchor value', 'raw: |\n  text',
                      'raw: [one, {two: value}]', 'raw:\n  - key: value'):
            with self.subTest(value=value):
                result = parse_frontmatter('---\n' + value + '\n---\n')
                self.assertTrue(result.errors)
                self.assertGreaterEqual(result.errors[0].line, 2)

    def test_inline_lists_require_commas_and_no_empty_items(self):
        for value in ('[a,,b]', '["a" "b"]', '[a,]', '[,a]', '["a,b", c'):
            with self.subTest(value=value):
                self.assertTrue(parse_frontmatter('---\ntags: ' + value + '\n---').errors)
        result = parse_frontmatter('---\ntags: ["a,b", c]\n---')
        self.assertEqual(result.errors, [])
        self.assertEqual(result.data['tags'], ['a,b', 'c'])

    def test_reference_links_images_and_escaped_links(self):
        found = links('[页面][ref] ![图片](image.png) \\[不是链接](missing.md)\n'
                      '[ref]: target.md#标题 "标题"\n')
        self.assertEqual([(x.target, x.line) for x in found], [('target.md#标题', 1), ('image.png', 1)])

    def test_html_entities_in_heading_anchors(self):
        self.assertIn('foo--bar', anchors('# Foo &amp; Bar'))

    def test_duplicate_key_and_unclosed_header(self):
        self.assertEqual(parse_frontmatter('---\nx: a\nx: b\n---').errors[0].line, 3)
        self.assertTrue(parse_frontmatter('---\nx: a').errors)

    def test_links_sections_and_callouts_skip_code(self):
        text = ('## 现行结论\n[现行](#现行结论) `[[hidden]]`\n'
                '~~~md\n## 假章节\n[[hidden]]\n~~~\n'
                '> [!outdated] 2026-01-01 → [现行](#现行结论)\n> 旧内容\n'
                '[[非法]] 和 [来源](../../inbox/a.md)\n')
        self.assertEqual(list(sections(text)), ['现行结论'])
        found = links(text)
        self.assertEqual([(x.target, x.line) for x in found],
                         [('#现行结论', 2), ('#现行结论', 7), ('非法', 9), ('../../inbox/a.md', 9)])
        self.assertTrue(found[2].wiki)
        block = callouts(text)[0]
        self.assertEqual((block.kind, block.line, block.body), ('outdated', 7, '旧内容'))

    def test_github_anchors_and_duplicates(self):
        self.assertEqual(anchors('# 标题！ 中文\n## Hello, *World*!\n## 现行结论\n## 现行结论'),
                         {'标题-中文', 'hello-world', '现行结论', '现行结论-1'})

    def test_balanced_destinations_and_encoded_anchors(self):
        found = links('[页面](a(b).md#中文) [中文](<a%20b.md#%E4%B8%AD%E6%96%87>)')
        self.assertEqual([x.target for x in found], ['a(b).md#中文', 'a%20b.md#%E4%B8%AD%E6%96%87'])


if __name__ == '__main__':
    unittest.main()
