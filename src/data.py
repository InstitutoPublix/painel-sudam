"""Carga e padronização das bases (Brasil, Regiões, Estados, Municípios).

Convenção das bases: as colunas até "Ano" identificam o território/período e
todas as colunas depois de "Ano" são indicadores (nome da coluna = indicador).
O resultado é uma tabela longa única, com uma linha por território × ano × indicador.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from . import fmt

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
ASSETS = ROOT / "assets"

LEVELS = ["Brasil", "Amazônia Legal", "Grande Região", "Estado", "Município"]
FILE_SUFFIX = {
    "Brasil": "Recorte Brasil",
    "Grande Região": "Recorte Regional",
    "Estado": "Recorte Estadual",
    "Município": "Recorte Municipal",
}
REGIONS = {1: "Norte", 2: "Nordeste", 3: "Sudeste", 4: "Sul", 5: "Centro-Oeste"}

PORTES = [
    ("Até 5 mil", 0, 5_000),
    ("5 a 10 mil", 5_000, 10_000),
    ("10 a 20 mil", 10_000, 20_000),
    ("20 a 50 mil", 20_000, 50_000),
    ("50 a 100 mil", 50_000, 100_000),
    ("100 a 500 mil", 100_000, 500_000),
    ("Mais de 500 mil", 500_000, float("inf")),
]


# --------------------------------------------------------------------------- #
# Indicadores
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Indicator:
    col: str          # nome da coluna na base (ou chave do indicador derivado)
    label: str        # nome de exibição
    unit: str
    kind: str         # 'pop' | 'brl' | 'brl_pc'
    scale: float = 1  # multiplicador para exibir na unidade real (R$ mil -> R$)
    additive: bool = True
    meta_id: str | None = None  # id na ficha do protótipo HTML
    derived: bool = False
    icon: str = "●"

    def fmt(self, v, compact: bool = True) -> str:
        if fmt.isna(v):
            return "—"
        v = v * self.scale
        pre = "R$ " if self.kind.startswith("brl") else ""
        return pre + (fmt.compact(v) if compact else fmt.num(v, 0))


def _kind_of(col: str) -> str:
    c = col.lower()
    if "pib" in c or "r$" in c:
        return "brl"
    return "pop"


def make_indicator(col: str) -> Indicator:
    kind = _kind_of(col)
    if kind == "brl":
        return Indicator(col, "PIB municipal", "R$ (preços correntes)", "brl", 1000, True, "IND-068", icon="R$")
    return Indicator(col, "População total", "habitantes", "pop", 1, True, "IND-001", icon="👥")


PCAP_KEY = "PIB per capita"
PCAP = Indicator(PCAP_KEY, "PIB per capita", "R$ por habitante (preços correntes)", "brl_pc", 1,
                 False, "IND-069", derived=True, icon="R$/hab")


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #
def _csv_path(level: str) -> Path:
    suf = FILE_SUFFIX[level]
    for p in DATA_DIR.iterdir():
        if p.suffix.lower() == ".csv" and p.stem.endswith(f"({suf})"):
            return p
    raise FileNotFoundError(f"Base não encontrada para '{level}' em {DATA_DIR}")


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="latin-1")


def _std(df: pd.DataFrame, level: str) -> tuple[pd.DataFrame, list[str]]:
    """Padroniza colunas de identificação e devolve (df, colunas de indicadores)."""
    cols = list(df.columns)
    ano_i = cols.index("Ano")
    ind_cols = cols[ano_i + 1:]
    ids = cols[:ano_i]
    out = pd.DataFrame({"cod": df[ids[0]].astype("int64"), "ano": df["Ano"].astype("int64")})
    if level == "Município":
        out["nome"] = df["Município"].str.title().str.replace(r"\b(D[aeo]s?|E)\b", lambda m: m.group(0).lower(),
                                                               regex=True)
        out["uf"] = df["Estado"]
        out["al"] = df["Amazônia Legal"].str.upper().eq("SIM")
    else:
        out["nome"] = df[ids[1]]
        out["uf"] = None
        out["al"] = pd.NA
    for c in ind_cols:
        out[c] = pd.to_numeric(df[c], errors="coerce")
    return out, ind_cols


def _add_pcap(df: pd.DataFrame, pop_col: str | None, pib_col: str | None) -> pd.DataFrame:
    if pop_col and pib_col:
        df[PCAP_KEY] = df[pib_col] * 1000 / df[pop_col]
    return df


@st.cache_resource(show_spinner="Carregando bases…")
def load() -> dict:
    """Devolve dict com a tabela longa, indicadores e dimensões territoriais."""
    frames, ind_cols = {}, None
    for lvl in FILE_SUFFIX:
        frames[lvl], cols = _std(_read_csv(_csv_path(lvl)), lvl)
        ind_cols = cols if ind_cols is None else [c for c in ind_cols if c in cols]

    mun, est, reg, bra = (frames[k] for k in ("Município", "Estado", "Grande Região", "Brasil"))

    # dimensões territoriais derivadas do código IBGE
    uf_code = mun.drop_duplicates("cod").assign(ufc=lambda d: d.cod // 100000)[["ufc", "uf"]].drop_duplicates("ufc")
    code2uf = dict(zip(uf_code.ufc, uf_code.uf))
    al_ufs = set(mun.loc[mun.al, "uf"])
    est["uf"] = est.cod.map(code2uf)
    est["al"] = est.uf.isin(al_ufs)
    est["regiao"] = est.cod.floordiv(10).map(REGIONS)
    mun["regiao"] = mun.cod.floordiv(1_000_000).map(REGIONS)
    reg["uf"], bra["uf"] = None, None

    # Amazônia Legal = soma dos municípios marcados como "SIM"
    amz = (mun[mun.al].groupby("ano")[ind_cols].sum(min_count=1).reset_index())
    amz["cod"], amz["nome"], amz["uf"] = 0, "Amazônia Legal", None

    registry: dict[str, Indicator] = {c: make_indicator(c) for c in ind_cols}
    pop_col = next((c for c, i in registry.items() if i.kind == "pop"), None)
    pib_col = next((c for c, i in registry.items() if i.kind == "brl"), None)
    derived = bool(pop_col and pib_col)
    if derived:
        registry[PCAP_KEY] = PCAP
        for df in (mun, est, reg, bra, amz):
            _add_pcap(df, pop_col, pib_col)
    inds = list(registry)

    parts = []
    for lvl, df in (("Brasil", bra), ("Amazônia Legal", amz), ("Grande Região", reg),
                    ("Estado", est), ("Município", mun)):
        d = df.copy()
        d["nivel"] = lvl
        for c in ("uf", "regiao", "al"):
            if c not in d:
                d[c] = None
        parts.append(d.melt(id_vars=["nivel", "cod", "nome", "uf", "regiao", "al", "ano"],
                            value_vars=inds, var_name="ind", value_name="valor"))
    long = pd.concat(parts, ignore_index=True)
    long["al"] = long["al"].astype("boolean")
    long["label"] = np.where(long.nivel.eq("Município"), long.nome + " (" + long.uf.fillna("") + ")", long.nome)
    for c in ("nivel", "ind", "uf", "regiao", "nome", "label"):
        long[c] = long[c].astype("category")
    long["tid"] = long["nivel"].astype(str) + ":" + long["cod"].astype(str)
    long["tid"] = long["tid"].astype("category")

    # população de referência (mais próxima disponível) → porte do município
    porte = None
    if pop_col:
        p = mun.pivot(index="cod", columns="ano", values=pop_col)
        ref = p.median(axis=1)
        porte = pd.cut(ref, [b[1] for b in PORTES] + [float("inf")], right=False,
                       labels=[b[0] for b in PORTES]).astype(str).rename("porte")

    meta = json.loads((ASSETS / "indicators.json").read_text(encoding="utf-8"))
    return {
        "long": long,
        "registry": registry,
        "indicators": inds,
        "porte": porte,
        "ufs": sorted(al_ufs | set(est.uf.dropna())),
        "al_ufs": sorted(al_ufs),
        "meta": {i["id"]: i for i in meta["indicators"]},
        "axis_colors": meta["axisColors"],
        "axis_desc": meta["axisDescriptions"],
        "pop_col": pop_col,
        "pib_col": pib_col,
        "n_mun": int(mun.cod.nunique()),
        "n_mun_al": int(mun[mun.al].cod.nunique()),
    }


# --------------------------------------------------------------------------- #
# Consultas
# --------------------------------------------------------------------------- #
def years_with_data(D: dict, ind: str) -> list[int]:
    d = D["long"]
    s = d.loc[(d.ind == ind) & d.valor.notna() & d.nivel.eq("Estado"), "ano"]
    return sorted(s.unique().tolist())


def snapshot(D: dict, level: str, ind: str, year: int, *, al_only=False, ufs=None, portes=None) -> pd.DataFrame:
    """Territórios de um nível em um ano, já com os filtros do painel aplicados."""
    d = D["long"]
    d = d[(d.nivel == level) & (d.ind == ind) & (d.ano == year)]
    d = d[d.valor.notna()].copy()
    d["cod"] = d["cod"].astype(int)
    if level in ("Estado", "Município"):
        if al_only:
            d = d[d.al.fillna(False).astype(bool)]
        if ufs:
            d = d[d.uf.isin(ufs)]
    if level == "Município" and portes and D["porte"] is not None:
        d = d[d.cod.map(D["porte"]).isin(portes)]
    for c in ("nivel", "ind", "uf", "regiao", "nome", "label", "tid"):
        d[c] = d[c].astype(str)
    return d.reset_index(drop=True)


def series(D: dict, tids, ind: str) -> pd.DataFrame:
    d = D["long"]
    d = d[d.tid.isin(list(tids)) & (d.ind == ind)]
    d = d.assign(label=d.label.astype(str), tid=d.tid.astype(str), nivel=d.nivel.astype(str))
    return d[["tid", "nivel", "label", "ano", "valor"]].sort_values(["tid", "ano"]).reset_index(drop=True)


def territories(D: dict, level: str) -> pd.DataFrame:
    d = D["long"]
    d = d[(d.nivel == level) & (d.ind == D["indicators"][0]) & (d.ano == d.ano.min())]
    d = d[["tid", "label", "uf", "cod"]].copy()
    for c in ("tid", "label", "uf"):
        d[c] = d[c].astype(str)
    return d.sort_values("label").reset_index(drop=True)


def bands(values: pd.Series, k: int = 5) -> pd.Series:
    """Faixas por quantis (0 = menores valores … k-1 = maiores)."""
    r = values.rank(method="first")
    return pd.qcut(r, k, labels=False)


def band_ranges(values: pd.Series, k: int = 5) -> list[tuple[float, float]]:
    b = bands(values, k)
    return [(values[b == i].min(), values[b == i].max()) for i in range(k)]


def cagr(first: float, last: float, years: int) -> float:
    if fmt.isna(first) or fmt.isna(last) or first <= 0 or years <= 0:
        return float("nan")
    return ((last / first) ** (1 / years) - 1) * 100
