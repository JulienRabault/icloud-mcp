# icloud-mcp

MCP server for iCloud Mail. Read, search and send email from Claude, Codex or
any MCP client.

Most mail MCP servers target Gmail. This one speaks IMAP directly to
`imap.mail.me.com` — stdlib `imaplib` and `email`, no third-party dependency for
networking or MIME parsing.

## Tools

**Read** — none of these modify anything (`SELECT ... readonly`, `BODY.PEEK`), so
nothing gets marked as read, moved or deleted.

| Tool | What it does |
|---|---|
| `list_folders` | List IMAP folders, optionally with message and unread counts |
| `folder_status` | Counts for one folder without listing its messages |
| `search_emails` | Search one folder by text, sender, recipient, subject, date, flags, size |
| `search_all_folders` | Same search across every folder at once |
| `read_email` | Full message: decoded text body, optional HTML, attachment metadata |
| `get_thread` | Rebuild a conversation, optionally with each message body |
| `save_attachments` | Download attachments to disk and return their paths |

**Write** — explicit by design.

| Tool | What it does |
|---|---|
| `save_draft` | Put a message in Drafts. Nothing is sent |
| `set_flag` | Mark read/unread, flagged, answered. Reversible |
| `move_emails` | Move between folders. Simulates unless `dry_run=false` |
| `send_email` | Actually sends. No draft step, no undo |

There is no delete tool, by design.

`search_all_folders` is the one to reach for when asking *did someone reply?* —
replies are routinely filed into a topic folder by a mail rule, and an
`INBOX`-only search silently misses them.

Attachment content never goes through the model: `save_attachments` writes files
to disk and returns paths. Filenames coming from email are sanitised — they're
hostile input, not trusted paths.

## Resources

| URI | Content |
|---|---|
| `icloud://folders` | Every folder with its message and unread counts |
| `icloud://unread` | Unread messages in the inbox |

## Prompts

| Prompt | Purpose |
|---|---|
| `triage_inbox` | Sort recent mail into action required / info / waiting / ignorable |
| `draft_reply` | Read a message and its thread, then draft a reply into Drafts |
| `follow_up` | Reconstruct an exchange with one contact and say who owes whom a reply |

## Install

```bash
git clone https://github.com/JulienRabault/icloud-mcp.git
cd icloud-mcp
uv sync
```

## Configure

iCloud rejects your main password over IMAP. You need an **app-specific
password**: [account.apple.com](https://account.apple.com/account/manage) →
Sign-In and Security → App-Specific Passwords.

Copy `.env.example` to `.env`:

```
ICLOUD_EMAIL=you@icloud.com
ICLOUD_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
ICLOUD_DISPLAY_NAME=Your Name
```

`.env` is gitignored. Environment variables take precedence over the file if you
prefer keeping nothing on disk.

Check it works:

```bash
uv run python -m icloud_mcp.cli check
uv run python -m icloud_mcp.cli latest -n 5
```

## Connect a client

Replace `/path/to/icloud-mcp` with your clone directory.

**Claude Code**

```bash
claude mcp add icloud-mail --scope user -- uv run --directory /path/to/icloud-mcp python -m icloud_mcp
```

**Codex** — in `~/.codex/config.toml`:

```toml
[mcp_servers.icloud-mail]
command = "uv"
args = ["run", "--directory", "/path/to/icloud-mcp", "python", "-m", "icloud_mcp"]
```

**Claude Desktop** — in `claude_desktop_config.json`:

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

On Windows, use the absolute path to `uv.exe` — desktop clients don't always
inherit your shell `PATH`.

MCP servers are only loaded at client startup. **Restart after any config
change**, including after adding a tool to the server.

## iCloud quirks handled here

Things that cost time to discover, in case you're writing your own client:

- **`SEARCH` returns UIDs out of order.** RFC 3501 doesn't guarantee ordering and
  iCloud genuinely returns unsorted lists. Taking the tail of the response gives
  you the wrong messages — sort numerically first.
- **No `MOVE`, no `UIDPLUS`.** Moving means `COPY` + `\Deleted` + `EXPUNGE`, and
  `EXPUNGE` purges *every* `\Deleted` message in the folder. `move_emails`
  refuses to run if the folder holds deleted messages outside the requested
  batch, which would otherwise be destroyed.
- **`SEARCH CHARSET UTF-8` works.** Accented queries can go server-side across
  the whole mailbox. A client-side fallback exists for servers that refuse, and
  the response flags it via `filtered_client_side`.
- **Folder names use modified UTF-7** (RFC 3501). Implemented in `utf7.py`, so
  folders like « Éléments envoyés » work.
- **Charsets lie.** Bodies fall back to latin-1 when the declared charset fails
  to decode, and to stripped HTML when a message has no `text/plain` part.

Search results fetch headers only (`BODY.PEEK[HEADER.FIELDS …]`), so listing 20
results doesn't download 20 full messages. Attachment content is never returned —
only name, type and size.

## Bundled skill

`skills/mailbox-search/` is a Claude Code skill that forces a sweep of every IMAP
folder before concluding a message doesn't exist. Replies are often filed into a
topic folder by a mail rule, and an `INBOX`-only search misses them.

```bash
cp -r skills/mailbox-search ~/.claude/skills/
```

## Layout

```
src/icloud_mcp/
  config.py       env / .env loading, password never in repr
  utf7.py         modified UTF-7 for folder names
  models.py       frozen Pydantic models
  mime.py         header, body and attachment decoding
  imap_client.py  connection, LIST, STATUS, SELECT, FETCH
  search.py       SEARCH criteria, threading, multi-folder search
  smtp_client.py  MIME building, SMTP send, best-effort copy to Sent
  attachments.py  attachment extraction and filename sanitising
  drafts.py       APPEND to the Drafts folder
  flags.py        \Seen, \Flagged, \Answered
  move.py         COPY + EXPUNGE with the anti-purge guard
  server.py       tools, resources and prompts
  cli.py          terminal checks
```

## Tests

```bash
uv run pytest -q
```

44 offline tests — no network, no credentials required.

## License

MIT
