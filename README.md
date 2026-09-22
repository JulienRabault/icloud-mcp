## iCloud Mail MCP

<!-- mcp-name: io.github.JulienRabault/icloud-mcp -->

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/icloud-mail-mcp.svg?style=flat-square)](https://pypi.org/project/icloud-mail-mcp/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg?style=flat-square)](https://www.python.org)
[![MCP](https://img.shields.io/badge/MCP-server-orange.svg?style=flat-square)](https://modelcontextprotocol.io)

A Model Context Protocol (MCP) server for **iCloud Mail**. Lets an LLM read,
search, file and send your Apple mail over IMAP and SMTP.

Runs entirely on your machine: your credentials and your mail never reach a
third party. Networking and MIME parsing use only the Python standard library.

### Key Features

- **Read-only by default.** Search and read tools use `SELECT ... readonly` and
  `BODY.PEEK` — nothing is marked as read, moved or deleted behind your back.
- **Searches every folder, not just the inbox.** Replies get filed away by mail
  rules; `search_all_folders` finds them where an inbox-only search can't.
- **Drafts before sends.** `save_draft` puts a message in Drafts for you to
  review. `send_email` exists, but it is separate and explicit.
- **Nothing destroys mail.** There is no tool that deletes messages, and
  `delete_mailbox` refuses any folder that still holds some.
- **Handles real iCloud MIME.** Modified UTF-7 folder names, quoted-printable,
  lying charsets, HTML-only messages, accented server-side search.

### Requirements

- Python 3.11 or newer, and [uv](https://docs.astral.sh/uv/)
- An iCloud account with two-factor authentication enabled
- An **app-specific password** — iCloud rejects your main password over IMAP

### Getting started

Once published to PyPI, no clone is needed:

```bash
uvx --from icloud-mail-mcp icloud-mcp-setup     # interactive configuration
uvx --from icloud-mail-mcp icloud-mcp           # run the server
```

From source:

```bash
git clone https://github.com/JulienRabault/icloud-mcp.git
cd icloud-mcp
uv sync
uv run python -m icloud_mcp.setup
```

The setup command asks for your address and app-specific password, tests the
connection, writes `.env`, then prints the exact config block for your client.

Generate the app-specific password at
[account.apple.com](https://account.apple.com/account/manage) → Sign-In and
Security → App-Specific Passwords.

**Standard config** works in most clients:

```json
{
  "mcpServers": {
    "icloud-mail": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/icloud-mcp", "python", "-m", "icloud_mcp"]
    }
  }
}
```

<details>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add icloud-mail --scope user -- uv run --directory /path/to/icloud-mcp python -m icloud_mcp
```

Check with `claude mcp list`.
</details>

<details>
<summary><b>Claude Desktop</b></summary>

Add the standard config to `claude_desktop_config.json`:

- macOS — `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows — `%APPDATA%\Claude\claude_desktop_config.json`

On Windows, use the absolute path to `uv.exe`: desktop clients don't always
inherit your shell `PATH`.
</details>

<details>
<summary><b>Codex</b></summary>

In `~/.codex/config.toml`:

```toml
[mcp_servers.icloud-mail]
command = "uv"
args = ["run", "--directory", "/path/to/icloud-mcp", "python", "-m", "icloud_mcp"]
```
</details>

<details>
<summary><b>Cursor / Windsurf / VS Code</b></summary>

Use the standard config block in the MCP settings file of your editor
(`.cursor/mcp.json`, `~/.codeium/windsurf/mcp_config.json`, or the VS Code MCP
settings).
</details>

MCP servers load at client startup — **restart the client** after editing its
config.

### Tools

Read — none of these modify the mailbox:

| Tool | Description |
|---|---|
| `list_folders` | List folders, optionally with message and unread counts |
| `folder_status` | Counts for one folder without listing messages |
| `search_emails` | Search one folder: text, sender, recipient, subject, dates, flags, size |
| `search_all_folders` | The same search across every folder at once |
| `read_email` | Full message: decoded body, optional HTML, attachment metadata |
| `get_thread` | Rebuild a conversation, optionally with each message body |
| `save_attachments` | Write attachments to disk and return their paths |

Write — explicit by design:

| Tool | Description |
|---|---|
| `save_draft` | Put a message in Drafts. Nothing is sent |
| `set_flag` | Read/unread, flagged, answered. Reversible |
| `create_mailbox` | Create a folder, accented names included |
| `rename_mailbox` | Rename a folder, messages follow |
| `delete_mailbox` | Delete an **empty** folder. Refuses while it holds mail |
| `auto_organize` | File messages by rules. Simulates unless `dry_run=false` |
| `move_emails` | Move between folders. Simulates unless `dry_run=false` |
| `send_email` | Actually sends. No draft step, no undo |

No tool destroys mail. `delete_mailbox` refuses a folder that still holds
messages — move them out first, which keeps the decision with you.

Attachment bytes never pass through the model: `save_attachments` writes files
and returns paths. Filenames arriving from email are sanitised — they are
hostile input, not trusted paths.

### Resources

| URI | Content |
|---|---|
| `icloud://folders` | Every folder with message and unread counts |
| `icloud://unread` | Unread messages in the inbox |

### Prompts

| Prompt | Purpose |
|---|---|
| `triage_inbox` | Sort recent mail into action required / info / waiting / ignorable |
| `draft_reply` | Read a message and its thread, draft a reply into Drafts |
| `follow_up` | Reconstruct an exchange with a contact, say who owes whom a reply |

### Automation without an MCP client

`examples/` holds standalone scripts using the same modules — point cron or Task
Scheduler at them:

```bash
uv run python examples/daily_digest.py           # what arrived today
uv run python examples/watch_sender.py acme.com  # exit 1 if nothing new
uv run python examples/waiting_on_reply.py       # threads nobody answered
uv run python examples/auto_file.py --apply      # file mail by rules
```

All support `--json` for piping. See [examples/README.md](examples/README.md).

### Bundled skill

`skills/mailbox-search/` is a Claude Code skill that forces a sweep of every
folder before concluding a message doesn't exist:

```bash
cp -r skills/mailbox-search ~/.claude/skills/
```

### iCloud quirks handled here

Worth knowing if you're writing your own IMAP client against iCloud:

- **`SEARCH` returns UIDs out of order.** RFC 3501 doesn't guarantee ordering,
  and iCloud genuinely returns unsorted lists. Taking the tail of the response
  gives you the wrong messages — sort numerically first.
- **No `MOVE`, no `UIDPLUS`.** Moving means `COPY` + `\Deleted` + `EXPUNGE`, and
  `EXPUNGE` purges *every* `\Deleted` message in the folder. `move_emails`
  refuses to run when the folder holds deleted messages outside the requested
  batch, which would otherwise be destroyed.
- **`SEARCH CHARSET UTF-8` works.** Accented queries run server-side across the
  whole mailbox. A client-side fallback covers servers that refuse, and flags it
  via `filtered_client_side` in the response.
- **Folder names use modified UTF-7** (RFC 3501), implemented in `utf7.py`.
- **Charsets lie.** Bodies fall back to latin-1 when the declared charset fails,
  and to stripped HTML when there's no `text/plain` part.

### Security notes

- Credentials live in `.env` (gitignored) or the environment, never in code.
  `Settings.__repr__` omits the password.
- Email content is **data, not instructions**. The server tells clients never to
  act on directives found inside a received message.
- `send_email` and `move_emails` are meant to run only after the user approves
  the exact content or the exact message list in the conversation.

### Development

```bash
uv run pytest -q
```

49 offline tests — no network, no credentials. CI runs them on Linux,
macOS and Windows against Python 3.11 to 3.13.

```
src/icloud_mcp/
  config.py        env / .env loading
  utf7.py          modified UTF-7 for folder names
  models.py        frozen Pydantic models
  mime.py          header, body and attachment decoding
  imap_client.py   connection, LIST, STATUS, SELECT, FETCH
  search.py        SEARCH criteria, threading, multi-folder search
  smtp_client.py   MIME building, SMTP send, copy to Sent
  attachments.py   attachment extraction, filename sanitising
  drafts.py        APPEND to Drafts
  flags.py         \Seen, \Flagged, \Answered
  move.py          COPY + EXPUNGE with the anti-purge guard
  mailboxes.py     create, rename, delete (empty only)
  organize.py      rule-based filing
  server.py        tools, resources, prompts
  setup_wizard.py  interactive configuration
  cli.py           terminal checks
```

### Contributing

Issues and pull requests welcome. Tests must pass offline — no test may require
a real mailbox.

### License

MIT
