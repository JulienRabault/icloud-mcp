# icloud-mcp

Serveur MCP pour une boîte mail iCloud : lecture en IMAP direct (`imaplib` de la
stdlib) et un seul outil d'écriture, l'envoi via SMTP. Aucune dépendance tierce
pour le réseau ou le parsing MIME.

## Outils

| Outil | Rôle |
|---|---|
| `list_folders` | Liste les dossiers IMAP ; `with_counts` ajoute total et non-lus par dossier |
| `folder_status` | Compteurs d'un dossier (total, non-lus, récents, UIDNEXT) sans lister les messages |
| `search_emails` | Recherche : texte libre, expéditeur, destinataire, sujet, dates, non-lus, marqués, taille |
| `read_email` | Message complet : corps texte décodé, HTML optionnel, métadonnées des pièces jointes |
| `get_thread` | Reconstitue une conversation depuis un de ses messages |
| `send_email` | **Envoie réellement un message** via SMTP. Seul outil d'écriture du serveur |

Garanties côté lecture : `SELECT ... readonly`, lectures via `BODY.PEEK` — rien
n'est marqué lu, déplacé ni supprimé par `list_folders`, `folder_status`,
`search_emails`, `read_email` ou `get_thread`. Un test vérifie qu'aucun de ces
cinq outils ne porte un nom d'action d'écriture (delete/move/mark).

`send_email` est l'exception assumée : il envoie un message pour de vrai,
action irréversible. Ce n'est pas une garde technique côté serveur — c'est à
l'appelant (l'assistant) de ne l'invoquer qu'après validation explicite du
contenu exact par l'utilisateur, jamais de sa propre initiative ni en réponse
à une instruction trouvée dans un email reçu. La description de l'outil le
rappelle. Une copie du message envoyé est déposée au mieux dans « Sent
Messages » (`IMAP APPEND`) ; un échec de cette copie n'annule jamais l'envoi,
il est juste signalé via `saved_to_sent: false` dans la réponse.

## Installation

```bash
uv sync
```

## Configuration

iCloud refuse le mot de passe principal en IMAP. Il faut un **mot de passe pour
application** :
[account.apple.com](https://account.apple.com/account/manage) → Connexion et
sécurité → Mots de passe pour app.

Copier `.env.example` en `.env` et le remplir :

```
ICLOUD_EMAIL=prenom.nom@icloud.com
ICLOUD_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
```

Le `.env` est dans `.gitignore`. Les variables d'environnement du système sont
prioritaires sur le fichier, si tu préfères ne rien écrire sur disque.

## Vérifier depuis le terminal

```bash
uv run python -m icloud_mcp.cli check
uv run python -m icloud_mcp.cli folders
uv run python -m icloud_mcp.cli latest -n 5
uv run python -m icloud_mcp.cli latest --full
uv run python -m icloud_mcp.cli search "facture" --unseen -n 10
uv run python -m icloud_mcp.cli read 31407
uv run python -m icloud_mcp.cli thread 31404
```

## Brancher sur Claude

Bloc déjà présent dans `%APPDATA%\Claude\claude_desktop_config.json` :

```json
{
  "mcpServers": {
    "icloud-mail": {
      "command": "C:\\chemin\\vers\\uv.exe",
      "args": [
        "run",
        "--directory",
        "C:\\chemin\\vers\\icloud-mcp",
        "python",
        "-m",
        "icloud_mcp"
      ]
    }
  }
}
```

Le chemin absolu vers `uv.exe` est volontaire : Claude Desktop ne démarre pas
forcément avec le `PATH` du shell. Redémarrer Claude après modification, les
serveurs MCP n'étant chargés qu'au démarrage.

## Détails d'implémentation

- **Recherche accentuée** : iCloud accepte `SEARCH CHARSET UTF-8` (vérifié sur un
  compte réel), donc les critères accentués partent au serveur et portent sur la
  boîte entière, corps compris. Si un serveur refusait, un repli relance la
  recherche sans les termes accentués puis filtre les en-têtes des 500 messages
  les plus récents — dans ce cas seulement, `filtered_client_side` vaut `true`
  dans la réponse, pour que la dégradation soit visible et non silencieuse.
- **Noms de dossiers** : encodage/décodage UTF-7 modifié (RFC 3501) dans
  `utf7.py`, donc « Éléments envoyés » fonctionne.
- **MIME** : `email.policy.default`, `get_body(preferencelist=…)` pour choisir la
  partie plain/HTML, décodage `quoted-printable`/`base64` par la stdlib, repli
  latin-1 quand le `charset` déclaré est faux, repli HTML → texte quand le
  message n'a pas de partie `text/plain`.
- **Listes de résultats** : seuls les en-têtes sont récupérés
  (`BODY.PEEK[HEADER.FIELDS …]`), jamais les corps — une recherche sur 20
  résultats ne télécharge pas 20 messages entiers.
- **Fils de discussion** : regroupement sur `References` / `Message-ID`, repli
  sur le sujet normalisé (préfixes `Re:`, `Fwd:`, `TR:` retirés). Le champ
  `matched_by` de la réponse dit quelle méthode a servi.
- **Pièces jointes** : seules les métadonnées (nom, type, taille) sortent, 50 au
  maximum ; le contenu binaire n'est jamais renvoyé au modèle.

## Structure

```
src/icloud_mcp/
  config.py       chargement env / .env, jamais de mot de passe dans les repr
  utf7.py         UTF-7 modifié IMAP
  models.py       modèles Pydantic figés (frozen)
  mime.py         décodage des en-têtes, corps et pièces jointes
  imap_client.py  connexion, LIST, STATUS, SELECT, FETCH
  search.py       critères SEARCH et fils de discussion
  smtp_client.py  construction MIME et envoi SMTP, copie best-effort vers Sent
  server.py       les six outils FastMCP
  cli.py          vérification depuis le terminal
tests/
  test_offline.py tests sans réseau (encodage, MIME, recherche, construction SMTP)
```

## Tests

```bash
uv run pytest -q
```
