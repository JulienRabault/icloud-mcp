# icloud-mcp

MCP server for iCloud Mail. Read, search and send email from Claude, Codex or
any MCP client.

Most mail MCP servers target Gmail. This one speaks IMAP directly to
`imap.mail.me.com` — stdlib `imaplib` and `email`, no third-party dependency for
networking or MIME parsing.

## Tools

| Tool | What it does |
|---|---|
| `list_folders` | List IMAP folders, optionally with message and unread counts |
| `folder_status` | Counts for one folder without listing its messages |
| `search_emails` | Search by text, sender, recipient, subject, date, flags, size |
| `read_email` | Full message: decoded text body, optional HTML, attachment metadata |
| `get_thread` | Rebuild a conversation from any message in it |
| `send_email` | Send a message over SMTP |
| `move_emails` | Move messages between folders (dry run by default) |

**Read tools never modify anything.** They use `SELECT ... readonly` and
`BODY.PEEK`, so nothing is marked as read, moved or deleted.

**Write tools are explicit.** `send_email` really sends — there is no draft step.
`move_emails` simulates by default and only acts when `dry_run=false`. Neither
should be called without the user approving the exact content or the exact list
of messages first.

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
  search.py       SEARCH criteria and threading
  smtp_client.py  MIME building, SMTP send, best-effort copy to Sent
  move.py         COPY + EXPUNGE with the anti-purge guard
  server.py       the seven FastMCP tools
  cli.py          terminal checks
```

## Tests

```bash
uv run pytest -q
```

32 offline tests — no network, no credentials required.

## License

MIT
