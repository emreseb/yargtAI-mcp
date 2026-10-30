"""Hukuki yapıya duyarlı parçalama (chunking).

Sabit pencereyle kesmek yerine, önce MADDE/paragraf sınırlarında böleriz; her
parçanın başına kararın künyesini ekleriz ki parça tek başına geldiğinde bile
hangi karara ait olduğu belli olsun. Retrieval kalitesi büyük ölçüde buna bağlı.
"""

from __future__ import annotations

import re
from typing import Any

from .config import CHUNK_CHARS, CHUNK_OVERLAP

# "MADDE 5", "Madde 5", "5." gibi madde başlangıçlarını kaba biçimde yakalar.
_SEG_RE = re.compile(
    r"(?=^\s*(?:MADDE|Madde)\s+\d+)"
    r"|(?=^\s*\d{1,3}[\.\)]\s)"
    r"|\n\s*\n",
    re.MULTILINE,
)


def _segments(metin: str) -> list[str]:
    """Metni madde/paragraf sınırlarında kaba parçalara ayırır."""
    parts = [p.strip() for p in _SEG_RE.split(metin) if p and p.strip()]
    return parts or ([metin.strip()] if metin.strip() else [])


def _pack(segments: list[str]) -> list[str]:
    """Küçük parçaları ~CHUNK_CHARS boyutuna kadar birleştirir, örtüşme bırakır."""
    chunks: list[str] = []
    buf = ""
    for seg in segments:
        if not buf:
            buf = seg
        elif len(buf) + 1 + len(seg) <= CHUNK_CHARS:
            buf = f"{buf}\n{seg}"
        else:
            chunks.append(buf)
            # önceki parçanın sonundan örtüşme taşı
            tail = buf[-CHUNK_OVERLAP:] if CHUNK_OVERLAP else ""
            buf = f"{tail}\n{seg}".strip() if tail else seg
    if buf:
        chunks.append(buf)

    # Tek bir segment CHUNK_CHARS'tan büyükse sert bölme uygula.
    out: list[str] = []
    for c in chunks:
        if len(c) <= CHUNK_CHARS * 1.5:
            out.append(c)
            continue
        step = CHUNK_CHARS - CHUNK_OVERLAP
        for i in range(0, len(c), step):
            out.append(c[i : i + CHUNK_CHARS])
    return out


def chunk_karar(karar: dict[str, Any]) -> list[dict[str, Any]]:
    """Bir karar kaydını, her birine künye başlığı eklenmiş parçalara böler.

    Beklenen alanlar: karar_id, baslik, mahkeme, tarih, kaynak, metin.
    Döner: her biri karar_id, parca_no, metin (+ künye alanları) içeren parçalar.
    """
    metin = (karar.get("metin") or "").strip()
    if not metin:
        return []

    kunye = " · ".join(
        str(v)
        for v in (karar.get("baslik"), karar.get("mahkeme"), karar.get("tarih"))
        if v
    )
    rows: list[dict[str, Any]] = []
    for i, body in enumerate(_pack(_segments(metin))):
        text = f"{kunye}\n{body}" if kunye else body
        rows.append(
            {
                "karar_id": karar["karar_id"],
                "parca_no": i,
                "metin": text,
                "baslik": karar.get("baslik") or "",
                "mahkeme": karar.get("mahkeme") or "",
                "tarih": karar.get("tarih") or "",
                "kaynak": karar.get("kaynak") or "",
            }
        )
    return rows
