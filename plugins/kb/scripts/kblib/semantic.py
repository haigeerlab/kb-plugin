"""Read-only semantic clues and literal verification of model findings."""

from datetime import date
from itertools import combinations
import json
import posixpath
import re

from . import KbError, checks, evidence, markdown
from .config import load_blocklist
from .redaction import mask_text


GROUPS = (('contradiction', '疑似矛盾'), ('stale', '疑似过期'),
          ('missing-page', '缺页概念'), ('promote', '建议升级为规则'))
MAX_BYTES = 60000
BODY_CHARS = 4000
TIME_RE = re.compile(
    r'(?<![\w.])(?:v\d+(?:\.(?:\d+|x))*|\d+\.(?:\d+|x)(?:\.(?:\d+|x))*)(?!\w|\.\w)'
    r'|\b\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?\b|\d{4}年\d{1,2}月(?:\d{1,2}日)?'
    r'|目前|最新|现在|\b(?:currently|latest|now)\b', re.IGNORECASE)
IMPERATIVE_RE = re.compile(r'总是|必须|永远不要|不要|\b(?:never|always)\b', re.IGNORECASE)


def _current_body(doc):
    """Use the shared callout boundaries, including all callout kinds."""
    excluded = set()
    start = doc.frontmatter.end
    for block in markdown.callouts(doc.text):
        excluded.update(range(block.line, block.end_line + 1))
    return '\n'.join(line if number not in excluded else ''
                     for number, line in enumerate(doc.text.splitlines(), 1)
                     if number > start).strip()


def _wiki_links(vault, path, text, after=0, before=None):
    result = set()
    for link in markdown.links(text):
        if link.wiki or link.line <= after or (before is not None and link.line >= before):
            continue
        target, error = checks._target(vault, path, link.target)
        if error is None and target is not None and target.startswith('wiki/'):
            if target in vault.documents and target.lower().endswith('.md'):
                result.add(target)
    return sorted(result)


def _terms(text):
    # Inline code with whitespace is a command fragment, not a concept.
    return {match[2].casefold() for match in re.finditer(r'(`+)([^`\n]+?)\1(?!`)', text)
            if match[2].strip() and not re.search(r'\s', match[2])}


def _sentences(text):
    return [part.strip() for part in re.split(r'(?<=[。！？!?；;\n])|(?<=\.)\s+', text)
            if part.strip() and not re.match(r'^#{1,6}\s', part.strip())]


def _clues(pages, bodies, annotated, known, log_counts, backlinks):
    terms = {p['path']: _terms(bodies[p['path']]) for p in pages}
    tags = {p['path']: {t.casefold() for t in p['tags']} for p in pages}
    pairs = []
    for left, right in combinations(pages, 2):
        a, b = left['path'], right['path']
        if b in annotated[a] or a in annotated[b]:
            continue
        shared_tags, shared_terms = tags[a] & tags[b], terms[a] & terms[b]
        if shared_tags or shared_terms:
            pairs.append({'pages': sorted((a, b)), 'shared_tags': sorted(shared_tags),
                          'shared_terms': sorted(shared_terms)})
    pairs.sort(key=lambda p: (-len(p['shared_tags']) - len(p['shared_terms']), p['pages']))
    stale, missing, promote = [], {}, []
    for page in pages:
        path = page['path']
        sentences = _sentences(bodies[path])
        stale.extend({'page': path, 'sentence': sentence, 'updated_days': page['updated_days']}
                     for sentence in sentences if TIME_RE.search(sentence))
        for term in tags[path] | terms[path]:
            if term not in known:
                missing.setdefault(term, []).append(path)
        if page['type'] not in ('pitfall', 'decision'):
            continue
        signals = []
        incoming = sorted(backlinks.get(path, ()))
        if len(incoming) >= 2:
            signals.append({'kind': 'incoming-links', 'pages': incoming})
        count = log_counts.get(page['title'], 0)
        if count >= 2:
            signals.append({'kind': 'log-updates', 'count': count})
        imperative = [sentence for sentence in sentences if IMPERATIVE_RE.search(sentence)]
        if imperative:
            signals.append({'kind': 'imperative', 'sentences': imperative})
        if signals:
            promote.append({'page': path, 'signals': signals})
    return {'contradiction': pairs[:30], 'stale': stale,
            'missing-page': [{'term': term, 'pages': sorted(paths)}
                             for term, paths in sorted(missing.items()) if len(paths) >= 2],
            'promote': promote}


def _size(result):
    # Match the CLI's UTF-8 JSON encoding, reserving its final newline.
    return len(json.dumps(result, ensure_ascii=False).encode('utf-8')) + 1


def pack(vault, today):
    """Return facts only, with older pages taking priority within 60,000 bytes."""
    if not isinstance(today, date):
        raise KbError('语义体检用法错误：today 必须是日期')
    pages, bodies, annotated, known, log_counts = [], {}, {}, set(), {}
    for doc in vault.pages():
        fm = doc.frontmatter.data
        title = fm.get('title', '')
        title = title if isinstance(title, str) else ''
        known.update((posixpath.splitext(posixpath.basename(doc.path))[0].casefold(), title.casefold()))
        body = _current_body(doc)
        bodies[doc.path] = body
        updated = checks._date(fm.get('updated'), today)
        created = checks._date(fm.get('created'), today)
        sections = markdown.sections(doc.text)
        related = sections.get('相关')
        related_end = (min((section.line for section in sections.values() if section.line > related.line),
                           default=None) if related else None)
        page = {'path': doc.path, 'type': fm.get('type'), 'title': title,
                'tags': fm.get('tags', []) if checks._string_list(fm.get('tags', [])) else [],
                'created': fm.get('created'), 'updated': fm.get('updated'),
                'created_days': (today - created).days if created is not None else None,
                'updated_days': (today - updated).days if updated is not None else None,
                'related': _wiki_links(vault, doc.path, doc.text, related.line, related_end) if related else [],
                'links': _wiki_links(vault, doc.path, doc.text),
                'body': body[:BODY_CHARS], 'truncated': len(body) > BODY_CHARS}
        pages.append(page)
        annotated[doc.path] = set()
        for block in markdown.callouts(doc.text):
            if block.kind in ('outdated', 'disputed'):
                annotated[doc.path].update(_wiki_links(
                    vault, doc.path, doc.text, block.line - 1, block.end_line + 1))
    log = vault.documents.get('log.md')
    if log is not None:
        for _, line in markdown.visible_lines(log.text):
            match = re.fullmatch(r'## \[\d{4}-\d{2}-\d{2}\] (?:save|compile) \| (\S.*)', line)
            if match:
                log_counts[match[1]] = log_counts.get(match[1], 0) + 1
    pages.sort(key=lambda p: (p['updated'] if isinstance(p['updated'], str) else '', p['path']))
    backlinks = {}
    for page in pages:
        for target in page['links']:
            if target != page['path']:
                backlinks.setdefault(target, set()).add(page['path'])
    truncated = {p['path'] for p in pages if p['truncated']}
    result = {'version': 1, 'ok': True, 'today': today.isoformat(), 'pages': pages,
              'candidates': {}, 'truncated': False, 'truncated_pages': [],
              'truncated_page_count': 0, 'omitted_page_count': 0}

    def refresh(candidates=False):
        if candidates:
            result['candidates'] = _clues(pages, bodies, annotated, known, log_counts, backlinks)
        # The path inventory must also stay bounded for very large vaults.
        paths, path_bytes = [], 2
        for path in sorted(truncated):
            size = len(json.dumps(path, ensure_ascii=False).encode('utf-8')) + 2
            if path_bytes + size <= MAX_BYTES // 4:
                paths.append(path)
                path_bytes += size
        result['truncated_pages'] = paths
        result['truncated_page_count'] = len(truncated)
        result['truncated'] = bool(truncated)

    refresh(candidates=True)
    while _size(result) > MAX_BYTES and pages:
        # Trim the newest page first. If its metadata and clues alone do not fit,
        # omit it before reducing an older page's body.
        page = pages[-1]
        body = page['body']
        truncated.add(page['path'])
        page.update(body='', truncated=True)
        refresh()
        if _size(result) > MAX_BYTES:
            pages.pop()
            result['omitted_page_count'] += 1
            refresh(candidates=True)
            continue
        low, high = 0, len(body)
        while low < high:
            middle = (low + high + 1) // 2
            page['body'] = body[:middle]
            refresh()
            if _size(result) <= MAX_BYTES:
                low = middle
            else:
                high = middle - 1
        page['body'] = body[:low]
        refresh()
    return result


def _page_error(path, documents):
    if (not isinstance(path, str) or not path.startswith('wiki/') or '\\' in path
            or '\0' in path or any(part in ('', '.', '..') for part in path.split('/'))
            or posixpath.normpath(path) != path or not path.lower().endswith('.md')):
        return '页面路径必须是 wiki/ 下的相对路径，禁止绝对路径和 ..'
    if path not in documents:
        return '页面不存在或无法读取：' + path
    return None


def _finding_errors(finding, documents, bodies):
    if not isinstance(finding, dict):
        return ['finding 必须是 JSON 对象']
    errors = []
    category = finding.get('category')
    if not isinstance(category, str) or category not in dict(GROUPS):
        errors.append('category 缺失或未知；仅支持 contradiction、stale、missing-page、promote')
    for key in ('reason', 'action'):
        if not isinstance(finding.get(key), str) or not finding[key].strip():
            errors.append(key + ' 必须是非空字符串')
    pages = finding.get('pages')
    if not isinstance(pages, list) or not pages:
        errors.append('pages 必须是非空页面路径数组')
        pages = []
    for path in pages:
        error = _page_error(path, documents)
        if error:
            errors.append(error)
    quotes = finding.get('quotes')
    if not isinstance(quotes, list) or not quotes:
        errors.append('quotes 必须是非空引文数组')
        quotes = []
    for quote in quotes:
        if not isinstance(quote, dict):
            errors.append('quote 必须包含 page 和 text')
            continue
        path, text = quote.get('page'), quote.get('text')
        error = _page_error(path, documents)
        if error:
            errors.append(error)
        elif path not in pages:
            errors.append('quotes.page 必须包含在 pages 中：' + path)
        if not isinstance(text, str) or not text.strip():
            errors.append('quote.text 必须是非空字符串')
        elif error is None:
            candidate = evidence.Candidate('quote', evidence.normalize(text))
            if not evidence.contains(bodies[path], candidate):
                errors.append('引文未逐字存在于现行结论区：' + path)
    if 'verified_by' in finding and not isinstance(finding['verified_by'], str):
        errors.append('verified_by 必须是字符串')
    return errors


def _masked(value, blocklist):
    if isinstance(value, str):
        return mask_text(value, blocklist)
    if isinstance(value, list):
        return [_masked(item, blocklist) for item in value]
    if isinstance(value, dict):
        fields = ('version', 'ok', 'accepted', 'rejected', 'finding', 'errors', 'category',
                  'pages', 'quotes', 'page', 'text', 'reason', 'action', 'verified_by')
        result = {}
        for key, item in value.items():
            name = key if key in fields else _masked(key, blocklist)
            # Fixed category identifiers are part of the report schema.
            result[name] = (item if key == 'category' and isinstance(item, str) and item in dict(GROUPS)
                            else _masked(item, blocklist))
        return result
    return value


def verify(vault, findings):
    """Verify raw quotes first, then redact every field of the resulting report."""
    if (not isinstance(findings, dict) or type(findings.get('version')) is not int
            or findings['version'] != 1 or not isinstance(findings.get('findings'), list)):
        raise KbError('语义体检 findings 格式错误：需要 version: 1 和 findings 数组')
    documents = {doc.path: doc for doc in vault.pages()}
    bodies = {path: evidence.normalize(_current_body(doc)) for path, doc in documents.items()}
    accepted, rejected = [], []
    for finding in findings['findings']:
        errors = _finding_errors(finding, documents, bodies)
        if errors:
            rejected.append({'finding': finding, 'errors': errors})
        else:
            accepted.append(finding)
    blocklist = (load_blocklist({'KB_CONFIG': str(vault.config_file)})
                 if vault.config_file is not None else load_blocklist())
    return _masked({'version': 1, 'ok': not rejected, 'accepted': accepted, 'rejected': rejected},
                   blocklist)


def print_report(result):
    for category, title in GROUPS:
        findings = [f for f in result['accepted'] if f['category'] == category]
        print(f'{title}（{len(findings)}）')
        for finding in findings:
            print('页面：' + '、'.join(finding['pages']))
            for quote in finding['quotes']:
                print(f"  {quote['page']}：{quote['text']}")
            print(f"理由：{finding['reason']}\n建议动作：{finding['action']}")
            if finding.get('verified_by'):
                print('本机核实：' + finding['verified_by'])
    print(f"引文核对失败，已剔除（{len(result['rejected'])}）")
    for item in result['rejected']:
        finding = item['finding'] if isinstance(item['finding'], dict) else {}
        pages = finding.get('pages') if isinstance(finding.get('pages'), list) else []
        label = f"{finding.get('category', '?')}：{'、'.join(str(p) for p in pages) or '无页面'}"
        print(f"{label}；{'；'.join(item['errors'])}")
