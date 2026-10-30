"""Dilekçe şablonları + doldurma.

Fikir: yapay zekâya koca dilekçeyi sıfırdan yazdırmak yerine, hukuki yapısı
sabit şablonlara yalnızca OLGULARI doldurtmak. Boilerplate (mahkeme başlığı,
bölüm etiketleri, standart ifadeler) burada deterministik olarak üretilir;
model sadece alan değerlerini ve serbest metin bölümlerini (açıklamalar, talep)
verir. Böylece token tasarrufu + tutarlı biçim + yanlış format riski azalır.

Şablonlar HMK'nın zorunlu unsurlarına dayanır (dava dilekçesi m.119,
cevap dilekçesi m.129).
"""

from __future__ import annotations

from typing import Any

# Eksik zorunlu alanlar bu işaretle gösterilir (model/kullanıcı tamamlasın diye).
EKSIK = "⟦EKSİK: {}⟧"


# Her alan: anahtar, aciklama, zorunlu; isteğe bağlı "varsayilan".
_DAVA_ALANLAR = [
    {"anahtar": "mahkeme", "aciklama": "Dava açılacak mahkeme (ör. İSTANBUL 3. ASLİYE HUKUK MAHKEMESİ)", "zorunlu": True},
    {"anahtar": "davaci_ad", "aciklama": "Davacının adı soyadı / unvanı", "zorunlu": True},
    {"anahtar": "davaci_tc", "aciklama": "Davacının T.C. kimlik numarası", "zorunlu": True},
    {"anahtar": "davaci_adres", "aciklama": "Davacının adresi", "zorunlu": True},
    {"anahtar": "vekil", "aciklama": "Davacı vekili avukatın adı (varsa)", "zorunlu": False, "varsayilan": "—"},
    {"anahtar": "davali_ad", "aciklama": "Davalının adı soyadı / unvanı", "zorunlu": True},
    {"anahtar": "davali_adres", "aciklama": "Davalının adresi", "zorunlu": True},
    {"anahtar": "konu", "aciklama": "Davanın konusu (tek cümle)", "zorunlu": True},
    {"anahtar": "dava_degeri", "aciklama": "Dava değeri (malvarlığı davalarında)", "zorunlu": False, "varsayilan": "Belirsiz / harca esas değer ayrıca bildirilecektir."},
    {"anahtar": "aciklamalar", "aciklama": "Vakıaların sıra numaralı açık özeti (1., 2., 3. …)", "zorunlu": True},
    {"anahtar": "hukuki_sebepler", "aciklama": "Dayanılan hukuki sebepler", "zorunlu": False, "varsayilan": "6100 s. HMK, 6098 s. TBK ve ilgili sair mevzuat."},
    {"anahtar": "deliller", "aciklama": "Her vakıanın hangi delille ispatlanacağı", "zorunlu": False, "varsayilan": "Her türlü yasal delil (belge, tanık, bilirkişi, yemin vb.)."},
    {"anahtar": "talep", "aciklama": "Açık talep sonucu (neyin hüküm altına alınmasını istiyorsunuz)", "zorunlu": True},
    {"anahtar": "tarih", "aciklama": "Dilekçe tarihi (GG.AA.YYYY)", "zorunlu": False, "varsayilan": "…/…/20…"},
]

_DAVA_GOVDE = """{mahkeme}'NE


DAVACI            : {davaci_ad}
                    T.C. Kimlik No: {davaci_tc}
                    {davaci_adres}

VEKİLİ            : {vekil}

DAVALI            : {davali_ad}
                    {davali_adres}

KONU              : {konu}

DAVA DEĞERİ       : {dava_degeri}

AÇIKLAMALAR       :
{aciklamalar}

HUKUKİ SEBEPLER   : {hukuki_sebepler}

DELİLLER          : {deliller}

SONUÇ VE İSTEM    : {talep}


                                                        {tarih}
                                                      Davacı / Vekili
                                                        {vekil}
"""


_CEVAP_ALANLAR = [
    {"anahtar": "mahkeme", "aciklama": "Dosyanın görüldüğü mahkeme", "zorunlu": True},
    {"anahtar": "dosya_no", "aciklama": "Dosya esas numarası (ör. 2025/123 E.)", "zorunlu": True},
    {"anahtar": "davali_ad", "aciklama": "Cevap veren davalının adı / unvanı", "zorunlu": True},
    {"anahtar": "davali_tc", "aciklama": "Davalının T.C. kimlik numarası", "zorunlu": True},
    {"anahtar": "davali_adres", "aciklama": "Davalının adresi", "zorunlu": True},
    {"anahtar": "vekil", "aciklama": "Davalı vekili avukatın adı (varsa)", "zorunlu": False, "varsayilan": "—"},
    {"anahtar": "davaci_ad", "aciklama": "Karşı tarafın (davacının) adı", "zorunlu": True},
    {"anahtar": "davaci_adres", "aciklama": "Davacının adresi", "zorunlu": False, "varsayilan": "Dosyada mevcuttur."},
    {"anahtar": "konu", "aciklama": "Konu", "zorunlu": False, "varsayilan": "Davaya karşı süresinde cevaplarımızın sunulmasından ibarettir."},
    {"anahtar": "aciklamalar", "aciklama": "Savunmanın dayanağı vakıaların sıra numaralı açık özeti", "zorunlu": True},
    {"anahtar": "hukuki_sebepler", "aciklama": "Dayanılan hukuki sebepler", "zorunlu": False, "varsayilan": "6100 s. HMK, 6098 s. TBK ve ilgili sair mevzuat."},
    {"anahtar": "deliller", "aciklama": "Savunmayı ispat edecek deliller", "zorunlu": False, "varsayilan": "Her türlü yasal delil (belge, tanık, bilirkişi, yemin vb.)."},
    {"anahtar": "talep", "aciklama": "Talep sonucu", "zorunlu": False, "varsayilan": "Haksız ve dayanaksız davanın REDDİNE, yargılama giderleri ile vekâlet ücretinin davacı üzerinde bırakılmasına karar verilmesini saygıyla talep ederiz."},
    {"anahtar": "tarih", "aciklama": "Dilekçe tarihi (GG.AA.YYYY)", "zorunlu": False, "varsayilan": "…/…/20…"},
]

_CEVAP_GOVDE = """{mahkeme}'NE

DOSYA NO          : {dosya_no}

CEVAP VEREN
(DAVALI)          : {davali_ad}
                    T.C. Kimlik No: {davali_tc}
                    {davali_adres}

VEKİLİ            : {vekil}

DAVACI            : {davaci_ad}
                    {davaci_adres}

KONU              : {konu}

AÇIKLAMALAR
(SAVUNMA)         :
{aciklamalar}

HUKUKİ SEBEPLER   : {hukuki_sebepler}

DELİLLER          : {deliller}

SONUÇ VE İSTEM    : {talep}


                                                        {tarih}
                                                     Davalı / Vekili
                                                        {vekil}
"""


SABLONLAR: dict[str, dict[str, Any]] = {
    "dava_dilekcesi": {
        "ad": "Dava Dilekçesi",
        "aciklama": "Genel hukuk dava dilekçesi (HMK m.119 zorunlu unsurları).",
        "dayanak": "HMK m.119",
        "alanlar": _DAVA_ALANLAR,
        "govde": _DAVA_GOVDE,
    },
    "cevap_dilekcesi": {
        "ad": "Cevap Dilekçesi",
        "aciklama": "Davalının cevap dilekçesi (HMK m.129 zorunlu unsurları).",
        "dayanak": "HMK m.129",
        "alanlar": _CEVAP_ALANLAR,
        "govde": _CEVAP_GOVDE,
    },
}


def sablonlari_listele() -> dict[str, Any]:
    """Mevcut dilekçe şablonlarını ve her birinin alanlarını döndürür."""
    return {
        "sablonlar": [
            {
                "tur": tur,
                "ad": s["ad"],
                "aciklama": s["aciklama"],
                "dayanak": s["dayanak"],
                "alanlar": [
                    {"anahtar": a["anahtar"], "aciklama": a["aciklama"], "zorunlu": a["zorunlu"]}
                    for a in s["alanlar"]
                ],
            }
            for tur, s in SABLONLAR.items()
        ]
    }


def coz(tur: str, alanlar: dict[str, Any] | None = None):
    """Alan değerlerini çözer. Hem metin hem .docx üretimi bunu kullanır.

    Döner: (sablon, cozum, eksik). cozum[anahtar] = {deger, placeholder, aciklama}:
    placeholder True ise zorunlu alan boş bırakılmıştır (doldurulmalı).
    """
    s = SABLONLAR.get(tur)
    if not s:
        raise ValueError(
            f"Bilinmeyen şablon: {tur!r}. Seçenekler: {', '.join(SABLONLAR)}"
        )
    alanlar = alanlar or {}
    cozum: dict[str, dict[str, Any]] = {}
    eksik: list[str] = []
    for a in s["alanlar"]:
        k = a["anahtar"]
        v = alanlar.get(k)
        if v is not None and str(v).strip():
            cozum[k] = {"deger": str(v).strip(), "placeholder": False, "aciklama": a["aciklama"]}
        elif "varsayilan" in a:
            cozum[k] = {"deger": a["varsayilan"], "placeholder": False, "aciklama": a["aciklama"]}
        elif a["zorunlu"]:
            cozum[k] = {"deger": None, "placeholder": True, "aciklama": a["aciklama"]}
            eksik.append(k)
        else:
            cozum[k] = {"deger": "—", "placeholder": False, "aciklama": a["aciklama"]}
    return s, cozum, eksik


def olustur(tur: str, alanlar: dict[str, Any] | None = None) -> dict[str, Any]:
    """Şablonu verilen alan değerleriyle doldurup biçimli dilekçe metnini döndürür.

    Boilerplate deterministik üretilir; yalnızca `alanlar` içinde verilen değerler
    yerleştirilir. Eksik zorunlu alanlar metinde ⟦EKSİK: …⟧ olarak işaretlenir ve
    `eksik_alanlar` listesinde döner.
    """
    s, cozum, eksik = coz(tur, alanlar)
    degerler = {
        k: (c["deger"] if not c["placeholder"] else EKSIK.format(c["aciklama"]))
        for k, c in cozum.items()
    }
    metin = s["govde"].format(**degerler)
    return {
        "tur": tur,
        "ad": s["ad"],
        "dayanak": s["dayanak"],
        "dilekce": metin,
        "eksik_alanlar": eksik,
        "not": (
            "Taslak hazır. Eksik alan yok."
            if not eksik
            else f"{len(eksik)} zorunlu alan eksik (⟦EKSİK⟧ ile işaretlendi); tamamlayın."
        )
        + " Bu bir taslaktır; göndermeden önce avukat kontrolünden geçirin.",
    }
