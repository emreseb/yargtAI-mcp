"""Yapılandırma: veri yolları, model adları ve sabitler.

Hepsi ortam değişkenleriyle ezilebilir; böylece hem ingest (çevrimdışı) hem de
server (çevrimiçi) aynı ayarları paylaşır.
"""

from __future__ import annotations

import os
from pathlib import Path

# İndeks ve ham verinin yazılacağı kök klasör.
DATA_DIR = Path(os.environ.get("ICTIHAT_DATA_DIR", "./.ictihat_data")).expanduser()

# LanceDB (gömme vektörleri + tam metin burada durur).
LANCE_DIR = DATA_DIR / "lancedb"

# Üretilen dilekçe .docx dosyalarının yazılacağı klasör.
DILEKCE_DIR = Path(os.environ.get("ICTIHAT_DILEKCE_DIR", "./dilekceler")).expanduser()

# Tablo adları.
CHUNKS_TABLE = "parcalar"    # aranan parçalar (vektör + metin + künye)
KARARLAR_TABLE = "kararlar"  # karar_id -> tam metin + künye

# Gömme (embedding) modeli — fastembed'in (ONNX) desteklediği adlardan biri.
# Varsayılan: küçük, hızlı, çok dilli (Türkçe dahil), ~220 MB. Kalite yükseltmek
# için ICTIHAT_EMBED_MODEL=intfloat/multilingual-e5-large (1024 boyut, ~2.2 GB).
EMBED_MODEL = os.environ.get(
    "ICTIHAT_EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

# e5 ailesi sorgu/metin için önek ister; diğer modellerde ikisi de boş kalır.
_IS_E5 = "e5" in EMBED_MODEL.lower()
QUERY_PREFIX = "query: " if _IS_E5 else ""
PASSAGE_PREFIX = "passage: " if _IS_E5 else ""

# Parçalama (chunking) ayarları — yaklaşık karakter cinsinden.
CHUNK_CHARS = int(os.environ.get("ICTIHAT_CHUNK_CHARS", "1200"))
CHUNK_OVERLAP = int(os.environ.get("ICTIHAT_CHUNK_OVERLAP", "200"))


def _truthy(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "yes", "on", "evet")


# --- Hibrit arama + yeniden sıralama (rerank) ---------------------------------
# Aday üretimi: vektör + BM25 (FTS) birleşiminden kaç aday toplanır.
CANDIDATE_K = int(os.environ.get("ICTIHAT_CANDIDATE_K", "40"))

# ONNX Runtime iş parçacığı sınırı: modeller tüm CPU çekirdeklerini kapıp
# makineyi dondurmasın diye. Varsayılan = çekirdeklerin yarısı (en çok 4).
ONNX_THREADS = int(
    os.environ.get("ICTIHAT_THREADS", str(max(1, min(4, (os.cpu_count() or 2) // 2))))
)

# Cross-encoder reranker (fastembed/ONNX, torch gerektirmez). Çok dilli, int8.
RERANK_ENABLED = _truthy(os.environ.get("ICTIHAT_RERANK", "1"))
RERANK_MODEL = os.environ.get("ICTIHAT_RERANK_MODEL", "BAAI/bge-reranker-v2-m3-int8")

# Alaka eşiği: reranker skorunun sigmoidi bunun altındaysa sonuç "zayıf" sayılır
# (sonuç gösterilmez / GİB'e düşülür). 0-1 arası.
RELEVANCE_MIN = float(os.environ.get("ICTIHAT_RELEVANCE_MIN", "0.30"))

# --- GİB canlı yedeği ---------------------------------------------------------
# Yerelde güçlü sonuç yoksa GİB'den canlı çekip indekse ekler.
GIB_FALLBACK = _truthy(os.environ.get("ICTIHAT_GIB_FALLBACK", "1"))
GIB_FALLBACK_SAYFA = int(os.environ.get("ICTIHAT_GIB_FALLBACK_SAYFA", "1"))
GIB_FALLBACK_BOYUT = int(os.environ.get("ICTIHAT_GIB_FALLBACK_BOYUT", "20"))
