"""Dilekçeyi UYAP UDF (.udf) belgesi olarak üretir.

UDF = UYAP Doküman Formatı: içinde `content.xml` bulunan bir ZIP. content.xml:
  * <content><![CDATA[ ...tüm metin tek string... ]]></content>
  * <elements> → her <paragraph> içinde satır-içi "run"lar; her run metnin bir
    dilimine (startOffset+length) denk gelir: <content> düz metin, <field> ise
    AVUKATIN UYAP editöründe dolduracağı boş/doldurulabilir alan.
  * <styles> → biçim tanımları.

Tasarım: dolu alanlar düz <content> olur; eksik zorunlu alanlar gerçek <field>
(fieldType="1") olur — yani avukat .udf'yi UYAP'ta açıp bu alanları doldurur ve
KENDİ e-imzasıyla imzalar. Biz İMZASIZ taslak üretiriz (sign.sgn eklemeyiz; imza
ve doğrulama kodu UYAP'ta eklenir).

Not: Bu bir taslaktır; göndermeden önce avukat kontrolünden geçmelidir.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from . import dilekce
from .config import DILEKCE_DIR

# Alan yer tutucularını metin içinde taşımak için özel (private-use) işaretçiler.
# Hukuki metinde geçmeyeceğinden çakışma riski yok.
_F0, _F1, _F2 = "", "", ""  # alan_başı, ayraç, alan_sonu

_STYLES = (
    '<styles>'
    '<style name="default" description="Gövde" family="Times New Roman" size="12" '
    'resolver="hvl-default" bold="false" Alignment="0" LineSpacing="0.0" '
    'SpaceAbove="0.0" SpaceBelow="0.0" LeftIndent="0.0" RightIndent="0.0" />'
    '</styles>'
)
_PAGE = (
    '<properties><pageFormat mediaSizeName="1" leftMargin="42.525" rightMargin="42.525" '
    'topMargin="42.525" bottomMargin="42.525" paperOrientation="1" '
    'headerFOffset="20.0" footerFOffset="20.0" /></properties>'
)

_FIELD_RE = re.compile(_F0 + r"(.*?)" + _F1 + r"(.*?)" + _F2, re.DOTALL)


def _degerler_isaretli(cozum: dict[str, Any]) -> dict[str, str]:
    """Dolu alan → değer; eksik zorunlu alan → alan-işaretçisi (sonra <field> olur)."""
    out: dict[str, str] = {}
    for k, c in cozum.items():
        if c["placeholder"]:
            # fieldName = anahtar, görünen yer tutucu = açıklama
            out[k] = f"{_F0}{k}{_F1}[{c['aciklama']}]{_F2}"
        else:
            out[k] = c["deger"]
    return out


def _content_xml(metin: str) -> str:
    """İşaretli metinden UDF content.xml üretir (CDATA + elements + styles)."""
    cdata_parcalar: list[str] = []
    paragraf_xml: list[str] = []
    off = 0

    for para in metin.split("\n"):
        runs: list[tuple[str, str | None, str]] = []  # (tip, fieldName, metin)
        son = 0
        for m in _FIELD_RE.finditer(para):
            if m.start() > son:
                runs.append(("content", None, para[son:m.start()]))
            runs.append(("field", m.group(1), m.group(2)))
            son = m.end()
        if son < len(para):
            runs.append(("content", None, para[son:]))
        if not runs:
            runs.append(("content", None, ""))
        # Paragraf sonu: son run'a '\n' ekle (CDATA'da paragraflar \n ile ayrılır).
        tip, fn, txt = runs[-1]
        runs[-1] = (tip, fn, txt + "\n")

        ic: list[str] = []
        for tip, fn, txt in runs:
            uz = len(txt)
            cdata_parcalar.append(txt)
            if tip == "field":
                ic.append(
                    f'<field resolver="hvl-default" fieldName={quoteattr(fn or "")} '
                    f'fieldType="1" isList="false" size="12" '
                    f'startOffset="{off}" length="{uz}" />'
                )
            else:
                ic.append(
                    f'<content resolver="hvl-default" size="12" '
                    f'startOffset="{off}" length="{uz}" />'
                )
            off += uz
        paragraf_xml.append(f'<paragraph Alignment="0">{"".join(ic)}</paragraph>')

    cdata = "".join(cdata_parcalar).replace("]]>", "]]]]><![CDATA[>")  # CDATA güvenliği
    return (
        '<?xml version="1.0" encoding="UTF-8" ?>\n'
        '<template format_id="1.8" >\n'
        f"<content><![CDATA[{cdata}]]></content>"
        f"{_PAGE}\n"
        "<elements >\n" + "".join(paragraf_xml) + "\n</elements>\n"
        f"{_STYLES}\n"
        "</template>"
    )


def belge_olustur_udf(
    tur: str, alanlar: dict[str, Any] | None = None, dosya_adi: str | None = None
) -> dict[str, Any]:
    """Dilekçeyi UYAP'a yüklenebilir, İMZASIZ bir .udf taslağı olarak üretir.

    Dolu alanlar metne gömülür; eksik zorunlu alanlar UYAP'ta doldurulacak
    <field> (doldurulabilir alan) olur. Avukat UYAP editöründe açar, alanları
    doldurur ve kendi e-imzasıyla imzalar.
    """
    s, cozum, eksik = dilekce.coz(tur, alanlar)
    metin = s["govde"].format(**_degerler_isaretli(cozum))
    xml = _content_xml(metin)

    DILEKCE_DIR.mkdir(parents=True, exist_ok=True)
    ad = dosya_adi or f"{tur}_{datetime.now():%Y%m%d_%H%M%S}"
    if not ad.lower().endswith(".udf"):
        ad += ".udf"
    yol = DILEKCE_DIR / ad

    # UDF = içinde content.xml olan ZIP (imzasız: sign.sgn yok).
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("content.xml", xml.encode("utf-8"))
    yol.write_bytes(buf.getvalue())

    return {
        "tur": tur,
        "ad": s["ad"],
        "dosya_yolu": str(yol),
        "eksik_alanlar": eksik,
        "not": (
            (
                "Taslak hazır; eksik alan yok."
                if not eksik
                else f"{len(eksik)} zorunlu alan UYAP'ta doldurulacak <field> olarak bırakıldı."
            )
            + " İMZASIZ taslaktır: UYAP'ta açın, alanları doldurun, kendi "
            "e-imzanızla imzalayın. Göndermeden önce avukat kontrolünden geçirin."
        ),
    }
