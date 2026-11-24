# kb

[中文](README.md) | English

Use the same local knowledge base in Claude Code and Codex. Version `0.1.0` implements the plugin shell, vault location configuration, self-check, vault initialization, contract validation, redaction scanning, knowledge saving, search, and deterministic lint. It requires Python 3.9 or later and has no third-party dependencies.

## Install

Replace `/absolute/path/kb-plugin` in the commands below with the path to this repository.

Claude Code:

```bash
claude plugin marketplace add /absolute/path/kb-plugin
claude plugin install kb@kb-marketplace
```

Codex:

```bash
codex plugin marketplace add /absolute/path/kb-plugin
codex plugin add kb@kb-marketplace
```

After installing, open a new session and run or trigger the doctor skill. Both hosts share `plugins/kb/skills/` and `plugins/kb/scripts/`.
The commands above passed on both hosts on this machine (2026-11-19). The automated tests do not run them.

### After updating the plugin

- **Claude Code**: The local directory marketplace reads `plugins/kb` directly from the repository. Open a new session to apply changes.
- **Codex**: Installation copies the plugin into a cache (`~/.codex/plugins/cache/kb-marketplace/kb/<version>`). The skill text reads from this copy. After changing a skill, run the install command again to refresh the cache, then open a new session:

  ```bash
  codex plugin add kb@kb-marketplace
  ```

  `codex plugin marketplace upgrade` only refreshes Git-based marketplaces. It has no effect on local directory marketplaces.

## Command list

| Command | Status | Purpose |
| --- | --- | --- |
| `/kb:doctor` | Implemented | Check configuration, show the vault location, and run a self-check |
| `/kb:init` | Implemented | Preview and, after confirmation, create the vault skeleton. Existing files are not overwritten |
| `/kb:save` | Implemented | Validate a draft, preview it, and after confirmation save one entry and commit it locally |
| `/kb:ask` | Implemented | Read-only search of the vault. Answers from candidate pages with sources and distinguishes current, outdated, and disputed content |
| `/kb:compile` | Implemented | Process the inbox backlog and candidate sessions. Preview in batch, then compile one item at a time and commit locally |
| `/kb:lint` | Implemented | Check the vault and group results by impact, show maintenance hints, and after preview and confirmation apply three types of safe fixes |

You can also use the scripts directly. When calling from any directory, replace the script path with the absolute path inside this repository:

```bash
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py doctor
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py doctor --json
```

doctor checks the configuration, whether the vault directory exists and is readable, and whether the Python version meets the requirement. It does not perform any knowledge operations.
Exit codes: `0` success, `1` the self-check found problems, `2` configuration or usage error.

## Configure the vault location

The default configuration file is `~/.config/kb/config.json`, with this format:

```json
{
  "version": 1,
  "vault": "/absolute/path/vault"
}
```

The vault must be an existing directory. The script does not create it. Preview first. After confirming the path and contents, add `--confirm` to write:

```bash
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py config set-vault /absolute/path/vault
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py config set-vault /absolute/path/vault --confirm
```

Preview does not create the configuration file or its parent directories, and it does not overwrite an existing configuration. When you pass a relative path to `set-vault` explicitly, it converts the path to an absolute path before saving.
doctor reads only absolute paths from the configuration. It never guesses the vault from the current directory. If the configuration is missing or invalid, it reports the configuration file path and the repair command.

For testing, the environment variable `KB_CONFIG` overrides the configuration file location. Use the same variable for preview, write, and self-check to isolate your real configuration:

```bash
export KB_CONFIG="/tmp-dir/kb-config.json"
```

`config set-vault` also supports `--json`. In JSON mode, each command outputs exactly one object. doctor has fixed fields `ok`, `config`, `vault`, `checks`, `error`. set-vault has fixed fields `ok`, `config`, `content`, `written`, `error`.
`content` is the configuration object that will be written. `written` indicates whether it was written. On failure, `error` gives the reason in Chinese (the tool prints Chinese messages).

### git identity

`save`, `compile`, and `lint fix` make local commits in the vault, so the directory containing the vault must have a git identity. If `user.useConfigOnly = true` is set globally and the identity is applied only per directory through `includeIf "gitdir:…"`, put the vault under the directory that the identity is applied to (on this machine, `~/Documents/haigeerlab/`). If the vault is placed elsewhere, writes succeed but commits fail with `Author identity unknown`. The files are kept and not rolled back.

## Initialization and contract check

After the configuration points to an existing vault directory, preview the creation list, the skip list, and whether `git init` will run. Write only after confirmation:

```bash
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py init
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py init --confirm
```

The `/kb:init` skill runs the preview first, reports the result verbatim, and waits for explicit consent before running the confirm command.
init creates only missing files and directories and never overwrites existing files. It runs `git init` only when the vault does not already have its own git repository.
It generates SCHEMA.md, index.md, log.md, the inbox/ and raw/ directories, the five type directories under wiki/, and the five page templates in templates/. Dates use the local timezone.
init supports `--json` with fields `ok`, `vault`, `create`, `skip`, `git_init`, `written`, `error`. Directory entries end with `/`. Preview writes no files. Exit code `0` means success, `2` means a configuration, usage, or initialization error.

Read-only contract validation:

```bash
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py check
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py check --json
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py check wiki/pitfalls/example.md wiki/decisions
```

Paths are resolved relative to the configured vault root, regardless of the current directory. You can also pass an absolute path inside the vault. By default, the whole vault is checked. When paths are given, only those pages are checked, while schema, index, log, and immutable checks still run globally.
Exit codes: `0` no problems, `1` contract problems found, `2` configuration or usage error. The Chinese output lists the file, the original line number, the check code, and the reason.
Standard output in `--json` mode is always `{ "ok": true, "findings": [] }`. Each problem includes `code`, `path`, `line`, and `message`. For configuration or usage errors, it returns `ok: false` with empty findings, and writes the Chinese reason to standard error.

For the detailed writing rules, see SCHEMA.md generated by init. Body text uses relative Markdown links. In Obsidian, turn off "Use [[Wiki links]]". Put an outdated conclusion in full inside an outdated annotation block, and put disputes in a disputed block. Evidence inside these blocks is also validated.
If a committed original in `inbox/` or `raw/` is modified or deleted, check reports `immutable`. Adding new files is allowed. After validation, commit the vault to create an immutable baseline. check does not call a model, does not auto-repair, and does not commit files.

## Redact before writing

Before writing a draft into the vault, scan the file or standard input:

```bash
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py redact /tmp-dir/draft.md
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py redact /tmp-dir/draft.md --json
cat /tmp-dir/draft.md | python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py redact -
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py redact /tmp-dir/draft.md --apply-aliases
```

redact first replaces real project names using the local alias map. Then it scans for keys and credentials, IPv4 addresses, internal hostnames, email addresses, and the local blocklist. Code blocks are included. It does not do entropy detection. Placeholders, documentation example IPs, and email addresses under example.com, example.org, example.net, and their subdomains are excluded.
By default, it outputs only the replacement count and masked findings. It does not modify files. Exit codes: `0` no problems, `1` sensitive content found or the allowlist format is invalid, `2` configuration, usage, or read error. For standard input, the path is recorded as `<stdin>`. For files inside the vault, the vault-relative path is used so it can match the allowlist.

`--json` outputs `{ok, replaced, findings}`. Each finding includes `code: "redaction"`, `category` (secret/network/email/blocklist), `path`, `line`, `column`, and `masked`. Lines and columns start at 1 and refer to the text after alias replacement. Error messages output only the Chinese reason and never include the original input.
`--apply-aliases` writes the safe, replaced text to stdout as-is, and writes the replacement count to stderr. It does not write any file. If matches remain, stdout is empty, stderr contains the masked report, and the command exits with 1. It cannot be used together with `--json`.

You maintain three configuration files:

| File | Location, format, and purpose |
| --- | --- |
| `blocklist.txt` | Default `~/.config/kb/blocklist.txt`. One term per line. Leading and trailing whitespace is trimmed. Empty lines and lines starting with `#` are ignored. Matching is case-insensitive and substring-based, blocking company, customer, brand, and similar names. Stored locally. Not in the vault and not committed |
| `aliases.json` | Default `~/.config/kb/aliases.json`, for example `{"real project name": "proj-example"}`. Names are case-sensitive and replaced literally. When one name contains another, the longest match wins. Replacement is not recursive. Stored locally. Not in the vault and not committed. A format error exits with 2. Blocklist terms left after replacement are still reported as errors |
| `redaction-allow.txt` | Located at the vault root. Committed to git. Each line is `relative-path SHA-256-first-16-hex # note`, for example `raw/example.md 0123456789abcdef # manually confirmed false positive`. It stores only the path and hash, never the original text. An entry allows a finding only for the same path and the same matched content. It becomes invalid if the file is renamed or its content changes. Empty lines and `#` comments are ignored. Format errors are reported with the original line number |

blocklist.txt and aliases.json always follow the directory that contains the configuration file. If you set `KB_CONFIG=/tmp-dir/config.json`, they are also located in `/tmp-dir/` and the default directory is not read. If any of the three files is missing, it is treated as empty. redact can run even without a configured vault. It just does not read the vault's allowlist.
The allowlist hash is computed over the full fragment that the scan actually matched. It is encoded as UTF-8, hashed with SHA-256, and the first 16 hex characters are kept. Do not write sensitive original text into the allowlist or its comments. Repeated occurrences of the same content in the same file share one allowlist entry.

`kb check` registers redaction. It checks inbox/, raw/, wiki/, index.md, and log.md. It reads the blocklist and the allowlist and scans the original text. It does not perform alias replacement. When paths are given, it scans only the corresponding content. The index, log, and allowlist format are still checked globally. Templates and SCHEMA.md are outside the scope of redaction scanning.

## Save an entry

The save flow is: draft directory → preview → explicit user confirmation → `apply --confirm <fingerprint>`.
The model extracts the lesson and chooses whether to create a new page, merge into an existing one, record a conflict, or report that there is nothing new. The script handles redaction, full contract checks, writing, and the local commit.
Before saving, make sure the vault has been initialized with init and its skeleton is committed, and that the working tree has no uncommitted changes.

The draft directory must be outside the vault. Its structure mirrors vault-relative paths. It must contain exactly one new file under `inbox/`. It may also contain new or modified files under `wiki/`, plus `index.md` and `log.md`.
Modifying existing inbox files, writing to raw, symbolic links, paths outside the draft, and `..` paths are not allowed. Deletion is not supported. Existing vault files that are not in the draft stay unchanged.

```bash
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py save preview /tmp-dir/kb-save-draft
# After explicit user confirmation, use the preview fingerprint:
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py save apply /tmp-dir/kb-save-draft --confirm <fingerprint>
```

preview first replaces codenames using `aliases.json` from the real configuration directory. It scans for sensitive content, then runs all checks on a temporary copy that keeps the git history. It outputs the new files, modified files, a unified diff, the replacement count, and a 16-character preview fingerprint. It does not modify the vault or the draft.
apply reruns the same validation and compares the fingerprint. If the vault HEAD, the working tree state, the original draft text, or the replaced content has changed, the confirmation becomes invalid and you must run preview again.
A dirty working tree is rejected with exit code `1`. Running apply with a preview fingerprint from before a change to the working tree returns `3`.
After validation and fingerprint checks pass, each file is atomically replaced using a temporary file in the same directory. If writing fails, the files changed in this run are rolled back. Then only the files from this run are staged and committed locally as `save: <title>`. Nothing is pushed.
The title is taken from the frontmatter `title` of the main wiki page matching the inbox file if there is one. If there is no new content, the inbox `title` is used. If that is missing, the inbox filename is used.
If the commit fails, the written files and staging state are kept. The masked reason is reported, and nothing is reset automatically.

Both commands support `--json`. preview has fixed fields `{ok, fingerprint, created, modified, diff, replaced_aliases, findings}`. apply has `{ok, commit, created, modified, findings}`.
findings use Chinese reasons and masked sensitive values. Exit codes: `0` success, `1` validation or redaction failure, or a write or commit failure, `2` usage or configuration error, `3` fingerprint mismatch.

### What to do when a commit fails

If save apply, compile apply, or lint fix apply has already written files but `git add` or the commit fails, the files and staging state are kept. A `.kb-pending.json` file is created at the vault root. It records the relative paths of this run's files, the SHA-256 of each file after writing, the original commit message, the operation, the preview fingerprint, and the local time. The error message gives the full recovery command:

```bash
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py commit-pending
# To get a structured result:
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py commit-pending --json
```

The command first verifies that the file contents match the record and that the working tree has no changes outside the record (including untracked files). Then it runs a full `kb check`. If everything passes, it stages and commits only the files in the record, using the original commit message. On success, it deletes the record and reports the commit hash. `.kb-pending.json` is never added to a commit, and `kb check` and lint do not scan it. While a record exists, preview and apply for save, compile, and lint fix are all rejected, with a prompt to run `commit-pending` first.

Exit codes: `0` commit succeeded. `1` content verification, working tree verification, full check, or a second commit attempt failed. The record is kept. `2` no pending record, the record is corrupted or malformed, or usage or configuration error. `--json` outputs the fixed fields `{ok, commit, files, findings, error}`. If the record itself cannot be written, the files are kept and the original commit failure reason is reported.

When running in the Codex sandbox fails because `.git` is not writable, pass the full command from the error message to the user. They run it in Claude Code, a terminal, or an interactive Codex session with elevated permissions. Do not run `git add` or `git commit` yourself, and do not modify `.git`. Use `commit-pending` to complete verification and the commit.

## Batch compile backlog and candidate sessions

`/kb:compile` handles two sources: inbox items that have no wiki `raw` reference and no save-log processing record, and `pending` candidate sessions in the local queue. The backlog check uses the same function as lint. Entries whose save-log text states "no new content" with a path are also excluded.

The candidate queue is located by default at `~/.local/state/kb/candidates.jsonl`. You can override its parent directory with `KB_STATE_DIR`. It stores only pointers to local sessions. It is not placed in the vault and is not part of the vault's git commits. Each line is one JSON object:

```json
{"id":"0123456789ab","session_id":"session id","transcript_path":"/absolute/path/session.jsonl","cwd":"/absolute/path/project","reason":"contains lessons to compile","ended_at":"2026-11-19T16:00:00+08:00","status":"pending"}
```

`id` is the first 12 hex characters of the SHA-256 of `session_id`. `ended_at` is the local ISO time of the most recent enqueue. Status values are `pending`, `compiled`, `dropped`, or `expired`. Enqueuing the same `session_id` again updates the path, project directory, reason, and time. `pending` and `expired` return to `pending`. `compiled` and `dropped` keep their status. No duplicate row is added. The queue is replaced atomically. Corrupted lines are skipped and their line numbers are reported. Updates preserve the other lines.

```bash
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py candidates add --session-id <session-id> --transcript /absolute/path/session.jsonl --cwd /absolute/path/project --reason "lesson to compile"
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py candidates list --json
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py candidates show <candidate-id> --max-chars 40000
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py candidates mark <candidate-id> --status compiled
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py candidates mark <candidate-id> --status dropped
```

Without `--json`, `list` outputs a Chinese list (the tool prints Chinese). In JSON, `items` merges the `kind: inbox` backlog and the pending `kind: candidate` items. `expired` lists expired items separately, and `corrupt_lines` lists the line numbers of corrupted queue lines. If a session file no longer exists, the item is written back as `expired` automatically. A candidate whose most recent enqueue is more than 25 days old is marked "expiring soon" (即将过期). A candidate exactly 25 days old is not marked.
`show` supports only Claude Code JSONL. It keeps non-meta, non-subagent user string input (with system-reminder fragments removed) and non-subagent assistant text blocks, and outputs them in the order 【用户】 (user) and 【助手】 (assistant). Tool results, tool calls, thinking, attachments, and system injections are not output. The built-in redaction rules and the `blocklist.txt` next to the configuration directory mask matched fragments while keeping context. If the masked output exceeds the default 40000 characters, only the end is kept, labeled "truncated to the first N characters" (已截断前 N 字), and the number of unparseable or unrecognized records is reported at the end.
Candidate command exit codes: `0` success (including an empty list or skipped corrupted lines), `1` operation failure (candidate not found, session expired, or queue read/write failure), `2` usage or configuration error. `mark` only accepts `compiled` or `dropped`. Dropping changes only the queue. It does not write to the vault.

Compilation has three steps, and the user makes two decisions:

1. **List**: List the full backlog and candidates, summarize each item, and recommend compile, drop, or keep. Wait for the user to choose. Multiple lessons from the same session become separate list items.
2. **Batch preview**: Create a separate draft for each selected item and run preview on each one. Show the dispositions, file list, full diff, and fingerprints together. Wait for the user to confirm all or some of them.
3. **Write one at a time**: Apply only the confirmed items. Each item is its own transaction with its own `compile: <title>` commit. Stop at the first failure. Completed transactions are kept. A session is marked `compiled` only after all selected lessons from it are processed. After an earlier item changes HEAD, later items must be previewed again and the confirmed content checked. If the preview content changes, get user confirmation again.

```bash
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py compile preview /tmp-dir/compile-draft --json
# After explicit user confirmation, use the preview fingerprint:
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py compile apply /tmp-dir/compile-draft --confirm <fingerprint> --json
```

Drafts for backlog items do not create a new inbox. The wiki's `raw` references point to the existing backlog file. Drafts for candidate sessions create one new inbox excerpt, with key facts copied verbatim from the session. compile allows 0 or 1 new inbox. Two or more are rejected. The rest of the allowlist, codename replacement, redaction, full overlay checks, fingerprint, and atomic writes reuse save. Modifying existing inbox or raw files is not allowed. If there are 0 inbox files and no wiki pages are actually changed, it reports "nothing to write" (没有可写入的内容) and rejects the request. The title is taken from the wiki main page's title first. If no wiki pages changed, the inbox title or filename is used. The log operation name is `compile`.

preview and apply both support `--json`, with the same fields as save. Compile exit codes: `0` success, `1` validation, redaction, write, or commit failure, `2` usage or configuration error, `3` fingerprint mismatch. A commit failure creates `.kb-pending.json`. Recover with the `commit-pending` flow above. New writes are rejected while a commit is pending. compile does not register a SessionEnd hook, does not read Codex sessions, and does not archive ask answers automatically.

## Auto-queue candidates when a session ends

The hook is configured in `plugins/kb/hooks/hooks.json` and is **enabled** (2026-11-19). It is used only for Claude Code. Codex does not collect. SessionEnd fires for every end reason. Verified: `claude -p` fires on exit (reason=other), and entering `/clear` in an interactive session fires it too (reason=clear). Whether archiving or closing a session tab in the desktop app fires it has not been verified separately.

Collection records only the session ID, the transcript path, the working directory, and the end reason in the local candidate queue. It uses the queue's short hash, time, and processing status. **It does not record session content.** The script only reads the transcript to count messages. It does not excerpt content, call a model, access the network, write to the vault, or modify configuration. The next `/kb:compile` lets you choose which candidates to process.

The `session_capture` setting defaults to `true`. `capture_min_user_messages` defaults to `2`. `capture_ignore_dirs` defaults to an empty array. Only non-meta, non-subagent user messages are counted. For a string or text block, the `system-reminder`, `task-notification`, and `side-sessions-event` injection blocks are removed. If non-empty text remains, it counts as one message. Tool results, attachments, and assistant messages are not counted. A single message containing several text blocks counts as one. Reading stops once the count reaches the threshold. Sessions below the threshold are not queued. Each session is deduplicated. A session that is already compiled or dropped keeps its status.

Exclusion directories match on the normalized full path components, including the directory itself and all subdirectories. `/a/b` does not exclude `/a/bc`. The vault directory and the plugin source directory can be queued by default.

```bash
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py capture status
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py capture status --json
# Preview first; append --confirm to write after reviewing:
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py config set-capture --enabled false
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py config set-capture --enabled true --min-user-messages 3 --ignore-dir /project/company-project /project/automation-dir
# Clear the exclusion list:
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py config set-capture --enabled true --ignore-dir
```

`set-capture` supports `--json`. It previews the full configuration and writes only with `--confirm`. It preserves other existing fields. If no threshold or exclusion options are passed, the existing values are kept. The status command shows the switch, the thresholds, the exclusion directories, the number of `pending` items in the queue, the log location, and the last 5 log lines. It does not update queue status. If the configuration has a type error or is corrupted, the status query exits with `2`. The hook logs the problem and skips.

The hook always exits silently with `0`. The timeout is 5 seconds. Error reasons are appended to `~/.local/state/kb/capture.log`. If `KB_STATE_DIR` is set, the log is `capture.log` inside that directory. Each line contains the local ISO time, the reason, and the session ID when available. When the log exceeds 1 MB, the second half is kept as complete lines. If the log cannot be written, the hook still exits silently. Normal filtering and successful enqueueing do not write to the log.

## Codex execution result feedback

After its existing session candidate collection, the Claude Code SessionEnd hook also reads delegate's public result files and reply files. It saves results worth compiling as local snapshots and adds them to the candidate queue as `source: delegate`. This runs independently of `session_capture`, the session message threshold, and the exclusion directories. It does not read Codex's own session files and does not write to the vault automatically. At the next compile, you still choose whether to compile or drop each result.

Only results with `schema: 1` and `kind: run` are processed, and only if their status is `done`, `failed`, `timeout`, `unmarked`, `unreaped`, or `empty`. Statuses such as `review` and `needs-input` are skipped. For the same `chainRoot`, the run that finished last is selected and collected once. After a chain has been collected, later runs in it are not appended. If the actual reply is shorter than the byte threshold and all commands succeeded, it is skipped. A short reply that includes a failed command is still collected. Corrupted JSON, missing fields, unsupported schema, missing replies, and inaccessible directories are skipped. The reason is recorded in `capture.log` in the state directory.

The configuration reuses the JSON file specified by `KB_CONFIG` (default `~/.config/kb/config.json`). New fields can be maintained alongside existing ones:

```json
{
  "version": 1,
  "vault": "/absolute/path/vault",
  "delegate_capture": true,
  "delegate_min_answer_bytes": 200
}
```

`delegate_capture` defaults to `true`. Setting it to `false` disables both the hook and manual scanning. `delegate_min_answer_bytes` defaults to `200`. It accepts any non-negative integer. `0` means no filtering by short replies. Changing the threshold does not reprocess results that were already judged. `config set-capture` preserves the delegate fields that are already set.

```bash
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py candidates scan-delegate
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py candidates scan-delegate --json
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py candidates list
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py candidates show <candidate-id>
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py capture status --json
```

Scanning sorts by runId. It processes at most 20 new results per run and leaves the rest for next time. Both collected and skipped runIds are recorded in `delegate-scan.json` in the state directory, so they are not judged again later. A manual scan reports only counts, runIds, and reasons. It does not output replies. `capture status` shows the switch, the byte threshold, the time of the last scan, and the number processed. The hook does not create scan state when the directory is empty.

Snapshots are located at `${KB_STATE_DIR:-~/.local/state/kb}/delegate/<runId>.json`. They contain the runId, status, repository, read/write mode, start and end times, changed files, failed commands, and reply. Failed commands are truncated to 300 characters. Replies are truncated to 20000 characters. The original result file is not copied. `candidates list` shows the repository name, status, and time. `show` applies the existing masking rules and the local blocklist to the snapshot content. A session candidate without a `source` is read as `session`. Old queues need no migration.

**The delegate directory is always read-only.** By default, it reads `${TMPDIR:-/tmp}/delegate`. You can point to another directory with `KB_DELEGATE_DIR`. Scanning never writes, modifies, or deletes files in that directory. It writes only snapshots, the queue, scan state, and logs to the local state directory. Tests use temporary `KB_CONFIG`, `KB_STATE_DIR`, and `KB_DELEGATE_DIR` values to isolate real data.

## Query the vault

In any project, run `/kb:ask <question>`, or call the deterministic read-only search script directly:

```bash
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py ask search cache plugin --json
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py ask search dispatch cost --limit 5
```

Multiple terms match if any one of them matches. Matching is case-insensitive. Regex special characters are treated as literals. The scope is Markdown pages under `wiki/`. Frontmatter does not produce matches. index is used only to boost the matching page. Code blocks are searched too.
Each match is labeled `current`, `outdated`, or `disputed`. For pages with `status: superseded`, all matches are outdated, and the path of the superseding page is returned.
Sorting scores pages by the number of distinct matched terms. Title and index matches are boosted. Pages with only outdated matches rank after pages with current or disputed matches. Ties are broken by most recent update date first, then ascending path. By default, 10 pages are returned, with at most 20 match lines per page.

Exit codes: `0` matches found, `1` no matches (`--json` still returns valid JSON with an empty `pages`), `2` configuration or usage error. Normal JSON output is schema 1. It includes the absolute vault path, the search terms, the candidate pages, scores, sources, regions, and original line numbers. `truncated` indicates whether candidates were omitted because of the page limit.
Search reads only the configured vault. It writes no files and does not change Git state. Other plugins can probe contract `1.0` through [interface.json](plugins/kb/interface.json). The parameter templates, fields, exit codes, version rules, and silent probing method are described in the [interface contract](plugins/kb/references/interface.md).

## Lint and safe fixes

Run `/kb:lint`, or call the script directly. The report is printed to the terminal only and is not saved to disk:

```bash
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py lint
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py lint --json --stale-days 180
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py lint fix preview --json
# After explicit user confirmation, use the preview fingerprint:
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py lint fix apply --confirm <fingerprint> --json
```

The report includes all `kb check` problems. They are ordered as: broken navigation → content reliability → format → maintenance hints. Each group shows a count. A summary appears at the end. Maintenance hints include: orphan pages with no links from other wiki pages (links from index and self-links do not count, and project pages are excluded), `current` pages that are suspected stale because they are older than the `updated` threshold, and inbox backlog items not referenced by any wiki frontmatter `raw`.
The default stale threshold is 180 days. `--stale-days N` sets a positive integer. Exactly 180 days is not reported. Any file whose save-log entry text states a vault-relative path `inbox/…md` is excluded from the backlog. "No new content" saves should also record their paths this way.
Maintenance hints do not affect the check-level results of `kb check` or lint. Scale metrics are shown separately as the wiki page count and the index.md byte size. A hint is shown when these exceed 300 pages or 40960 bytes. ask does not yet record the number of files read, so the average shows "no data yet" (暂无数据).

Safe fixes generate only these three types of drafts:

- Wiki page not in index: add `- [title](wiki/<dir>/<file>.md) — （待补摘要） · updated` under the matching type's level-2 heading. (The text "（待补摘要）" is literal output, meaning "summary pending.")
- Index points to a page that does not exist: delete that index line.
- A Markdown link inside a wiki page points to a non-existent vault target, and there is exactly one same-named file under `wiki/`: change it to the correct relative path and keep the anchor. If there are multiple candidates, it is not fixed.

preview reuses save's shared write flow. It runs a full check on a temporary overlay copy that keeps complete Git history. It outputs the diff and the 16-character fingerprint. If there is nothing to fix, it exits successfully and reports "no fix needed" (无需修复). If the full check still reports problems, writing is refused until those problems are resolved.
After explicit user confirmation, apply regenerates the draft, verifies the fingerprint and all contracts, writes atomically if all pass, and commits the fixes together with an appended `## [今天] lint | 安全修复 N 处` log entry (today's lint log: N safe fixes). The commit message is `lint: 安全修复 N 处` (lint: N safe fixes). Nothing is pushed.
Fixes may modify only `index.md`, `log.md`, and existing pages under `wiki/`. They do not touch inbox or raw, and they are not subject to save's "exactly one inbox" rule. The vault must already have a HEAD and a clean working tree. A failed write is rolled back. If the commit fails, the files and staging state are kept and the reason is reported.

Exit codes: `lint` returns `0` when there are no check-level problems (hints are allowed), `1` when check-level problems exist, `2` for usage or configuration error. `lint fix` returns `0` on success (including "no fix needed"), `1` for validation, write, or commit failure, `2` for usage or configuration error, and `3` for fingerprint mismatch.
The `--json` report includes ordered `groups`, `hints`, `metrics`, the count of `fixable` items, and `summary`. `metrics.ask_average_reads.value` is `null` and includes a `reason`. The fix result also includes `findings`, `created`, and `modified`. preview includes `diff` and `fingerprint`. apply includes `commit`.

### Semantic lint (optional)

For a deeper check, you can extract candidate packs after the deterministic lint. A model then identifies four kinds of problems: suspected contradictions, suspected staleness, missing-page concepts, and suggestions to promote content to rules. The verbatim quotes in the report are checked afterward:

```bash
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py lint semantic-pack
python3 -B /absolute/path/kb-plugin/plugins/kb/scripts/kb.py lint semantic-verify /tmp-dir/findings.json --json
```

`semantic-pack` outputs JSON by default, so `--json` can be omitted. Tests can use `--today YYYY-MM-DD` to fix the current date. Otherwise it uses the local date. The pack includes metadata for each page, the number of days since creation and since update, related and in-body wiki page links, the current body with all annotation blocks removed, and the four kinds of fact hints. Each page body is limited to 4000 characters. The whole UTF-8 JSON pack must not exceed 60000 bytes. Pages with older `updated` dates are kept first. `truncated` and `truncated_pages` mark truncation. If metadata and candidates still do not fit, newer pages are omitted, and `omitted_page_count` records how many. Omitted pages are also listed in the truncation list. That list itself is limited to 15000 bytes. `truncated_page_count` always records the total number of truncated pages. Contradiction candidates are limited to 30 pairs. Hints are not proof that a problem exists.

Model-generated findings use this format. `category` is one of `contradiction`, `stale`, `missing-page`, or `promote`. Quotes must come from the current-conclusion sections of the listed wiki pages:

```json
{"version": 1, "findings": [
  {"category": "stale",
   "pages": ["wiki/tech/example.md"],
   "quotes": [{"page": "wiki/tech/example.md", "text": "verbatim quote from the page goes here"}],
   "reason": "reason why re-verification is needed",
   "action": "suggest re-verifying and updating the date",
   "verified_by": "optional: read-only local verification command and result"}
]}
```

`semantic-verify -` reads the same JSON from stdin. This is useful in a read-only sandbox where temporary files cannot be written. Verification rejects paths that escape the vault, are not wiki pages, or do not exist. Outdated conclusions inside annotation blocks cannot serve as evidence. Quotes reuse evidence's whitespace normalization and exact containment check. The JSON result is split into `accepted` and `rejected`, where each rejected entry includes the failure reason. All content goes through the existing masking rules and the local blocklist. Without `--json`, the accepted items are printed grouped by the four categories, and at the end, items are listed separately under "quote verification failed, removed" (引文核对失败，已剔除). Exit codes: `0` all passed, `1` some items were removed, `2` input format, configuration, or usage error.

Semantic lint only produces a report. It does not modify the vault, write to the log, check facts online, or execute promoted rules. The user decides whether to take the suggested actions separately.

## Uninstall

Claude Code:

```bash
claude plugin uninstall kb@kb-marketplace
claude plugin marketplace remove kb-marketplace
```

Codex:

```bash
codex plugin remove kb@kb-marketplace
codex plugin marketplace remove kb-marketplace
```

Open a new session after uninstalling. Host uninstall does not delete the vault. It also does not delete `~/.config/kb/config.json` (or the file specified by `KB_CONFIG`). If you no longer need it, you can delete the configuration file yourself. Keep the vault as needed.

## Development verification

Run this from the repository root:

```bash
kb_test_root=$(mktemp -d)
mkdir "$kb_test_root/delegate"
KB_CONFIG="$kb_test_root/config.json" KB_STATE_DIR="$kb_test_root/state" \
  KB_DELEGATE_DIR="$kb_test_root/delegate" python3 -m unittest discover -s tests -v
rm -rf "$kb_test_root"
python3 -B scripts/check-manifests.py
```

The full test run isolates real data with a temporary `KB_CONFIG`, a temporary `KB_STATE_DIR`, and an empty `KB_DELEGATE_DIR`. Each test overrides these with its own temporary directories as needed. The tests do not read or write the real configuration, state, delegate results, or vault, and they do not install the plugin.
The root-resolution tests use a fake `codex`. The manifest-failure tests modify only temporary copies.
The vault tests copy the valid sample and the three-part AC6 material sample into a temporary directory, and commit a baseline in a temporary git repository. They cover all 13 check codes, evidence regression, read-only checks, and init's no-overwrite behavior. The redaction tests assemble fake secrets at runtime. They cover rule counterexamples, aliases, hash allowlisting, masked output, and the 3 matches and 1 replacement in session excerpts. The SHA-256 of the vendored original files and licenses is also verified in the tests.
The save tests cover the path allowlist, redaction and codename replacement, full-history validation, fingerprint invalidation, write rollback, and commit failure. Separately, in a vault created by init in a temporary directory, they save a new pitfall page, a new decision page, and an outdated block that overturns an old conclusion, using three materials in sequence. Each check reports zero problems. They also verify the three save commits and that the inbox originals are immutable.
The ask tests cover regions and code blocks, whole-page superseded status, scoring and sorting, truncation, literal multi-term matching, the JSON contract and exit codes, and that files and Git state in both clean and dirty vaults remain unchanged. The interface check builds an ask skill in a temporary copy and covers missing contracts, format errors, versions, and skill references.

The lint tests cover hint boundaries, log exclusion, grouping and scale metrics, the acceptance of the four kinds of problems, the three types of safe fixes, ambiguous candidates, fingerprint invalidation, fixes and log committed together, and that files and Git state are unchanged before and after read-only runs. The refactor of the shared writer is protected by the existing save tests together with the lint tests.

The candidate and compile tests isolate configuration and the queue with temporary `KB_CONFIG` and `KB_STATE_DIR`. They cover deduplication, status, corrupted lines, the 25-day boundary, the session text allowlist, truncation after masking, and compile's 0, 1, and 2 inbox cases, immutable originals, fingerprints, write rollback, and pending-commit recovery. The end-to-end test generates two drafts from one backlog item and one candidate. It completes two compile commits, candidate marking, and a zero-problem contract check.

The session capture tests cover message filtering, thresholds, directory boundaries, disabling, deduplication, silent error handling and log rotation, configuration preview with preservation of other fields, read-only status queries, early stop when reading records of 5 MB, and the draft command running as-is along with manifest validation. They verify that the vault and configuration file are unchanged before and after capture.

## Committing changes

`main` is branch-protected. You cannot push directly, force-push, or delete it. All changes must be merged through a PR from a branch. CI on the PR runs the unified check entry `bash scripts/validate.sh` on macOS with Python 3.9 (the system Python on macOS) and with 3.14. The checks are manifest checks, local path checks, and the full unit test suite. `--quick` runs only the first two. A `plugin validate` job checks the plugin with `claude plugin validate --strict`. The only required check on `main` is the summary job `CI required`, which passes only when all of these jobs pass. CI uses only the fictional fixtures in the repository and never reads a real vault.

Risk tiers are defined in `.github/autopr/risk-tiers.yml`. The redaction module, the check scripts, and the unified check entry are T4. The maintainer decides in the conversation whether to merge them: the session asks "can this be merged?", and after the maintainer replies "merge" it runs `gh pr merge --auto --merge`, so GitHub merges once `CI required` passes. Merging T4 changes without asking is never enabled.
