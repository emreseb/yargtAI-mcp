"""Cross-encoder yeniden sıralama (rerank) — fastembed/ONNX ile (torch yok).

Aday parçaları (sorgu, metin) çifti olarak puanlar; yüksek puan = daha alakalı.
Model tembel yüklenir ve ilk kullanımda indirilir (~0.5 GB, int8 çok dilli).
Reranker kapalıysa ya da yüklenemezse çağıran taraf vektör sırasına döner.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import TYPE_CHECKING, Optional

from .config import ONNX_THREADS, RERANK_ENABLED, RERANK_MODEL

if TYPE_CHECKING:
    from fastembed.rerank.cross_encoder import TextCrossEncoder


@lru_cache(maxsize=1)
def _model() -> "TextCrossEncoder":
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    # threads: ONNX'in tüm çekirdekleri kapmasını engeller (makineyi dondurmasın).
    try:
        return TextCrossEncoder(model_name=RERANK_MODEL, threads=ONNX_THREADS)
    except TypeError:
        return TextCrossEncoder(model_name=RERANK_MODEL)


def available() -> bool:
    """Reranker açık ve yüklenebiliyor mu? (ilk çağrıda modeli indirebilir)"""
    if not RERANK_ENABLED:
        return False
    try:
        _model()
        return True
    except Exception:
        return False


def sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def skorla(sorgu: str, belgeler: list[str]) -> Optional[list[float]]:
    """Her belge için ham reranker skoru döndürür; yüklenemezse None."""
    if not belgeler or not RERANK_ENABLED:
        return None
    try:
        return [float(s) for s in _model().rerank(sorgu, belgeler)]
    except Exception:
        return None
