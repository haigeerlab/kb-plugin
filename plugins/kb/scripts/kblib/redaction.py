"""Pure redaction rules, masked findings, aliases, and hashed exceptions."""

from bisect import bisect_right
from dataclasses import dataclass
import hashlib
import ipaddress
import posixpath
import re
from typing import Callable, Optional


@dataclass(frozen=True)
class Rule:
    category: str
    name: str
    pattern: str
    allow: Optional[Callable] = None


@dataclass(frozen=True)
class RedactionFinding:
    category: str
    path: str
    line: int
    column: int
    masked: str


def mask(value):
    # Four-character matches must not be echoed in full either.
    return '*' * len(value) if len(value) <= 4 else value[:4] + '*' * (len(value) - 4)


def _placeholder(value):
    value = value.strip().strip('\"\'').strip()
    lower = value.lower()
    return (not value or (value.startswith('<') and value.endswith('>'))
            or (value.startswith('${') and value.endswith('}'))
            or (value.startswith('{{') and value.endswith('}}'))
            or bool(re.fullmatch(r'[xX*._?\-]{3,}', value))
            or lower.startswith('your-')
            or lower in ('placeholder', 'changeme', 'example', 'dummy'))


def _credential_placeholder(value):
    value = value.strip().strip('\"\'')
    value = re.sub(r'^(?:AKIA|github_pat_|gh[pousr]_|sk-(?:ant-|proj-)?|xox[abprs]-|Bearer\s+)',
                   '', value, flags=re.IGNORECASE)
    return _placeholder(value)


def _token_placeholder(match):
    return _credential_placeholder(match[0])


def _assignment_placeholder(match):
    return _credential_placeholder(match['value'])


def _connection_placeholder(match):
    return _placeholder(match['password'])


def _ipv4_allowed(match):
    try:
        address = ipaddress.IPv4Address(match[0])
    except ipaddress.AddressValueError:
        return True
    return (str(address) in ('127.0.0.1', '0.0.0.0')
            or any(address in network for network in DOCUMENTATION_NETWORKS))


def _email_allowed(match):
    domain = match[0].rsplit('@', 1)[1].lower()
    return any(domain == example or domain.endswith('.' + example)
               for example in ('example.com', 'example.org', 'example.net'))


DOCUMENTATION_NETWORKS = tuple(ipaddress.IPv4Network(value) for value in
                               ('192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24'))
RULES = (
    Rule('secret', 'private-key', r'-----BEGIN (?P<kind>(?:[A-Z0-9]+ )*PRIVATE KEY)-----[\s\S]*?-----END (?P=kind)-----'),
    Rule('secret', 'aws-access-key', r'(?<![A-Za-z0-9])AKIA[A-Z0-9]{16}(?![A-Za-z0-9])', _token_placeholder),
    Rule('secret', 'github-token', r'(?<![A-Za-z0-9_])(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}(?![A-Za-z0-9_])', _token_placeholder),
    Rule('secret', 'api-token', r'(?<![A-Za-z0-9_])sk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])', _token_placeholder),
    Rule('secret', 'slack-token', r'(?<![A-Za-z0-9_])xox[abprs]-[A-Za-z0-9-]{20,}(?![A-Za-z0-9-])', _token_placeholder),
    Rule('secret', 'jwt', r'(?<![A-Za-z0-9_.-])eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])'),
    Rule('secret', 'bearer', r'(?i:\bBearer)[ \t]+[A-Za-z0-9._~+/-]{20,}=*', _token_placeholder),
    Rule('secret', 'connection', r'\b[A-Za-z][A-Za-z0-9+.-]*://[^\s:/@]+:(?P<password>[^\s/@]+)@[^\s/\"\'<>`]+', _connection_placeholder),
    Rule('secret', 'assignment', r'(?i)(?<![\w-])[\"\']?(?:password|passwd|secret|token|api_key|apikey|access_key)[\"\']?[ \t]*[:=][ \t]*(?P<value>\"[^\"\n]*\"|\'[^\'\n]*\'|<[^>\n]*>|\$\{[^}\n]*\}|\{\{[^\n]*?\}\}|[^\s,;`\"\'}\]]*)', _assignment_placeholder),
    Rule('network', 'ipv4', r'(?<![\w.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?!\w|\.\d)', _ipv4_allowed),
    Rule('network', 'internal-host', r'(?i)(?<![\w.-])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:internal|local|corp|lan|intra)(?![\w-]|\.[a-z0-9-])'),
    Rule('email', 'email-address', r'(?i)(?<![\w.+-])[a-z0-9.!#$%&\'*+/=?^_`{|}~-]+@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}(?![\w-]|\.[a-z0-9-])', _email_allowed),
)


def _matches(text, blocklist):
    matches = []
    for rule in RULES:
        for match in re.finditer(rule.pattern, text):
            if rule.allow is None or not rule.allow(match):
                matches.append((match.start(), match.end(), rule.category))
    for word in blocklist:
        if word:
            matches.extend((m.start(), m.end(), 'blocklist')
                           for m in re.finditer(re.escape(word), text, re.IGNORECASE))
    # Report a credential once even when an assignment or URL contains another rule.
    end = -1
    for start, stop, category in sorted(set(matches), key=lambda item: (item[0], -item[1], item[2])):
        if stop > end:
            yield start, stop, category
            end = stop


def scan(text, path, blocklist, allow_entries):
    """Scan all text, including fenced code; retain no unmasked match in findings."""
    line_starts = [0] + [m.end() for m in re.finditer('\n', text)]
    findings = []
    for start, stop, category in _matches(text, blocklist):
        value = text[start:stop]
        digest = hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]
        if (path, digest) in allow_entries:
            continue
        line = bisect_right(line_starts, start)
        findings.append(RedactionFinding(category, path, line, start - line_starts[line - 1] + 1, mask(value)))
    return findings


def mask_text(text, blocklist=()):
    """Protect diagnostics that may quote input or contain sensitive filenames."""
    parts, previous = [], 0
    for start, stop, _ in _matches(text, blocklist):
        parts.extend((text[previous:start], mask(text[start:stop])))
        previous = stop
    parts.append(text[previous:])
    return ''.join(parts)


def apply_aliases(text, aliases):
    if not aliases:
        return text, 0
    pattern = '|'.join(re.escape(name) for name in sorted(aliases, key=len, reverse=True))
    return re.subn(pattern, lambda match: aliases[match[0]], text)


def parse_allowlist(text):
    """Parse vault-relative paths and hashes without ever echoing invalid records."""
    entries, findings = set(), []
    for number, line in enumerate(text.splitlines(), 1):
        record = line.split('#', 1)[0].strip()
        if not record:
            continue
        match = re.fullmatch(r'(.+?)\s+([0-9a-fA-F]{16})', record)
        path = match[1] if match else ''
        if (not match or path.startswith('/') or '\\' in path
                or posixpath.normpath(path) != path or path in ('.', '..')
                or path.startswith('../')):
            findings.append(RedactionFinding('secret', 'redaction-allow.txt', number, 1,
                                             '放行清单格式错误：需要知识库相对路径与 16 位十六进制哈希'))
        else:
            entries.add((path, match[2].lower()))
    return entries, findings
