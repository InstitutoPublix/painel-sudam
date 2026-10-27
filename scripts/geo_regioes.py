"""Gera assets/geo/rg.json: o contorno das cinco Grandes Regiões, unindo os estados de cada uma.

Uso:
    python scripts/geo_regioes.py

Lê assets/geo/uf.json. O código da região é o primeiro dígito do código IBGE do estado (1 Norte ... 5 Centro-Oeste).
"""
from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
UF = ROOT / "assets" / "geo" / "uf.json"
OUT = ROOT / "assets" / "geo" / "rg.json"


def arredonda(c, d=3):
    return [round(c[0], d), round(c[1], d)] if isinstance(c[0], (int, float)) else [arredonda(x, d) for x in c]


def main() -> None:
    por_rg: dict[str, list] = {}
    for f in json.loads(UF.read_text())["features"]:
        por_rg.setdefault(f["properties"]["codarea"][0], []).append(shape(f["geometry"]).buffer(1e-4))
    feats = []
    for cod, geoms in sorted(por_rg.items()):
        g = unary_union(geoms).buffer(-1e-4).simplify(0.003)
        feats.append({"type": "Feature", "id": cod, "properties": {"codarea": cod},
                      "geometry": {"type": g.geom_type, "coordinates": arredonda(mapping(g)["coordinates"])}})
        print(f"região {cod}: {len(geoms)} estados · {g.geom_type}")
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":")))
    print(f"gravado {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
