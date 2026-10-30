"""İçtihat/mevzuat semantik arama MCP sunucusu.

gib-mcp ile aynı kalıp: MCPServer + ara/oku ikilisi, artı doğrulama.
  * ictihat_ara   — anlamsal arama; snippet + karar_id döndürür.
  * karar_oku     — karar_id ile tam metni ve künyeyi getirir.
  * kunye_dogrula — bir karar_id/künyenin korpusta var olduğunu doğrular.

Künye bütünlüğü: yapay zekâya künyeyi serbest metin olarak ürettirmek yerine
karar_id'yi taşıtıp karar_oku ile çözdürürüz; kunye_dogrula da ''uydurulmuş''
atıfları yakalar. Böylece var olmayan bir karar numarası kullanılamaz.
"""

from __future__ import annotations

from typing import Any, Optional

from mcp.server.mcpserver import MCPServer

from . import dilekce, dilekce_docx, dilekce_udf, prep, retrieve

server = MCPServer("ictihat")


@server.tool()
async def ictihat_ara(
    anahtar: str,
    mahkeme: Optional[str] = None,
    boyut: int = 10,
) -> dict[str, Any]:
    """İçtihat ve mevzuatta anlamsal (semantik) arama yapar.

    Args:
        anahtar: Doğal dildeki arama ifadesi (ör. "kira gelirinde istisna
            tutarı nasıl hesaplanır").
        mahkeme: İsteğe bağlı kaynak/mahkeme ön-filtresi (ör. "GİB Özelge").
        boyut: Döndürülecek karar sayısı (1-50).

    Returns:
        "sonuclar" listesi; her biri karar_id, baslik, mahkeme, tarih, kaynak
        ve kısa "ozet" içerir. Tam metin için karar_oku(karar_id) kullanın.
        karar_id'yi olduğu gibi aktarın; künyeyi kendiniz üretmeyin.
    """
    return retrieve.ara(anahtar, mahkeme=mahkeme, boyut=boyut)


@server.tool()
async def karar_oku(karar_id: str) -> dict[str, Any]:
    """Bir kararın/özelgenin tam metnini ve künyesini getirir.

    Args:
        karar_id: ictihat_ara sonucundan gelen kimlik (ör. "gib-ozelge-38733").

    Returns:
        karar_id, baslik, mahkeme, tarih, kanun, kaynak ve "metin" (tam gövde).
    """
    try:
        return retrieve.oku(karar_id)
    except LookupError as exc:
        raise RuntimeError(str(exc)) from exc


@server.tool()
async def kunye_dogrula(ifade: str) -> dict[str, Any]:
    """Bir karar_id ya da serbest künye ifadesinin korpusta gerçekten var olup
    olmadığını doğrular. Yapay zekânın ''uydurduğu'' atıfları yakalamak içindir.

    Args:
        ifade: Doğrulanacak karar_id (ör. "gib-ozelge-38733") ya da künye metni
            (ör. "Yargıtay 9. HD E.2023/123 K.2023/456").

    Returns:
        durum ("dogrulandi" | "olasi_eslesme" | "bulunamadi"), mesafe, varsa
        gerçek künye/adaylar ve bir uyari. "bulunamadi" ise atfı kullanmayın.
    """
    return retrieve.dogrula(ifade)


@server.tool()
async def dilekce_sablonlari() -> dict[str, Any]:
    """Kullanılabilir dilekçe şablonlarını ve her birinin doldurulacak alanlarını listeler.

    Bir dilekçe hazırlamadan önce bunu çağırın; hangi şablonun (dava_dilekcesi,
    cevap_dilekcesi) ve hangi alanların gerektiğini öğrenin, sonra kullanıcıdan bu
    bilgileri toplayıp dilekce_olustur'u çağırın.

    Returns:
        "sablonlar": her biri tur, ad, aciklama, dayanak (HMK maddesi) ve "alanlar"
        (anahtar, aciklama, zorunlu) içeren liste.
    """
    return dilekce.sablonlari_listele()


@server.tool()
async def dilekce_olustur(tur: str, alanlar: dict[str, Any]) -> dict[str, Any]:
    """Seçilen şablonu verilen alan değerleriyle doldurup biçimli dilekçe taslağı üretir.

    Boilerplate (mahkeme başlığı, bölüm etiketleri, standart ifadeler) sunucuda
    deterministik üretilir; siz yalnızca `alanlar` içindeki değerleri ve serbest
    metin bölümlerini (aciklamalar = vakıaların sıra numaralı özeti, talep = sonuç
    ve istem) sağlarsınız. Böylece tüm metni baştan yazmak gerekmez.

    Args:
        tur: Şablon türü (dilekce_sablonlari'ndan: "dava_dilekcesi" | "cevap_dilekcesi").
        alanlar: {anahtar: değer} eşlemesi (ör. {"mahkeme": "...", "davaci_ad": "...",
            "aciklamalar": "1. ...\\n2. ...", "talep": "..."}).

    Returns:
        tur, ad, dayanak, "dilekce" (tam biçimli metin), "eksik_alanlar" (doldurulmayan
        zorunlu alanlar; metinde ⟦EKSİK: …⟧ ile işaretli) ve bir "not".
    """
    return dilekce.olustur(tur, alanlar)


@server.tool()
async def dilekce_belge(
    tur: str, alanlar: dict[str, Any], dosya_adi: str | None = None
) -> dict[str, Any]:
    """Dilekçeyi biçimli bir Word (.docx) belgesi olarak üretir ve diske yazar.

    Düz metin yerine avukatın Word'de açıp düzenleyebileceği gerçek bir dosya verir:
    hizalı taraf bloğu, kalın bölüm başlıkları, iki yana yaslı gövde, imza. Boş
    bırakılan zorunlu alanlar belgede SARI VURGULU "[ … buraya yazınız ]" yer
    tutucusu olur — yani `alanlar`'ı boş/eksik bırakırsanız kullanıcının Word'de
    dolduracağı boş bir form; dolu verirseniz hazır taslak üretir.

    Args:
        tur: "dava_dilekcesi" | "cevap_dilekcesi".
        alanlar: {anahtar: değer} (bkz. dilekce_sablonlari). Boş {} verilebilir.
        dosya_adi: İsteğe bağlı dosya adı (verilmezse tür + zaman damgası).

    Returns:
        tur, ad, "dosya_yolu" (oluşturulan .docx'in tam yolu), "eksik_alanlar"
        (Word'de doldurulacak sarı alanlar) ve bir "not".
    """
    return dilekce_docx.belge_olustur(tur, alanlar, dosya_adi)


@server.tool()
async def dilekce_udf(
    tur: str, alanlar: dict[str, Any], dosya_adi: str | None = None
) -> dict[str, Any]:
    """Dilekçeyi UYAP'a yüklenebilir **İMZASIZ** bir UDF (.udf) taslağı olarak üretir.

    .docx yerine doğrudan UYAP editöründe açılan gerçek bir .udf dosyası verir.
    Dolu alanlar metne gömülür; eksik zorunlu alanlar UYAP'ta DOLDURULABİLİR
    `<field>` alanı olur. Avukat UYAP'ta açar, alanları doldurur ve KENDİ
    e-imzasıyla imzalar — imzayı biz üretmeyiz (sahte imza yok).

    Args:
        tur: "dava_dilekcesi" | "cevap_dilekcesi".
        alanlar: {anahtar: değer} (bkz. dilekce_sablonlari). Boş {} verilebilir.
        dosya_adi: İsteğe bağlı dosya adı (verilmezse tür + zaman damgası).

    Returns:
        tur, ad, "dosya_yolu" (.udf tam yolu), "eksik_alanlar" (UYAP'ta
        doldurulacak alanlar) ve bir "not".
    """
    return dilekce_udf.belge_olustur_udf(tur, alanlar, dosya_adi)


@server.tool()
async def durusma_hazirligi_sablonu() -> dict[str, Any]:
    """Duruşma hazırlık notunun yapısını (bölümler + kaynak kuralı) döndürür.

    Hazırlığa başlamadan önce bunu çağırın: hangi bölümlerin olduğunu ve hangi
    bölümlerde her maddenin KAYNAK gerektirdiğini öğrenin, sonra dava evrakından
    ve (kunye_dogrula ile doğrulanmış) içtihattan doldurup durusma_hazirligi'ni
    çağırın. Uyarı metni sabittir, kaldırılamaz.
    """
    return prep.sablon()


@server.tool()
async def durusma_hazirligi(hazirlik: dict[str, Any]) -> dict[str, Any]:
    """Doldurulmuş bölümlerden biçimli bir duruşma hazırlık notu üretir.

    Her ''kaynak_zorunlu'' bölümde maddeler {"nokta": "...", "kaynak": "..."}
    biçiminde olmalı; kaynağı olmayan maddeler ⟦KAYNAK YOK⟧ olarak İŞARETLENİR
    (sessizce dayanaksız iddia geçmez). Kaynak = dava evrakı referansı, DOĞRULANMIŞ
    karar_id ya da mevzuat maddesi. Uyarı başa/sona otomatik eklenir.

    Args:
        hazirlik: Bölüm anahtarlarından içeriğe eşleme (bkz. durusma_hazirligi_sablonu).
            Liste bölümlerinde değer {nokta, kaynak} nesnelerinin listesidir.

    Returns:
        "not_metni" (tam metin, uyarı dahil), "kaynaksiz_noktalar" (işaretlenen
        dayanaksız maddeler) ve bir "durum".
    """
    return prep.olustur(hazirlik)


def main() -> None:
    """stdio taşıması üzerinden MCP sunucusunu çalıştırır."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
