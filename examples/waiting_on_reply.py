"""Fils ou vous avez ecrit en dernier et ou personne n'a repondu.

Compare vos envois aux messages recus : tout sujet present dans Sent Messages
sans reponse plus recente est signale.

    uv run python examples/waiting_on_reply.py
    uv run python examples/waiting_on_reply.py --days 30 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone

from icloud_mcp import imap_client
from icloud_mcp.config import ConfigError, load_settings
from icloud_mcp.imap_client import ImapError
from icloud_mcp.search import SearchCriteria, normalize_subject, search, search_everywhere


def _age_days(moment: datetime | None) -> int:
    if moment is None:
        return 0
    now = datetime.now(timezone.utc)
    return (now - moment.astimezone(timezone.utc)).days


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30, help="Fenetre d'analyse")
    parser.add_argument("--quiet-for", type=int, default=3, help="Silence minimal, en jours")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    since = date.today() - timedelta(days=args.days)
    try:
        with imap_client.connect(load_settings()) as conn:
            sent, _, _ = search(
                conn, "Sent Messages", SearchCriteria(since=since), limit=100, scan_limit=500
            )
            received, _, _ = search_everywhere(
                conn,
                SearchCriteria(since=since),
                limit=100,
                scan_limit=500,
                folders=None,
            )
    except (ConfigError, ImapError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 1

    # Date de la derniere reponse recue, par sujet normalise.
    replies: dict[str, datetime] = {}
    for item in received:
        if item.folder == "Sent Messages" or item.date is None:
            continue
        key = normalize_subject(item.subject).casefold()
        if key and (key not in replies or item.date > replies[key]):
            replies[key] = item.date

    pending = []
    seen_keys: set[str] = set()
    for item in sorted(sent, key=lambda msg: msg.date or datetime.min, reverse=True):
        key = normalize_subject(item.subject).casefold()
        if not key or key in seen_keys or item.date is None:
            continue
        seen_keys.add(key)
        answered_at = replies.get(key)
        if answered_at is not None and answered_at > item.date:
            continue
        age = _age_days(item.date)
        if age >= args.quiet_for:
            pending.append((age, item))

    if args.json:
        print(
            json.dumps(
                [
                    {"days_silent": age, **item.model_dump(mode="json")}
                    for age, item in pending
                ],
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if not pending:
        print("Aucun fil en attente de reponse.")
        return 0

    print(f"{len(pending)} fil(s) sans reponse :\n")
    for age, item in sorted(pending, key=lambda pair: pair[0], reverse=True):
        print(f"  {age:3} jours — {', '.join(item.to)[:45]}")
        print(f"              {item.subject[:66]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
