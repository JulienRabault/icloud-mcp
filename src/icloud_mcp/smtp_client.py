"""Envoi de messages via SMTP iCloud, avec copie dans un dossier IMAP.

Contrairement au reste du serveur (deliberement en lecture seule), ce module
ecrit reellement : il envoie un email pour de vrai. Chaque appel doit rester
un acte explicite, jamais une action de fond.
"""

from __future__ import annotations

import imaplib
import mimetypes
import smtplib
import ssl
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from email.message import EmailMessage as StdEmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Iterator

from .config import Settings
from .imap_client import ImapError, connect as imap_connect, quote_folder


class SmtpError(RuntimeError):
    """Erreur lors de l'envoi, deja traduite pour l'utilisateur."""


@dataclass(frozen=True, slots=True)
class SendResult:
    message_id: str
    to: tuple[str, ...]
    cc: tuple[str, ...]
    saved_to_sent: bool


MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024


def _attach(message: StdEmailMessage, path: Path) -> None:
    """Joint un fichier local au message."""
    if not path.is_file():
        raise ValueError(f"Piece jointe introuvable : {path}")
    payload = path.read_bytes()
    if len(payload) > MAX_ATTACHMENT_BYTES:
        raise ValueError(
            f"{path.name} fait {len(payload) // 1024 // 1024} Mo, au-dela de la "
            f"limite de {MAX_ATTACHMENT_BYTES // 1024 // 1024} Mo."
        )
    guessed, _ = mimetypes.guess_type(path.name)
    maintype, _, subtype = (guessed or "application/octet-stream").partition("/")
    message.add_attachment(
        payload, maintype=maintype, subtype=subtype, filename=path.name
    )


def build_message(
    settings: Settings,
    *,
    to: Sequence[str],
    subject: str,
    body_text: str,
    cc: Sequence[str] = (),
    in_reply_to: str | None = None,
    references: str | None = None,
    attachments: Sequence[Path] = (),
) -> StdEmailMessage:
    message = StdEmailMessage()
    message["From"] = formataddr((settings.sender_name, settings.email))
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain="icloud.com")
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if references:
        message["References"] = references
    elif in_reply_to:
        message["References"] = in_reply_to
    message.set_content(body_text)
    for path in attachments:
        _attach(message, Path(path))
    return message


@contextmanager
def _smtp_connect(settings: Settings) -> Iterator[smtplib.SMTP]:
    try:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
    except OSError as error:
        raise SmtpError(
            f"Connexion a {settings.smtp_host}:{settings.smtp_port} impossible : {error}"
        ) from error
    try:
        client.ehlo()
        client.starttls(context=ssl.create_default_context())
        client.ehlo()
        client.login(settings.email, settings.app_password)
    except smtplib.SMTPException as error:
        client.close()
        raise SmtpError(
            "Authentification SMTP refusee par iCloud. Verifie le mot de passe "
            f"pour application. Detail serveur : {error}"
        ) from error
    try:
        yield client
    finally:
        try:
            client.quit()
        except (smtplib.SMTPException, OSError):
            pass


def _append_to_sent(settings: Settings, raw: bytes) -> bool:
    """Copie le message envoye dans 'Sent Messages'. Best-effort : un echec ici
    ne doit jamais faire croire que l'envoi lui-meme a echoue."""
    try:
        with imap_connect(settings) as conn:
            status, _ = conn.append(
                quote_folder("Sent Messages"), r"(\Seen)", None, raw
            )
            return status == "OK"
    except (ImapError, imaplib.IMAP4.error, OSError):
        return False


def send_email(
    settings: Settings,
    *,
    to: Sequence[str],
    subject: str,
    body_text: str,
    cc: Sequence[str] = (),
    in_reply_to: str | None = None,
    references: str | None = None,
    attachments: Sequence[Path] = (),
) -> SendResult:
    """Envoie un email via SMTP iCloud et tente d'en garder une copie dans Sent."""
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
    recipients = [*to, *cc]
    raw = message.as_bytes()

    with _smtp_connect(settings) as client:
        try:
            client.sendmail(settings.email, recipients, raw)
        except smtplib.SMTPException as error:
            raise SmtpError(f"Envoi refuse par le serveur : {error}") from error

    saved = _append_to_sent(settings, raw)
    return SendResult(
        message_id=message["Message-ID"],
        to=tuple(to),
        cc=tuple(cc),
        saved_to_sent=saved,
    )


_build_message = build_message
