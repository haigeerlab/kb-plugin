"""Deterministic vault health reports and conservative repair drafts."""

from dataclasses import asdict
import posixpath
import re
from urllib.parse import urlsplit, urlunsplit

from . import KbError, checks, markdown, writer
from .config import config_path, load_blocklist, resolve_vault
from .redaction import mask_text
from .vault import TYPE_DIRS, Vault


GROUPS = (
    ('导航断裂', ('link', 'index')),
    ('内容可信度', ('evidence', 'raw-ref', 'callout', 'immutable', 'redaction')),
    ('格式', ('frontmatter', 'sections', 'filename', 'inbox', 'log', 'schema-version')),
    ('维护提示', ('orphan', 'stale', 'backlog')),
)


def _page_links(doc):
    yield from markdown.links(doc.text)
    fm = doc.frontmatter
    for key, value in fm.data.items():
        values = value if isinstance(value, list) else [value]
        for index, item in enumerate(values):
            if isinstance(item, str):
                for link in markdown.links(item):
                    yield markdown.Link(link.target, checks._field_line(fm, key, index),
                                        link.wiki, link.label)


def maintenance_hints(vault, stale_days):
    pages = vault.pages()
    incoming = set()
    for doc in pages:
        for link in _page_links(doc):
            if not link.wiki:
                target, error = checks._target(vault, doc.path, link.target)
                if error is None and target != doc.path:
                    incoming.add(target)
    hints = []
    for doc in pages:
        fm = doc.frontmatter
        if doc.path not in incoming and fm.data.get('type') != 'project':
            hints.append(checks.Finding('orphan', doc.path, 1, '没有其他 wiki 页面链接到此页，建议补充关联'))
        updated = checks._date(fm.data.get('updated'), vault.date)
        if fm.data.get('status') == 'current' and updated is not None:
            age = (vault.date - updated).days
            if age > stale_days:
                hints.append(checks.Finding('stale', doc.path, fm.lines.get('updated', 1),
                                            f'距上次更新 {age} 天，超过 {stale_days} 天，建议复查'))
    return hints + inbox_backlog(vault)


def inbox_backlog(vault):
    """Return the shared backlog definition used by lint and compile candidates."""
    referenced = set()
    for doc in vault.pages():
        raw = doc.frontmatter.data.get('raw', [])
        if isinstance(raw, list):
            referenced.update(value for value in raw if isinstance(value, str))
    hints = []
    log = vault.documents.get('log.md')
    save_lines, in_save = [], False
    if log is not None:
        visible = dict(markdown.visible_lines(log.text))
        for number, line in enumerate(log.text.splitlines(), 1):
            if number in visible and re.match(r'^ {0,3}##(?:\s|$)', line):
                in_save = bool(re.fullmatch(r'## \[\d{4}-\d{2}-\d{2}\] save \| \S.*', line))
            elif in_save:
                save_lines.append(line)
    save_body = '\n'.join(save_lines)
    for path in sorted(vault.files):
        if not path.startswith('inbox/') or path in referenced:
            continue
        # Match complete root-relative paths, including paths inside inline code.
        pattern = r'(?<![\w/\\.\-])' + re.escape(path) + r'(?![\w/\\.\-])'
        if re.search(pattern, save_body) is None:
            hints.append(checks.Finding('backlog', path, 1, '尚无 wiki raw 引用或 save 日志处理记录，建议编译'))
    return hints


def report(vault, stale_days=180):
    if type(stale_days) is not int or stale_days <= 0:
        raise KbError('体检用法错误：--stale-days 必须是正整数')
    findings = checks.check(vault)
    hints = maintenance_hints(vault, stale_days)
    environ = {'KB_CONFIG': str(vault.config_file)} if vault.config_file is not None else {}
    blocklist = load_blocklist(environ)
    hints = [checks.Finding(f.code, mask_text(f.path, blocklist), f.line,
                            mask_text(f.message, blocklist)) for f in hints]
    groups = []
    for name, codes in GROUPS:
        items = [asdict(f) for code in codes for f in findings + hints if f.code == code]
        groups.append({'name': name, 'codes': list(codes), 'count': len(items),
                       'severity': 'hint' if name == '维护提示' else 'check', 'findings': items})
    page_count = sum(path.startswith('wiki/') and path.lower().endswith('.md') for path in vault.files)
    index_bytes = (vault.root / 'index.md').stat().st_size if 'index.md' in vault.files else 0
    _, fixable = repair_draft(vault)
    return {'ok': not findings, 'groups': groups, 'hints': [asdict(f) for f in hints],
            'metrics': {'wiki_pages': {'value': page_count, 'threshold': 300, 'exceeded': page_count > 300},
                        'index_bytes': {'value': index_bytes, 'threshold': 40960, 'exceeded': index_bytes > 40960},
                        'ask_average_reads': {'value': None, 'reason': '暂无数据：ask 不记录读取文件数'}},
            'fixable': fixable,
            'summary': {'check': len(findings), 'hints': len(hints), 'fixable': fixable}}


def _repair_index(vault):
    doc = vault.documents.get('index.md')
    if doc is None:
        return None, 0
    aliases = {**{kind: kind for kind in TYPE_DIRS},
               **{directory: kind for kind, directory in TYPE_DIRS.items()},
               '踩坑': 'pitfall', '决策': 'decision', '技术': 'tech', '模式': 'pattern', '项目': 'project'}
    headings, present, removed = {}, set(), set()
    for number, line in markdown.visible_lines(doc.text):
        heading = re.fullmatch(r'## +(.+?)\s*', line)
        if heading and heading[1] in aliases:
            headings.setdefault(aliases[heading[1]], number)
        if not line.lstrip().startswith('- '):
            continue
        links = [link for link in markdown.links(line) if not link.wiki]
        for link in links:
            target, error = checks._target(vault, 'index.md', link.target)
            if target is not None and target not in vault.files and len(links) == 1:
                removed.add(number)
            elif target in vault.files:
                present.add(target)
    additions = {}
    for page in vault.pages():
        fm = page.frontmatter.data
        kind, title, updated = fm.get('type'), fm.get('title'), fm.get('updated')
        if (page.path in present or not isinstance(kind, str) or kind not in headings
                or not isinstance(title, str) or not title.strip()
                or checks._date(updated, vault.date) is None):
            continue
        entry = f'- [{title}]({page.path}) — （待补摘要） · {updated}\n'
        additions.setdefault(headings[kind], []).append(entry)
    lines = []
    for number, line in enumerate(doc.text.splitlines(keepends=True), 1):
        if number not in removed:
            lines.append(line)
        if number in additions:
            if not line.endswith('\n'):
                lines.append('\n')
            lines.extend(['\n', *additions[number], '\n'])
    return ''.join(lines), len(removed) + sum(map(len, additions.values()))


def _replace_destination(value, replacements):
    target = markdown._destination(value)
    if target not in replacements:
        return value, 0
    leading = len(value) - len(value.lstrip())
    stripped = value[leading:]
    if stripped.startswith('<') and '>' in stripped:
        end = leading + stripped.index('>')
        return value[:leading + 1] + replacements[target] + value[end:], 1
    title = re.search(r'\s+["\']', stripped)
    end = leading + (title.start() if title else len(stripped.rstrip()))
    return value[:leading] + replacements[target] + value[end:], 1


def _rewrite_line(line, replacements):
    probe = markdown.strip_inline_code(line)
    definition = re.match(r'^ {0,3}\[[^\]]+\]:\s*(.+)', probe)
    if definition:
        start, end = definition.span(1)
        value, count = _replace_destination(line[start:end], replacements)
        return line[:start] + value + line[end:], count
    edits = []
    for match in re.finditer(r'\[[^\[\]\n]*\]\(', probe):
        if markdown._escaped(probe, match.start()):
            continue
        start = end = match.end()
        depth, quoted = 1, False
        while end < len(probe):
            char = probe[end]
            if char == '\\':
                end += 2
                continue
            if char == '<' and end == start:
                quoted = True
            elif char == '>':
                quoted = False
            elif not quoted:
                if char == '(':
                    depth += 1
                elif char == ')':
                    depth -= 1
                    if depth == 0:
                        break
            end += 1
        if depth == 0:
            value, count = _replace_destination(line[start:end], replacements)
            if count:
                edits.append((start, end, value))
    for start, end, value in reversed(edits):
        line = line[:start] + value + line[end:]
    return line, len(edits)


def _repair_page(vault, doc, candidates):
    replacements = {}
    links = list(_page_links(doc))
    for link in links:
        if link.wiki:
            continue
        target, error = checks._target(vault, doc.path, link.target)
        if target is None or target in vault.files:
            continue
        matches = candidates.get(posixpath.basename(target), [])
        if len(matches) != 1:
            continue
        url = urlsplit(link.target)
        path = posixpath.relpath(matches[0], posixpath.dirname(doc.path))
        replacements[link.target] = urlunsplit(('', '', path, url.query, url.fragment))
    lines = doc.text.splitlines(keepends=True)
    count = 0
    visible = {number for number, _ in markdown.visible_lines(doc.text)}
    for number in sorted(visible | {link.line for link in links}):
        lines[number - 1], changed = _rewrite_line(lines[number - 1], replacements)
        count += changed
    return ''.join(lines), count


def repair_draft(vault):
    """Return only the three approved repair types; never write the snapshot."""
    content = {}
    index, count = _repair_index(vault)
    if count:
        content['index.md'] = index
    candidates = {}
    for path in sorted(vault.files):
        if path.startswith('wiki/'):
            candidates.setdefault(posixpath.basename(path), []).append(path)
    for doc in vault.pages():
        text, changed = _repair_page(vault, doc, candidates)
        if changed:
            content[doc.path] = text
            count += changed
    if count and 'log.md' in vault.documents:
        content['log.md'] = (vault.documents['log.md'].text
                             + f'\n\n## [{vault.date.isoformat()}] lint | 安全修复 {count} 处\n\n'
                             + '补齐总目录、移除失效目录条目或更正唯一同名目标的相对链接。\n')
    return content, count


def _validate_repairs(vault, content):
    for path in content:
        target = writer.target_path(vault.root, path)
        allowed = path in ('index.md', 'log.md') or (path.startswith('wiki/') and path.lower().endswith('.md'))
        if not allowed or path not in vault.files or not target.is_file():
            raise writer.WriteError('安全修复只允许修改 index.md、log.md 与 wiki/ 下已存在的页面', 'path', path)


def fix(confirm=None):
    applying = confirm is not None
    result = writer.empty_result(applying)
    result.update(groups=[], hints=[], metrics={}, fixable=0)
    blocklist = load_blocklist()
    root = resolve_vault().resolve()
    try:
        writer.reject_pending(root)
        initial_state = writer.state(root)
        vault = Vault.load()
        health = report(vault)
        result.update({key: health[key] for key in ('groups', 'hints', 'metrics', 'fixable', 'summary')})
        content, count = repair_draft(vault)
        _validate_repairs(vault, content)
        originals = {path: text.encode('utf-8') for path, text in content.items()}
        if not count:
            if applying:
                raise writer.WriteError('预览指纹不匹配，当前无需修复；请重新 preview',
                                        'fingerprint', exit_code=3)
            result.update(ok=True, message='无需修复：没有可安全修复的问题。')
            return result, 0
        result['message'] = f'安全修复 {count} 处'
        return writer.publish(root, initial_state, originals, content, confirm, result, blocklist,
                              config_path(), lambda text, paths: f'lint: 安全修复 {count} 处',
                              operation='lint fix')
    except writer.WriteError as error:
        result['ok'] = False
        result['findings'] = [{'code': error.code, 'path': error.path, 'line': 1, 'message': str(error)}]
        return writer.masked(result, blocklist), error.exit_code
    except (OSError, UnicodeError, ValueError, RuntimeError):
        result['ok'] = False
        result['findings'] = [{'code': 'lint', 'path': '.', 'line': 1,
                               'message': '无法生成或校验安全修复，请检查文件、权限与 git 状态'}]
        return writer.masked(result, blocklist), 1


def print_fix(result):
    for finding in result['findings']:
        print(f"{finding['path']}:{finding['line']} [{finding['code']}] {finding['message']}")
    if not result['ok']:
        print('安全修复失败，未完成修复。')
    elif not result['fixable']:
        print(result['message'])
    elif 'commit' in result:
        print(f"安全修复成功，已本地提交：{result['commit']}")
    else:
        for path in result['modified']:
            print('修改：' + path)
        print(result['diff'], end='')
        print(f"预览指纹：{result['fingerprint']}\n校验通过；确认后运行 lint fix apply --confirm {result['fingerprint']}。")


def print_report(result):
    for group in result['groups']:
        print(f"{group['name']}（{group['count']}）")
        for finding in group['findings']:
            print(f"{finding['path']}:{finding['line']} [{finding['code']}] {finding['message']}")
    print('规模指标')
    for key, label in (('wiki_pages', 'wiki 页数'), ('index_bytes', 'index.md 字节数')):
        metric = result['metrics'][key]
        print(f"{label}：{metric['value']}；阈值 {metric['threshold']}；"
              + ('已超过' if metric['exceeded'] else '未超过'))
    print('ask 平均读文件数：' + result['metrics']['ask_average_reads']['reason'])
    summary = result['summary']
    print(f"摘要：check 级 {summary['check']} 个问题，维护提示 {summary['hints']} 条，"
          f"可安全修复 {result['fixable']} 处。")
