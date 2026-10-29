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

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import streamlit as st

from . import fmt

ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / "build"
ASSETS = ROOT / "assets"
GCS_PREFIX = "painel/"
MANIFEST_TTL = 600  # segundos entre checagens de nova versão no bucket

LEVELS = ["Brasil", "Amazônia Legal", "Grande Região", "Estado", "Município"]
PARTE_AL = "Estado (parte AL)"  # nível com o valor da parcela de um estado que está só em parte na Amazônia Legal
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

    def fmt_col(self, valores) -> list[str]:
        """Formata uma coluna ou um conjunto de valores do mesmo indicador com UMA escala só, para a leitura ficar
        comparável (evita "8,8 mi" ao lado de "887.794"). Até 1 bilhão, números inteiros com separador de milhar;
        acima disso, uma unidade comum (mi, bi ou tri) escolhida pela mediana."""
        vs = [float("nan") if fmt.isna(v) else float(v) for v in valores]
        if self.kind == "percentual":
            return [self.fmt(v) for v in vs]
        a = [abs(v * self.scale) for v in vs if not fmt.isna(v)]
        if not a or max(a) < 1e6:
            return [self.fmt(v) for v in vs]
        pre = "R$ " if self.kind == "moeda" else ""
        if max(a) < 1e9:
            return ["—" if fmt.isna(v) else pre + fmt.num(v * self.scale, self.decimals) for v in vs]
        nz = sorted(x for x in a if x > 0)
        med = nz[len(nz) // 2] if nz else 0
        un, suf = ((1e12, " tri") if med >= 1e12 else (1e9, " bi") if med >= 1e9 else (1e6, " mi") if med >= 1e6
                   else (1, ""))
        return ["—" if fmt.isna(v) else pre + (fmt.num(v * self.scale, self.decimals) if un == 1
                                              else fmt.num(v * self.scale / un, 1) + suf) for v in vs]

    @property
    def polarity_text(self) -> str:
        return {1: "maior é melhor", -1: "menor é melhor"}.get(self.polarity, "")

    # ------------------------------------------------------------------ comparação entre dois valores
    @property
    def delta(self) -> str:
        """Como comparar dois valores: 'pp' (proporções: diferença em pontos percentuais), 'pts' (índices de escala
        fixa: diferença em pontos do índice) ou 'pct' (totais, taxas e valores por habitante: variação relativa)."""
        if self.kind == "percentual":
            return "pp"
        if self.unit.strip().lower().startswith("índice"):
            return "pts"
        return "pct"

    @property
    def delta_unit(self) -> str:
        return {"pp": "p.p.", "pts": "pontos", "pct": "%"}[self.delta]

    @property
    def diff_decimals(self) -> int:
        return {"pp": 1, "pts": max(self.decimals, 1), "pct": 1}[self.delta]

    def diff(self, v, v0) -> float:
        """Diferença de v0 para v na medida do indicador; NaN sem dado (ou base zero, na variação %)."""
        if fmt.isna(v) or fmt.isna(v0):
            return float("nan")
        if self.delta != "pct":
            return float(v - v0) * self.scale
        return float("nan") if v0 == 0 else (v / v0 - 1) * 100

    def rate(self, v0, v1, years: int) -> float:
        """Variação média por ano: taxa composta (%) ou diferença média anual (p.p. ou pontos)."""
        if fmt.isna(v0) or fmt.isna(v1) or years <= 0:
            return float("nan")
        if self.delta != "pct":
            return float(v1 - v0) * self.scale / years
        return float("nan") if v0 <= 0 or v1 < 0 else ((v1 / v0) ** (1 / years) - 1) * 100

    def fmt_diff(self, d) -> str:
        """'+7,0 p.p.', '−0,046 pontos', '+13,1%'."""
        if fmt.isna(d):
            return "—"
        d = round(d, self.diff_decimals)
        sinal = "+" if d > 0 else "−" if d < 0 else ""
        num = fmt.num(abs(d), self.diff_decimals)
        return f"{sinal}{num}%" if self.delta == "pct" else f"{sinal}{num}\u00a0{self.delta_unit}"

    def situacao(self, d) -> int:
        """1 = melhora, −1 = piora, 0 = sem juízo (sem polaridade, sem dado ou diferença que arredonda para zero)."""
        if fmt.isna(d) or not self.polarity or round(d, self.diff_decimals) == 0:
            return 0
        return 1 if d * self.polarity > 0 else -1


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
    """Bases do painel, recarregadas quando a versão no manifest muda. Os indicadores (objetos Indicator) são
    recriados a cada execução, fora do cache: assim uma mudança no código da classe vale na hora, sem reiniciar."""
    D = _load(_manifest()["versao"])
    return {**D, "registry": {k: make_indicator(f) for k, f in D["meta"].items()}}


@st.cache_resource(show_spinner="Carregando bases…", max_entries=1)
def _load(versao: str) -> dict:
    manifest = _manifest()
    fichas = json.loads(_read_bytes("fichas.json"))["indicadores"]
    # leitura sem threads e liberando a tabela Arrow durante a conversão: menos pico de memória na carga
    tabela = pq.read_table(io.BytesIO(_read_bytes("dados.parquet")), use_threads=False)
    long = tabela.to_pandas(self_destruct=True, split_blocks=True)
    del tabela

    registry = {f["id"]: make_indicator(f) for f in fichas}
    com_dado = {str(i) for i in long.ind.unique()}  # calculado uma vez: a base tem milhões de linhas
    inds = [f["id"] for f in fichas if f["id"] in com_dado]

    long["al"] = long["al"].astype("boolean")
    long["ano"] = long["ano"].astype("int64")
    # nome, rótulo e id de cada território: montados uma vez por território (alguns milhares) e ligados às linhas
    # por código, em vez de concatenar texto em milhões de linhas (o que estourava a memória na carga)
    for c in ("nivel", "ind", "uf", "regiao"):
        long[c] = long[c].astype("category")
    chave = long.nivel.cat.codes.astype("int64") * 10**8 + long.cod
    pos, uniq = pd.factorize(chave)
    terr = long.iloc[np.unique(pos, return_index=True)[1]][["nivel", "cod", "nome", "uf"]]  # 1ª linha de cada território
    terr = terr.assign(nome=terr.nome.astype(str), nivel=terr.nivel.astype(str), uf=terr.uf.astype(str))
    rotulos = {
        "nome": terr.nome,
        "label": terr.nome.where(terr.nivel.ne("Município"), terr.nome + " (" + terr.uf + ")"),
        "tid": terr.nivel + ":" + terr.cod.astype(str),
    }
    for c, v in rotulos.items():
        cats, inv = pd.factorize(v.values)  # rótulos repetidos entre territórios viram uma categoria só
        long[c] = pd.Categorical.from_codes(cats[pos], categories=inv)

    mun = long[long.nivel == "Município"]
    al_ufs = sorted(mun.loc[mun.al.fillna(False).astype(bool), "uf"].astype(str).unique())
    est_ufs = set(long.loc[long.nivel == "Estado", "uf"].dropna().astype(str))
    # estados com só parte dos municípios na Amazônia Legal (ex.: Maranhão): {UF: (municípios na AL, total)}
    m = mun[["uf", "cod", "al"]].drop_duplicates("cod").assign(al=lambda d: d.al.fillna(False).astype(bool))
    g = m.groupby("uf", observed=True).al.agg(["sum", "count"])
    al_parcial = {str(u): (int(r["sum"]), int(r["count"])) for u, r in g.iterrows() if 0 < r["sum"] < r["count"]}

    # população de referência (mediana dos anos disponíveis) → porte do município
    porte = None
    if POP_ID in registry:
        p = mun[mun.ind == POP_ID].pivot_table(index="cod", columns="ano", values="valor", observed=True)
        ref = p.median(axis=1)
        porte = pd.cut(ref, [b[1] for b in PORTES] + [float("inf")], right=False,
                       labels=[b[0] for b in PORTES]).astype(str).rename("porte")

    carac = load_caracterizacao()

    # último ano com dado de cada indicador (em qualquer nível): base do modo "mais recente" do painel
    latest = long[long.valor.notna()].groupby("ind", observed=True).ano.max()

    axis_meta = json.loads((ASSETS / "indicators.json").read_text(encoding="utf-8"))
    return {
        "long": long,
        "registry": registry,
        "indicators": inds,
        "porte": porte,
        "carac": carac,
        "latest": {str(k): int(v) for k, v in latest.items()},
        "ufs": sorted(set(al_ufs) | est_ufs),
        "al_ufs": al_ufs,
        "al_parcial": al_parcial,
        # indicadores com valor da parcela do estado na Amazônia Legal (nível "Estado (parte AL)"); os publicados só
        # para o estado inteiro (ex.: IDHM) ficam de fora
        "al_parte_ind": {str(i) for i in long.loc[(long.nivel == PARTE_AL) & long.valor.notna(), "ind"].unique()},
        "meta": {f["id"]: f for f in fichas},
        "axis_colors": axis_meta.get("axisColors", {}),
        "axis_desc": axis_meta.get("axisDescriptions", {}),
        "manifest": manifest,
        "pop_col": POP_ID if POP_ID in inds else None,
        "n_mun": int(mun.cod.nunique()),
        "n_mun_al": int(mun.loc[mun.al.fillna(False).astype(bool), "cod"].nunique()),
    }


def load_caracterizacao() -> pd.DataFrame | None:
    """Agrupamentos dos municípios (gerados por scripts/caracterizacao.py), indexados pelo código IBGE.
    Nomes de regiões se repetem entre UFs, por isso levam a UF entre parênteses."""
    path = ASSETS / "municipios_caracterizacao.csv"
    if not path.exists():
        return None
    c = pd.read_csv(path)
    for col in ("rg_intermediaria", "rg_imediata"):
        c[col] = c[col] + " (" + c.uf + ")"
    return c.set_index("cod")


# Filtros por agrupamento: coluna da caracterização → rótulo na barra lateral
AGRUPAMENTOS = {
    "rg_intermediaria": "Região Geográfica Intermediária",
    "rg_imediata": "Região Geográfica Imediata",
    "pndr": "Tipologia PNDR",
    "idhm": "Classe do IDHM (2010)",
}
# filtros Sim/Não (colunas booleanas)
AGRUPAMENTOS_SN = {"fronteira": "Município de fronteira", "sede_imediata": "Sede de região imediata"}
ORDEM_CLASSES = ["Muito baixo", "Baixo", "Médio", "Alto", "Muito alto"]


# --------------------------------------------------------------------------- #
# Consultas
# --------------------------------------------------------------------------- #
def years_with_data(D: dict, ind: str) -> list[int]:
    d = D["long"]
    s = d.loc[(d.ind == ind) & d.valor.notna(), "ano"]
    return sorted(s.unique().tolist())


def snapshot(D: dict, level: str, ind: str, year: int, *, al_only=False, ufs=None, portes=None,
             grupos=None, parte_al=False) -> pd.DataFrame:
    """Territórios de um nível em um ano, já com os filtros do painel aplicados.

    parte_al: nos estados só em parte na Amazônia Legal (ex.: Maranhão), troca o valor do estado inteiro pelo da parcela
    que fica na região, quando o indicador tem esse cálculo. A coluna `parcela` diz em quais linhas isso aconteceu."""
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
    if level == "Município" and grupos and D["carac"] is not None:
        for col, vals in grupos.items():
            d = d[d.cod.map(D["carac"][col]).isin(vals)]
    for c in ("nivel", "ind", "uf", "regiao", "nome", "label", "tid"):
        d[c] = d[c].astype(str)
    d["parcela"] = False
    if level == "Estado" and parte_al and D["al_parcial"]:
        p = D["long"]
        p = p[(p.nivel == PARTE_AL) & (p.ind == ind) & (p.ano == year) & p.valor.notna()]
        valores = dict(zip(p.cod.astype(int), p.valor))
        d["parcela"] = d.cod.isin(valores)
        d.loc[d.parcela, "valor"] = d.loc[d.parcela, "cod"].map(valores)
    return d.reset_index(drop=True)


def series(D: dict, tids, ind: str) -> pd.DataFrame:
    """Série de cada território. A base só guarda células com valor; aqui os anos do indicador sem dado no
    território voltam como vazios (valor NaN), para os gráficos e avisos de lacunas."""
    d = D["long"]
    d = d[d.tid.isin(list(tids)) & (d.ind == ind)]
    d = d.assign(label=d.label.astype(str), tid=d.tid.astype(str), nivel=d.nivel.astype(str))
    d = d[["tid", "nivel", "label", "ano", "valor"]]
    anos = years_with_data(D, ind)
    if len(d) and anos:
        terr = d.drop_duplicates("tid")[["tid", "nivel", "label"]]
        grade = terr.merge(pd.DataFrame({"ano": anos}), how="cross")
        d = grade.merge(d[["tid", "ano", "valor"]], on=["tid", "ano"], how="left")
    return d.sort_values(["tid", "ano"]).reset_index(drop=True)


def territories(D: dict, level: str) -> pd.DataFrame:
    d = D["long"]
    d = d[(d.nivel == level) & (d.ind == D["indicators"][0])].drop_duplicates("tid")
    d = d[["tid", "label", "uf", "cod"]].copy()
    for c in ("tid", "label", "uf"):
        d[c] = d[c].astype(str)
    return d.sort_values("label").reset_index(drop=True)


def n_bands(n: int) -> int:
    """Nº de faixas: 5 quando há territórios para isso; só 3 com poucos (ex.: 9 estados), para não ter faixa de um."""
    return 5 if n >= 20 else 3


def _quantis(values: pd.Series, k: int) -> pd.Series:
    b = pd.qcut(values, k, labels=False, duplicates="drop") if values.nunique() > 1 else None
    return pd.Series(0, index=values.index) if b is None else b.astype(int)


def bands(values: pd.Series, k: int | None = None) -> pd.Series:
    """Faixas por quantis (0 = menores valores … última = maiores). Valores iguais ficam na mesma faixa.
    Se um mesmo valor extremo (ex.: zero) reúne ao menos 1/k dos territórios, ele ganha uma faixa própria e o
    resto se divide nas demais; senão, valores repetidos reduzem o nº de faixas. As faixas saem numeradas sem
    buracos (0, 1, 2…), para mapa, legenda e tabela usarem as mesmas cores."""
    b = _bands(values, k)
    return (b.rank(method="dense").astype(int) - 1) if len(b) else b


def _bands(values: pd.Series, k: int | None = None) -> pd.Series:
    k = k or n_bands(len(values))
    top = values.value_counts().index[0]
    if k > 2 and values.nunique() > 2 and (values == top).mean() >= 1 / k and top in (values.min(), values.max()):
        tie = values == top
        rest = _quantis(values[~tie], k - 1)
        out = pd.Series(0, index=values.index)
        if top == values.min():
            out[~tie] = rest + 1
        else:
            out[~tie], out[tie] = rest, int(rest.max()) + 1
        return out
    return _quantis(values, k)


def band_ranges(values: pd.Series, k: int | None = None) -> list[tuple[float, float, int]]:
    """(mínimo, máximo, nº de territórios) de cada faixa, do menor ao maior valor."""
    b = bands(values, k)
    return [(values[b == i].min(), values[b == i].max(), int((b == i).sum())) for i in sorted(b.unique())]


def cagr(first: float, last: float, years: int) -> float:
    if fmt.isna(first) or fmt.isna(last) or first <= 0 or years <= 0:
        return float("nan")
    return ((last / first) ** (1 / years) - 1) * 100


def ranks(values: pd.Series, polarity: int) -> pd.Series:
    """Posição de cada território: 1º = melhor situação (maior valor se 'maior é melhor', menor valor se 'menor é
    melhor'); sem polaridade, 1º = maior valor. Empatados recebem a mesma posição (1º, 1º, 3º…)."""
    return values.rank(method="min", ascending=polarity < 0).astype(int)


def rank_rule(polarity: int) -> str:
    return {1: "1º = maior valor (melhor situação)", -1: "1º = menor valor (melhor situação)"}.get(
        polarity, "1º = maior valor (indicador sem polaridade)")


def position(values: pd.Series, v: float, polarity: int) -> tuple[int, int]:
    """Posição de v entre `values` pela regra de `ranks`, e quantos territórios têm o mesmo valor (empate)."""
    import numpy as np
    igual = np.isclose(values, v)
    melhor = (values < v) if polarity < 0 else (values > v)
    return int((melhor & ~igual).sum()) + 1, int(igual.sum())


def position_txt(values: pd.Series, v: float, polarity: int) -> str:
    """'3º de 9' ou '=3º de 9' quando a posição é dividida com outro território."""
    p, emp = position(values, v, polarity)
    return ("=" if emp > 1 else "") + f"{p}º de {len(values):,}".replace(",", ".")
