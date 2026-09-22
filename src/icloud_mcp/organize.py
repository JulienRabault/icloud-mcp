"""Classement automatique par regles.

Chaque regle associe un critere (expediteur, sujet, anciennete) a un dossier.
Simule par defaut : l'appelant doit demander explicitement l'application.
"""

from __future__ import annotations

import imaplib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from .imap_client import ImapError
from .models import EmailSummary
from .move import move_emails
from .search import SearchCriteria, search


@dataclass(frozen=True, slots=True)
class OrganizeRule:
    """Une regle de classement. Au moins un critere est requis."""

    folder: str
    sender: str | None = None
    subject: str | None = None
    older_than_days: int | None = None

    def criteria(self) -> SearchCriteria:
        before = (
            date.today() - timedelta(days=self.older_than_days)
            if self.older_than_days
            else None
        )
        return SearchCriteria(sender=self.sender, subject=self.subject, before=before)

    def label(self) -> str:
        parts = []
        if self.sender:
            parts.append(f"de={self.sender}")
        if self.subject:
            parts.append(f"sujet={self.subject}")
        if self.older_than_days:
            parts.append(f"plus de {self.older_than_days} j")
        return ", ".join(parts) or "tout"


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    rule: OrganizeRule
    matched: tuple[EmailSummary, ...]
    moved: bool


def organize(
    conn: imaplib.IMAP4_SSL,
    rules: Sequence[OrganizeRule],
    source: str,
    *,
    limit_per_rule: int,
    dry_run: bool = True,
) -> tuple[RuleOutcome, ...]:
    """Applique les regles sur `source`. Ne deplace rien tant que dry_run est vrai."""
    if not rules:
        raise ValueError("Aucune regle fournie.")
    for rule in rules:
        if not (rule.sender or rule.subject or rule.older_than_days):
            raise ValueError(
                f"Regle vers {rule.folder!r} sans aucun critere : elle deplacerait "
                "tout le dossier."
            )
        if rule.folder == source:
            raise ValueError(f"Regle vers {rule.folder!r} : source et cible identiques.")

    outcomes: list[RuleOutcome] = []
    for rule in rules:
        messages, _, _ = search(
            conn, source, rule.criteria(), limit=limit_per_rule, scan_limit=500
        )
        if not messages:
            outcomes.append(RuleOutcome(rule, (), False))
            continue
        if not dry_run:
            move_emails(
                conn,
                [item.uid for item in messages],
                source,
                rule.folder,
                dry_run=False,
            )
        outcomes.append(RuleOutcome(rule, messages, not dry_run))
    return tuple(outcomes)
