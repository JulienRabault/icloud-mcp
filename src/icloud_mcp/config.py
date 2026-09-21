"""Chargement de la configuration (variables d'environnement ou fichier .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

IMAP_HOST = "imap.mail.me.com"
IMAP_PORT = 993
SMTP_HOST = "smtp.mail.me.com"
SMTP_PORT = 587


class ConfigError(RuntimeError):
    """Configuration absente ou invalide."""


@dataclass(frozen=True, slots=True)
class Settings:
    email: str
    app_password: str
    host: str = IMAP_HOST
    port: int = IMAP_PORT
    smtp_host: str = SMTP_HOST
    smtp_port: int = SMTP_PORT
    display_name: str = ""

    @property
    def sender_name(self) -> str:
        """Nom affiche dans l'entete From, a defaut la partie locale."""
        return self.display_name or self.email.split("@")[0]

    def __repr__(self) -> str:  # ne jamais laisser fuiter le mot de passe
        return (
            f"Settings(email={self.email!r}, host={self.host!r}, port={self.port}, "
            f"smtp_host={self.smtp_host!r}, smtp_port={self.smtp_port})"
        )


def _parse_dotenv(path: Path) -> dict[str, str]:
    """Parse un .env minimal : KEY=VALUE, commentaires '#', guillemets optionnels."""
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _candidate_dotenv_paths(explicit: Path | None) -> tuple[Path, ...]:
    if explicit is not None:
        return (explicit,)
    project_root = Path(__file__).resolve().parents[2]
    return (Path.cwd() / ".env", project_root / ".env")


def load_settings(env_file: Path | None = None) -> Settings:
    """Construit les reglages depuis l'environnement, complete par un .env."""
    from_file: dict[str, str] = {}
    for candidate in _candidate_dotenv_paths(env_file):
        if candidate.is_file():
            from_file = _parse_dotenv(candidate)
            break

    def read(key: str) -> str:
        return (os.environ.get(key) or from_file.get(key) or "").strip()

    email = read("ICLOUD_EMAIL")
    password = read("ICLOUD_APP_PASSWORD")
    missing = [
        name
        for name, value in (("ICLOUD_EMAIL", email), ("ICLOUD_APP_PASSWORD", password))
        if not value
    ]
    if missing:
        raise ConfigError(
            "Variables manquantes : "
            + ", ".join(missing)
            + ". Definis-les dans l'environnement ou dans un fichier .env "
            "(voir .env.example). Le mot de passe doit etre un mot de passe "
            "pour application Apple, pas ton mot de passe iCloud principal."
        )
    return Settings(
        email=email,
        app_password=password.replace(" ", ""),
        host=read("ICLOUD_IMAP_HOST") or IMAP_HOST,
        port=int(read("ICLOUD_IMAP_PORT") or IMAP_PORT),
        smtp_host=read("ICLOUD_SMTP_HOST") or SMTP_HOST,
        smtp_port=int(read("ICLOUD_SMTP_PORT") or SMTP_PORT),
        display_name=read("ICLOUD_DISPLAY_NAME"),
    )
