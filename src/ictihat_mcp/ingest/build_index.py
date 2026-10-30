"""İndeks kurucu CLI: kaynak -> normalize -> parçala -> gömle -> LanceDB.

Thin-slice: tek kaynak (GİB özelge). GİB araması bir anahtar kelime ister
(''hepsini listele'' yoktur), bu yüzden korpusu bir ya da birkaç tohum
kelimeyle doldururuz.

Örnek:
    uv run ictihat-index --anahtar "kira geliri" --sayfa-sayisi 3 --boyut 50
    uv run ictihat-index --anahtar "serbest meslek" "kira geliri" "amortisman"
"""

from __future__ import annotations

import argparse
import asyncio

from .. import embed, store
from ..chunk import chunk_karar
from .sources import gib, yargitay


async def _run(
    anahtarlar: list[str],
    sayfa_sayisi: int,
    boyut: int,
    grup: int,
    *,
    kaynak: str = "gib",
    adet: int = 20,
    kurul: str | None = None,
    hukuk_daire: str | None = None,
    ceza_daire: str | None = None,
) -> None:
    dim = embed.embedding_dim()
    print(f"Gömme modeli hazır (boyut={dim}). İndeksleniyor…")

    goruldu: set[str] = set()
    karar_tampon: list[dict] = []
    parca_tampon: list[dict] = []
    toplam_karar = 0

    async def bosalt() -> None:
        """Tamponlardaki parçaları gömüp depoya yazar."""
        nonlocal parca_tampon, karar_tampon
        if parca_tampon:
            vektorler = embed.embed_passages([p["metin"] for p in parca_tampon])
            rows = [{**p, "vector": v} for p, v in zip(parca_tampon, vektorler)]
            store.add_chunks(rows, dim)
        if karar_tampon:
            store.add_kararlar(karar_tampon)
        parca_tampon, karar_tampon = [], []

    for anahtar in anahtarlar:
        if kaynak == "yargitay":
            print(f"\n» '{anahtar}' için Yargıtay kararları çekiliyor…")
            kaynak_iter = yargitay.fetch(
                anahtar,
                kurul=kurul,
                hukuk_daire=hukuk_daire,
                ceza_daire=ceza_daire,
                adet=adet,
                sayfa_boyut=boyut,
            )
        else:
            print(f"\n» '{anahtar}' için GİB özelgeleri çekiliyor…")
            kaynak_iter = gib.fetch(anahtar, sayfa_sayisi=sayfa_sayisi, boyut=boyut)
        async for karar in kaynak_iter:
            if karar["karar_id"] in goruldu or not karar["metin"]:
                continue
            goruldu.add(karar["karar_id"])
            parcalar = chunk_karar(karar)
            if not parcalar:
                continue
            karar_tampon.append(
                {
                    "karar_id": karar["karar_id"],
                    "baslik": karar["baslik"],
                    "mahkeme": karar["mahkeme"],
                    "tarih": karar["tarih"],
                    "kanun": karar["kanun"],
                    "kaynak": karar["kaynak"],
                    "metin": karar["metin"],
                }
            )
            parca_tampon.extend(parcalar)
            toplam_karar += 1
            if len(parca_tampon) >= grup:
                await bosalt()
                print(f"  …{toplam_karar} karar yazıldı", end="\r", flush=True)

    await bosalt()
    print("\nBM25 (tam metin) indeksi kuruluyor…")
    store.ensure_fts_index()
    s = store.stats()
    print(f"Bitti. İndekste {s['karar']} karar, {s['parca']} parça.")


def main() -> None:
    ap = argparse.ArgumentParser(description="İçtihat/özelge indeksini kurar.")
    ap.add_argument(
        "--anahtar",
        nargs="+",
        required=True,
        help="Korpusu tohumlayan bir ya da birkaç arama kelimesi.",
    )
    ap.add_argument(
        "--kaynak",
        choices=["gib", "yargitay"],
        default="gib",
        help="Hangi kaynaktan ingest edilsin (varsayılan: gib).",
    )
    ap.add_argument("--sayfa-sayisi", type=int, default=2, help="GİB: çekilecek sayfa.")
    ap.add_argument("--boyut", type=int, default=50, help="Sayfa başına kayıt (pageSize).")
    ap.add_argument("--grup", type=int, default=64, help="Gömme toplu-iş boyutu.")
    # Yargıtay'a özel: toplam adet + daire/kurul filtreleri (birim gürültüsünü budar)
    ap.add_argument("--adet", type=int, default=20, help="Yargıtay: anahtar başına toplam karar.")
    ap.add_argument("--kurul", default=None, help="Yargıtay kurulu (ör. 'Hukuk Genel Kurulu').")
    ap.add_argument("--hukuk-daire", default=None, help="Hukuk dairesi (ör. '9. Hukuk Dairesi').")
    ap.add_argument("--ceza-daire", default=None, help="Ceza dairesi (ör. '1. Ceza Dairesi').")
    args = ap.parse_args()
    asyncio.run(
        _run(
            args.anahtar,
            args.sayfa_sayisi,
            args.boyut,
            args.grup,
            kaynak=args.kaynak,
            adet=args.adet,
            kurul=args.kurul,
            hukuk_daire=args.hukuk_daire,
            ceza_daire=args.ceza_daire,
        )
    )


if __name__ == "__main__":
    main()
