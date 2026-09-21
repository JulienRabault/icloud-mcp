"""Primitives IMAP en lecture seule : connexion, LIST, STATUS, SELECT, FETCH."""

from __future__ import annotations

import imaplib
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from . import mime, utf7
from .config import Settings
from .models import Attachment, EmailMessage, EmailSummary, Folder, FolderStatus

_LIST_LINE = re.compile(rb'\((?P<flags>[^)]*)\) "(?P<delim>[^"]*)" (?P<name>.+)')
_UID = re.compile(rb"UID (?P<uid>\d+)")
_FLAGS = re.compile(rb"FLAGS \((?P<flags>[^)]*)\)")
_SIZE = re.compile(rb"RFC822\.SIZE (?P<size>\d+)")
_STATUS_ITEM = re.compile(rb"(?P<key>[A-Z]+) (?P<value>\d+)")

_SUMMARY_ITEMS = (
    "(UID FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS "
    "(FROM TO SUBJECT DATE MESSAGE-ID REFERENCES IN-REPLY-TO)])"
)


class ImapError(RuntimeError):
    """Erreur cote serveur IMAP, deja traduite pour l'utilisateur."""


@contextmanager
def connect(settings: Settings) -> Iterator[imaplib.IMAP4_SSL]:
    """Ouvre une session IMAP authentifiee, fermee proprement a la sortie."""
    try:
        conn = imaplib.IMAP4_SSL(settings.host, settings.port)
    except OSError as error:
        raise ImapError(
            f"Connexion a {settings.host}:{settings.port} impossible : {error}"
        ) from error
    try:
        conn.login(settings.email, settings.app_password)
    except imaplib.IMAP4.error as error:
        conn.logout()
        raise ImapError(
            "Authentification refusee par iCloud. Verifie ICLOUD_EMAIL et utilise un "
            "mot de passe pour application (account.apple.com > Securite), pas le mot "
            f"de passe principal. Detail serveur : {error}"
        ) from error
    try:
        yield conn
    finally:
        for close in (conn.close, conn.logout):
            try:
                close()
            except (imaplib.IMAP4.error, OSError):
                pass


def check(result: tuple[str, Sequence], action: str) -> Sequence:
    status, data = result
    if status != "OK":
        raise ImapError(f"{action} a echoue : {data!r}")
    return data


def quote_folder(folder: str) -> str:
    return '"' + utf7.encode(folder) + '"'


def list_folders(conn: imaplib.IMAP4_SSL) -> tuple[Folder, ...]:
    data = check(conn.list(), "LIST")
    folders: list[Folder] = []
    for line in data:
        if not isinstance(line, bytes):
            continue
        match = _LIST_LINE.search(line)
        if match is None:
            continue
        raw_name = match.group("name").decode("ascii", "replace").strip().strip('"')
        folders.append(
            Folder(
                name=utf7.decode(raw_name),
                flags=tuple(match.group("flags").decode("ascii", "replace").split()),
                delimiter=match.group("delim").decode("ascii", "replace") or "/",
            )
        )
    return tuple(folders)


def folder_status(conn: imaplib.IMAP4_SSL, folder: str) -> FolderStatus:
    """Compteurs d'un dossier via STATUS, sans le selectionner."""
    data = check(
        conn.status(quote_folder(folder), "(MESSAGES UNSEEN RECENT UIDNEXT)"), "STATUS"
    )
    raw = data[0] if data and isinstance(data[0], bytes) else b""
    values = {
        match.group("key").decode("ascii"): int(match.group("value"))
        for match in _STATUS_ITEM.finditer(raw)
    }
    return FolderStatus(
        folder=folder,
        messages=values.get("MESSAGES", 0),
        unseen=values.get("UNSEEN", 0),
        recent=values.get("RECENT", 0),
        uid_next=values.get("UIDNEXT"),
    )


def select(conn: imaplib.IMAP4_SSL, folder: str) -> None:
    """Selectionne un dossier en lecture seule (aucun message marque comme lu)."""
    status, data = conn.select(quote_folder(folder), readonly=True)
    if status != "OK":
        raise ImapError(f"Dossier introuvable : {folder!r} ({data!r})")


def fetch_parts(
    conn: imaplib.IMAP4_SSL, uids: Sequence[str], items: str
) -> list[tuple[bytes, bytes]]:
    if not uids:
        return []
    data = check(conn.uid("FETCH", ",".join(uids), items), "FETCH")
    return [
        (part[0], part[1])
        for part in data
        if isinstance(part, tuple) and len(part) >= 2 and part[1] is not None
    ]


def sort_key(summary: EmailSummary) -> tuple[int, str]:
    """Trie par date quand elle existe, sinon par UID numerique."""
    timestamp = int(summary.date.timestamp()) if summary.date is not None else 0
    return (timestamp, summary.uid.zfill(12))


def _flag_text(prefix: bytes) -> str:
    match = _FLAGS.search(prefix)
    return match.group("flags").decode("ascii", "replace") if match else ""


def fetch_summaries(
    conn: imaplib.IMAP4_SSL, folder: str, uids: Sequence[str]
) -> tuple[EmailSummary, ...]:
    """Recupere les entetes seules, sans telecharger les corps."""
    summaries: list[EmailSummary] = []
    for prefix, payload in fetch_parts(conn, uids, _SUMMARY_ITEMS):
        uid_match = _UID.search(prefix)
        if uid_match is None:
            continue
        size = _SIZE.search(prefix)
        flags = _flag_text(prefix)
        message = mime.parse_bytes(payload)
        summaries.append(
            EmailSummary(
                uid=uid_match.group("uid").decode("ascii"),
                folder=folder,
                subject=mime.header(message, "Subject"),
                sender=" ".join(mime.address_list(message, "From")),
                to=mime.address_list(message, "To"),
                date=mime.sent_at(message),
                seen="\\Seen" in flags,
                flagged="\\Flagged" in flags,
                answered="\\Answered" in flags,
                size_bytes=int(size.group("size")) if size else 0,
                message_id=mime.header(message, "Message-ID"),
            )
        )
    return tuple(summaries)


def fetch_headers(conn: imaplib.IMAP4_SSL, uid: str) -> dict[str, str]:
    """Entetes brutes d'un message, pour reconstituer un fil de discussion."""
    parts = fetch_parts(conn, [uid], _SUMMARY_ITEMS)
    if not parts:
        raise ImapError(f"Message UID {uid} introuvable.")
    message = mime.parse_bytes(parts[0][1])
    return {
        "message_id": mime.header(message, "Message-ID"),
        "references": mime.header(message, "References"),
        "in_reply_to": mime.header(message, "In-Reply-To"),
        "subject": mime.header(message, "Subject"),
    }


def _limited_attachments(
    found: tuple[Attachment, ...], max_items: int
) -> tuple[Attachment, ...]:
    return found[:max_items]


def fetch_message(
    conn: imaplib.IMAP4_SSL,
    folder: str,
    uid: str,
    *,
    max_body_chars: int,
    include_html: bool,
) -> EmailMessage:
    """Telecharge et decode un message entier."""
    parts = fetch_parts(conn, [uid], "(UID FLAGS RFC822.SIZE BODY.PEEK[])")
    if not parts:
        raise ImapError(f"Message UID {uid} introuvable dans {folder!r}.")
    prefix, payload = parts[0]
    size = _SIZE.search(prefix)
    flags = _flag_text(prefix)
    message = mime.parse_bytes(payload)
    text, html = mime.bodies(message)
    return EmailMessage(
        uid=uid,
        folder=folder,
        subject=mime.header(message, "Subject"),
        sender=" ".join(mime.address_list(message, "From")),
        to=mime.address_list(message, "To"),
        cc=mime.address_list(message, "Cc"),
        reply_to=" ".join(mime.address_list(message, "Reply-To")),
        in_reply_to=mime.header(message, "In-Reply-To"),
        message_id=mime.header(message, "Message-ID"),
        date=mime.sent_at(message),
        seen="\\Seen" in flags,
        flagged="\\Flagged" in flags,
        answered="\\Answered" in flags,
        size_bytes=int(size.group("size")) if size else len(payload),
        body_text=text[:max_body_chars],
        body_html=html if include_html else None,
        attachments=_limited_attachments(mime.attachments(message), 50),
        body_truncated=len(text) > max_body_chars,
    )
