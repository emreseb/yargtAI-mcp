"""LanceDB deposu.

İki tablo:
  * parcalar  — aranan parçalar: vektör + metin + künye alanları.
  * kararlar  — karar_id -> tam metin + künye (karar_oku bunu okur).

Tam metni parçalardan ayrı tutmak, aramada kullanılan kopya ile birebir dönen
kaynağı birbirinden ayırır (künye bütünlüğü için önemli).
"""

from __future__ import annotations

from typing import Any, Optional

import lancedb
import pyarrow as pa

from .config import CHUNKS_TABLE, KARARLAR_TABLE, LANCE_DIR


def _db():
    LANCE_DIR.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(str(LANCE_DIR))


def _chunks_schema(dim: int) -> pa.Schema:
    return pa.schema(
        [
            pa.field("karar_id", pa.string()),
            pa.field("parca_no", pa.int32()),
            pa.field("metin", pa.string()),
            pa.field("baslik", pa.string()),
            pa.field("mahkeme", pa.string()),
            pa.field("tarih", pa.string()),
            pa.field("kaynak", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
        ]
    )


_KARARLAR_SCHEMA = pa.schema(
    [
        pa.field("karar_id", pa.string()),
        pa.field("baslik", pa.string()),
        pa.field("mahkeme", pa.string()),
        pa.field("tarih", pa.string()),
        pa.field("kanun", pa.string()),
        pa.field("kaynak", pa.string()),
        pa.field("metin", pa.string()),
    ]
)


def _open_or_create(db, name: str, schema: pa.Schema):
    if name in db.table_names():
        return db.open_table(name)
    return db.create_table(name, schema=schema)


def add_chunks(rows: list[dict[str, Any]], dim: int) -> None:
    """Vektörlü parçaları 'parcalar' tablosuna ekler."""
    if not rows:
        return
    db = _db()
    tbl = _open_or_create(db, CHUNKS_TABLE, _chunks_schema(dim))
    tbl.add(rows)


def add_kararlar(rows: list[dict[str, Any]]) -> None:
    """Tam metin kayıtlarını 'kararlar' tablosuna ekler (karar_id ile)."""
    if not rows:
        return
    db = _db()
    tbl = _open_or_create(db, KARARLAR_TABLE, _KARARLAR_SCHEMA)
    tbl.add(rows)


def search_chunks(
    query_vector: list[float],
    limit: int = 30,
    mahkeme: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Vektör araması; isteğe bağlı mahkeme ön-filtresiyle parça döndürür."""
    db = _db()
    if CHUNKS_TABLE not in db.table_names():
        return []
    tbl = db.open_table(CHUNKS_TABLE)
    q = tbl.search(query_vector).metric("cosine").limit(limit)
    if mahkeme:
        # Basit ve enjeksiyona kapalı: tek tırnakları çiftle.
        safe = mahkeme.replace("'", "''")
        q = q.where(f"mahkeme = '{safe}'")
    return q.to_list()


def ensure_fts_index() -> None:
    """'metin' sütununda tam metin (BM25) indeksi kurar/yeniler.

    Vektör araması anlamı, FTS ise birebir terimleri (madde no, özel ad) yakalar.
    İçerik eklendikten sonra çağrılır (ingest sonu ve GİB yedeği sonrası).
    """
    db = _db()
    if CHUNKS_TABLE not in db.table_names():
        return
    tbl = db.open_table(CHUNKS_TABLE)
    try:
        tbl.create_fts_index("metin", use_tantivy=False, replace=True)
    except TypeError:
        # İmza farkı olursa parametresiz dene.
        tbl.create_fts_index("metin", replace=True)


def fts_search(query_text: str, limit: int = 30) -> list[dict[str, Any]]:
    """BM25 tam metin araması. İndeks yoksa ya da hata olursa boş döner."""
    db = _db()
    if CHUNKS_TABLE not in db.table_names():
        return []
    tbl = db.open_table(CHUNKS_TABLE)
    try:
        return tbl.search(query_text, query_type="fts").limit(limit).to_list()
    except Exception:
        return []


def get_karar(karar_id: str) -> Optional[dict[str, Any]]:
    """Tam metin kaydını karar_id ile getirir."""
    db = _db()
    if KARARLAR_TABLE not in db.table_names():
        return None
    tbl = db.open_table(KARARLAR_TABLE)
    safe = karar_id.replace("'", "''")
    rows = tbl.search().where(f"karar_id = '{safe}'").limit(1).to_list()
    return rows[0] if rows else None


def stats() -> dict[str, int]:
    """İndeksteki parça ve karar sayıları."""
    db = _db()
    names = db.table_names()
    parca = db.open_table(CHUNKS_TABLE).count_rows() if CHUNKS_TABLE in names else 0
    karar = db.open_table(KARARLAR_TABLE).count_rows() if KARARLAR_TABLE in names else 0
    return {"parca": parca, "karar": karar}
