"""CLI de verification : `python -m icloud_mcp.cli <commande>`.

Sert a tester la connexion sans passer par Claude, et a lire un message
directement depuis le terminal.
"""

from __future__ import annotations

import argparse
import sys

from . import imap_client
from .config import ConfigError, load_settings
from .imap_client import ImapError
from .search import SearchCriteria, search as search_messages, thread as thread_messages
from .models import EmailMessage, EmailSummary


def _format_summary(summary: EmailSummary, index: int) -> str:
    when = summary.date.astimezone().strftime("%Y-%m-%d %H:%M") if summary.date else "date inconnue"
    state = " " if summary.seen else "*"
    return f"{index:>2}. [{state}] {when}  uid={summary.uid}\n     De    : {summary.sender}\n     Sujet : {summary.subject or '(sans sujet)'}"


def _format_message(message: EmailMessage) -> str:
    when = message.date.astimezone().strftime("%Y-%m-%d %H:%M") if message.date else "date inconnue"
    lines = [
        f"De      : {message.sender}",
        f"A       : {', '.join(message.to) or '-'}",
        f"Date    : {when}",
        f"Sujet   : {message.subject or '(sans sujet)'}",
        f"Dossier : {message.folder}  uid={message.uid}",
    ]
    if message.attachments:
        joined = ", ".join(f"{a.filename} ({a.content_type}, {a.size_bytes} o)" for a in message.attachments)
        lines.append(f"PJ      : {joined}")
    lines.append("")
    lines.append(message.body_text or "(corps vide)")
    if message.body_truncated:
        lines.append("\n[corps tronque]")
    return "\n".join(lines)


def _cmd_check(args: argparse.Namespace) -> int:
    settings = load_settings()
    with imap_client.connect(settings) as conn:
        folders = imap_client.list_folders(conn)
    print(f"Connexion OK pour {settings.email} ({len(folders)} dossiers).")
    return 0


def _cmd_folders(args: argparse.Namespace) -> int:
    with imap_client.connect(load_settings()) as conn:
        for folder in imap_client.list_folders(conn):
            print(f"{folder.name}  {' '.join(folder.flags)}")
    return 0


def _cmd_latest(args: argparse.Namespace) -> int:
    with imap_client.connect(load_settings()) as conn:
        messages, _total, _client_side = search_messages(
            conn, args.folder, SearchCriteria(), limit=args.count, scan_limit=500
        )
        if not messages:
            print(f"Aucun message dans {args.folder}.")
            return 0
        if args.full:
            imap_client.select(conn, args.folder)
            full = imap_client.fetch_message(
                conn, args.folder, messages[0].uid, max_body_chars=4000, include_html=False
            )
            print(_format_message(full))
            return 0
    for index, summary in enumerate(messages, start=1):
        print(_format_summary(summary, index))
    return 0


def _cmd_read(args: argparse.Namespace) -> int:
    with imap_client.connect(load_settings()) as conn:
        imap_client.select(conn, args.folder)
        message = imap_client.fetch_message(
            conn, args.folder, args.uid, max_body_chars=args.max_chars, include_html=False
        )
    print(_format_message(message))
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    criteria = SearchCriteria(
        query=args.query,
        sender=args.sender,
        subject=args.subject,
        unseen_only=args.unseen,
    )
    with imap_client.connect(load_settings()) as conn:
        messages, total, client_side = search_messages(
            conn, args.folder, criteria, limit=args.count, scan_limit=500
        )
    suffix = " (filtrage client, entetes seules)" if client_side else ""
    print(f"{total} correspondance(s){suffix}\n")
    for index, summary in enumerate(messages, start=1):
        print(_format_summary(summary, index))
    return 0


def _cmd_thread(args: argparse.Namespace) -> int:
    with imap_client.connect(load_settings()) as conn:
        messages, root, method = thread_messages(conn, args.folder, args.uid, limit=args.count)
    print(f"Fil regroupe par {method} (racine {root or '-'}), {len(messages)} message(s)\n")
    for index, summary in enumerate(messages, start=1):
        print(_format_summary(summary, index))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="icloud-mcp-cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Teste la connexion IMAP").set_defaults(func=_cmd_check)
    sub.add_parser("folders", help="Liste les dossiers").set_defaults(func=_cmd_folders)

    latest = sub.add_parser("latest", help="Affiche les derniers messages")
    latest.add_argument("-n", "--count", type=int, default=5)
    latest.add_argument("-f", "--folder", default="INBOX")
    latest.add_argument("--full", action="store_true", help="Affiche le corps du plus recent")
    latest.set_defaults(func=_cmd_latest)

    read = sub.add_parser("read", help="Affiche un message par UID")
    read.add_argument("uid")
    read.add_argument("-f", "--folder", default="INBOX")
    read.add_argument("--max-chars", type=int, default=20_000)
    read.set_defaults(func=_cmd_read)

    found = sub.add_parser("search", help="Recherche des messages")
    found.add_argument("query", nargs="?", default=None)
    found.add_argument("-f", "--folder", default="INBOX")
    found.add_argument("--sender")
    found.add_argument("--subject")
    found.add_argument("--unseen", action="store_true")
    found.add_argument("-n", "--count", type=int, default=10)
    found.set_defaults(func=_cmd_search)

    conversation = sub.add_parser("thread", help="Reconstitue le fil d'un message")
    conversation.add_argument("uid")
    conversation.add_argument("-f", "--folder", default="INBOX")
    conversation.add_argument("-n", "--count", type=int, default=30)
    conversation.set_defaults(func=_cmd_thread)
    return parser


def _force_utf8_output() -> None:
    """La console Windows est en cp1252 par defaut et casse les accents."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    args = _build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ConfigError, ImapError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
