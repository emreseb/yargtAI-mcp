"""Metin normalleştirme — gib-mcp'deki yardımcıların aynısı.

Resmî kaynaklar gövdeyi HTML olarak verir; bunu yapay zekânın okuyabileceği
düz metne çeviririz.
"""

from __future__ import annotations

import html
import re
from typing import Optional

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t ]+")
_MULTI_NL_RE = re.compile(r"\n\s*\n\s*\n+")


def html_to_text(raw: Optional[str]) -> str:
    """HTML gövdesini okunabilir düz metne çevirir."""
    if not raw:
        return ""
    text = raw
    # blok sonlarını satır sonuna çevir
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</tr\s*>", "\n", text)
    text = re.sub(r"(?i)</td\s*>", "\t", text)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = text.replace(" ", " ")
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = _MULTI_NL_RE.sub("\n\n", text)
    return text.strip()


def fmt_date(raw: Optional[str]) -> Optional[str]:
    """'2025-06-11T00:00:00' -> '11.06.2025'."""
    if not raw:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if not m:
        return raw
    y, mo, d = m.groups()
    return f"{d}.{mo}.{y}"
