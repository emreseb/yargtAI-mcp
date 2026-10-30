"""GİB özelge kaynağı — gib-mcp'nin keşfettiği API'yi ingest için kullanır.

Not: Buradaki istemci bilinçli olarak gib-mcp ile aynı uç noktaları ve
tarayıcı-benzeri başlıkları kullanır (kendi kendine yeter; gib-mcp paketine
bağımlı değildir). Liste yanıtı 'description' alanında tam gövdeyi döndürdüğü
için tek tek 'oku' çağrısına gerek kalmaz.

Üretilen 'karar' sözlüğü ortak şema: karar_id, baslik, mahkeme, tarih, kanun,
kaynak, metin.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Optional

import httpx

from ...normalize import fmt_date, html_to_text

BASE_URL = "https://gib.gov.tr"
LIST_PATH = "/api/gibportal/mevzuat/ozelge/list"

KTYPE_OZELGE = 99
STATUS_PUBLISHED = 2

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Content-Type": "application/json",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/mevzuat/arama",
}


async def _request_json(
    client: httpx.AsyncClient,
    path: str,
    *,
    params: dict,
    json: dict,
    max_retries: int = 4,
) -> dict[str, Any]:
    """429/5xx durumunda üstel beklemeyle yeniden deneyen POST yardımcısı."""
    delay = 1.0
    for attempt in range(max_retries + 1):
        try:
            resp = await client.post(path, params=params, json=json)
        except httpx.HTTPError as exc:
            if attempt == max_retries:
                raise RuntimeError(f"GİB isteği başarısız: {exc}") from exc
            await asyncio.sleep(delay)
            delay *= 2
            continue

        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == max_retries:
                raise RuntimeError(f"GİB sunucusu {resp.status_code} döndürdü.")
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if (retry_after or "").isdigit() else delay
            await asyncio.sleep(wait)
            delay *= 2
            continue

        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("GİB isteği başarısız.")


def _to_karar(item: dict[str, Any]) -> dict[str, Any]:
    """Ham GİB kaydını ortak 'karar' şemasına çevirir."""
    return {
        "karar_id": f"gib-ozelge-{item.get('id')}",
        "baslik": item.get("title") or "",
        "mahkeme": "GİB Özelge",  # kaynağı ayırt etmek için 'mahkeme' alanına koyuyoruz
        "tarih": fmt_date(item.get("ozelgeTarih")) or "",
        "kanun": item.get("kanunTitle") or "",
        "kaynak": item.get("siteLink") or "",
        "metin": html_to_text(item.get("description")),
    }


async def fetch(
    anahtar: str,
    sayfa_sayisi: int = 2,
    boyut: int = 50,
    bekleme: float = 0.5,
) -> AsyncIterator[dict[str, Any]]:
    """Bir anahtar kelimeyle eşleşen özelgeleri sayfalayarak 'karar' olarak verir."""
    body: dict[str, Any] = {
        "status": STATUS_PUBLISHED,
        "deleted": False,
        "ktype": KTYPE_OZELGE,
        "title": anahtar,
        "kanunNo": anahtar,
        "description": anahtar,
    }
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers=DEFAULT_HEADERS,
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
    ) as client:
        for sayfa in range(sayfa_sayisi):
            data = await _request_json(
                client,
                LIST_PATH,
                params={
                    "page": sayfa,
                    "size": boyut,
                    "sortFieldName": "ozelgeTarih",
                    "sortType": "DESC",
                },
                json=body,
            )
            rc = data.get("resultContainer") or {}
            content = rc.get("content") or []
            if not content:
                break
            for item in content:
                yield _to_karar(item)
            # nazik davran: sayfalar arası kısa bekleme
            await asyncio.sleep(bekleme)
