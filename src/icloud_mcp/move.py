"""Deplacement de messages entre dossiers IMAP.

iCloud n'annonce ni MOVE ni UIDPLUS : il faut donc COPY, puis marquer \\Deleted,
puis EXPUNGE. Or EXPUNGE purge TOUS les messages marques \\Deleted du dossier,
y compris ceux qu'un autre client aurait marques. Ce module refuse donc
d'operer si le dossier contient deja des messages marques supprimes qui ne
font pas partie du lot demande.
"""

from __future__ import annotations

import imaplib
from collections.abc import Sequence
from dataclasses import dataclass

from .imap_client import ImapError, check, fetch_summaries, quote_folder, select
from .models import EmailSummary


class UnsafeExpungeError(ImapError):
    """Le dossier contient des messages \\Deleted etrangers au lot demande."""


@dataclass(frozen=True, slots=True)
class MoveOutcome:
    source: str
    destination: str
    dry_run: bool
    moved: tuple[EmailSummary, ...]
    missing_uids: tuple[str, ...]


def _select_writable(conn: imaplib.IMAP4_SSL, folder: str) -> None:
    """Selectionne un dossier en ecriture (contrairement a imap_client.select)."""
    status, data = conn.select(quote_folder(folder), readonly=False)
    if status != "OK":
        raise ImapError(f"Impossible d'ouvrir {folder!r} en ecriture : {data!r}")


def _already_deleted(conn: imaplib.IMAP4_SSL) -> frozenset[str]:
    """UIDs deja marques \\Deleted dans le dossier actuellement selectionne."""
    data = check(conn.uid("SEARCH", None, "DELETED"), "SEARCH DELETED")
    raw = data[0] if data and isinstance(data[0], bytes) else b""
    return frozenset(raw.decode("ascii", "replace").split())


def move_emails(
    conn: imaplib.IMAP4_SSL,
    uids: Sequence[str],
    source: str,
    destination: str,
    *,
    dry_run: bool = True,
) -> MoveOutcome:
    """Deplace des messages de `source` vers `destination`.

    En dry_run (defaut), rien n'est modifie : les messages concernes sont
    seulement lus et renvoyes pour verification.
    """
    if not uids:
        raise ValueError("Aucun UID fourni.")
    if source == destination:
        raise ValueError("Dossier source et destination identiques.")

    select(conn, source)  # lecture seule pour l'inventaire
    found = fetch_summaries(conn, source, uids)
    found_uids = {item.uid for item in found}
    missing = tuple(uid for uid in uids if uid not in found_uids)

    if dry_run:
        return MoveOutcome(source, destination, True, found, missing)

    if not found:
        raise ImapError(f"Aucun des UIDs demandes n'existe dans {source!r}.")

    _select_writable(conn, source)

    strangers = _already_deleted(conn) - found_uids
    if strangers:
        raise UnsafeExpungeError(
            f"{len(strangers)} message(s) deja marque(s) supprime(s) dans "
            f"{source!r} ne font pas partie du lot. Un EXPUNGE les detruirait "
            "definitivement. Vide la corbeille du dossier avant de relancer."
        )

    targets = ",".join(sorted(found_uids, key=int))
    check(conn.uid("COPY", targets, quote_folder(destination)), "COPY")
    check(conn.uid("STORE", targets, "+FLAGS", r"(\Deleted)"), "STORE")
    check(conn.expunge(), "EXPUNGE")

    return MoveOutcome(source, destination, False, found, missing)
