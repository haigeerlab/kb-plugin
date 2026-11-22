#!/usr/bin/env python3
"""Fail when a tracked file names a local home directory (S107 path privacy).

The repository is public, so `/Users/<name>/...`, `/home/<name>/...` and the encoded form `-Users-<name>-...`
(Claude's project directory names) must not carry a real account name. Write a placeholder instead: `~/...`,
`$HOME/...` or `/Users/<user>/...` (angle brackets never match). ALLOWED holds made-up names only.

Only the files git tracks in this repository are scanned; nothing outside it (and never a kb vault) is read.
Prints `path:line: kind` for each hit, never the line itself (CI logs are public too), and exits 1 on any hit.
Adapted from agent-relay's scripts/check_local_paths.py.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

ALLOWED = frozenset({'example', 'someone', 'private', 'x', 'runner', 'user'})

PATTERNS = (
    ('path', re.compile(r'/(?:Users|home)/([A-Za-z0-9._-]+)')),
    ('encoded', re.compile(r'-Users-([A-Za-z0-9_]+)-')),
)


def hits_in_text(text):
    """(line number, kind) of every local home path in text whose name is not allowed."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        for kind, pattern in PATTERNS:
            if any(match.group(1) not in ALLOWED for match in pattern.finditer(line)):
                found.append((number, kind))
    return found


def tracked_files(repo):
    result = subprocess.run(['git', '-C', str(repo), 'ls-files', '-z'], capture_output=True, check=True)
    return [name for name in result.stdout.decode('utf-8').split('\0') if name]


def scan(repo=REPO):
    """`path:line: kind` for every hit in the tracked files; binary files are skipped."""
    out = []
    for name in tracked_files(repo):
        path = Path(repo) / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b'\0' in data:
            continue
        for number, kind in hits_in_text(data.decode('utf-8', errors='replace')):
            out.append(f'{name}:{number}: {kind}')
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description='Fail on local home paths in tracked files.')
    parser.add_argument('--repo', default=str(REPO), help='repository to scan (default: this one)')
    hits = scan(Path(parser.parse_args(argv).repo))
    for hit in hits:
        print(hit)
    if hits:
        print(f'{len(hits)} local home path(s) found; replace the account name with a placeholder such as '
              '~/..., $HOME/... or /Users/<user>/...', file=sys.stderr)
        return 1
    print('local paths: none')
    return 0


if __name__ == '__main__':
    sys.exit(main())
