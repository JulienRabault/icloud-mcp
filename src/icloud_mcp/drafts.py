"""Enregistrement de brouillons dans le dossier Drafts via IMAP APPEND.

Alternative sure a send_email : le message est prepare et visible dans le
client mail, mais rien ne part tant que l'utilisateur n'appuie pas sur envoyer.
"""

from __future__ import annotations

import imaplib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .imap_client import ImapError, check, quote_folder
from .smtp_client import build_message

DRAFTS_CANDIDATES = ("Drafts", "Brouillons", "INBOX.Drafts")


@dataclass(frozen=True, slots=True)
class SavedDraft:
    folder: str
    message_id: str
    to: tuple[str, ...]
    subject: str


def _find_drafts_folder(conn: imaplib.IMAP4_SSL) -> str:
    """Repere le dossier des brouillons : son nom depend de la langue du compte."""
    from .imap_client import list_folders

    existing = {folder.name for folder in list_folders(conn)}
    for candidate in DRAFTS_CANDIDATES:
        if candidate in existing:
            return candidate
    for folder in list_folders(conn):
        if "\\Drafts" in folder.flags:
            return folder.name
    raise ImapError(
        "Dossier de brouillons introuvable. Noms cherches : "
        + ", ".join(DRAFTS_CANDIDATES)
    )


def save_draft(
    settings: Settings,
    conn: imaplib.IMAP4_SSL,
    *,
    to: Sequence[str],
    subject: str,
    body_text: str,
    cc: Sequence[str] = (),
    in_reply_to: str | None = None,
    references: str | None = None,
    attachments: Sequence[Path] = (),
    folder: str | None = None,
) -> SavedDraft:
    """Depose un brouillon sans rien envoyer."""
    if not to:
        raise ValueError("'to' ne peut pas etre vide.")

    message = build_message(
        settings,
        to=to,
        subject=subject,
        body_text=body_text,
        cc=cc,
        in_reply_to=in_reply_to,
        references=references,
        attachments=attachments,
    )
    target = folder or _find_drafts_folder(conn)
    check(
        conn.append(quote_folder(target), r"(\Draft)", None, message.as_bytes()),
        "APPEND",
    )
    return SavedDraft(
        folder=target,
        message_id=message["Message-ID"],
        to=tuple(to),
        subject=subject,
    )
