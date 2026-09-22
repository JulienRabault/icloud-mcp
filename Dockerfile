# Image minimale pour faire tourner le serveur MCP en stdio.
#
# Le serveur demarre et repond a l'introspection sans identifiants : la
# configuration n'est lue qu'au premier appel d'outil. Un scanner peut donc
# lister outils, resources et prompts sans acces a une boite mail.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

# Identifiants a fournir a l'execution :
#   docker run -i --rm \
#     -e ICLOUD_EMAIL=you@icloud.com \
#     -e ICLOUD_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx \
#     icloud-mcp
ENTRYPOINT ["python", "-m", "icloud_mcp"]
