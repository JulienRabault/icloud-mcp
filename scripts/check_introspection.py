"""Verifie que le serveur demarre et repond sans identifiants.

Les annuaires MCP et les scanners lancent le serveur sans boite mail : il doit
lister outils, resources et prompts malgre tout. La configuration n'est lue
qu'au premier appel d'outil, ce script verifie que cette propriete tient.
"""

from __future__ import annotations

import asyncio
import os
import sys

EXPECTED_TOOLS = 15
EXPECTED_RESOURCES = 2
EXPECTED_PROMPTS = 3


async def main() -> int:
    # On s'assure qu'aucun identifiant ne traine dans l'environnement.
    for key in ("ICLOUD_EMAIL", "ICLOUD_APP_PASSWORD", "ICLOUD_DISPLAY_NAME"):
        os.environ.pop(key, None)

    from icloud_mcp.server import mcp

    tools = await mcp.list_tools()
    resources = await mcp.list_resources()
    prompts = await mcp.list_prompts()

    print(f"outils    : {len(tools)}")
    print(f"resources : {len(resources)}")
    print(f"prompts   : {len(prompts)}")

    problems = []
    if len(tools) != EXPECTED_TOOLS:
        problems.append(f"{EXPECTED_TOOLS} outils attendus, {len(tools)} trouves")
    if len(resources) != EXPECTED_RESOURCES:
        problems.append(f"{EXPECTED_RESOURCES} resources attendues, {len(resources)}")
    if len(prompts) != EXPECTED_PROMPTS:
        problems.append(f"{EXPECTED_PROMPTS} prompts attendus, {len(prompts)}")

    if problems:
        for item in problems:
            print(f"ECHEC : {item}", file=sys.stderr)
        return 1

    print("Introspection sans identifiants : OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
