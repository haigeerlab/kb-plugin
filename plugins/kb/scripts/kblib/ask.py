"""Literal, read-only search over a captured vault snapshot."""

import posixpath
from urllib.parse import unquote, urlsplit

from . import KbError, markdown


def _index_terms(vault, folded):
    result = {}
    index = vault.documents.get('index.md')
    if index is None:
        return result
    lines = dict(markdown.visible_lines(index.text))
    for link in markdown.links(index.text):
        if link.wiki:
            continue
        try:
            url = urlsplit(link.target)
        except ValueError:
            continue
        if url.scheme or url.netloc or url.path.startswith('/'):
            continue
        path = posixpath.normpath(unquote(url.path))
        line = lines[link.line].casefold()
        result.setdefault(path, set()).update(term for term in folded if term in line)
    return result


def search(vault, terms, limit=10):
    """Return schema 1 results; metadata and index alone cannot select a page."""
    terms = list(terms)
    if not terms or any(not isinstance(term, str) or not term.strip() for term in terms):
        raise KbError('检索用法错误：至少需要一个非空检索词')
    if type(limit) is not int or limit <= 0:
        raise KbError('检索用法错误：--limit 必须是正整数')
    # Keep the first spelling and order, counting case variants only once.
    unique = {}
    for term in terms:
        unique.setdefault(term.casefold(), term)
    folded, terms = list(unique), list(unique.values())
    index_terms = _index_terms(vault, folded)
    ranked = []
    for doc in vault.pages():
        frontmatter = doc.frontmatter
        metadata = frontmatter.data
        lines = doc.text.splitlines()
        zones = {}
        for block in markdown.callouts(doc.text):
            if block.kind in ('outdated', 'disputed'):
                zones.update((line, block.kind) for line in range(block.line, block.end_line + 1))
        hits, matched, active = [], set(), False
        superseded = metadata.get('status') == 'superseded'
        for number, line in enumerate(lines[frontmatter.end:], frontmatter.end + 1):
            found = {term for term in folded if term in line.casefold()}
            if not found:
                continue
            matched.update(found)
            zone = 'outdated' if superseded else zones.get(number, 'current')
            active = active or zone != 'outdated'
            if len(hits) < 20:
                hits.append({'line': number, 'zone': zone, 'text': line.strip()[:200]})
        if not hits:
            continue
        title = metadata.get('title', '')
        score = (len(matched) * 2
                 + sum(term in title.casefold() for term in folded) * 3
                 + len(index_terms.get(doc.path, ())))
        page = {'path': doc.path, 'title': title, 'type': metadata.get('type', ''),
                'status': metadata.get('status', 'current'),
                'superseded_by': metadata.get('superseded_by'),
                'updated': metadata.get('updated', ''), 'raw': metadata.get('raw', []),
                'score': score, 'matched_terms': [unique[term] for term in folded if term in matched],
                'hits': hits}
        ranked.append((not active, page))
    # Stable sorts keep paths ascending while dates are descending.
    ranked.sort(key=lambda item: item[1]['path'])
    ranked.sort(key=lambda item: item[1]['updated'], reverse=True)
    ranked.sort(key=lambda item: (item[0], -item[1]['score']))
    return {'schema': 1, 'ok': True, 'vault': str(vault.root), 'terms': terms,
            'pages': [page for _, page in ranked[:limit]], 'truncated': len(ranked) > limit}
