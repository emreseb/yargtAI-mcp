"""Çekirdek retrieval mantığı — hem MCP sunucusu hem HTTP API bunu kullanır.

Akış (ara):
  1. Aday üretimi: vektör (anlam) + BM25/FTS (birebir terim) birleşimi.
  2. Cross-encoder reranker ile adayları yeniden sırala (varsa).
  3. Alaka eşiği: güçlü sonuç yoksa…
  4. GİB canlı yedeği: ilgili özelgeleri GİB'den çek, indekse ekle, tekrar ara.

Reranker yoksa (model yüklenemezse) vektör sırasına düşülür; eşik uygulanmaz.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from . import embed, rerank, store
from .config import (
    CANDIDATE_K,
    GIB_FALLBACK,
    GIB_FALLBACK_BOYUT,
    GIB_FALLBACK_SAYFA,
    RELEVANCE_MIN,
)

_SNIPPET_LEN = 320

# Kosinüs mesafesi bu eşiğin altındaysa dogrula "olası eşleşme" sayar (0 = birebir).
_DOGRULA_ESIK = 0.35

# Basit Türkçe durak/soru kelimeleri — GİB yedeği için anahtar çıkarımında atılır.
_STOP = {
    "ve", "ya", "da", "de", "ki", "mi", "mı", "mu", "mü", "ne", "kadar", "nasıl",
    "nedir", "neden", "için", "ile", "bir", "bu", "şu", "çok", "daha", "en",
    "gibi", "ama", "veya", "hem", "ise", "olur", "mıdır", "midir", "hangi",
}


def _snippet(metin: str) -> str:
    s = (metin or "").strip()[:_SNIPPET_LEN].rstrip()
    return s + "…" if len(metin or "") > _SNIPPET_LEN else s


def _karar_ozet(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "karar_id": row.get("karar_id"),
        "baslik": row.get("baslik") or "",
        "mahkeme": row.get("mahkeme") or "",
        "tarih": row.get("tarih") or "",
        "kaynak": row.get("kaynak") or "",
    }


def _hibrit_ara(
    anahtar: str, mahkeme: Optional[str], boyut: int
) -> tuple[list[dict[str, Any]], bool]:
    """Vektör + FTS adayları toplar, reranker ile sıralar, karar başına teke indirir.

    Döner: (sonuç listesi, rerank_kullanildi_mi).
    """
    qvec = embed.embed_query(anahtar)
    vec = store.search_chunks(qvec, limit=CANDIDATE_K, mahkeme=mahkeme)
    fts = store.fts_search(anahtar, limit=CANDIDATE_K)
    if mahkeme:
        fts = [r for r in fts if (r.get("mahkeme") or "") == mahkeme]

    # Parça bazında birleştir (aynı parça iki aramadan da gelebilir).
    birlesik: dict[tuple, dict[str, Any]] = {}
    for r in list(vec) + list(fts):
        birlesik.setdefault((r.get("karar_id"), r.get("parca_no")), r)
    adaylar = list(birlesik.values())
    if not adaylar:
        return [], False

    skorlar = rerank.skorla(anahtar, [a.get("metin") or "" for a in adaylar])
    rerank_used = skorlar is not None
    if rerank_used:
        for a, s in zip(adaylar, skorlar):
            a["_rr"] = s
        adaylar.sort(key=lambda a: a["_rr"], reverse=True)
    else:
        adaylar.sort(
            key=lambda a: a["_distance"] if a.get("_distance") is not None else 1e9
        )

    gorulen: set[str] = set()
    sonuclar: list[dict[str, Any]] = []
    for a in adaylar:
        kid = a.get("karar_id")
        if kid in gorulen:
            continue  # karar başına en iyi parça kazanır
        gorulen.add(kid)
        ozet = _karar_ozet(a)
        ozet["ozet"] = _snippet(a.get("metin") or "")
        if rerank_used:
            ozet["skor"] = round(rerank.sigmoid(a["_rr"]), 3)
        sonuclar.append(ozet)
        if len(sonuclar) >= boyut:
            break
    return sonuclar, rerank_used


def _anahtar_kelimeler(anahtar: str) -> str:
    """Doğal dil sorgusundan GİB araması için kaba anahtar kelimeler çıkarır."""
    toks = re.findall(r"\w+", anahtar.lower(), flags=re.UNICODE)
    icerik = [t for t in toks if t not in _STOP and len(t) > 2]
    icerik.sort(key=len, reverse=True)
    return " ".join(icerik[:3]) or anahtar


def _gib_yedek(anahtar: str) -> int:
    """GİB'den ilgili özelgeleri çekip indekse ekler; eklenen karar sayısını döndürür.

    Ağ işi olduğundan ayrı bir thread'de kendi event loop'uyla çalıştırılır
    (MCP/HTTP sunucusu zaten bir event loop içinde döndüğü için).
    """
    import asyncio
    import concurrent.futures

    from .chunk import chunk_karar
    from .ingest.sources import gib

    kelime = _anahtar_kelimeler(anahtar)

    async def _cek() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        async for k in gib.fetch(
            kelime, sayfa_sayisi=GIB_FALLBACK_SAYFA, boyut=GIB_FALLBACK_BOYUT
        ):
            out.append(k)
        return out

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            kayitlar = ex.submit(lambda: asyncio.run(_cek())).result()
    except Exception:
        return 0

    dim = embed.embedding_dim()
    yeni_chunks: list[dict[str, Any]] = []
    yeni_kararlar: list[dict[str, Any]] = []
    eklenen = 0
    for k in kayitlar:
        if not k.get("metin") or store.get_karar(k["karar_id"]):
            continue
        parcalar = chunk_karar(k)
        if not parcalar:
            continue
        yeni_chunks += parcalar
        yeni_kararlar.append(
            {x: k[x] for x in
             ("karar_id", "baslik", "mahkeme", "tarih", "kanun", "kaynak", "metin")}
        )
        eklenen += 1

    if yeni_chunks:
        vecs = embed.embed_passages([c["metin"] for c in yeni_chunks])
        store.add_chunks([{**c, "vector": v} for c, v in zip(yeni_chunks, vecs)], dim)
        store.add_kararlar(yeni_kararlar)
        store.ensure_fts_index()  # FTS indeksini tazele
    return eklenen


def ara(
    anahtar: str,
    mahkeme: Optional[str] = None,
    boyut: int = 10,
    gib_yedek: bool = True,
) -> dict[str, Any]:
    """Hibrit (vektör + BM25) + reranker ile arama; zayıfsa GİB'den canlı çeker."""
    anahtar = (anahtar or "").strip()
    if not anahtar:
        raise ValueError("'anahtar' boş olamaz.")
    boyut = max(1, min(boyut, 50))

    sonuclar, rr = _hibrit_ara(anahtar, mahkeme, boyut)
    guclu = [s for s in sonuclar if s.get("skor", 1.0) >= RELEVANCE_MIN] if rr else sonuclar

    if guclu:
        return {
            "anahtar": anahtar, "toplam_sonuc": len(guclu), "sonuclar": guclu,
            "kaynak": "yerel", "taze_cekildi": False, "rerank": rr,
        }

    # Yerelde güçlü sonuç yok → GİB canlı yedeği
    if gib_yedek and GIB_FALLBACK:
        eklenen = _gib_yedek(anahtar)
        if eklenen:
            sonuclar2, rr2 = _hibrit_ara(anahtar, mahkeme, boyut)
            return {
                "anahtar": anahtar, "toplam_sonuc": len(sonuclar2),
                "sonuclar": sonuclar2, "kaynak": "gib_canli",
                "taze_cekildi": True, "rerank": rr2, "gib_eklenen": eklenen,
            }

    return {
        "anahtar": anahtar, "toplam_sonuc": 0, "sonuclar": [],
        "kaynak": "yerel", "taze_cekildi": False, "rerank": rr,
        "not": "İlgili sonuç bulunamadı.",
    }


def oku(karar_id: str) -> dict[str, Any]:
    """karar_id ile tam metni ve künyeyi getirir."""
    karar_id = (karar_id or "").strip()
    if not karar_id:
        raise ValueError("'karar_id' boş olamaz.")
    rec = store.get_karar(karar_id)
    if not rec:
        raise LookupError(f"{karar_id!r} için karar bulunamadı.")
    return {
        "karar_id": rec.get("karar_id"),
        "baslik": rec.get("baslik"),
        "mahkeme": rec.get("mahkeme"),
        "tarih": rec.get("tarih"),
        "kanun": rec.get("kanun"),
        "kaynak": rec.get("kaynak"),
        "metin": rec.get("metin"),
    }


def dogrula(ifade: str) -> dict[str, Any]:
    """Bir karar_id ya da serbest künye ifadesinin korpusta var olup olmadığını denetler.

    Yapay zekânın ''uydurduğu'' atıfları yakalamak içindir. Üç durum döner:
      * "dogrulandi"    — karar_id birebir bulundu; gerçek künye verilir.
      * "olasi_eslesme" — metin yakın bir karara benziyor; adaylar + mesafe verilir.
                          Kullanıcı/model karar_oku ile teyit etmeli.
      * "bulunamadi"    — yakın eşleşme yok; bu atıf KULLANILMAMALI.
    """
    ifade = (ifade or "").strip()
    if not ifade:
        raise ValueError("'ifade' boş olamaz.")

    # 1) Doğrudan karar_id mi?
    rec = store.get_karar(ifade)
    if rec:
        return {
            "durum": "dogrulandi",
            "mesafe": 0.0,
            "karar": {
                "karar_id": rec.get("karar_id"),
                "baslik": rec.get("baslik"),
                "mahkeme": rec.get("mahkeme"),
                "tarih": rec.get("tarih"),
                "kaynak": rec.get("kaynak"),
            },
            "uyari": None,
        }

    # 2) Serbest metin: anlamsal olarak en yakın kararları bul.
    qvec = embed.embed_query(ifade)
    ham = store.search_chunks(qvec, limit=12)

    adaylar: list[dict[str, Any]] = []
    gorulen: set[str] = set()
    en_iyi_mesafe: Optional[float] = None
    for row in ham:
        kid = row["karar_id"]
        if kid in gorulen:
            continue
        gorulen.add(kid)
        mesafe = row.get("_distance")
        if en_iyi_mesafe is None and mesafe is not None:
            en_iyi_mesafe = float(mesafe)
        aday = _karar_ozet(row)
        aday["mesafe"] = float(mesafe) if mesafe is not None else None
        adaylar.append(aday)
        if len(adaylar) >= 5:
            break

    if en_iyi_mesafe is not None and en_iyi_mesafe <= _DOGRULA_ESIK:
        return {
            "durum": "olasi_eslesme",
            "mesafe": en_iyi_mesafe,
            "adaylar": adaylar,
            "uyari": "Yakın bir karar bulundu ama birebir değil; karar_oku ile teyit edin.",
        }

    return {
        "durum": "bulunamadi",
        "mesafe": en_iyi_mesafe,
        "adaylar": adaylar,
        "uyari": "Bu künye korpusta doğrulanamadı; atfı KULLANMAYIN veya elle teyit edin.",
    }
