"""Decodage MIME : entetes, corps texte/HTML et pieces jointes."""

from __future__ import annotations

from datetime import datetime
from email import policy
from email.header import decode_header, make_header
from email.message import EmailMessage as StdEmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime

from .models import Attachment

_PARSER = BytesParser(policy=policy.default)


def parse_bytes(raw: bytes) -> StdEmailMessage:
    """Parse un message brut RFC 822."""
    return _PARSER.parsebytes(raw)


def decode_value(value: str | None) -> str:
    """Decode un entete encode (RFC 2047), tolerant aux encodages casses."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except (UnicodeDecodeError, LookupError, ValueError):
        return value.strip()


def header(message: StdEmailMessage, name: str) -> str:
    return decode_value(message.get(name))


def address_list(message: StdEmailMessage, name: str) -> tuple[str, ...]:
    """Liste d'adresses d'un entete, sous forme 'Nom <adresse>'."""
    raw_values = message.get_all(name, [])
    pairs = getaddresses([decode_value(str(value)) for value in raw_values])
    return tuple(
        f"{display} <{address}>".strip() if display else address
        for display, address in pairs
        if display or address
    )


def sent_at(message: StdEmailMessage) -> datetime | None:
    raw = message.get("Date")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(str(raw))
    except (TypeError, ValueError):
        return None


def _part_text(part: StdEmailMessage) -> str:
    """Decode une partie en texte, en retombant sur latin-1 si le charset ment."""
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("latin-1", errors="replace")


def bodies(message: StdEmailMessage) -> tuple[str, str | None]:
    """Retourne (texte, html) en privilegiant la partie non-attachee."""
    text_part = message.get_body(preferencelist=("plain",))
    html_part = message.get_body(preferencelist=("html",))
    text = _part_text(text_part) if text_part is not None else ""
    html = _part_text(html_part) if html_part is not None else None
    if not text and html:
        text = _html_to_text(html)
    return text.strip(), html


def _html_to_text(html: str) -> str:
    """Repli grossier quand le message n'a pas de partie texte."""
    import re

    without_blocks = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    with_breaks = re.sub(r"(?i)<(br|/p|/div|/tr)[^>]*>", "\n", without_blocks)
    stripped = re.sub(r"<[^>]+>", " ", with_breaks)
    import html as html_module

    return re.sub(r"[ \t]{2,}", " ", html_module.unescape(stripped)).strip()


def attachments(message: StdEmailMessage) -> tuple[Attachment, ...]:
    """Metadonnees des pieces jointes, contenu exclu."""
    found: list[Attachment] = []
    for part in message.walk():
        if part.is_multipart() or part.get_content_disposition() != "attachment":
            continue
        payload = part.get_payload(decode=True) or b""
        found.append(
            Attachment(
                filename=decode_value(part.get_filename()) or "(sans nom)",
                content_type=part.get_content_type(),
                size_bytes=len(payload),
            )
        )
    return tuple(found)
