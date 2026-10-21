"""Carga das bases do painel (Brasil, Amazônia Legal, Regiões, Estados, Municípios).

As bases são geradas por scripts/build_data.py a partir da planilha do PRDA e ficam na pasta
painel/ do bucket (ou em build/, quando não há bucket configurado):

    dados.parquet  tabela longa: nivel, cod, nome, uf, regiao, al, ano, ind (ID da ficha), valor
    fichas.json    ficha e formato de exibição de cada indicador
    manifest.json  versão da base; o painel recarrega sozinho quando ela muda
"""
from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

from . import fmt

ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / "build"
ASSETS = ROOT / "assets"
GCS_PREFIX = "painel/"
MANIFEST_TTL = 600  # segundos entre checagens de nova versão no bucket

LEVELS = ["Brasil", "Amazônia Legal", "Grande Região", "Estado", "Município"]
POP_ID = "IND-001"  # define o porte dos municípios e o tamanho dos pontos nas dispersões

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
    key: str          # ID da ficha (ex.: IND-001)
    label: str        # nome de exibição
    unit: str
    kind: str         # 'numero' | 'percentual' | 'moeda'
    decimals: int = 0
    scale: float = 1  # multiplicador para exibir na unidade real (R$ mil -> R$)
    additive: bool = True  # soma entre territórios (participação no total faz sentido)
    log: bool = True       # escala logarítmica em mapas, histogramas e dispersões
    polarity: int = 0      # 1 maior é melhor · -1 menor é melhor · 0 neutra
    axis: str = ""
    icon: str = "●"
    agg_note: str = ""

    def fmt(self, v, compact: bool = True) -> str:
        if fmt.isna(v):
            return "—"
        v = v * self.scale
        if self.kind == "percentual":
            return fmt.num(v, self.decimals) + "%"
        pre = "R$ " if self.kind == "moeda" else ""
        if compact and abs(v) >= 1e6:
            return pre + fmt.compact(v)
        return pre + fmt.num(v, self.decimals)

    @property
    def polarity_text(self) -> str:
        return {1: "maior é melhor", -1: "menor é melhor"}.get(self.polarity, "")


def make_indicator(f: dict) -> Indicator:
    d = f["display"]
    return Indicator(f["id"], d["label"], d["unit"], d["format"], d["decimals"], d["scale"], d["additive"],
                     d["log"], d["polarity"], f["axis"], d["icon"], f.get("aggregationApplied", ""))


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #
def _gcs_config() -> dict | None:
    """Config do bucket em st.secrets['gcs'] ({bucket, prefix}); None = usar build/ local."""
    try:
        return dict(st.secrets["gcs"])
    except (KeyError, FileNotFoundError):
        return None


@st.cache_resource
def _gcs_bucket(bucket_name: str):
    from google.cloud import storage
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]))
    return storage.Client(credentials=creds, project=creds.project_id).bucket(bucket_name)


def _read_bytes(name: str) -> bytes:
    cfg = _gcs_config()
    if cfg:
        prefix = cfg.get("prefix", GCS_PREFIX)
        path = f"{prefix.rstrip('/')}/{name}" if prefix else name
        blob = _gcs_bucket(cfg["bucket"]).blob(path)
        if not blob.exists():
            raise FileNotFoundError(f"gs://{cfg['bucket']}/{path} não encontrado. Suba os arquivos gerados por "
                                    "`python scripts/build_data.py` para essa pasta do bucket.")
        return blob.download_as_bytes()
    p = BUILD_DIR / name
    if not p.exists():
        raise FileNotFoundError(f"{p} não encontrado. Rode `python scripts/build_data.py` para gerar as bases.")
    return p.read_bytes()


@st.cache_data(ttl=MANIFEST_TTL, show_spinner=False)
def _manifest() -> dict:
    return json.loads(_read_bytes("manifest.json"))


def load() -> dict:
    """Bases do painel, recarregadas quando a versão no manifest muda."""
    return _load(_manifest()["versao"])


@st.cache_resource(show_spinner="Carregando bases…", max_entries=1)
def _load(versao: str) -> dict:
    manifest = _manifest()
    fichas = json.loads(_read_bytes("fichas.json"))["indicadores"]
    long = pd.read_parquet(io.BytesIO(_read_bytes("dados.parquet")))

    registry = {f["id"]: make_indicator(f) for f in fichas}
    inds = [f["id"] for f in fichas if f["id"] in set(long.ind.astype(str))]

    long["al"] = long["al"].astype("boolean")
    long["ano"] = long["ano"].astype("int64")
    long["nome"] = long["nome"].astype(str)
    long["label"] = long.nome.where(long.nivel.ne("Município"), long.nome + " (" + long.uf.astype(str) + ")")
    long["tid"] = long["nivel"].astype(str) + ":" + long["cod"].astype(str)
    for c in ("nivel", "ind", "uf", "regiao", "nome", "label", "tid"):
        long[c] = long[c].astype("category")

    mun = long[long.nivel == "Município"]
    al_ufs = sorted(mun.loc[mun.al.fillna(False).astype(bool), "uf"].astype(str).unique())
    est_ufs = set(long.loc[long.nivel == "Estado", "uf"].dropna().astype(str))

    # população de referência (mediana dos anos disponíveis) → porte do município
    porte = None
    if POP_ID in registry:
        p = mun[mun.ind == POP_ID].pivot_table(index="cod", columns="ano", values="valor", observed=True)
        ref = p.median(axis=1)
        porte = pd.cut(ref, [b[1] for b in PORTES] + [float("inf")], right=False,
                       labels=[b[0] for b in PORTES]).astype(str).rename("porte")

    # último ano com dado de cada indicador (em qualquer nível): base do modo "mais recente" do painel
    latest = long[long.valor.notna()].groupby("ind", observed=True).ano.max()

    axis_meta = json.loads((ASSETS / "indicators.json").read_text(encoding="utf-8"))
    return {
        "long": long,
        "registry": registry,
        "indicators": inds,
        "porte": porte,
        "latest": {str(k): int(v) for k, v in latest.items()},
        "ufs": sorted(set(al_ufs) | est_ufs),
        "al_ufs": al_ufs,
        "meta": {f["id"]: f for f in fichas},
        "axis_colors": axis_meta.get("axisColors", {}),
        "axis_desc": axis_meta.get("axisDescriptions", {}),
        "manifest": manifest,
        "pop_col": POP_ID if POP_ID in inds else None,
        "n_mun": int(mun.cod.nunique()),
        "n_mun_al": int(mun.loc[mun.al.fillna(False).astype(bool), "cod"].nunique()),
    }


# --------------------------------------------------------------------------- #
# Consultas
# --------------------------------------------------------------------------- #
def years_with_data(D: dict, ind: str) -> list[int]:
    d = D["long"]
    s = d.loc[(d.ind == ind) & d.valor.notna(), "ano"]
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
    d = d[(d.nivel == level) & (d.ind == D["indicators"][0])].drop_duplicates("tid")
    d = d[["tid", "label", "uf", "cod"]].copy()
    for c in ("tid", "label", "uf"):
        d[c] = d[c].astype(str)
    return d.sort_values("label").reset_index(drop=True)


def bands(values: pd.Series, k: int = 5) -> pd.Series:
    """Faixas por quantis (0 = menores valores … k-1 = maiores)."""
    r = values.rank(method="first")
    if len(r) < k:  # poucos territórios (ex.: uma UF filtrada): distribui pelas faixas sem repetir bordas
        return ((r - 1) * k // max(len(r), 1)).astype(int)
    return pd.qcut(r, k, labels=False)


def band_ranges(values: pd.Series, k: int = 5) -> list[tuple[float, float]]:
    b = bands(values, k)
    return [(values[b == i].min(), values[b == i].max()) for i in range(k)]


def cagr(first: float, last: float, years: int) -> float:
    if fmt.isna(first) or fmt.isna(last) or first <= 0 or years <= 0:
        return float("nan")
    return ((last / first) ** (1 / years) - 1) * 100
