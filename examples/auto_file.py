"""Classe les messages dans des dossiers selon des regles. Simule par defaut.

Les regles vivent dans examples/rules.json : une liste d'objets avec un
expediteur ou un sujet, et un dossier de destination.

    uv run python examples/auto_file.py            # simulation
    uv run python examples/auto_file.py --apply    # deplace vraiment
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from icloud_mcp import imap_client
from icloud_mcp.config import ConfigError, load_settings
from icloud_mcp.imap_client import ImapError
from icloud_mcp.move import move_emails
from icloud_mcp.search import SearchCriteria, search

RULES_PATH = Path(__file__).parent / "rules.json"


def _load_rules() -> list[dict]:
    if not RULES_PATH.is_file():
        print(f"Aucun fichier de regles : {RULES_PATH}", file=sys.stderr)
        print("Voir examples/rules.json.example pour le format.", file=sys.stderr)
        return []
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Deplacer pour de vrai")
    parser.add_argument("--source", default="INBOX")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(argv)

    rules = _load_rules()
    if not rules:
        return 1

    try:
        with imap_client.connect(load_settings()) as conn:
            for rule in rules:
                destination = rule["folder"]
                criteria = SearchCriteria(
                    sender=rule.get("sender"),
                    subject=rule.get("subject"),
                )
                messages, total, _ = search(
                    conn, args.source, criteria, limit=args.limit, scan_limit=500
                )
                if not messages:
                    continue

                label = rule.get("sender") or rule.get("subject")
                verb = "Deplace" if args.apply else "Deplacerait"
                print(f"{verb} {len(messages)} message(s) « {label} » -> {destination}")
                for item in messages[:3]:
                    print(f"    {item.sender[:40]} | {item.subject[:45]}")
                if len(messages) > 3:
                    print(f"    … et {len(messages) - 3} autre(s)")

                if args.apply:
                    move_emails(
                        conn,
                        [item.uid for item in messages],
                        args.source,
                        destination,
                        dry_run=False,
                    )
    except (ConfigError, ImapError, KeyError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 1

    if not args.apply:
        print("\nSimulation. Relancer avec --apply pour deplacer reellement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
