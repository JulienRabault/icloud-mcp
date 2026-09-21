"""Signale les messages recents d'un expediteur. Code de sortie 1 si aucun.

Pense pour un cron : le code de sortie permet de chainer une notification.

    uv run python examples/watch_sender.py billing@example.com
    uv run python examples/watch_sender.py example.com --days 3 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta

from icloud_mcp import imap_client
from icloud_mcp.config import ConfigError, load_settings
from icloud_mcp.imap_client import ImapError
from icloud_mcp.search import SearchCriteria, search_everywhere


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sender", help="Adresse ou domaine a surveiller")
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    criteria = SearchCriteria(
        sender=args.sender,
        since=date.today() - timedelta(days=args.days),
    )
    try:
        with imap_client.connect(load_settings()) as conn:
            messages, totals, _ = search_everywhere(
                conn, criteria, limit=50, scan_limit=500
            )
    except (ConfigError, ImapError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                [item.model_dump(mode="json") for item in messages],
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0 if messages else 1

    if not messages:
        print(f"Rien de {args.sender} depuis {args.days} jour(s).")
        return 1

    print(f"{len(messages)} message(s) de {args.sender} :\n")
    for item in messages:
        when = item.date.strftime("%Y-%m-%d %H:%M") if item.date else "?"
        print(f"  {when}  [{item.folder}] {item.subject[:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
