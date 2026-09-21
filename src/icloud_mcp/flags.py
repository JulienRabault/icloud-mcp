"""Modification des drapeaux IMAP : lu, marque, repondu.

Operations reversibles, contrairement a move_emails et send_email : reposer un
drapeau annule l'effet. Elles restent neanmoins des ecritures.
"""

from __future__ import annotations

import imaplib
from collections.abc import Sequence
from dataclasses import dataclass

from .imap_client import ImapError, check, quote_folder

FLAGS = {
    "seen": r"\Seen",
    "flagged": r"\Flagged",
    "answered": r"\Answered",
}


@dataclass(frozen=True, slots=True)
class FlagChange:
    folder: str
    uids: tuple[str, ...]
    flag: str
    added: bool


def _select_writable(conn: imaplib.IMAP4_SSL, folder: str) -> None:
    status, data = conn.select(quote_folder(folder), readonly=False)
    if status != "OK":
        raise ImapError(f"Impossible d'ouvrir {folder!r} en ecriture : {data!r}")


def set_flag(
    conn: imaplib.IMAP4_SSL,
    folder: str,
    uids: Sequence[str],
    flag: str,
    *,
    add: bool,
) -> FlagChange:
    """Ajoute ou retire un drapeau sur les messages designes."""
    if not uids:
        raise ValueError("Aucun UID fourni.")
    key = flag.strip().lower()
    if key not in FLAGS:
        raise ValueError(
            f"Drapeau inconnu : {flag!r}. Valeurs acceptees : {', '.join(sorted(FLAGS))}."
        )

    _select_writable(conn, folder)
    targets = ",".join(sorted(uids, key=int))
    operation = "+FLAGS" if add else "-FLAGS"
    check(conn.uid("STORE", targets, operation, f"({FLAGS[key]})"), "STORE")
    return FlagChange(folder, tuple(uids), key, add)
