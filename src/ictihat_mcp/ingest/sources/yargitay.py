"""Yargıtay karar kaynağı — karararama.yargitay.gov.tr JSON API'si (ingest).

Siteyi canlı inceleyerek doğrulanan uç noktalar (çerez/oturum GEREKTİRMEZ):
  * POST /aramadetaylist  — anahtar kelime + daire/kurul filtreli arama listesi.
  * GET  /getDokuman?id=  — bir kararın tam metni (HTML).

Önemli: Sitenin kendi araması SÖZCÜK tabanlıdır (anlamsal değil). Bu yüzden bu
kaynak yalnız ADAY üretir; "bağlam" eşleştirmesi bizim gömme + reranker
katmanımızda yapılır. Daire filtresi (birimYrg*) yanlış-alan gürültüsünü
(ör. "tazminat" hem ceza hem hukukta geçer) aday aşamasında budar.

Üretilen 'karar' sözlüğü ortak şema: karar_id, baslik, mahkeme, tarih, kanun,
kaynak, metin.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, AsyncIterator, Optional

import httpx

from ...normalize import html_to_text

BASE_URL = "https://karararama.yargitay.gov.tr"
SEARCH_PATH = "/aramadetaylist"   # filtreli/detaylı liste (sade /aramalist filtreleri yok sayar)
DOC_PATH = "/getDokuman"          # ?id= ile tam metin

# siralama: "1"=Esas No'ya, "2"=Karar No'ya, "3"=Karar Tarihine göre.
SIRALAMA_TARIH = "3"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Content-Type": "application/json",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/",
}


async def _request_json(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    json: Optional[dict] = None,
    params: Optional[dict] = None,
    max_retries: int = 4,
) -> dict[str, Any]:
    """429/5xx durumunda üstel beklemeyle yeniden deneyen istek yardımcısı."""
    delay = 1.0
    for attempt in range(max_retries + 1):
        try:
            resp = await client.request(method, path, params=params, json=json)
        except httpx.HTTPError as exc:
            if attempt == max_retries:
                raise RuntimeError(f"Yargıtay isteği başarısız: {exc}") from exc
            await asyncio.sleep(delay)
            delay *= 2
            continue

        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == max_retries:
                raise RuntimeError(f"Yargıtay sunucusu {resp.status_code} döndürdü.")
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if (retry_after or "").isdigit() else delay
            await asyncio.sleep(wait)
            delay *= 2
            continue

        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("Yargıtay isteği başarısız.")


# --- Sonuç (hüküm) sınıflandırma --------------------------------------------
# Kural tabanlı: kararın SONUÇ/hüküm bölümü disposition'ı açıkça yazar. Ucuz,
# deterministik, denetlenebilir. Nötr disposition döner ("kabul/ret" DEĞİL —
# o, kimi temsil ettiğine bağlı olduğundan sorgu anında eşlenir). Sıra önemli:
# daha spesifik kalıp önce gelir.
_SONUC_KURAL: list[tuple[str, str]] = [
    ("duzelterek_onama", r"düzelt\w*\s+onan"),
    ("kismen_bozma", r"kısmen\w*\s+bozul|bozul\w*.{0,40}kısmen"),
    ("bozma", r"bozulmasına|bozulması"),
    ("onama", r"onanmasına|onanması"),
    ("temyiz_red", r"temyiz\s+(iste\w+|dilekçe\w+)\s+\w*red"),
    ("kismen_kabul", r"kısmen\s+kabul"),
    ("kabul", r"davan\w+\s+kabul"),
    ("ret", r"davan\w+\s+red|reddine"),
]


def siniflandir_sonuc(metin: str) -> tuple[str, str]:
    """(sonuc, dayanak_cumle) döndürür. Önce SONUÇ bölümüne (metin kuyruğu),
    sonra tüm metne bakar. Eşleşme yoksa ('belirsiz', '')."""
    if not metin:
        return "belirsiz", ""
    tail = metin[-700:]
    for hedef in (tail, metin):
        dusuk = hedef.lower()
        for sonuc, kalip in _SONUC_KURAL:
            m = re.search(kalip, dusuk)
            if m:
                # eşleşmeyi içeren cümleyi (nokta/br arası) dayanak olarak ver
                bas = hedef.rfind(".", 0, m.start()) + 1
                son = hedef.find(".", m.end())
                son = son if son != -1 else min(m.end() + 120, len(hedef))
                return sonuc, hedef[bas:son].strip()
    return "belirsiz", ""


def _to_karar(item: dict[str, Any], metin: str) -> dict[str, Any]:
    """Ham liste kaydı + tam metni ortak 'karar' şemasına çevirir."""
    daire = (item.get("daire") or "").strip()
    esas = item.get("esasNo") or ""
    karar_no = item.get("kararNo") or ""
    return {
        "karar_id": f"yargitay-{item.get('id')}",
        "baslik": f"{daire} E.{esas} K.{karar_no}".strip(),
        "mahkeme": f"Yargıtay {daire}".strip(),  # kaynağı ayırt etmek için
        "tarih": (item.get("kararTarihi") or "").strip(),  # dd.mm.yyyy
        "kanun": "",
        "kaynak": f"{BASE_URL}{DOC_PATH}?id={item.get('id')}",
        "metin": metin,
    }


async def fetch(
    anahtar: str,
    *,
    kurul: Optional[str] = None,
    hukuk_daire: Optional[str] = None,
    ceza_daire: Optional[str] = None,
    adet: int = 20,
    sayfa_boyut: int = 10,
    siralama: str = SIRALAMA_TARIH,
    bekleme: float = 0.4,
) -> AsyncIterator[dict[str, Any]]:
    """Bir anahtar kelimeyle eşleşen Yargıtay kararlarını 'karar' olarak verir.

    Daire/kurul filtreleri sitenin kendi değerlerini bekler (ör. hukuk_daire=
    "9. Hukuk Dairesi", ceza_daire="1. Ceza Dairesi", kurul="Hukuk Genel Kurulu").
    Hiçbiri verilmezse tüm birimlerde arar.

    Args:
        anahtar: Aranacak kelime (sözcük tabanlı; aday üretir).
        kurul/hukuk_daire/ceza_daire: Birim filtresi (gürültüyü budar).
        adet: Toplam çekilecek karar sayısı.
        sayfa_boyut: Liste sayfası başına kayıt (pageSize).
        bekleme: Her belge çekimi arası bekleme (nazik davranış).
    """
    base_data: dict[str, Any] = {
        "arananKelime": anahtar,
        "birimYrgKurulDaire": kurul or "",
        "birimYrgHukukDaire": hukuk_daire or "",
        "birimYrgCezaDaire": ceza_daire or "",
        "esasYil": "", "esasIlkSiraNo": "", "esasSonSiraNo": "",
        "kararYil": "", "kararIlkSiraNo": "", "kararSonSiraNo": "",
        "baslangicTarihi": "", "bitisTarihi": "",
        "siralama": siralama, "siralamaDirection": "desc",
    }
    verilen = 0
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers=DEFAULT_HEADERS,
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
    ) as client:
        sayfa = 1
        while verilen < adet:
            data = await _request_json(
                client,
                "POST",
                SEARCH_PATH,
                json={"data": {**base_data, "pageSize": sayfa_boyut, "pageNumber": sayfa}},
            )
            icerik = ((data.get("data") or {}).get("data")) or []
            if not icerik:
                break
            for item in icerik:
                if verilen >= adet:
                    break
                try:
                    dok = await _request_json(
                        client, "GET", DOC_PATH, params={"id": item.get("id")}
                    )
                except RuntimeError:
                    continue
                metin = html_to_text(dok.get("data") or "")
                if not metin:
                    continue
                yield _to_karar(item, metin)
                verilen += 1
                await asyncio.sleep(bekleme)
            sayfa += 1
