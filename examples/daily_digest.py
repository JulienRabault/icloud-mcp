"""Resume de ce qui est arrive aujourd'hui, groupe par expediteur.

    uv run python examples/daily_digest.py
    uv run python examples/daily_digest.py --days 3 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, timedelta

from icloud_mcp import imap_client
from icloud_mcp.config import ConfigError, load_settings
from icloud_mcp.imap_client import ImapError
from icloud_mcp.search import SearchCriteria, search_everywhere


def _domain(sender: str) -> str:
    local, _, rest = sender.rpartition("@")
    return rest.rstrip(">").strip() or sender


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--unread-only", action="store_true")
    parser.add_argument("--json", action="store_true", help="Sortie machine")
    args = parser.parse_args(argv)

    criteria = SearchCriteria(
        since=date.today() - timedelta(days=args.days),
        unseen_only=args.unread_only,
    )
    try:
        with imap_client.connect(load_settings()) as conn:
            messages, totals, _ = search_everywhere(
                conn, criteria, limit=100, scan_limit=500
            )
    except (ConfigError, ImapError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "days": args.days,
                    "total": len(messages),
                    "by_folder": totals,
                    "messages": [item.model_dump(mode="json") for item in messages],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if not messages:
        print(f"Rien de nouveau sur {args.days} jour(s).")
        return 0

    grouped: dict[str, list] = defaultdict(list)
    for item in messages:
        grouped[_domain(item.sender)].append(item)

    print(f"{len(messages)} message(s) sur {args.days} jour(s)\n")
    for domain, items in sorted(grouped.items(), key=lambda pair: -len(pair[1])):
        print(f"{domain} ({len(items)})")
        for item in items[:5]:
            mark = " " if item.seen else "*"
            print(f"  [{mark}] {item.subject[:70]}")
        if len(items) > 5:
            print(f"      … et {len(items) - 5} autre(s)")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
