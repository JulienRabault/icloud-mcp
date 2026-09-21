"""Envoi de messages via SMTP iCloud, avec copie dans un dossier IMAP.

Contrairement au reste du serveur (deliberement en lecture seule), ce module
ecrit reellement : il envoie un email pour de vrai. Chaque appel doit rester
un acte explicite, jamais une action de fond.
"""

from __future__ import annotations

import imaplib
import smtplib
import ssl
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass
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


def _build_message(
    settings: Settings,
    *,
    to: Sequence[str],
    subject: str,
    body_text: str,
    cc: Sequence[str] = (),
    in_reply_to: str | None = None,
    references: str | None = None,
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
) -> SendResult:
    """Envoie un email via SMTP iCloud et tente d'en garder une copie dans Sent."""
    if not to:
        raise ValueError("'to' ne peut pas etre vide.")
    message = _build_message(
        settings,
        to=to,
        subject=subject,
        body_text=body_text,
        cc=cc,
        in_reply_to=in_reply_to,
        references=references,
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
