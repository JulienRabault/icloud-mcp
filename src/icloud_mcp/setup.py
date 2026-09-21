"""Alias pour `python -m icloud_mcp.setup`."""

from __future__ import annotations

import sys

from .setup_wizard import main

if __name__ == "__main__":
    sys.exit(main())
