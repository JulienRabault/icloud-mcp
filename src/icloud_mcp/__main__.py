"""Lancement du serveur MCP : `python -m icloud_mcp`."""

from __future__ import annotations

import sys

from .server import run


def main() -> int:
    try:
        run()
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
