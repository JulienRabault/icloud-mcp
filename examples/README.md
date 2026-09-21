# Automation recipes

These use the same modules the MCP server uses, so they run without any MCP
client. Point a cron job or Task Scheduler at them.

All of them read credentials from `.env` or the environment — nothing to pass on
the command line.

| Script | What it does |
|---|---|
| `daily_digest.py` | One-screen summary of what arrived today, grouped by sender |
| `watch_sender.py` | Alert when a specific contact writes, exit code 1 if nothing |
| `waiting_on_reply.py` | Threads where you wrote last and nobody answered |
| `auto_file.py` | Move messages matching rules into folders, dry run by default |

## Run one

```bash
uv run python examples/daily_digest.py
uv run python examples/watch_sender.py newsletter@example.com
uv run python examples/waiting_on_reply.py --days 7
uv run python examples/auto_file.py --apply
```

## Schedule it

**macOS / Linux** — `crontab -e`:

```cron
0 8 * * * cd /path/to/icloud-mcp && uv run python examples/daily_digest.py >> digest.log 2>&1
```

**Windows** — Task Scheduler, or:

```powershell
schtasks /create /tn "Mail digest" /tr "uv run --directory C:\path\to\icloud-mcp python examples\daily_digest.py" /sc daily /st 08:00
```

## Write your own

Every script follows the same three lines:

```python
from icloud_mcp import imap_client
from icloud_mcp.config import load_settings
from icloud_mcp.search import SearchCriteria, search_everywhere

with imap_client.connect(load_settings()) as conn:
    messages, totals, _ = search_everywhere(conn, SearchCriteria(unseen_only=True), 20, 500)
```

`search_everywhere` covers every folder — use it rather than `search`, which only
looks at one. Read tools never modify the mailbox; `move_emails` and `set_flag`
do, and take an explicit flag before acting.
