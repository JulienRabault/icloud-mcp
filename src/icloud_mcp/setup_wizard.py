"""Assistant de configuration : `python -m icloud_mcp.setup`.

Pose les questions, teste la connexion, ecrit le .env et affiche le bloc de
configuration a coller dans le client. Pense pour quelqu'un qui n'ouvre pas un
terminal tous les jours.
"""

from __future__ import annotations

import getpass
import json
import sys
from pathlib import Path

from .config import ConfigError, Settings, load_settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"

APP_PASSWORD_URL = "https://account.apple.com/account/manage"


def _say(message: str = "") -> None:
    print(message, flush=True)


def _ask(question: str, *, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{question}{suffix} : ").strip()
    return answer or default


def _confirm_overwrite() -> bool:
    if not ENV_PATH.is_file():
        return True
    _say(f"Un fichier .env existe deja : {ENV_PATH}")
    return _ask("Le remplacer ? (o/N)", default="N").lower().startswith("o")


def _collect() -> tuple[str, str, str]:
    _say("=" * 68)
    _say("  Configuration de icloud-mcp")
    _say("=" * 68)
    _say()
    _say("iCloud refuse votre mot de passe principal en IMAP.")
    _say("Il faut un MOT DE PASSE POUR APPLICATION, a generer ici :")
    _say(f"  {APP_PASSWORD_URL}")
    _say("  -> Connexion et securite -> Mots de passe pour application")
    _say()
    _say("Il ressemble a : abcd-efgh-ijkl-mnop")
    _say()

    email = ""
    while "@" not in email:
        email = _ask("Votre adresse iCloud")
        if "@" not in email:
            _say("  Adresse invalide, il manque le @.")

    password = ""
    while len(password.replace(" ", "").replace("-", "")) < 12:
        password = getpass.getpass("Mot de passe pour application (invisible) : ")
        if len(password.replace(" ", "").replace("-", "")) < 12:
            _say("  Trop court pour un mot de passe pour application.")

    default_name = email.split("@")[0].replace(".", " ").title()
    display = _ask("Nom affiche dans vos emails envoyes", default=default_name)
    return (email, password, display)


def _write_env(email: str, password: str, display: str) -> None:
    ENV_PATH.write_text(
        "# Genere par python -m icloud_mcp.setup\n"
        f"ICLOUD_EMAIL={email}\n"
        f"ICLOUD_APP_PASSWORD={password}\n"
        f"ICLOUD_DISPLAY_NAME={display}\n",
        encoding="utf-8",
    )
    _say(f"\nEcrit dans {ENV_PATH}")
    _say("Ce fichier contient votre mot de passe : il est deja exclu de git.")


def _test_connection() -> bool:
    from . import imap_client

    _say("\nTest de la connexion...")
    try:
        settings = load_settings(ENV_PATH)
        with imap_client.connect(settings) as conn:
            folders = imap_client.list_folders(conn)
            status = imap_client.folder_status(conn, "INBOX")
    except (ConfigError, Exception) as error:  # noqa: BLE001 - message lisible avant tout
        _say(f"  ECHEC : {error}")
        return False
    _say(f"  OK — {len(folders)} dossiers, {status.messages} messages dans INBOX.")
    return True


def _client_config(python_executable: str) -> str:
    block = {
        "mcpServers": {
            "icloud-mail": {
                "command": "uv",
                "args": [
                    "run",
                    "--directory",
                    str(PROJECT_ROOT),
                    "python",
                    "-m",
                    "icloud_mcp",
                ],
            }
        }
    }
    return json.dumps(block, indent=2)


def _print_next_steps() -> None:
    _say()
    _say("=" * 68)
    _say("  Derniere etape : brancher votre client")
    _say("=" * 68)
    _say()
    _say("Claude Code — une seule commande :")
    _say()
    _say(
        f"  claude mcp add icloud-mail --scope user -- "
        f"uv run --directory {PROJECT_ROOT} python -m icloud_mcp"
    )
    _say()
    _say("Claude Desktop — ajouter ce bloc dans claude_desktop_config.json :")
    if sys.platform == "win32":
        _say(r"  %APPDATA%\Claude\claude_desktop_config.json")
    elif sys.platform == "darwin":
        _say("  ~/Library/Application Support/Claude/claude_desktop_config.json")
    _say()
    _say(_client_config(sys.executable))
    _say()
    _say("Puis REDEMARREZ le client : les serveurs MCP ne sont charges")
    _say("qu'au demarrage.")
    _say()


def main() -> int:
    try:
        if not _confirm_overwrite():
            _say("Annule, le .env existant est conserve.")
            return 0
        email, password, display = _collect()
        _write_env(email, password, display)
        if not _test_connection():
            _say("\nLa configuration est ecrite mais la connexion echoue.")
            _say("Verifiez que le mot de passe est bien un mot de passe pour")
            _say("application, et que la double authentification est active.")
            return 1
        _print_next_steps()
        return 0
    except (KeyboardInterrupt, EOFError):
        _say("\nAnnule.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
