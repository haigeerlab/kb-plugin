"""Deterministic, side-effect-free checks over a captured vault snapshot."""

from dataclasses import dataclass
from datetime import date
import posixpath
import re
from urllib.parse import unquote, urlsplit

from . import evidence, markdown
from .vault import REQUIRED_SECTIONS, SCHEMA_VERSION, TYPE_DIRS, Vault


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    line: int
    message: str


STANDARD_CALLOUTS = {
    'note', 'abstract', 'summary', 'tldr', 'info', 'todo', 'tip', 'hint', 'important',
    'success', 'check', 'done', 'question', 'help', 'faq', 'warning', 'caution',
    'attention', 'failure', 'fail', 'missing', 'danger', 'error', 'bug', 'example',
    'quote', 'cite',
}
OPERATIONS = {'init', 'save', 'compile', 'lint', 'archive', 'promote'}
SLUG = r'[a-z0-9]+(?:-[a-z0-9]+)*'


def _date(value, today):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed <= today else None


def _field_line(frontmatter, key, index=None):
    item_lines = frontmatter.item_lines.get(key, [])
    if index is not None and index < len(item_lines):
        return item_lines[index]
    return frontmatter.lines.get(key, 1)


def _string_list(value):
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)


def _target(vault, path, destination, from_root=False):
    """Return (vault-relative path, error); external links have no target."""
    try:
        url = urlsplit(destination)
    except ValueError:
        return None, '链接格式无效'
    if url.scheme or url.netloc:
        if url.scheme in ('http', 'https', 'mailto') or (url.netloc and not url.scheme):
            return None, None
        return None, '知识库内链接必须使用相对路径'
    value = unquote(url.path)
    if value.startswith('/'):
        return None, '知识库内链接必须使用相对路径'
    base = '' if from_root else posixpath.dirname(path)
    target = posixpath.normpath(posixpath.join(base, value)) if value else path
    if target == '..' or target.startswith('../'):
        return None, '链接超出知识库范围'
    if target not in vault.files:
        return target, '链接指向不存在的文件'
    if url.fragment:
        doc = vault.documents.get(target)
        if doc is None or unquote(url.fragment) not in markdown.anchors(doc.text):
            return target, '链接指向不存在的标题锚点'
    return target, None


def _raw_target(vault, value):
    if not isinstance(value, str) or not value or value.startswith('/'):
        return None
    # Sources are root-relative file paths, never URLs or anchor links.
    if any(c in value for c in ('#', '?')):
        return None
    normalized = posixpath.normpath(value)
    if not normalized.startswith(('inbox/', 'raw/')) or normalized != value:
        return None
    return value if value in vault.files else None


def check_schema_version(vault: Vault) -> list[Finding]:
    doc = vault.documents.get('SCHEMA.md')
    if doc is None:
        return [Finding('schema-version', 'SCHEMA.md', 1, '缺少可读取的 SCHEMA.md，请运行 init 补齐')]
    fm = doc.frontmatter
    value = fm.data.get('schema_version')
    if fm.errors or type(value) is not int or value != SCHEMA_VERSION:
        return [Finding('schema-version', doc.path, fm.lines.get('schema_version', 1),
                        'schema_version 必须是整数 1')]
    return []


def check_frontmatter(vault: Vault) -> list[Finding]:
    findings = []
    for path, message in sorted(vault.read_errors.items()):
        if path.startswith('wiki/') and (vault.selected is None or path in vault.selected):
            findings.append(Finding('frontmatter', path, 1, message))
    for doc in vault.pages():
        fm = doc.frontmatter
        findings.extend(Finding('frontmatter', doc.path, error.line, error.message) for error in fm.errors)

        def report(key, message):
            findings.append(Finding('frontmatter', doc.path, fm.lines.get(key, 1), message))

        kind = fm.data.get('type')
        if not isinstance(kind, str) or kind not in TYPE_DIRS:
            report('type', 'type 必须是 pitfall、decision、tech、pattern 或 project')
        elif posixpath.dirname(doc.path) != 'wiki/' + TYPE_DIRS[kind]:
            report('type', 'type 与所在的 wiki 目录不一致')
        title = fm.data.get('title')
        if not isinstance(title, str) or not title.strip() or not re.search(r'[\u3400-\u9fff]', title):
            report('title', 'title 必须是非空中文标题')
        status = fm.data.get('status')
        if status not in ('current', 'superseded'):
            report('status', 'status 必须是 current 或 superseded')
        if status == 'superseded' and not isinstance(fm.data.get('superseded_by'), str):
            report('superseded_by', 'superseded 页面必须填写 superseded_by')
        if 'superseded_by' in fm.data:
            value = fm.data['superseded_by']
            target, error = _target(vault, doc.path, value, True) if isinstance(value, str) and value.strip() and not value.startswith('#') else (None, '无效')
            if error or target is None or not target.startswith('wiki/') or not target.endswith('.md'):
                report('superseded_by', 'superseded_by 必须指向存在的 wiki 页面')
        dates = {}
        for key in ('created', 'updated'):
            parsed = _date(fm.data.get(key), vault.date)
            if parsed is None:
                report(key, key + ' 必须是 YYYY-MM-DD 日期，且不晚于本机今天')
            else:
                dates[key] = parsed
        if len(dates) == 2 and dates['updated'] < dates['created']:
            report('updated', 'updated 不得早于 created')
        if kind != 'project' or 'raw' in fm.data:
            raw = fm.data.get('raw')
            if not _string_list(raw) or not raw:
                report('raw', 'raw 必须是非空字符串列表（project 可省略）')
        for key in ('tags', 'projects'):
            if key in fm.data and not _string_list(fm.data[key]):
                report(key, key + ' 必须是字符串列表')
    return findings


def check_sections(vault: Vault) -> list[Finding]:
    findings = []
    for doc in vault.pages():
        kind = doc.frontmatter.data.get('type')
        required = REQUIRED_SECTIONS.get(kind, ()) if isinstance(kind, str) else ()
        present = markdown.sections(doc.text)
        missing = [name for name in required if name not in present]
        if missing:
            findings.append(Finding('sections', doc.path, 1, '缺少二级标题章节：' + '、'.join(missing)))
    return findings


def check_filename(vault: Vault) -> list[Finding]:
    return [Finding('filename', doc.path, 1, '页面文件名必须是英文 kebab-case.md，且不超过 60 个字符')
            for doc in vault.pages()
            if len(posixpath.basename(doc.path)) > 60
            or not re.fullmatch(SLUG + r'\.md', posixpath.basename(doc.path))]


def check_link(vault: Vault) -> list[Finding]:
    findings = []
    docs = vault.pages() + vault.entries()
    docs.extend(vault.documents[path] for path in ('SCHEMA.md', 'index.md', 'log.md') if path in vault.documents)
    for doc in docs:
        for link in markdown.links(doc.text):
            if link.wiki:
                findings.append(Finding('link', doc.path, link.line, '禁止 [[wikilink]]，请使用相对 Markdown 链接'))
                continue
            _, error = _target(vault, doc.path, link.target)
            if error:
                findings.append(Finding('link', doc.path, link.line, error + '：' + link.target))
        fm = doc.frontmatter if doc.text.startswith('---\n') else None
        if fm is None:
            continue
        for key, value in fm.data.items():
            values = value if isinstance(value, list) else [value]
            for index, item in enumerate(values):
                if not isinstance(item, str):
                    continue
                for link in markdown.links(item):
                    _, error = _target(vault, doc.path, link.target)
                    if link.wiki or error:
                        message = '禁止 [[wikilink]]，请使用相对 Markdown 链接' if link.wiki else error + '：' + link.target
                        findings.append(Finding('link', doc.path, _field_line(fm, key, index), message))
        for key in ('raw', 'superseded_by'):
            values = fm.data.get(key, [])
            if isinstance(values, str):
                values = [values]
            if not isinstance(values, list):
                continue
            for index, value in enumerate(values):
                if isinstance(value, str):
                    _, error = _target(vault, doc.path, value, True)
                    if error:
                        findings.append(Finding('link', doc.path, _field_line(fm, key, index), error + '：' + value))
    return findings


def check_raw_ref(vault: Vault) -> list[Finding]:
    findings = []
    for doc in vault.pages():
        fm = doc.frontmatter
        raw = fm.data.get('raw')
        if raw is None and fm.data.get('type') == 'project':
            continue
        if not _string_list(raw) or not raw:
            findings.append(Finding('raw-ref', doc.path, fm.lines.get('raw', 1), 'raw 必须是非空出处路径列表'))
            continue
        for index, value in enumerate(raw):
            if _raw_target(vault, value) is None:
                findings.append(Finding('raw-ref', doc.path, _field_line(fm, 'raw', index),
                                        '出处必须指向存在的 inbox/ 或 raw/ 文件：' + value))
    return findings


def check_evidence(vault: Vault) -> list[Finding]:
    findings = []
    for doc in vault.pages():
        sources = []
        for index, value in enumerate(evidence.raw_links_of(doc.text)):
            target = _raw_target(vault, value)
            if target in vault.read_errors:
                findings.append(Finding('evidence', doc.path, _field_line(doc.frontmatter, 'raw', index),
                                        '无法读取出处：' + value))
            elif target in vault.documents:
                sources.append(evidence.source_content(vault.documents[target].text))
        if sources:
            findings.extend(Finding('evidence', doc.path, candidate.line,
                                    '出处中未逐字找到：' + candidate.value)
                            for candidate in evidence.missing_candidates(doc.text, sources))
    return findings


def check_callout(vault: Vault) -> list[Finding]:
    findings = []
    for doc in vault.pages():
        for block in markdown.callouts(doc.text):
            message = None
            if block.kind == 'outdated':
                dates = re.findall(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)', block.title)
                if not dates or not any(_date(value, vault.date) for value in dates) or not any(not link.wiki for link in markdown.links(block.title)):
                    message = 'outdated 标题行必须带合法日期和指向取代者的 Markdown 链接'
            elif block.kind == 'disputed':
                if not block.body.strip():
                    message = 'disputed 标注块不能为空，请填写各方说法和出处'
            elif block.kind not in STANDARD_CALLOUTS:
                message = '不支持自定义标注类型：' + block.kind
            if message:
                findings.append(Finding('callout', doc.path, block.line, message))
    return findings


def check_index(vault: Vault) -> list[Finding]:
    doc = vault.documents.get('index.md')
    if doc is None:
        return [Finding('index', 'index.md', 1, '缺少可读取的 index.md')]
    pages = {path for path in vault.files if path.startswith('wiki/') and path.lower().endswith('.md')}
    findings, counts = [], {}
    current_type = None
    aliases = {**{kind: kind for kind in TYPE_DIRS}, **{directory: kind for kind, directory in TYPE_DIRS.items()},
               '踩坑': 'pitfall', '决策': 'decision', '技术': 'tech', '模式': 'pattern', '项目': 'project'}
    for number, line in markdown.visible_lines(doc.text):
        heading = re.fullmatch(r'## +(.+?)\s*', line)
        if heading:
            current_type = aliases.get(heading[1])
        found = markdown.links(line)
        for link in found:
            if link.wiki or not line.lstrip().startswith('- '):
                continue
            target, error = _target(vault, 'index.md', link.target)
            if target is None and not error:
                continue
            if error or target not in pages:
                findings.append(Finding('index', 'index.md', number, '目录条目必须指向存在的 wiki 页面'))
                continue
            counts[target] = counts.get(target, 0) + 1
            if counts[target] > 1:
                findings.append(Finding('index', 'index.md', number, '页面在总目录中重复：' + target))
            expected = 'wiki/' + TYPE_DIRS.get(current_type, '') + '/'
            if not target.startswith(expected):
                findings.append(Finding('index', 'index.md', number, '条目必须位于对应页面类型的分节下'))
            match = re.fullmatch(r'- \[[^\]]+\]\(.+\) — .+ · (\d{4}-\d{2}-\d{2})\s*', line)
            if not match or _date(match[1], vault.date) is None or len(found) != 1:
                findings.append(Finding('index', 'index.md', number, '目录条目格式应为 - [标题](路径) — 一句话摘要 · YYYY-MM-DD'))
    for path in sorted(pages - counts.keys()):
        findings.append(Finding('index', 'index.md', 1, '总目录缺少页面：' + path))
    return findings


def check_log(vault: Vault) -> list[Finding]:
    doc = vault.documents.get('log.md')
    if doc is None:
        return [Finding('log', 'log.md', 1, '缺少可读取的 log.md')]
    findings, previous = [], None
    for number, line in markdown.visible_lines(doc.text):
        if not re.match(r'^ {0,3}##(?:\s|$)', line):
            continue
        match = re.fullmatch(r'## \[(\d{4}-\d{2}-\d{2})\] ([a-z]+) \| (\S.*)', line)
        parsed = _date(match[1], vault.date) if match else None
        if not match or parsed is None or match[2] not in OPERATIONS:
            findings.append(Finding('log', 'log.md', number, '日志应为 ## [YYYY-MM-DD] <操作> | <标题>，操作和日期必须合法'))
        elif previous and parsed < previous:
            findings.append(Finding('log', 'log.md', number, '日志日期必须从旧到新排列，只追加'))
        if parsed is not None:
            previous = max(previous, parsed) if previous else parsed
    return findings


def check_immutable(vault: Vault) -> list[Finding]:
    if vault.git_error:
        return [Finding('immutable', '.', 1, vault.git_error)]
    return [Finding('immutable', path, 1, '已提交的原文被修改或删除；inbox/ 和 raw/ 只允许追加新文件')
            for path in vault.immutable_paths]


def check_inbox(vault: Vault) -> list[Finding]:
    findings = []
    for path, message in sorted(vault.read_errors.items()):
        if path.startswith('inbox/') and (vault.selected is None or path in vault.selected):
            findings.append(Finding('inbox', path, 1, message))
    for doc in vault.entries():
        fm = doc.frontmatter
        findings.extend(Finding('inbox', doc.path, error.line, error.message) for error in fm.errors)

        def report(key, message):
            findings.append(Finding('inbox', doc.path, fm.lines.get(key, 1), message))

        filename = re.fullmatch(r'inbox/(\d{4}-\d{2}-\d{2})-(' + SLUG + r')\.md', doc.path)
        if not filename or _date(filename[1], vault.date) is None:
            findings.append(Finding('inbox', doc.path, 1, 'inbox 文件名必须是 YYYY-MM-DD-<英文-kebab-case>.md，日期不得晚于今天'))
        captured = fm.data.get('captured')
        if _date(captured, vault.date) is None or (filename and captured != filename[1]):
            report('captured', 'captured 必须是合法日期，与文件名相同且不晚于今天')
        if fm.data.get('source') not in ('session', 'delegate', 'manual'):
            report('source', 'source 必须是 session、delegate 或 manual')
        if fm.data.get('host') not in ('claude-code', 'codex', 'unknown'):
            report('host', 'host 必须是 claude-code、codex 或 unknown')
        if 'project' in fm.data and (not isinstance(fm.data['project'], str) or not fm.data['project'].strip()):
            report('project', 'project 必须是非空项目代号字符串')
    return findings


CHECKS = (check_schema_version, check_frontmatter, check_sections, check_filename,
          check_link, check_raw_ref, check_evidence, check_callout, check_index,
          check_log, check_immutable, check_inbox)


def check(vault: Vault) -> list[Finding]:
    return [finding for function in CHECKS for finding in function(vault)]
