"""Creation, renommage et suppression de dossiers IMAP.

La suppression refuse un dossier non vide : le principe du serveur est qu'aucun
outil ne detruit de courrier. Vider le dossier d'abord est un acte separe et
volontaire de l'utilisateur.
"""

from __future__ import annotations

import imaplib
from dataclasses import dataclass

from .imap_client import ImapError, check, folder_status, list_folders, quote_folder


@dataclass(frozen=True, slots=True)
class MailboxChange:
    action: str
    folder: str
    new_name: str | None = None


def _exists(conn: imaplib.IMAP4_SSL, name: str) -> bool:
    return any(folder.name == name for folder in list_folders(conn))


def create_mailbox(conn: imaplib.IMAP4_SSL, name: str) -> MailboxChange:
    """Cree un dossier. Sans effet s'il existe deja."""
    if not name.strip():
        raise ValueError("Le nom du dossier ne peut pas etre vide.")
    if _exists(conn, name):
        return MailboxChange("existe_deja", name)
    check(conn.create(quote_folder(name)), "CREATE")
    return MailboxChange("cree", name)


def rename_mailbox(conn: imaplib.IMAP4_SSL, name: str, new_name: str) -> MailboxChange:
    """Renomme un dossier. Les messages suivent."""
    if not new_name.strip():
        raise ValueError("Le nouveau nom ne peut pas etre vide.")
    if not _exists(conn, name):
        raise ImapError(f"Dossier introuvable : {name!r}")
    if _exists(conn, new_name):
        raise ImapError(f"Un dossier nomme {new_name!r} existe deja.")
    check(conn.rename(quote_folder(name), quote_folder(new_name)), "RENAME")
    return MailboxChange("renomme", name, new_name)


def delete_mailbox(conn: imaplib.IMAP4_SSL, name: str) -> MailboxChange:
    """Supprime un dossier VIDE.

    Refuse tant qu'il contient des messages : ce serveur ne detruit pas de
    courrier. Deplacer ou archiver le contenu d'abord.
    """
    if not _exists(conn, name):
        raise ImapError(f"Dossier introuvable : {name!r}")

    status = folder_status(conn, name)
    if status.messages:
        raise ImapError(
            f"{name!r} contient {status.messages} message(s). Suppression refusee : "
            "deplacez-les d'abord avec move_emails. Ce serveur ne supprime "
            "jamais de courrier."
        )
    check(conn.delete(quote_folder(name)), "DELETE")
    return MailboxChange("supprime", name)
