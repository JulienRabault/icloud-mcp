"""Tests hors-ligne : encodage des dossiers, decodage MIME, cablage des outils."""

from __future__ import annotations

import pytest

from icloud_mcp import mime, utf7
from icloud_mcp.config import Settings
from icloud_mcp.search import SearchCriteria, _imap_date, build_terms, normalize_subject
from icloud_mcp.models import EmailSummary
from icloud_mcp.smtp_client import _build_message
from datetime import date


@pytest.mark.parametrize(
    "name",
    ["INBOX", "Sent Messages", "Éléments envoyés", "Dossier & co", "Notes/2024", "Ré√©"],
)
def test_utf7_roundtrip(name: str) -> None:
    assert utf7.decode(utf7.encode(name)) == name


def test_utf7_decode_known_imap_name() -> None:
    assert utf7.decode("&AMk-l&AOk-ments envoy&AOk-s") == "Éléments envoyés"


QUOTED_PRINTABLE = b"""From: =?UTF-8?Q?Test_User?= <exp=?UTF-8?Q?=C3=A9?=@example.com>
To: user@example.com
Subject: =?UTF-8?B?RMOpasOgIHZ1ID8=?=
Date: Mon, 07 Sep 2026 09:15:00 +0200
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="SEP"

--SEP
Content-Type: text/plain; charset="utf-8"
Content-Transfer-Encoding: quoted-printable

Bonjour, voici un accent : =C3=A9t=C3=A9.
--SEP
Content-Type: application/pdf; name="facture.pdf"
Content-Disposition: attachment; filename="facture.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQK
--SEP--
"""


def test_quoted_printable_body_is_decoded() -> None:
    message = mime.parse_bytes(QUOTED_PRINTABLE)
    text, html = mime.bodies(message)
    assert "été" in text
    assert html is None


def test_encoded_subject_and_attachment_metadata() -> None:
    message = mime.parse_bytes(QUOTED_PRINTABLE)
    assert mime.header(message, "Subject") == "Déjà vu ?"
    found = mime.attachments(message)
    assert len(found) == 1
    assert found[0].filename == "facture.pdf"
    assert found[0].content_type == "application/pdf"
    assert found[0].size_bytes > 0


def test_html_only_message_falls_back_to_text() -> None:
    raw = (
        b"Subject: test\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
        b"<p>Salut<br>le <b>monde</b></p>"
    )
    text, html = mime.bodies(mime.parse_bytes(raw))
    assert "Salut" in text and "monde" in text and "<b>" not in text
    assert html is not None


def test_broken_charset_does_not_raise() -> None:
    raw = b"Subject: x\r\nContent-Type: text/plain; charset=nawak\r\n\r\nca\xe9va"
    text, _ = mime.bodies(mime.parse_bytes(raw))
    assert text


def test_ascii_criteria_go_to_the_server() -> None:
    terms, has_non_ascii = build_terms(
        SearchCriteria(subject="invoice", since=date(2026, 9, 1), unseen_only=True)
    )
    assert has_non_ascii is False
    assert terms == ["UNSEEN", "SINCE", "01-Sep-2026", "SUBJECT", '"invoice"']


def test_accented_criteria_are_sent_as_utf8_to_the_server() -> None:
    terms, has_non_ascii = build_terms(SearchCriteria(subject="facturé"))
    assert has_non_ascii is True
    assert terms[:2] == ["CHARSET", "UTF-8"]
    assert terms[-1] == '"facturé"'.encode("utf-8")


def test_ascii_only_fallback_drops_accented_terms() -> None:
    terms, has_non_ascii = build_terms(
        SearchCriteria(subject="facturé", unseen_only=True), ascii_only=True
    )
    assert has_non_ascii is True
    assert terms == ["UNSEEN"]
    assert all(isinstance(term, str) for term in terms)


def test_body_scope_uses_body_keyword() -> None:
    terms, _ = build_terms(SearchCriteria(query="facture", query_scope="body"))
    assert terms == ["BODY", '"facture"']


def test_size_and_flag_filters() -> None:
    terms, _ = build_terms(SearchCriteria(flagged_only=True, larger_than_kb=200))
    assert terms == ["FLAGGED", "LARGER", "204800"]


def test_quotes_are_stripped_from_values() -> None:
    terms, _ = build_terms(SearchCriteria(sender='a"b'))
    assert terms == ["FROM", '"ab"']


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Re: Fwd: Facture", "Facture"),
        ("TR : Réunion", "Réunion"),
        ("RE[2]: Re: Sujet", "Sujet"),
        ("Sujet simple", "Sujet simple"),
    ],
)
def test_normalize_subject(raw: str, expected: str) -> None:
    assert normalize_subject(raw) == expected


def test_imap_date_format() -> None:
    assert _imap_date(date(2026, 1, 5)) == "05-Jan-2026"


def test_summary_exposes_from_alias() -> None:
    summary = EmailSummary(uid="1", folder="INBOX", sender="a@b.c")
    assert summary.model_dump(by_alias=True)["from"] == "a@b.c"


@pytest.mark.anyio
async def test_every_tool_is_registered() -> None:
    from icloud_mcp.server import mcp

    tools = await mcp.list_tools()
    assert {tool.name for tool in tools} == {
        "list_folders",
        "folder_status",
        "search_emails",
        "read_email",
        "get_thread",
        "send_email",
        "move_emails",
    }
    # Deux outils d'ecriture seulement, deliberes et documentes comme tels.
    # Aucun outil de suppression ne doit exister.
    forbidden = ("delete", "purge", "expunge", "mark_read", "mark_unread")
    assert not [t.name for t in tools if any(word in t.name for word in forbidden)]

    by_name = {tool.name: tool for tool in tools}
    assert "irreversible" in (by_name["send_email"].description or "").lower()
    # move_emails doit simuler par defaut.
    move_schema = by_name["move_emails"].parameters
    assert move_schema["properties"]["dry_run"]["default"] is True


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_search_uids_are_sorted_numerically() -> None:
    """iCloud renvoie SEARCH dans le desordre : sans tri, on rate les recents."""
    from icloud_mcp.search import _parse_uids

    assert _parse_uids([b"27647 10239 31407 8254"]) == ("8254", "10239", "27647", "31407")


def test_parse_uids_handles_empty_response() -> None:
    from icloud_mcp.search import _parse_uids

    assert _parse_uids([None]) == ()
    assert _parse_uids([]) == ()


def _settings() -> Settings:
    return Settings(email="user@icloud.com", app_password="x", display_name="Test User")


def test_build_message_sets_core_headers() -> None:
    message = _build_message(
        _settings(),
        to=["dest@example.com"],
        subject="Bonjour",
        body_text="Corps du message avec accent : café.",
    )
    assert message["To"] == "dest@example.com"
    assert message["From"] == "Test User <user@icloud.com>"
    assert message["Subject"] == "Bonjour"
    assert message.get_content().strip() == "Corps du message avec accent : café."
    assert message["Message-ID"].endswith("@icloud.com>")
    assert "In-Reply-To" not in message
    assert "References" not in message


def test_build_message_threads_a_reply() -> None:
    message = _build_message(
        _settings(),
        to=["dest@example.com"],
        subject="Re: Bonjour",
        body_text="Suite du fil.",
        in_reply_to="<abc@example.com>",
    )
    assert message["In-Reply-To"] == "<abc@example.com>"
    assert message["References"] == "<abc@example.com>"


def test_build_message_keeps_explicit_references() -> None:
    message = _build_message(
        _settings(),
        to=["dest@example.com"],
        subject="Re: Bonjour",
        body_text="Suite du fil.",
        in_reply_to="<c@example.com>",
        references="<a@example.com> <b@example.com> <c@example.com>",
    )
    assert message["References"] == "<a@example.com> <b@example.com> <c@example.com>"


def test_build_message_adds_cc() -> None:
    message = _build_message(
        _settings(),
        to=["dest@example.com"],
        subject="Bonjour",
        body_text="Corps.",
        cc=["copie@example.com"],
    )
    assert message["Cc"] == "copie@example.com"


def test_move_rejects_empty_uid_list() -> None:
    from icloud_mcp.move import move_emails

    with pytest.raises(ValueError, match="Aucun UID"):
        move_emails(None, [], "INBOX", "Archive")


def test_move_rejects_identical_folders() -> None:
    from icloud_mcp.move import move_emails

    with pytest.raises(ValueError, match="identiques"):
        move_emails(None, ["1"], "INBOX", "INBOX")
