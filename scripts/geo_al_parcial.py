"""Gera assets/geo/al_parcial.json: o contorno da parte da Amazônia Legal nos estados que só participam em parte
(hoje, o Maranhão), unindo os municípios marcados como Amazônia Legal.

Uso:
    python scripts/geo_al_parcial.py

Lê assets/municipios_caracterizacao.csv (gerado por scripts/caracterizacao.py) e assets/geo/mun.json. O mapa de
estados do painel desenha esse contorno para mostrar onde fica a parte da região dentro do estado. Rode de novo quando
mudar a lista de municípios da Amazônia Legal.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "assets" / "municipios_caracterizacao.csv"
MUN = ROOT / "assets" / "geo" / "mun.json"
OUT = ROOT / "assets" / "geo" / "al_parcial.json"


def arredonda(c, d=3):
    return [round(c[0], d), round(c[1], d)] if isinstance(c[0], (int, float)) else [arredonda(x, d) for x in c]


def main() -> None:
    c = pd.read_csv(CSV)
    g = c.groupby("uf").al.agg(["sum", "count"])
    parciais = g[(g["sum"] > 0) & (g["sum"] < g["count"])].index.tolist()
    mun = {f["properties"]["codarea"]: shape(f["geometry"]) for f in json.loads(MUN.read_text())["features"]}
    feats = []
    for uf in parciais:
        cods = c.loc[(c.uf == uf) & c.al, "cod"].astype(str)
        geom = unary_union([mun[k].buffer(1e-4) for k in cods]).buffer(-1e-4).simplify(0.003)
        cod_uf = str(int(c.loc[c.uf == uf, "cod"].iloc[0]) // 100000)
        feats.append({"type": "Feature", "id": cod_uf, "properties": {"uf": uf, "municipios": len(cods)},
                      "geometry": {"type": geom.geom_type, "coordinates": arredonda(mapping(geom)["coordinates"])}})
        print(f"{uf}: {len(cods)} municípios · {geom.geom_type} · área {geom.area:.2f} graus²")
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":")))
    print(f"gravado {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
