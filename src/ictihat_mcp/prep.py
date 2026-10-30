"""Duruşma hazırlık notu — her maddeye KAYNAK zorunluluğuyla.

Fikir: yapay zekâya hazırlık içeriğini bir yapıya doldurtmak; kaynak_zorunlu
bölümlerde her madde bir kaynağa dayanmalı (dava evrakı §x, doğrulanmış karar_id,
mevzuat maddesi). Kaynağı olmayan madde ⟦KAYNAK YOK⟧ olarak işaretlenir — sessizce
dayanaksız iddia geçmez. Uyarı metni sabittir; model kaldıramaz/değiştiremez.

Bu bir YARDIMCIdır; doğruluğu otomatik doğrulanamaz. İçtihat kaynakları
kunye_dogrula ile ayrıca teyit edilmelidir.
"""

from __future__ import annotations

from typing import Any

UYARI = (
    "⚠️ UYARI — Bu not YALNIZCA bir hazırlık taslağıdır; duruşmada söylenecek "
    "sözlerin yerini TUTMAZ. Hiçbir madde körü körüne kullanılmamalı; her biri "
    "avukat tarafından değerlendirilip teyit edilmelidir. Sorumluluk tümüyle "
    "avukata aittir."
)

# tip: "metin" (serbest) | "liste" (madde listesi). kaynak_zorunlu yalnız listede.
BOLUMLER: list[dict[str, Any]] = [
    {"anahtar": "dava_ozeti", "baslik": "Dava Özeti", "tip": "metin", "kaynak_zorunlu": False,
     "aciklama": "Davanın konusu, talep ve temel olgular (2-4 cümle)."},
    {"anahtar": "ihtilafli_noktalar", "baslik": "İhtilaflı Noktalar", "tip": "liste", "kaynak_zorunlu": True,
     "aciklama": "Davanın döndüğü tartışmalı noktalar; her biri bir kaynağa dayanmalı."},
    {"anahtar": "lehe_deliller", "baslik": "Lehe Deliller", "tip": "liste", "kaynak_zorunlu": True,
     "aciklama": "Müvekkil lehine deliller; kaynak = evrak/karar referansı."},
    {"anahtar": "aleyhe_deliller", "baslik": "Aleyhe Deliller / Zayıf Noktalar", "tip": "liste", "kaynak_zorunlu": True,
     "aciklama": "Aleyhe deliller ve savunması zor noktalar; kaynaklı."},
    {"anahtar": "karsi_argumanlar", "baslik": "Olası Karşı Argümanlar ve Yanıtlar", "tip": "liste", "kaynak_zorunlu": True,
     "aciklama": "Karşı tarafın argümanı → hazırlanan yanıt; kaynaklı."},
    {"anahtar": "hazir_ictihat", "baslik": "Hazır İçtihat / Dayanak", "tip": "liste", "kaynak_zorunlu": True,
     "aciklama": "Duruşmada hazır bulunacak emsaller; kaynak = DOĞRULANMIŞ karar_id/künye (kunye_dogrula)."},
    {"anahtar": "hakim_sorulari", "baslik": "Hâkimin Sorabileceği Sorular", "tip": "liste", "kaynak_zorunlu": False,
     "aciklama": "Öngörülen sorular (avukat öngörüsü; kaynak isteğe bağlı)."},
    {"anahtar": "usul_notlari", "baslik": "Usul / Süre Notları", "tip": "liste", "kaynak_zorunlu": False,
     "aciklama": "Bu duruşmanın amacı, süreler, usule ilişkin hatırlatmalar."},
    {"anahtar": "riskler", "baslik": "Dikkat / Riskler", "tip": "liste", "kaynak_zorunlu": False,
     "aciklama": "Dikkat edilecek noktalar, tuzaklar."},
]

_BOLUM = {b["anahtar"]: b for b in BOLUMLER}


def sablon() -> dict[str, Any]:
    """Hazırlık yapısını döndürür (model bunu doldurur). Uyarı sabittir."""
    return {
        "uyari": UYARI,
        "bolumler": [
            {k: b[k] for k in ("anahtar", "baslik", "tip", "kaynak_zorunlu", "aciklama")}
            for b in BOLUMLER
        ],
        "kullanim": (
            "kaynak_zorunlu bölümlerde her madde {\"nokta\": \"...\", \"kaynak\": \"...\"} "
            "biçiminde olmalı. Kaynak = dava evrakı referansı (ör. 'dava dilekçesi §3'), "
            "DOĞRULANMIŞ karar_id ya da mevzuat maddesi. İçtihatları kunye_dogrula ile teyit edin."
        ),
    }


def _madde_satiri(m: Any, kaynak_zorunlu: bool, kaynaksiz: list, bolum: str) -> str:
    if isinstance(m, dict):
        nokta = (m.get("nokta") or "").strip()
        kaynak = (m.get("kaynak") or "").strip()
    else:
        nokta, kaynak = str(m).strip(), ""
    if kaynak:
        return f"  • {nokta}  [Kaynak: {kaynak}]"
    if kaynak_zorunlu:
        kaynaksiz.append({"bolum": bolum, "nokta": nokta})
        return f"  • {nokta}  [⟦KAYNAK YOK — teyit edin⟧]"
    return f"  • {nokta}"


def olustur(hazirlik: dict[str, Any] | None = None) -> dict[str, Any]:
    """Doldurulmuş bölümlerden biçimli hazırlık notu üretir; kaynaksız zorunlu
    maddeleri işaretler. Uyarı başa ve sona eklenir (kaldırılamaz)."""
    hazirlik = hazirlik or {}
    satirlar: list[str] = [UYARI, "", "DURUŞMA HAZIRLIK NOTU", "=" * 48]
    kaynaksiz: list[dict[str, str]] = []

    for b in BOLUMLER:
        deger = hazirlik.get(b["anahtar"])
        satirlar += ["", b["baslik"].upper()]
        if b["tip"] == "metin":
            satirlar.append((str(deger).strip() if deger else "—"))
        else:
            maddeler = deger if isinstance(deger, list) else []
            if not maddeler:
                satirlar.append("  —")
            for m in maddeler:
                satirlar.append(_madde_satiri(m, b["kaynak_zorunlu"], kaynaksiz, b["baslik"]))

    satirlar += ["", "-" * 48, UYARI]
    return {
        "not_metni": "\n".join(satirlar),
        "kaynaksiz_noktalar": kaynaksiz,
        "durum": (
            "Tüm zorunlu maddeler kaynaklı."
            if not kaynaksiz
            else f"{len(kaynaksiz)} madde kaynaksız — işaretlendi, teyit edin."
        ),
    }
