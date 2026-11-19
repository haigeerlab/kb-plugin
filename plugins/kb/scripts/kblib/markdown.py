"""Small, line-preserving parsers for the vault's Markdown contract."""

from dataclasses import dataclass, field
import html
import re
import unicodedata


@dataclass(frozen=True)
class ParseError:
    line: int
    message: str


@dataclass
class Frontmatter:
    data: dict = field(default_factory=dict)
    lines: dict = field(default_factory=dict)
    item_lines: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    end: int = 0


def _scalar(value):
    value = value.strip()
    if not value:
        raise ValueError('值不能为空')
    if value[0] in "\"'":
        if len(value) < 2 or value[-1] != value[0] or value[0] in value[1:-1]:
            raise ValueError('引号必须成对，暂不支持引号转义')
        return value[1:-1]
    if (any(c in value for c in '[]{}&*!|>\t') or ': ' in value
            or ' #' in value or value.startswith(('-', '?', '%', '@', '`'))):
        raise ValueError('只支持扁平字符串和字符串列表，不支持其他 YAML 语法')
    if value.lower() in ('true', 'false', 'null', '~'):
        return {'true': True, 'false': False}.get(value.lower())
    if re.fullmatch(r'-?\d+', value):
        return int(value)
    return value


def parse_frontmatter(text):
    result = Frontmatter()
    lines = text.splitlines()
    if not lines or lines[0] != '---':
        result.errors.append(ParseError(1, '文件必须以 --- frontmatter 开头'))
        return result
    try:
        end = lines.index('---', 1)
    except ValueError:
        result.errors.append(ParseError(1, 'frontmatter 缺少结束的 ---'))
        result.end = len(lines)
        return result
    result.end = end + 1
    list_key = None
    list_indent = None
    for number, line in enumerate(lines[1:end], 2):
        if not line.strip():
            continue
        try:
            item = re.fullmatch(r'( *)(- )(.+)', line)
            if item and list_key:
                indent = len(item[1])
                if list_indent is not None and list_indent != indent:
                    raise ValueError('不支持嵌套列表')
                list_indent = indent
                value = _scalar(item[3])
                if not isinstance(value, str):
                    raise ValueError('列表元素必须是字符串')
                result.data[list_key].append(value)
                result.item_lines[list_key].append(number)
                continue
            match = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_-]*):(?: +(.*))?', line)
            if not match:
                raise ValueError('只支持顶层 key: value 和 - item 列表，不支持嵌套 YAML')
            key, value = match.groups()
            if key in result.data:
                raise ValueError('字段重复：' + key)
            result.lines[key] = number
            list_key, list_indent = None, None
            if value is None or not value.strip():
                result.data[key] = []
                result.item_lines[key] = []
                list_key = key
            elif value.strip().startswith('['):
                value = value.strip()
                if not value.endswith(']'):
                    raise ValueError('行内列表缺少 ]')
                # Split only at unquoted commas, rejecting missing separators.
                inside = value[1:-1]
                parts, start, quote = [], 0, None
                for offset, char in enumerate(inside):
                    if quote:
                        if char == quote:
                            quote = None
                    elif char in "\"'":
                        quote = char
                    elif char == ',':
                        parts.append(inside[start:offset])
                        start = offset + 1
                if quote:
                    raise ValueError('列表内的引号必须成对')
                if inside.strip():
                    parts.append(inside[start:])
                parsed = [_scalar(part) for part in parts]
                if any(not isinstance(part, str) for part in parsed):
                    raise ValueError('列表元素必须是字符串')
                result.data[key] = parsed
                result.item_lines[key] = [number] * len(parsed)
            else:
                result.data[key] = _scalar(value)
        except ValueError as error:
            result.errors.append(ParseError(number, str(error)))
            list_key = None
    return result


def strip_inline_code(text):
    return re.sub(r'(`+)(.+?)\1(?!`)', lambda m: ' ' * len(m[0]), text)


def visible_lines(text, frontmatter=True):
    """Yield original line numbers, omitting frontmatter and fenced code."""
    lines = text.splitlines()
    start = parse_frontmatter(text).end if frontmatter and lines and lines[0] == '---' else 0
    fence = None
    for number, line in enumerate(lines[start:], start + 1):
        probe = re.sub(r'^ {0,3}> ?', '', line)
        if fence:
            closer = re.fullmatch(r' {0,3}(`{3,}|~{3,})[ \t]*', probe)
            if closer and closer[1][0] == fence[0] and len(closer[1]) >= fence[1]:
                fence = None
            continue
        opener = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', probe)
        if opener and not (opener[1][0] == '`' and '`' in opener[2]):
            fence = (opener[1][0], len(opener[1]))
            continue
        yield number, line


@dataclass(frozen=True)
class Section:
    line: int
    body: str


def sections(text):
    result = {}
    current = None
    body = []
    for number, line in visible_lines(text):
        heading = re.match(r'^ {0,3}## +(.+?)(?: +#+)?\s*$', line)
        if heading:
            if current:
                result[current] = Section(start, '\n'.join(body))
            current, start, body = heading[1], number, []
        elif current:
            body.append(line)
    if current:
        result[current] = Section(start, '\n'.join(body))
    return result


@dataclass(frozen=True)
class Link:
    target: str
    line: int
    wiki: bool = False
    label: str = ''


def _escaped(text, offset):
    count = 0
    while offset > 0 and text[offset - 1] == '\\':
        count += 1
        offset -= 1
    return count % 2 == 1


def _destination(value):
    value = value.strip()
    if value.startswith('<') and '>' in value:
        value = value[1:value.index('>')]
    else:
        value = re.split(r'\s+["\']', value, 1)[0]
    return re.sub(r'\\([!"#$%&\'()*+,\-./:;<=>?@\[\]\\^_`{|}~])', r'\1', value)


def links(text):
    result = []
    lines = [(number, strip_inline_code(line)) for number, line in visible_lines(text)]
    definitions = {}
    for _, line in lines:
        definition = re.match(r'^ {0,3}\[([^\]]+)\]:\s*(.+)$', line)
        if definition:
            definitions[definition[1].strip().casefold()] = _destination(definition[2])
    for number, line in lines:
        if re.match(r'^ {0,3}\[[^\]]+\]:', line):
            continue
        positions, consumed = [], []
        for match in re.finditer(r'\[\[([^\]\n]+)\]\]', line):
            if not _escaped(line, match.start()):
                positions.append((match.start(), Link(match[1], number, True)))
                consumed.append((match.start(), match.end()))
        for match in re.finditer(r'\[([^\[\]\n]*)\]\(', line):
            if _escaped(line, match.start()):
                continue
            start = match.end()
            depth, quoted, end = 1, False, start
            while end < len(line):
                char = line[end]
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
                value = _destination(line[start:end])
                positions.append((match.start(), Link(value, number, False, match[1])))
                consumed.append((match.start(), end + 1))
        for match in re.finditer(r'\[([^\[\]\n]+)\](?:\[([^\[\]\n]*)\])?', line):
            if _escaped(line, match.start()) or any(a <= match.start() < b for a, b in consumed):
                continue
            key = (match[2] or match[1]).strip().casefold()
            if key in definitions:
                positions.append((match.start(), Link(definitions[key], number, False, match[1])))
        result.extend(link for _, link in sorted(positions, key=lambda item: item[0]))
    return result


@dataclass(frozen=True)
class Callout:
    kind: str
    title: str
    body: str
    line: int


def callouts(text):
    result = []
    current = None
    body = []
    for number, line in visible_lines(text):
        match = re.match(r'^ {0,3}>\s*\[!([^\]]+)\][+-]?(?:\s+(.*))?$', line)
        if match or not re.match(r'^ {0,3}>', line):
            if current:
                result.append(Callout(*current, '\n'.join(body), start))
                current = None
        if match:
            current, start, body = (match[1].lower(), match[2] or ''), number, []
        elif current:
            body.append(re.sub(r'^ {0,3}> ?', '', line))
    if current:
        result.append(Callout(*current, '\n'.join(body), start))
    return result


def heading_anchor(title):
    title = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', title)
    title = html.unescape(re.sub(r'<[^>]*>', '', title)).lower()
    return ''.join(c for c in title if c in '-_ ' or unicodedata.category(c)[0] in 'LNM').replace(' ', '-')


def anchors(text):
    result = set()
    for _, line in visible_lines(text):
        match = re.match(r'^ {0,3}#{1,6} +(.+?)(?: +#+)?\s*$', line)
        if match:
            base = heading_anchor(match[1])
            anchor, suffix = base, 0
            while anchor in result:
                suffix += 1
                anchor = base + '-' + str(suffix)
            result.add(anchor)
    return result
