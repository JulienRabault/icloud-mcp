"""Construction des criteres IMAP SEARCH et regroupement en fils de discussion."""

from __future__ import annotations

import imaplib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from .imap_client import ImapError, check, fetch_headers, fetch_summaries, select, sort_key
from .models import EmailSummary

_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)
_REPLY_PREFIX = re.compile(r"^\s*(?:(?:re|ré|fw|fwd|tr)\s*(?:\[\d+\])?\s*:\s*)+", re.IGNORECASE)

Term = str | bytes


@dataclass(frozen=True, slots=True)
class SearchCriteria:
    """Criteres de recherche, tous optionnels et combines en ET."""

    query: str | None = None
    query_scope: str = "text"  # "text" = entetes + corps, "body" = corps seul
    sender: str | None = None
    recipient: str | None = None
    subject: str | None = None
    since: date | None = None
    before: date | None = None
    unseen_only: bool = False
    flagged_only: bool = False
    larger_than_kb: int | None = None


def _imap_date(value: date) -> str:
    return f"{value.day:02d}-{_MONTHS[value.month - 1]}-{value.year}"


def _quote(value: str) -> Term:
    """Encadre une valeur de guillemets ; encode en UTF-8 brut si accentuee."""
    cleaned = value.replace('"', "").replace("\\", "")
    if cleaned.isascii():
        return '"' + cleaned + '"'
    return b'"' + cleaned.encode("utf-8") + b'"'


def _text_terms(criteria: SearchCriteria) -> tuple[tuple[str, str], ...]:
    keyword = "BODY" if criteria.query_scope == "body" else "TEXT"
    pairs = (
        (keyword, criteria.query),
        ("FROM", criteria.sender),
        ("TO", criteria.recipient),
        ("SUBJECT", criteria.subject),
    )
    return tuple((key, value) for key, value in pairs if value)


def build_terms(criteria: SearchCriteria, *, ascii_only: bool = False) -> tuple[list[Term], bool]:
    """Construit la liste de termes IMAP. Retourne (termes, contient_non_ascii)."""
    terms: list[Term] = []
    if criteria.unseen_only:
        terms.append("UNSEEN")
    if criteria.flagged_only:
        terms.append("FLAGGED")
    if criteria.since is not None:
        terms += ["SINCE", _imap_date(criteria.since)]
    if criteria.before is not None:
        terms += ["BEFORE", _imap_date(criteria.before)]
    if criteria.larger_than_kb:
        terms += ["LARGER", str(criteria.larger_than_kb * 1024)]

    has_non_ascii = False
    for keyword, value in _text_terms(criteria):
        if not value.isascii():
            has_non_ascii = True
            if ascii_only:
                continue
        terms += [keyword, _quote(value)]

    if not terms:
        terms = ["ALL"]
    if has_non_ascii and not ascii_only:
        terms = ["CHARSET", "UTF-8", *terms]
    return (terms, has_non_ascii)


def _parse_uids(data: Sequence) -> tuple[str, ...]:
    """UIDs d'une reponse SEARCH, tries par ordre croissant.

    RFC 3501 ne garantit pas l'ordre de SEARCH, et iCloud renvoie effectivement
    des listes desordonnees : sans ce tri, prendre la fin de la liste ne donne
    pas les messages les plus recents.
    """
    raw = data[0] if data and isinstance(data[0], bytes) else b""
    return tuple(sorted(raw.decode("ascii", "replace").split(), key=int))


def search_uids(conn: imaplib.IMAP4_SSL, criteria: SearchCriteria) -> tuple[tuple[str, ...], bool]:
    """Lance SEARCH cote serveur. Retourne (uids, repli_client_necessaire).

    iCloud accepte SEARCH CHARSET UTF-8, donc les criteres accentues partent au
    serveur. Si un serveur refuse, on relance sans les termes accentues et on
    signale que le filtrage devra se terminer cote client.
    """
    terms, has_non_ascii = build_terms(criteria)
    try:
        data = check(conn.uid("SEARCH", None, *terms), "SEARCH")
        return (_parse_uids(data), False)
    except (ImapError, imaplib.IMAP4.error):
        if not has_non_ascii:
            raise
    fallback_terms, _ = build_terms(criteria, ascii_only=True)
    data = check(conn.uid("SEARCH", None, *fallback_terms), "SEARCH (repli ASCII)")
    return (_parse_uids(data), True)


def matches(summary: EmailSummary, criteria: SearchCriteria) -> bool:
    """Filtre de repli, applique aux entetes uniquement."""
    haystacks = {
        "query": " ".join((summary.subject, summary.sender, *summary.to)).casefold(),
        "sender": summary.sender.casefold(),
        "recipient": " ".join(summary.to).casefold(),
        "subject": summary.subject.casefold(),
    }
    checks = (
        ("query", criteria.query),
        ("sender", criteria.sender),
        ("recipient", criteria.recipient),
        ("subject", criteria.subject),
    )
    for field, value in checks:
        if value and not value.isascii() and value.casefold() not in haystacks[field]:
            return False
    return True


def search(
    conn: imaplib.IMAP4_SSL,
    folder: str,
    criteria: SearchCriteria,
    limit: int,
    scan_limit: int,
) -> tuple[tuple[EmailSummary, ...], int, bool]:
    """Retourne (messages, total_correspondant, filtrage_client_applique)."""
    select(conn, folder)
    uids, needs_client_filter = search_uids(conn, criteria)
    if not uids:
        return ((), 0, needs_client_filter)

    if not needs_client_filter:
        found = fetch_summaries(conn, folder, uids[-limit:])
        return (tuple(sorted(found, key=sort_key, reverse=True)), len(uids), False)

    candidates = fetch_summaries(conn, folder, uids[-scan_limit:])
    kept = tuple(item for item in candidates if matches(item, criteria))
    ordered = tuple(sorted(kept, key=sort_key, reverse=True))
    return (ordered[:limit], len(kept), True)


def normalize_subject(subject: str) -> str:
    """Retire les prefixes Re:/Fwd:/TR: pour rapprocher les messages d'un fil."""
    previous = None
    current = subject.strip()
    while previous != current:
        previous = current
        current = _REPLY_PREFIX.sub("", current).strip()
    return current


def thread(
    conn: imaplib.IMAP4_SSL, folder: str, uid: str, limit: int
) -> tuple[tuple[EmailSummary, ...], str, str]:
    """Retourne (messages, message_id_racine, methode) pour la conversation de `uid`."""
    select(conn, folder)
    headers = fetch_headers(conn, uid)
    references = headers["references"].split()
    root = references[0] if references else (headers["message_id"] or headers["in_reply_to"])

    if root:
        terms: list[Term] = [
            "OR",
            "HEADER", "Message-ID", _quote(root),
            "HEADER", "References", _quote(root),
        ]
        data = check(conn.uid("SEARCH", None, *terms), "SEARCH (fil)")
        uids = _parse_uids(data)
        if uids:
            found = fetch_summaries(conn, folder, uids[-limit:])
            return (tuple(sorted(found, key=sort_key)), root, "references")

    base = normalize_subject(headers["subject"])
    if not base:
        found = fetch_summaries(conn, folder, [uid])
        return (found, root, "seul")
    data = check(conn.uid("SEARCH", None, *build_terms(SearchCriteria(subject=base))[0]), "SEARCH")
    uids = _parse_uids(data)
    found = fetch_summaries(conn, folder, uids[-limit:])
    return (tuple(sorted(found, key=sort_key)), root, "subject")
