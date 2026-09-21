"""UTF-7 modifie (RFC 3501) pour les noms de dossiers IMAP."""

from __future__ import annotations

import base64

_B64_ALPHABET = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+,"


def _b64_encode(chunk: str) -> str:
    encoded = base64.b64encode(chunk.encode("utf-16-be")).rstrip(b"=")
    return "&" + encoded.replace(b"/", b",").decode("ascii") + "-"


def encode(name: str) -> str:
    """Encode un nom de dossier Python vers l'UTF-7 modifie IMAP."""
    parts: list[str] = []
    buffer: list[str] = []
    for char in name:
        if "\x20" <= char <= "\x7e":
            if buffer:
                parts.append(_b64_encode("".join(buffer)))
                buffer = []
            parts.append("&-" if char == "&" else char)
        else:
            buffer.append(char)
    if buffer:
        parts.append(_b64_encode("".join(buffer)))
    return "".join(parts)


def decode(name: str) -> str:
    """Decode un nom de dossier IMAP (UTF-7 modifie) vers du texte Python."""
    parts: list[str] = []
    index = 0
    while index < len(name):
        char = name[index]
        if char != "&":
            parts.append(char)
            index += 1
            continue
        end = name.find("-", index)
        if end == -1:  # sequence tronquee : on rend le texte tel quel
            parts.append(name[index:])
            break
        chunk = name[index + 1 : end]
        if not chunk:
            parts.append("&")
        else:
            payload = chunk.encode("ascii", "ignore").replace(b",", b"/")
            padding = b"=" * (-len(payload) % 4)
            parts.append(base64.b64decode(payload + padding).decode("utf-16-be"))
        index = end + 1
    return "".join(parts)
