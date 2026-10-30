"""Gömme (embedding) sarmalayıcı — fastembed (ONNX Runtime) ile.

torch/CUDA gerektirmez; model tembel (lazy) yüklenir ve hem ingest hem server
aynı tekil modeli kullanır. e5 ailesi sorgu/metin için önek ister (config'te
ayarlı); diğer modellerde önekler boştur.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

import numpy as np

from .config import EMBED_MODEL, ONNX_THREADS, PASSAGE_PREFIX, QUERY_PREFIX

if TYPE_CHECKING:  # ağır içe aktarmayı çalışma zamanına bırak
    from fastembed import TextEmbedding


@lru_cache(maxsize=1)
def _model() -> "TextEmbedding":
    # İçe aktarmayı fonksiyona aldık ki paket sadece gömme gerektiğinde yüklensin.
    from fastembed import TextEmbedding

    # threads: ONNX'in tüm çekirdekleri kapmasını engeller (makineyi dondurmasın).
    try:
        return TextEmbedding(model_name=EMBED_MODEL, threads=ONNX_THREADS)
    except TypeError:
        return TextEmbedding(model_name=EMBED_MODEL)


def _normalize(vec) -> list[float]:
    """Kosinüs benzerliği için L2 normu 1'e indirger."""
    arr = np.asarray(vec, dtype="float32")
    norm = float(np.linalg.norm(arr))
    if norm:
        arr = arr / norm
    return arr.tolist()


@lru_cache(maxsize=1)
def embedding_dim() -> int:
    """Modelin vektör boyutu (LanceDB şeması için gerekir)."""
    vec = next(iter(_model().embed(["boyut yoklaması"])))
    return int(len(vec))


def embed_passages(texts: list[str]) -> list[list[float]]:
    """İndekslenecek metin parçalarını vektörleştirir."""
    if not texts:
        return []
    prefixed = [PASSAGE_PREFIX + t for t in texts]
    return [_normalize(v) for v in _model().embed(prefixed)]


def embed_query(text: str) -> list[float]:
    """Arama sorgusunu vektörleştirir."""
    vec = next(iter(_model().embed([QUERY_PREFIX + text])))
    return _normalize(vec)
