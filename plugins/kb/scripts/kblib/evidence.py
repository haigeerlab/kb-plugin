"""Literal evidence checking, adapted from karpathy-llm-wiki (MIT).

Source: https://github.com/Astro-Han/karpathy-llm-wiki
Commit: eafcc77001e496cc43499e4923b663aec722c813
Copyright (c) 2026 Yuhan Lei. License: ../vendor/karpathy-llm-wiki/LICENSE.
The unmodified upstream script and license are preserved in that directory.

Changes: read frontmatter raw; check callout contents; recognize 「」 quotes.
Integration also preserves original line numbers and consumes vault snapshots.
The upstream closed candidate set is retained: quotes of 15+ characters,
ISO dates/months, grouped/dotted/suffixed numbers and plain 4+ digit numbers.
Small plain integers remain outside this mechanical check.
"""

from dataclasses import dataclass, field
import re

from .markdown import parse_frontmatter, strip_inline_code, visible_lines


NUMBER_TOKEN_RE = re.compile(
    r'(?:\d{1,3}(?:,\d{3})+(?:\.\d+)*(?:\s*[KMB%](?![A-Za-z]))?'
    r'|\d+(?:\.\d+)*(?:\s*[KMB%](?![A-Za-z]))?)(?![A-Za-z])'
)
SUFFIX_RE = re.compile(r'[KMB%]$')
DATE_RE = re.compile(r'\d{4}-\d{2}(?:-\d{2})?')
QUOTE_RES = [re.compile(r'"([^"\n]*)"'), re.compile(r'“([^”\n]*)”'), re.compile(r'「([^」\n]*)」')]
LINK_RE = re.compile(r'\[([^\]]*)\]\(([^)]*)\)')
METADATA_RE = re.compile(r'^>\s*(Sources?|Raw|Collected|Published|Updated|Archived):')
CALLOUT_RE = re.compile(r'^>\s*\[![^\]]+\]')
STATUS_LINE_RE = re.compile(r'^>\s*\*\*Status:')
WS_RE = re.compile(r'\s+')


@dataclass(frozen=True)
class Candidate:
    kind: str
    value: str
    line: int = field(default=1, compare=False)


def normalize(text):
    return WS_RE.sub(' ', text).strip()


def strip_noise(text):
    return LINK_RE.sub(r'\1', strip_inline_code(text))


def keep_number(token):
    token = token.strip()
    return bool(SUFFIX_RE.search(token) or ',' in token or '.' in token or len(token) >= 4)


def extract_numeric_date_candidates(line, number=1):
    line = strip_noise(line)
    dates = list(DATE_RE.finditer(line))
    candidates = [Candidate('date', m[0], number) for m in dates]
    remaining = list(line)
    for match in dates:
        remaining[match.start():match.end()] = ' ' * len(match[0])
    candidates.extend(Candidate('number', m[0], number)
                      for m in NUMBER_TOKEN_RE.finditer(''.join(remaining)) if keep_number(m[0]))
    return candidates


def extract_candidates(text):
    candidates, blockquote, paragraph = [], [], []
    in_callout = False

    def flush_quote():
        if blockquote:
            joined = normalize(' '.join(value for _, value in blockquote))
            if len(joined) >= 15:
                candidates.append(Candidate('quote', joined, blockquote[0][0]))
            blockquote.clear()

    def flush_paragraph():
        if paragraph:
            joined = ' '.join(value for _, value in paragraph)
            for quote_re in QUOTE_RES:
                for match in quote_re.finditer(joined):
                    if len(match[1].strip()) >= 15:
                        offset = 0
                        for number, value in paragraph:
                            if offset + len(value) >= match.start():
                                break
                            offset += len(value) + 1
                        candidates.append(Candidate('quote', normalize(match[1]), number))
            paragraph.clear()

    for number, line in visible_lines(text):
        stripped = line.strip()
        if CALLOUT_RE.match(stripped) or STATUS_LINE_RE.match(stripped):
            flush_quote()
            flush_paragraph()
            in_callout = True
            continue
        if not stripped.startswith('>'):
            if in_callout:
                flush_paragraph()
            in_callout = False
        if stripped.startswith('>'):
            content = strip_noise(stripped.lstrip('>').strip())
            candidates.extend(extract_numeric_date_candidates(content, number))
            if in_callout:
                # Callout text is a conclusion, not necessarily a verbatim quotation.
                if content:
                    paragraph.append((number, content))
                else:
                    flush_paragraph()
            else:
                flush_paragraph()
                blockquote.append((number, content))
            continue
        flush_quote()
        if not stripped:
            flush_paragraph()
            continue
        content = strip_noise(line)
        candidates.extend(extract_numeric_date_candidates(content, number))
        paragraph.append((number, content))
    flush_quote()
    flush_paragraph()
    seen, unique = set(), []
    for candidate in candidates:
        value = candidate.value.strip().strip('.,;:()[]')
        cleaned = Candidate(candidate.kind, value, candidate.line)
        if value and cleaned not in seen:
            seen.add(cleaned)
            unique.append(cleaned)
    return unique


def raw_links_of(text):
    raw = parse_frontmatter(text).data.get('raw', [])
    return raw if isinstance(raw, list) and all(isinstance(item, str) for item in raw) else []


def contains(haystack, candidate):
    if candidate.kind == 'quote':
        return candidate.value in haystack
    right = r'(?!-\d{2})' if candidate.kind == 'date' and len(candidate.value) == 7 else ''
    pattern = r'(?<![\d.,])' + re.escape(candidate.value) + right + r'(?![A-Za-z0-9]|[.,]\d|%)'
    return re.search(pattern, haystack) is not None


def source_content(text):
    """Exclude frontmatter and the legacy metadata header from evidence."""
    body, state = [], 'before_title'
    for _, line in visible_lines(text):
        if state == 'before_title' and line.startswith('# '):
            state = 'after_title'
            continue
        if state == 'after_title':
            if not line.strip():
                continue
            if METADATA_RE.match(line.strip()):
                continue
            state = 'body'
        body.append(line)
    return normalize('\n'.join(body))


def missing_candidates(text, sources):
    return [candidate for candidate in extract_candidates(text)
            if not any(contains(source, candidate) for source in sources)]
