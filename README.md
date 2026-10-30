# ictihat-mcp

> **Türk hukuku için bir MCP araç seti.** Avukat kendi yapay zekâsını (Claude,
> ChatGPT…) getirir; bu **MCP sunucusu** ona Türk hukuku becerileri verir:
> semantik içtihat araması, **doğrulanmış** künye, dilekçe üretimi
> (metin · Word · UYAP UDF) ve kaynaklı duruşma hazırlığı.
>
> *An MCP server that gives any AI assistant Turkish-law skills: semantic
> case-law search with verified citations, petition (dilekçe) drafting
> (text · Word · UYAP `.udf`), and sourced hearing prep. Bring your own model.*

## Tasarım ilkesi — künye bütünlüğü (uydurma atıf yok)

Model künyeyi serbest metin olarak üretmez: opak bir `karar_id` taşır, tam metni
`karar_oku` ile çözer, atfı `kunye_dogrula` ile teyit eder. Böylece var olmayan
bir karar numarası kullanılamaz; üretilen her belge/hazırlıkta atıflar ya
gerçektir ya da ⟦işaretlenir⟧.

## Araçlar (9)

**Araştırma**

| Araç | Ne yapar |
|------|----------|
| `ictihat_ara(anahtar, mahkeme?, boyut?)` | Hibrit (vektör + BM25) arama + cross-encoder reranker + alaka eşiği; yerelde sonuç zayıfsa GİB'den canlı çekip indeksler. |
| `karar_oku(karar_id)` | Tam metin + künye. |
| `kunye_dogrula(ifade)` | Bir karar_id/atıfın korpusta var olduğunu doğrular (`dogrulandi` / `olasi_eslesme` / `bulunamadi`). |

**Dilekçe & duruşma hazırlığı**

| Araç | Ne yapar |
|------|----------|
| `dilekce_sablonlari()` | Dilekçe şablonları + alanları (dava HMK m.119, cevap m.129). |
| `dilekce_olustur(tur, alanlar)` | Metin dilekçe taslağı; eksik zorunlu alan ⟦EKSİK⟧. |
| `dilekce_belge(tur, alanlar, dosya_adi?)` | Biçimli **Word (.docx)**; boş alanlar sarı doldurma slotu. |
| `dilekce_udf(tur, alanlar, dosya_adi?)` | UYAP'a yüklenebilen **imzasız `.udf`**; eksik alanlar doldurulabilir `<field>`. Avukat UYAP'ta kendi e-imzasıyla imzalar. |
| `durusma_hazirligi_sablonu()` | Duruşma hazırlık notunun yapısı + kaynak kuralı. |
| `durusma_hazirligi(hazirlik)` | Kaynaklı hazırlık notu; **her maddeye kaynak zorunlu** (yoksa ⟦KAYNAK YOK⟧), uyarı metni sabit. |

## Kurulum

```bash
uv sync          # hafif: fastembed (ONNX), torch/CUDA YOK; python-docx
```

Gömme modeli (~220 MB) ilk aramada indirilir. Reranker modeli (~0.57 GB) ilk
rerank'li aramada indirilir — `ICTIHAT_RERANK=0` ile kapatılabilir (hafif mod).

## Korpusu kur (çevrimdışı)

Arama, yerel bir LanceDB indeksi üzerinde çalışır; önce onu doldurun:

```bash
# GİB özelgeleri
uv run ictihat-index --kaynak gib --anahtar "kira geliri" "serbest meslek" --sayfa-sayisi 3 --boyut 50

# Yargıtay kararları (daire filtresiyle)
uv run ictihat-index --kaynak yargitay --anahtar "kıdem tazminatı" --hukuk-daire "9. Hukuk Dairesi" --adet 50
```

İndeks `./.ictihat_data/` altında oluşur (git'e girmez).

## Çalıştırma

```bash
uv run ictihat-mcp        # stdio MCP sunucusu (yapay zekâ istemcisi buna bağlanır)
```

### Claude'a bağlamak

Proje köküne, makinenize göre bir `.mcp.json` koyun (örnek):

```json
{
  "mcpServers": {
    "ictihat": {
      "command": "uv",
      "args": ["run", "--directory", "/MUTLAK/YOL/ictihat-mcp", "ictihat-mcp"],
      "env": { "ICTIHAT_RERANK": "0" }
    }
  }
}
```

ya da elle:

```bash
claude mcp add ictihat --scope project -- uv run ictihat-mcp
```

## Ortam değişkenleri

| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `ICTIHAT_DATA_DIR` | `./.ictihat_data` | İndeks klasörü |
| `ICTIHAT_EMBED_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Gömme modeli |
| `ICTIHAT_RERANK` | `1` | `0` = reranker kapalı (hafif) |
| `ICTIHAT_RERANK_MODEL` | `BAAI/bge-reranker-v2-m3-int8` | Reranker modeli |
| `ICTIHAT_THREADS` | çekirdek/2 (≤4) | ONNX iş parçacığı sınırı |
| `ICTIHAT_RELEVANCE_MIN` | `0.30` | Alaka eşiği (altı elenir) |
| `ICTIHAT_GIB_FALLBACK` | `1` | Zayıf sonuçta GİB canlı yedeği |
| `ICTIHAT_DILEKCE_DIR` | `./dilekceler` | Üretilen .docx/.udf klasörü |

## Modüller

```
src/ictihat_mcp/
  server.py        MCP sunucusu (9 aracı tanımlar)
  retrieve.py      hibrit arama + rerank + alaka eşiği + GİB yedeği (çekirdek)
  embed.py         fastembed gömme (ONNX; thread sınırlı)
  rerank.py        cross-encoder reranker (fastembed ONNX; torch yok)
  store.py         LanceDB: vektör + BM25/FTS + tam metin
  chunk.py         hukuki yapıya duyarlı parçalama
  normalize.py     HTML→metin
  dilekce.py       HMK şablonları + doldurma (metin)
  dilekce_docx.py  Word (.docx) üretimi
  dilekce_udf.py   UYAP UDF (.udf) üretimi (imzasız)
  prep.py          duruşma hazırlığı (kaynak zorunlu + uyarı)
  ingest/          korpus kaynakları (sources/gib.py, sources/yargitay.py) + build_index
```

## Yol haritası

1. **Mevzuat** — kanun/yönetmelik korpusu (mevzuat.gov.tr) ve kaynaklı maddeler; `mevzuat_dogrula`.
2. **Emsal karşılaştırma** — bir olaya en benzer kararlar + sonuç dağılımı (tahmin değil, dürüst sayım).
3. **Daha çok içtihat kaynağı** — Danıştay (UYAP Emsal), AYM.

## Lisans

MIT — bkz. [LICENSE](LICENSE).

## Uyarı

Bu araçlar avukata **yardımcıdır; hukuki danışmanlık değildir.** Üretilen her
belge/hazırlık avukat kontrolünden geçmeli, atıflar teyit edilmelidir. `.udf`
çıktıları **imzasızdır**; imza UYAP'ta avukatın kendi e-imzasıyla atılır.
