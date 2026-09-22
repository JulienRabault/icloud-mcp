"""Modeles Pydantic exposes par les outils MCP."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Folder(BaseModel):
    """Un dossier IMAP."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Nom lisible du dossier, a passer aux autres outils")
    flags: tuple[str, ...] = Field(default=(), description="Attributs IMAP du dossier")
    delimiter: str = Field(default="/", description="Separateur de hierarchie")
    messages: int | None = Field(
        default=None, description="Nombre de messages, si les compteurs ont ete demandes"
    )
    unseen: int | None = Field(
        default=None, description="Nombre de non-lus, si les compteurs ont ete demandes"
    )


class FolderStatus(BaseModel):
    """Compteurs d'un dossier, sans recuperer les messages."""

    model_config = ConfigDict(frozen=True)

    folder: str
    messages: int = 0
    unseen: int = 0
    recent: int = 0
    uid_next: int | None = None


class Attachment(BaseModel):
    """Metadonnees d'une piece jointe (le contenu n'est jamais telecharge)."""

    model_config = ConfigDict(frozen=True)

    filename: str
    content_type: str
    size_bytes: int


class EmailSummary(BaseModel):
    """Entete d'un message, sans le corps."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    uid: str = Field(description="UID IMAP stable, a passer a read_email")
    folder: str
    subject: str = ""
    sender: str = Field(default="", alias="from", description="Expediteur")
    to: tuple[str, ...] = ()
    date: datetime | None = None
    seen: bool = False
    flagged: bool = False
    answered: bool = False
    size_bytes: int = 0
    message_id: str = Field(default="", description="Message-ID RFC 822, utile pour les fils")


class EmailMessage(EmailSummary):
    """Message complet : entetes, corps decode et pieces jointes."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    cc: tuple[str, ...] = ()
    reply_to: str = ""
    in_reply_to: str = ""
    body_text: str = ""
    body_html: str | None = None
    attachments: tuple[Attachment, ...] = ()
    body_truncated: bool = False


class SearchResult(BaseModel):
    """Reponse de search_emails."""

    model_config = ConfigDict(frozen=True)

    folder: str
    total_matched: int = Field(description="Nombre de messages correspondant aux criteres")
    returned: int = Field(description="Nombre de messages effectivement renvoyes")
    filtered_client_side: bool = Field(
        default=False,
        description=(
            "Vrai si le serveur a refuse la recherche et qu'un filtrage de repli, "
            "limite aux entetes des messages recents, a ete applique"
        ),
    )
    messages: tuple[EmailSummary, ...] = ()


class SendReceipt(BaseModel):
    """Confirmation d'envoi renvoyee par send_email."""

    model_config = ConfigDict(frozen=True)

    sent: bool = True
    message_id: str
    to: tuple[str, ...]
    cc: tuple[str, ...] = ()
    saved_to_sent: bool = Field(
        description="Vrai si une copie a pu etre deposee dans 'Sent Messages'"
    )


class MoveReceipt(BaseModel):
    """Resultat de move_emails."""

    model_config = ConfigDict(frozen=True)

    dry_run: bool = Field(description="Vrai si rien n'a ete modifie")
    source: str
    destination: str
    count: int
    messages: tuple[EmailSummary, ...] = ()
    missing_uids: tuple[str, ...] = Field(
        default=(), description="UIDs demandes mais introuvables dans le dossier source"
    )


class ThreadResult(BaseModel):
    """Reponse de get_thread : les messages d'une meme conversation."""

    model_config = ConfigDict(frozen=True)

    folder: str
    root_message_id: str = Field(description="Message-ID racine ayant servi au regroupement")
    matched_by: str = Field(description="'references' ou 'subject' selon la methode utilisee")
    returned: int
    messages: tuple[EmailSummary, ...] = ()


class SavedFile(BaseModel):
    """Une piece jointe ecrite sur disque."""

    model_config = ConfigDict(frozen=True)

    filename: str
    content_type: str
    size_bytes: int
    path: str = Field(description="Chemin local du fichier ecrit")


class AttachmentResult(BaseModel):
    """Reponse de save_attachments."""

    model_config = ConfigDict(frozen=True)

    uid: str
    folder: str
    saved: tuple[SavedFile, ...] = ()
    count: int = 0


class FlagResult(BaseModel):
    """Reponse de set_flag."""

    model_config = ConfigDict(frozen=True)

    folder: str
    uids: tuple[str, ...]
    flag: str
    added: bool = Field(description="Vrai si le drapeau a ete ajoute, faux s'il a ete retire")


class DraftReceipt(BaseModel):
    """Reponse de save_draft."""

    model_config = ConfigDict(frozen=True)

    folder: str
    message_id: str
    to: tuple[str, ...]
    subject: str
    sent: bool = Field(default=False, description="Toujours faux : un brouillon ne part pas")


class MultiSearchResult(BaseModel):
    """Reponse de search_all_folders."""

    model_config = ConfigDict(frozen=True)

    folders_searched: int
    totals_by_folder: dict[str, int] = Field(
        default_factory=dict, description="Nombre de correspondances par dossier"
    )
    returned: int
    filtered_client_side: bool = False
    messages: tuple[EmailSummary, ...] = ()


class ThreadMessage(EmailSummary):
    """Message d'un fil, avec son corps quand il a ete demande."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    body_text: str = ""


class MailboxChangeResult(BaseModel):
    """Reponse des outils de gestion de dossiers."""

    model_config = ConfigDict(frozen=True)

    action: str = Field(description="cree, renomme, supprime ou existe_deja")
    folder: str
    new_name: str | None = None


class RuleMatch(BaseModel):
    """Ce qu'une regle de classement a trouve."""

    model_config = ConfigDict(frozen=True)

    folder: str
    rule: str = Field(description="Criteres de la regle, en clair")
    matched: int
    moved: bool
    sample: tuple[EmailSummary, ...] = Field(
        default=(), description="Quelques messages concernes, pour verification"
    )


class OrganizeResult(BaseModel):
    """Reponse de auto_organize."""

    model_config = ConfigDict(frozen=True)

    source: str
    dry_run: bool
    total_matched: int
    rules: tuple[RuleMatch, ...] = ()
