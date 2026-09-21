"""Extraction et sauvegarde des pieces jointes.

Le contenu binaire n'est jamais renvoye au modele : il est ecrit sur disque et
seul le chemin est retourne. Un PDF de 3 Mo n'a rien a faire dans un contexte
de conversation.
"""

from __future__ import annotations

import imaplib
import re
import unicodedata
from dataclasses import dataclass
from email.message import EmailMessage as StdEmailMessage
from pathlib import Path

from . import mime
from .imap_client import ImapError, fetch_parts, select

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
MAX_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SavedAttachment:
    filename: str
    content_type: str
    size_bytes: int
    path: str


def safe_filename(raw: str, fallback: str) -> str:
    """Nettoie un nom de fichier venu d'un email : c'est une donnee hostile."""
    name = unicodedata.normalize("NFKD", raw or "")
    name = name.encode("ascii", "ignore").decode("ascii")
    name = _UNSAFE.sub("_", name).strip("._")
    # Path.name neutralise toute tentative de remontee de repertoire.
    name = Path(name).name
    return name or fallback


def _attachment_parts(message: StdEmailMessage) -> list[StdEmailMessage]:
    return [
        part
        for part in message.walk()
        if not part.is_multipart() and part.get_content_disposition() == "attachment"
    ]


def save_attachments(
    conn: imaplib.IMAP4_SSL,
    folder: str,
    uid: str,
    out_dir: Path,
    *,
    index: int | None = None,
) -> tuple[SavedAttachment, ...]:
    """Ecrit les pieces jointes du message dans `out_dir`.

    `index` (base 1) ne sauve qu'une piece jointe precise ; None les sauve toutes.
    """
    select(conn, folder)
    parts = fetch_parts(conn, [uid], "(UID BODY.PEEK[])")
    if not parts:
        raise ImapError(f"Message UID {uid} introuvable dans {folder!r}.")

    message = mime.parse_bytes(parts[0][1])
    found = _attachment_parts(message)
    if not found:
        return ()
    if index is not None:
        if not 1 <= index <= len(found):
            raise ValueError(
                f"index {index} hors bornes : le message a {len(found)} piece(s) jointe(s)."
            )
        found = [found[index - 1]]

    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[SavedAttachment] = []
    for position, part in enumerate(found, start=1):
        payload = part.get_payload(decode=True) or b""
        if len(payload) > MAX_BYTES:
            raise ValueError(
                f"Piece jointe de {len(payload) // 1024 // 1024} Mo, au-dela de la "
                f"limite de {MAX_BYTES // 1024 // 1024} Mo."
            )
        name = safe_filename(
            mime.decode_value(part.get_filename()), f"piece_jointe_{position}"
        )
        target = out_dir / f"{uid}_{name}"
        target.write_bytes(payload)
        saved.append(
            SavedAttachment(
                filename=name,
                content_type=part.get_content_type(),
                size_bytes=len(payload),
                path=str(target),
            )
        )
    return tuple(saved)
