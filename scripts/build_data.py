"""Gera as bases do painel a partir da planilha Excel do PRDA.

Uso:
    python scripts/build_data.py                  # usa o .xlsx mais recente de data/
    python scripts/build_data.py caminho.xlsx
    python scripts/build_data.py --cobertura-minima 80     # limite padrão da Amazônia Legal (%)

Lê as abas de recorte (Municipal, Estadual, Regional, Brasil) e a "Lista de Indicadores", filtra os
indicadores de config/indicadores.toml, valida e grava em build/:

    dados.parquet  tabela longa: nivel, cod, nome, uf, regiao, al, ano, ind (ID da ficha), valor
    fichas.json    ficha e formato de exibição de cada indicador
    manifest.json  versão da base, planilha de origem e avisos da validação

Esses três arquivos vão para a pasta painel/ do bucket. Se a validação encontrar erros, nada é gravado.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import tomllib
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "build"
CONFIG = ROOT / "config" / "indicadores.toml"
GEO_MUN = ROOT / "assets" / "geo" / "mun.json"
CENSO = ROOT / "assets" / "censo_municipios.csv"  # população dos Censos 2010 e 2022 (scripts/censo_ibge.py)
CAMPOS_CENSO = {"pop_total": "população do Censo", "pop_urbana": "população urbana do Censo",
                "pop_0_14": "população de 0 a 14 anos do Censo", "pop_15_64": "população de 15 a 64 anos do Censo",
                "pop_65_mais": "população de 65 anos ou mais do Censo"}
# totais por município e ano que a planilha não traz, gerados por scripts próprios a partir das tabulações das fontes:
# numerador e denominador das razões (`numerador_<fonte>` e `peso_<fonte>` em config/indicadores.toml)
TOTAIS_EXTERNOS = {
    "rais": (ROOT / "assets" / "rais_vinculos_municipios.csv",
             "python scripts/rais_vinculos.py <tabulação> --ano <ano>",
             {"total": "vínculos formais ativos em 31/12 (RAIS)",
              "superior": "vínculos com superior completo, mestrado ou doutorado (RAIS)"}),
    "sim": (ROOT / "assets" / "mortalidade_infantil_municipios.csv",
            "python scripts/sim_sinasc.py <óbitos infantis> <nascidos vivos>",
            {"obitos": "óbitos de menores de 1 ano (SIM)", "nascidos": "nascidos vivos (SINASC)"}),
    "ripsa": (ROOT / "assets" / "populacao_ripsa_municipios.csv",
              "python scripts/populacao_ripsa.py <tabulação da RIPSA>",
              {"pop": "população residente da RIPSA (estimativas do Ministério da Saúde)"}),
    # sem coluna de ano: o mesmo valor serve de peso em todos os anos do indicador
    "ana": (ROOT / "assets" / "seguranca_hidrica_ana_municipios.csv",
            "python scripts/seguranca_hidrica_ana.py",
            {"pop_urbana": "população urbana de 2020 da planilha da ANA (Atlas Águas)"}),
    "pib": (ROOT / "assets" / "valor_adicionado_municipios.csv",
            "python scripts/valor_adicionado_ibge.py",
            {"va_total": "valor adicionado bruto total do município (PIB dos Municípios/IBGE)"}),
}
# totais por grupo (ex.: uma razão por vacina) para a regra "media_razoes": a razão de cada grupo é a soma do
# numerador ÷ a soma do denominador nos municípios do recorte, e o valor é a média simples entre os grupos
TOTAIS_POR_GRUPO = {
    "vacinas": (ROOT / "assets" / "cobertura_vacinal_municipios.csv",
                "python scripts/cobertura_vacinal.py <planilha.xlsx> --ano <ano>",
                "vacina", "doses", "populacao_alvo", "doses aplicadas ÷ população-alvo de cada vacina"),
}

LISTA = "Lista de Indicadores"
LISTA_HEADER_ROW = 4  # linhas 0–3 são título e grupos de colunas
SHEETS = {"Município": "Recorte Municipal", "Estado": "Recorte Estadual",
          "Grande Região": "Recorte Regional", "Brasil": "Recorte Brasil"}
NAME_COL = {"Município": "Município", "Estado": "Estado", "Grande Região": "Grande Região", "Brasil": "Território"}
REGIONS = {1: "Norte", 2: "Nordeste", 3: "Sudeste", 4: "Sul", 5: "Centro-Oeste"}
MIN_COVER = 90.0  # % mínima dos municípios da Amazônia Legal com dado para calcular o agregado de um ano
MISSING_MARKS = {"", "-", "—", "–", "...", "..", "x", "X", "nan", "None"}

# coluna da "Lista de Indicadores" -> chave em fichas.json
FICHA = {
    "Indicador": "name", "Descrição do Indicador": "description", "Fórmula / Forma de Cálculo": "formula", "Eixo P1": "axis", "Tema": "theme",
    "Subtema": "subtheme", "Eixo(s) PRDA Relacionado(s)": "prda", "Unidade de Medida": "unit",
    "Polaridade": "polarity", "Fonte dos Dados": "source", "Periodicidade": "periodicity",
    "Série Histórica Disponível": "series", "Ano de Referência mais Recente": "latest",
    "Código da Tabela/Série": "table", "Link para a Base de Dados": "link",
    "Limitações Metodológicas": "limits", "Menor Unidade Territorial Disponível": "minTerritory",
    "Cobertura Municipal (%)": "coverage", "Regra de Agregação Territorial": "aggregation",
    "Variável de Ponderação": "weight", "Comparabilidade Temporal": "temporal", "Observação": "note",
}


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def cell(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip() or "—"


def title_name(s: pd.Series) -> pd.Series:
    return s.str.title().str.replace(r"\b(D[aeo]s?|E)\b", lambda m: m.group(0).lower(), regex=True)


# --------------------------------------------------------------------------- #
# Configuração e fichas
# --------------------------------------------------------------------------- #
def load_config(path: Path = CONFIG) -> list[dict]:
    cfg = tomllib.loads(path.read_text(encoding="utf-8"))
    items = cfg.get("indicador", [])
    for it in items:
        it.setdefault("chave", it["id"])  # várias entradas podem vir da mesma ficha (uma por categoria)
    chaves = [i["chave"] for i in items]
    dup = {i for i in chaves if chaves.count(i) > 1}
    if dup:
        sys.exit(f"{path.name}: chaves repetidas: {', '.join(sorted(dup))} (use `chave` para distinguir entradas da "
                 "mesma ficha)")
    return items


def read_lista(book: pd.ExcelFile) -> pd.DataFrame:
    df = book.parse(LISTA, header=LISTA_HEADER_ROW)
    df = df.dropna(subset=["ID"])
    df["ID"] = df["ID"].astype(str).str.strip()
    return df.set_index("ID")


def make_ficha(item: dict, row: pd.Series) -> dict:
    """Ficha da entrada no painel, com metadados próprios quando a ficha reúne séries de fontes distintas."""
    overrides = item.get("ficha", {})
    unknown = set(overrides) - set(FICHA)
    if unknown:
        raise ValueError("campos desconhecidos em `ficha`: " + ", ".join(sorted(unknown)))
    return {"id": item["chave"], "ref": item["id"],
            **{k: cell(overrides.get(c, row.get(c))) for c, k in FICHA.items()}}


def agg_rule(text: str) -> str | None:
    t = norm(text)
    if t.startswith("soma"):
        return "soma"
    if t.startswith("media simples"):
        return "media_simples"
    if t.startswith("dado ja publicado"):
        return "publicado"  # valor oficial já pronto na fonte: não se agrega a partir dos municípios
    if "razao entre totais" in t or "media ponderada" in t:
        return "media_ponderada"
    return None


def display_spec(item: dict, ficha: dict, rule: str) -> dict:
    unit = item.get("unidade", ficha["unit"])
    default_fmt = "percentual" if "%" in unit else "moeda" if unit.strip().upper().startswith("R$") else "numero"
    formato = item.get("formato", default_fmt)
    # somável (participação no total, escala log): regra "soma" ou ficha que manda somar, mesmo quando a Amazônia
    # Legal fica sem valor (ex.: dado só por estado); `aditivo` no config decide quando a ficha engana. Percentual nunca
    # é somável por padrão: a ficha às vezes manda somar o numerador (ex.: valor adicionado da agropecuária)
    somavel = bool(item.get("aditivo", formato != "percentual" and (
        rule in ("soma", "soma_estados", "soma_com_sem_municipio")
        or (rule == "publicado" and norm(ficha["aggregation"]).startswith("soma")))))
    casas = item.get("casas", {"percentual": 1, "moeda": 0}.get(formato, 0 if somavel else 2))
    pol = norm(ficha["polarity"])
    return {
        "label": item.get("rotulo", ficha["name"]),
        "unit": unit,
        "format": formato,
        "decimals": int(casas),
        "scale": float(item.get("escala", 1)),
        "log": bool(item.get("log", somavel)),
        "additive": somavel,
        "polarity": 1 if pol.startswith("maior") else -1 if pol.startswith("menor") else 0,
        "icon": item.get("icone", {"percentual": "%", "moeda": "R$"}.get(formato, "●")),
        # ressalvas exibidas com o valor: ano que não é o de dezembro (ex.: "set./2026"), variação que não se compara
        # e aviso curto sobre o que o número conta
        "yearLabels": {str(a): str(t) for a, t in item.get("rotulo_ano", {}).items()},
        "noChange": item.get("sem_variacao", ""),
        "caveat": item.get("ressalva", ""),
        # leitura de magnitude: contagens e participações que não se comparam com as referências como taxas (ex.: rotas
        # do estado × rotas da região; participação do estado × Brasil = 100%); sem desempenho, como os totais
        "magnitude": somavel or item.get("leitura") == "magnitude",
        # quebra de método: a variação só compara anos do mesmo trecho (ano em que o trecho novo começa e o motivo)
        **({"break": {"ano": int(item["quebra"]["ano"]), "trecho": item["quebra"].get("trecho", ""),
                      "motivo": item["quebra"]["motivo"]}} if item.get("quebra") else {}),
    }


# --------------------------------------------------------------------------- #
# Abas de recorte
# --------------------------------------------------------------------------- #
CAT = " — "  # separador entre o nome do indicador e a categoria nas colunas das abas de recorte


def resolve_columns(header: list[str], wanted: dict[str, str | tuple]) -> dict[str, list[str] | None]:
    """wanted: chave -> nome esperado da coluna, "nome — *" para somar todas as categorias do indicador, ou uma tupla
    de nomes para somar só essas colunas. Devolve chave -> colunas reais (ou None)."""
    by_norm: dict[str, str] = {}
    for c in header:
        by_norm.setdefault(norm(c), c)
    out = {}
    for i, name in wanted.items():
        if isinstance(name, tuple):
            cs = [by_norm.get(norm(n)) for n in name]
            out[i] = cs if all(cs) else None
        elif name.endswith(CAT + "*"):
            pre = norm(name[:-len(CAT + "*")])
            cs = [c for c in header if CAT in c and norm(c.split(CAT, 1)[0]) == pre]
            out[i] = cs or None
        else:
            c = by_norm.get(norm(name))
            out[i] = [c] if c else None
    return out


def to_numeric(s: pd.Series, label: str, rep: Report) -> pd.Series:
    v = pd.to_numeric(s, errors="coerce")
    raw = s[s.notna() & v.isna()].astype(str).str.strip()
    bad = raw[~raw.isin(MISSING_MARKS)]
    if len(bad):
        filled = int(s.notna().sum())
        msg = (f"{label}: {len(bad)} células não numéricas tratadas como vazias "
               f"(ex.: {', '.join(map(repr, bad.unique()[:3]))})")
        (rep.error if len(bad) > 0.05 * filled else rep.warn)(msg)
    return v


def read_level(book: pd.ExcelFile, level: str, wanted: dict[str, str], rep: Report,
               factors: dict[str, float] | None = None) -> pd.DataFrame:
    sheet = SHEETS[level]
    header = [str(c) for c in book.parse(sheet, nrows=0).columns]
    if "Ano" not in header:
        rep.error(f"Aba '{sheet}': coluna 'Ano' não encontrada.")
        return pd.DataFrame()
    ids = header[:header.index("Ano")]
    cols = resolve_columns(header[header.index("Ano") + 1:], wanted)
    for i, c in cols.items():
        if c is None:
            # ausência em um nível é aviso; só vira erro se o indicador não aparecer em nenhuma aba (ver main)
            rep.warn(f"{i}: coluna {wanted[i]!r} não encontrada na aba '{sheet}' (indicador fica sem dado neste nível; "
                     "use `coluna` em config/indicadores.toml se o nome for diferente).")
    found = {i: c for i, c in cols.items() if c}
    df = book.parse(sheet, usecols=ids + ["Ano"] + sorted({c for cs in found.values() for c in cs}))
    out = pd.DataFrame({"cod": pd.to_numeric(df[ids[0]], errors="coerce"),
                        "ano": pd.to_numeric(df["Ano"], errors="coerce")})
    if out.isna().any().any():
        rep.error(f"Aba '{sheet}': {int(out.isna().any(axis=1).sum())} linhas sem código ou ano válidos.")
        out = out.dropna()
    out = out.astype("int64")
    df = df.loc[out.index]
    dups = out.duplicated(["cod", "ano"]).sum()
    if dups:
        rep.error(f"Aba '{sheet}': {dups} linhas repetidas para o mesmo território e ano.")
    if level == "Município":
        out["nome"] = title_name(df["Município"].astype(str))
        out["uf"] = df["Estado"].astype(str).str.strip()
        flag = df["Amazônia Legal"].astype(str).str.strip().str.upper()
        odd = sorted(set(flag) - {"SIM", "NÃO", "NAO"})
        if odd:
            rep.error(f"Aba '{sheet}': valores inesperados em 'Amazônia Legal': {odd}")
        out["al"] = flag.eq("SIM")
    else:
        out["nome"] = df[NAME_COL[level]].astype(str).str.strip()
    vals = {}
    for i, cs in found.items():
        v = pd.concat([to_numeric(df[c], f"{i} ({sheet})", rep) for c in cs], axis=1)
        vals[i] = v.iloc[:, 0] if len(cs) == 1 else v.sum(axis=1, min_count=1)  # soma das categorias
        if level == "Município" and factors and i in factors:
            vals[i] = vals[i] * factors[i]  # ex.: 0/1 por município -> 0/100, como nas abas Estadual/Regional/Brasil
    return pd.concat([out, pd.DataFrame(vals, index=out.index)], axis=1)


# --------------------------------------------------------------------------- #
# Amazônia Legal
# --------------------------------------------------------------------------- #
def taxa_censo(cods, censo: pd.DataFrame) -> float:
    """Taxa média geométrica anual de crescimento da população entre os Censos de 2010 e 2022 (12 anos), recalculada a
    partir dos totais dos municípios `cods`, como manda a ficha: [(pop 2022 ÷ pop 2010)^(1/12) − 1] × 100.
    Municípios criados depois de 2010 não têm população em 2010 (ela está contada no município de origem), então o total
    de 2010 soma os que já existiam e o de 2022 soma todos; o conjunto é o mesmo território nos dois anos."""
    c = censo[censo.cod.isin(set(cods))]
    p10, p22 = c.loc[c.ano == 2010, "pop_total"].sum(), c.loc[c.ano == 2022, "pop_total"].sum()
    return float(((p22 / p10) ** (1 / 12) - 1) * 100) if p10 > 0 and p22 > 0 else float("nan")


def interpolated(mun: pd.DataFrame, col: str) -> pd.DataFrame:
    """Peso por município × ano, com anos sem dado interpolados (linear) ou repetidos nas pontas."""
    p = mun.pivot(index="cod", columns="ano", values=col).sort_index(axis=1)
    return p.interpolate(axis=1, method="index", limit_direction="both")


def years_text(years) -> str:
    ys = sorted(int(y) for y in years)
    runs, start = [], 0
    for k in range(1, len(ys) + 1):
        if k == len(ys) or ys[k] != ys[k - 1] + 1:
            runs.append(str(ys[start]) if k - start == 1 else f"{ys[start]}–{ys[k - 1]}")
            start = k
    return ", ".join(runs)


def amazonia_legal(mun: pd.DataFrame, rules: dict[str, tuple[str, str | None]], minimos: dict[str, float],
                   rep: Report, rotulo: str = "Amazônia Legal", razoes: dict[str, tuple[str, float]] | None = None) -> pd.DataFrame:
    """Agrega os municípios da Amazônia Legal presentes em `mun`. Em cada ano, só publica o valor se a cobertura
    (municípios com dado ÷ municípios da Amazônia Legal em `mun`) alcançar o mínimo do indicador; abaixo disso
    fica vazio. Passando só os municípios de um estado, calcula a parcela desse estado na região (`rotulo` nomeia
    o recorte nos avisos).
    razoes: para a regra "razao_totais", chave -> (indicador do numerador, fator): total do numerador nos municípios da
    região dividido pelo total do peso (com os anos sem dado interpolados) × fator. Para "media_razoes", chave ->
    (lista de pares de colunas numerador/denominador, fator): média simples das razões de cada par × fator."""
    al = mun[mun.al]
    n_al = al.cod.nunique()
    years = sorted(mun.ano.unique())
    out = pd.DataFrame({"ano": years})
    cols: dict[str, pd.Series] = {}  # montadas à parte e unidas no fim (evita fragmentar o DataFrame)
    for i, (rule, peso) in rules.items():
        if rule in ("publicado", "soma_estados", "taxa_censo", "soma_com_sem_municipio"):  # preenchidas depois (ver main)
            cols[i] = pd.Series(np.nan, index=out.index)
            continue
        if rule == "razao_totais":
            num, fator = (razoes or {})[i]
            if num not in al or peso not in al or al[num].notna().sum() == 0:
                cols[i] = pd.Series(np.nan, index=out.index)
                continue
            s_num = al.groupby("ano")[num].sum(min_count=1)
            w = interpolated(al, peso)
            s_peso = w.sum(min_count=1).reindex(s_num.index)
            # só os anos em que a razão sai (com numerador): nos demais, o peso interpolado não é usado
            filled = sorted(int(y) for y in w.columns if al.pivot(index="cod", columns="ano", values=peso)[y].isna().any()
                            and w[y].notna().any() and pd.notna(s_num.get(y)))
            if filled:
                rep.warn(f"{i}: peso {peso} interpolado para calcular a {rotulo} em {years_text(filled)}.")
            cols[i] = out.ano.map((s_num / s_peso.where(s_peso > 0) * fator))
            continue
        if rule == "media_razoes":
            pares, fator = (razoes or {}).get(i, ([], 1))
            razoes_grupo = pd.concat([al.groupby("ano")[n].sum(min_count=1) / al.groupby("ano")[d].sum(min_count=1).where(lambda x: x > 0)
                                      for n, d in pares if n in al and d in al], axis=1) if pares else pd.DataFrame()
            cols[i] = out.ano.map(razoes_grupo.mean(axis=1) * fator) if len(razoes_grupo.columns) else pd.Series(np.nan, index=out.index)
            continue
        if i not in al or al[i].notna().sum() == 0 or (rule == "media_ponderada" and peso not in al):
            cols[i] = pd.Series(np.nan, index=out.index)  # sem dado municipal (ou sem o peso): o resumo final avisa que falta a Amazônia Legal
            continue
        if rule == "soma":
            s = al.groupby("ano")[i].sum(min_count=1)
            n = al.groupby("ano")[i].count()
        elif rule == "media_simples":
            s = al.groupby("ano")[i].mean()
            n = al.groupby("ano")[i].count()
        else:
            v = al.pivot(index="cod", columns="ano", values=i)
            w_raw = mun.pivot(index="cod", columns="ano", values=peso).reindex(index=v.index, columns=v.columns)
            w = interpolated(al, peso).reindex(index=v.index, columns=v.columns)
            ok = v.notna() & w.notna()
            s = (v * w).where(ok).sum(min_count=1) / w.where(ok).sum(min_count=1)
            n = ok.sum()
            filled = sorted(int(y) for y in v.columns if (v[y].notna() & w_raw[y].isna() & w[y].notna()).any())
            if filled:
                rep.warn(f"{i}: peso {peso} interpolado para calcular a Amazônia Legal em {filled}.")
        cover = (n / n_al * 100).reindex(s.index).fillna(0)
        minimo = minimos[i]
        low = s.notna() & (cover < minimo)
        if low.any():
            detail = ", ".join(f"{int(y)} ({cover[y]:.0f}%)" for y in s.index[low][:6])
            more = f" e mais {int(low.sum()) - 6}" if low.sum() > 6 else ""
            rep.warn(f"{i}: {rotulo} não calculada em {years_text(s.index[low])}: cobertura municipal abaixo de "
                     f"{minimo:g}% ({detail}{more}). Ajuste `cobertura_minima` em config/indicadores.toml se o "
                     "valor ainda fizer sentido.")
            s = s.mask(low)
        cols[i] = out.ano.map(s)
    out = pd.concat([out, pd.DataFrame(cols, index=out.index)], axis=1)
    out["cod"], out["nome"], out["uf"] = 0, "Amazônia Legal", None
    return out


# desvio relativo (mediana dos anos) tolerado entre a estimativa do estado inteiro e o valor publicado: o mesmo limite
# da conferência das aproximações da Amazônia Legal (README, "Conferência da regra": mediana até 1,5%)
TOL_PARTE = 0.015


def desvio_estimativa(estimado: pd.Series, publicado: pd.Series, formato: str) -> tuple[bool, str] | None:
    """Compara, ano a ano, o valor do estado inteiro estimado pela regra de agregação com o publicado. Devolve
    (descartar, descrição) ou None sem ano em comum. O desvio é a mediana das diferenças absolutas sobre a mediana do
    valor publicado (robusto a anos isolados e a valores perto de zero)."""
    a = pd.concat([estimado.rename("e"), publicado.rename("p")], axis=1).dropna()
    if a.empty:
        return None
    dif = (a.e - a.p).abs().median()
    base = a.p.abs().median()
    rel = dif / base if base > 0 else (0 if dif == 0 else float("inf"))
    descartar = rel > TOL_PARTE
    num = lambda x: f"{x:.3g}".replace(".", ",") + ("%" if formato == "percentual" else "")  # noqa: E731
    return descartar, (f"desvio mediano de {rel:.0%} em {len(a)} ano{'s' if len(a) != 1 else ''}; em "
                       f"{int(a.index[-1])}, {num(a.e.iloc[-1])} estimado contra {num(a.p.iloc[-1])} publicado")


# --------------------------------------------------------------------------- #
# Principal
# --------------------------------------------------------------------------- #
def find_xlsx(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    # ignora arquivos temporários do Excel e versões guardadas como ANTIGA
    files = [p for p in DATA_DIR.glob("*.xlsx") if not p.name.startswith(("~$", ".~lock")) and "ANTIGA" not in p.name.upper()]
    if not files:
        sys.exit(f"Nenhum .xlsx encontrado em {DATA_DIR}")
    return max(files, key=lambda p: p.stat().st_mtime)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("planilha", nargs="?", help="caminho do .xlsx (padrão: o mais recente em data/)")
    ap.add_argument("--cobertura-minima", type=float, default=MIN_COVER, metavar="%",
                    help=f"cobertura municipal mínima (%%) para calcular a Amazônia Legal em um ano (padrão {MIN_COVER:g})")
    ap.add_argument("--config", type=Path, default=CONFIG, help="lista de indicadores (padrão: config/indicadores.toml)")
    args = ap.parse_args()
    xlsx = find_xlsx(args.planilha)
    items = load_config(args.config)
    rep = Report()

    print(f"Planilha: {xlsx.name}\nLendo abas (pode levar alguns minutos)…")
    book = pd.ExcelFile(xlsx, engine="openpyxl")
    lista = read_lista(book)

    # fichas, regras de agregação e colunas a ler
    rules: dict[str, tuple[str, str | None]] = {}
    minimos: dict[str, float] = {}
    fichas: list[dict] = []
    chaves = {it["chave"] for it in items}
    pesos_coluna: dict[str, str] = {}  # pesos lidos direto de uma coluna da planilha (`peso_coluna`), sem ficha própria
    pesos_censo: dict[str, str] = {}  # pesos que vêm do arquivo do Censo (`peso_censo`): chave -> campo de CAMPOS_CENSO
    razoes: dict[str, tuple[str, float]] = {}  # razao_totais: chave -> (indicador do numerador, fator)
    medias_razoes: dict[str, tuple[str, float]] = {}  # media_razoes: chave -> (fonte de TOTAIS_POR_GRUPO, fator)
    campos_ext: dict[str, tuple[str, str]] = {}  # totais de TOTAIS_EXTERNOS (`numerador_rais`, `peso_sim`...): chave -> (fonte, campo)
    pesos_implicitos: dict[str, tuple[str, str]] = {}  # `peso_implicito`: peso -> (numerador, indicador); peso = numerador ÷ valor
    for it in items:
        i, ref = it["chave"], it["id"]
        if ref not in lista.index:
            rep.error(f"{i}: ID {ref} não existe na aba '{LISTA}'.")
            continue
        row = lista.loc[ref]
        try:
            ficha = make_ficha(it, row)
        except ValueError as exc:
            rep.error(f"{i}: {exc}.")
            continue
        if it.get("categoria") or it.get("categorias"):
            ficha["category"] = it.get("categoria") or " + ".join(it["categorias"])
        rule = it.get("agregacao") or agg_rule(ficha["aggregation"])
        peso = it.get("peso")
        if it.get("peso_coluna"):
            peso = f"{i}#peso"
            pesos_coluna[peso] = it["peso_coluna"]
        if it.get("peso_censo"):
            if it["peso_censo"] not in CAMPOS_CENSO:
                rep.error(f"{i}: peso_censo '{it['peso_censo']}' desconhecido (use um de {', '.join(CAMPOS_CENSO)}).")
                continue
            peso = f"{i}#censo"
            pesos_censo[peso] = it["peso_censo"]
        if it.get("peso_implicito"):
            # denominador implícito de cada município: numerador ÷ valor da razão (ex.: PIB ÷ PIB per capita = a população
            # que o IBGE usou); a média ponderada por ele é a soma dos numeradores ÷ a soma dos denominadores
            peso = f"{i}#implicito"
            pesos_implicitos[peso] = (it["peso_implicito"], i)
        # totais externos: numerador e denominador da razão vêm do arquivo da fonte, só nos anos que ele tem (sem interpolar)
        for fonte, (_, _, campos) in TOTAIS_EXTERNOS.items():
            for papel in ("numerador", "peso"):
                campo = it.get(f"{papel}_{fonte}")
                if not campo:
                    continue
                if campo not in campos:
                    rep.error(f"{i}: {papel}_{fonte} '{campo}' desconhecido (use um de {', '.join(campos)}).")
                    continue
                k = f"{i}#{fonte}_{campo}"
                campos_ext[k] = (fonte, campo)
                if papel == "peso":
                    peso = k
                else:
                    it["numerador"] = k
        if rule not in ("soma", "soma_estados", "soma_com_sem_municipio", "taxa_censo", "media_ponderada", "media_simples",
                        "razao_totais", "media_razoes", "publicado"):
            rep.error(f"{i}: regra de agregação '{ficha['aggregation']}' não reconhecida — defina `agregacao` "
                      "em config/indicadores.toml.")
            continue
        if it.get("leitura") not in (None, "magnitude"):
            rep.error(f"{i}: leitura '{it['leitura']}' desconhecida (o único valor aceito é \"magnitude\").")
            continue
        if it.get("quebra") is not None and not (isinstance(it["quebra"], dict) and it["quebra"].get("ano")
                                                 and it["quebra"].get("motivo")):
            rep.error(f"{i}: `quebra` precisa de `ano` e `motivo` (ex.: {{ ano = 2025, trecho = \"…\", motivo = \"…\" }}).")
            continue
        if rule == "media_ponderada" and not peso:
            rep.error(f"{i}: média ponderada exige `peso` em config/indicadores.toml "
                      f"(a ficha cita: '{ficha['weight']}').")
            continue
        if rule == "razao_totais":
            if not (it.get("numerador") and peso):
                rep.error(f"{i}: razao_totais exige `numerador` (chave de outro indicador) e `peso` (o denominador).")
                continue
            razoes[i] = (it["numerador"], float(it.get("fator", 1)))
        if rule == "media_razoes":
            if it.get("razoes_de") not in TOTAIS_POR_GRUPO:
                rep.error(f"{i}: media_razoes exige `razoes_de` (um de {', '.join(TOTAIS_POR_GRUPO)}).")
                continue
            medias_razoes[i] = (it["razoes_de"], float(it.get("fator", 1)))
        if (peso and peso not in lista.index and peso not in chaves and peso not in pesos_coluna
                and peso not in pesos_censo and peso not in campos_ext and peso not in pesos_implicitos):
            rep.error(f"{i}: peso {peso} não existe na aba '{LISTA}' nem em config/indicadores.toml.")
            continue
        rules[i] = (rule, peso if rule in ("media_ponderada", "razao_totais") else None)
        minimos[i] = float(it.get("cobertura_minima", args.cobertura_minima))
        ficha["display"] = display_spec(it, ficha, rule)
        fichas.append(ficha)

    cfg_by_key = {it["chave"]: it for it in items}
    weights = {p for _, p in rules.values() if p and p not in pesos_censo}  # os do Censo não vêm da planilha
    weights |= {num for num, _ in razoes.values()}  # numeradores das razões também precisam ser lidos
    weights -= set(campos_ext)  # os totais externos também não
    weights -= set(pesos_implicitos)  # calculados depois, a partir do numerador
    weights |= {num for num, _ in pesos_implicitos.values()}

    def coluna(i: str) -> str:
        """Coluna de cada entrada: `coluna` explícita, a `categoria` da ficha ("Nome — Categoria"), todas as
        categorias somadas (`somar_categorias`) ou o próprio nome do indicador."""
        if i in pesos_coluna:
            return pesos_coluna[i]
        it = cfg_by_key.get(i, {})
        nome = lista.loc[it.get("id", i), "Indicador"]
        if "coluna" in it:
            return it["coluna"]
        if it.get("categoria"):
            return f"{nome}{CAT}{it['categoria']}"
        if it.get("categorias"):  # soma só das categorias listadas
            return tuple(f"{nome}{CAT}{c}" for c in it["categorias"])
        return f"{nome}{CAT}*" if it.get("somar_categorias") else nome

    wanted = {i: coluna(i) for i in [*rules, *sorted(weights - set(rules))]}

    def nome_peso(p: str) -> str:
        if p in pesos_implicitos:
            num, ind = pesos_implicitos[p]
            return f"denominador implícito de cada município ({nome_peso(num)} ÷ {lista.loc[cfg_by_key[ind]['id'], 'Indicador']})"
        if p in pesos_censo:
            return CAMPOS_CENSO[pesos_censo[p]] + " (SIDRA/IBGE)"
        if p in campos_ext:
            fonte, campo = campos_ext[p]
            return TOTAIS_EXTERNOS[fonte][2][campo]
        if p in pesos_coluna:
            return pesos_coluna[p].split(CAT)[-1]
        it = cfg_by_key.get(p)
        nome = it.get("rotulo") if it else None
        return f"{nome or lista.loc[p, 'Indicador']} ({p})"

    factors = {i["chave"]: float(i["fator_municipal"]) for i in items if "fator_municipal" in i}
    frames = {lvl: read_level(book, lvl, wanted, rep, factors) for lvl in SHEETS}
    if rep.errors:
        return finish(rep, None)

    mun, est, reg, bra = (frames[k] for k in ("Município", "Estado", "Grande Região", "Brasil"))
    ind_ids = list(rules)

    censo = None
    if pesos_censo or any(r == "taxa_censo" for r, _ in rules.values()):
        # população do Censo por município e ano (2010 e 2022): peso das médias ponderadas e base da taxa de crescimento
        if not CENSO.exists():
            rep.error(f"{CENSO.relative_to(ROOT)} não encontrado: rode `python scripts/censo_ibge.py`.")
            return finish(rep, None)
        censo = pd.read_csv(CENSO)
        if pesos_censo:
            extra = {k: censo.set_index(["cod", "ano"])[campo] for k, campo in pesos_censo.items()}
            chave = pd.MultiIndex.from_frame(mun[["cod", "ano"]])
            mun = pd.concat([mun, pd.DataFrame({k: v.reindex(chave).to_numpy() for k, v in extra.items()}, index=mun.index)],
                            axis=1)

    # totais externos por município e ano: numerador e denominador das razões; anos fora do arquivo ficam vazios
    chave = pd.MultiIndex.from_frame(mun[["cod", "ano"]])
    for fonte in sorted({f for f, _ in campos_ext.values()}):
        arquivo, comando = TOTAIS_EXTERNOS[fonte][:2]
        if not arquivo.exists():
            rep.error(f"{arquivo.relative_to(ROOT)} não encontrado: rode `{comando}`.")
            return finish(rep, None)
        tot = pd.read_csv(arquivo)
        # arquivo sem ano (ex.: população urbana de 2020 da ANA): o valor de cada município vale em todos os anos
        tot = tot.set_index(["cod", "ano"]) if "ano" in tot else tot.set_index("cod").reindex(chave.get_level_values(0)).set_axis(chave)
        mun = pd.concat([mun, pd.DataFrame({k: tot[c].reindex(chave).to_numpy(float)
                                            for k, (f, c) in campos_ext.items() if f == fonte}, index=mun.index)], axis=1)

    # totais por grupo (media_razoes): uma coluna de numerador e uma de denominador por grupo; anos fora do arquivo vazios
    for i, (fonte, fator) in medias_razoes.items():
        arquivo, comando, grupo, col_num, col_den, _ = TOTAIS_POR_GRUPO[fonte]
        if not arquivo.exists():
            rep.error(f"{arquivo.relative_to(ROOT)} não encontrado: rode `{comando}`.")
            return finish(rep, None)
        tot = pd.read_csv(arquivo)
        grupos = sorted(tot[grupo].unique())
        largo = tot.pivot_table(index=["cod", "ano"], columns=grupo, values=[col_num, col_den], aggfunc="sum")
        largo = largo.reindex(chave)
        novas, pares = {}, []
        for n, g in enumerate(grupos):
            kn, kd = f"{i}#{fonte}_{n}_num", f"{i}#{fonte}_{n}_den"
            novas[kn], novas[kd] = largo[(col_num, g)].to_numpy(float), largo[(col_den, g)].to_numpy(float)
            pares.append((kn, kd))
        mun = pd.concat([mun, pd.DataFrame(novas, index=mun.index)], axis=1)
        razoes[i] = (pares, fator)

    # taxas de transição (ex.: evasão de 2021/2022, gravada em 2022): o peso é o do ano inicial do par, ou seja, o valor
    # do ano anterior (`peso_ano_anterior`); no primeiro ano da série, sem o anterior, vale o mais próximo (interpolação)
    for it in items:
        if it.get("peso_ano_anterior") and it["chave"] in rules and rules[it["chave"]][1] in mun:
            p = rules[it["chave"]][1]
            anterior = mun.set_index(["cod", "ano"])[p]
            mun[p] = anterior.reindex(pd.MultiIndex.from_arrays([mun.cod, mun.ano - 1])).to_numpy()

    # pesos implícitos (`peso_implicito`): numerador ÷ valor de cada município, nos anos em que os dois existem
    for p, (num, ind) in pesos_implicitos.items():
        if num in mun and ind in mun:
            mun[p] = mun[num] / mun[ind].where(mun[ind] > 0)

    # municípios fora da malha do IBGE usada nos mapas
    try:
        geo = {int(f["properties"]["codarea"]) for f in json.loads(GEO_MUN.read_text())["features"]}
        miss = sorted(set(mun.cod) - geo)
        if miss:
            rep.warn(f"{len(miss)} municípios sem polígono na malha dos mapas (ex.: {miss[:5]}).")
    except FileNotFoundError:
        rep.warn(f"Malha {GEO_MUN.name} não encontrada; checagem de municípios ignorada.")

    # dimensões territoriais
    code2uf = mun.assign(ufc=mun.cod // 100000).drop_duplicates("ufc").set_index("ufc").uf
    al_ufs = set(mun.loc[mun.al, "uf"])
    mun["regiao"] = (mun.cod // 1_000_000).map(REGIONS)
    est["uf"] = est.cod.map(code2uf)
    est["al"] = est.uf.isin(al_ufs)
    est["regiao"] = (est.cod // 10).map(REGIONS)
    # valores sabidamente errados na planilha (`descartar`): saem antes de qualquer agregação, e o motivo vai para a ficha
    niveis = {"Município": mun, "Estado": est, "Grande Região": reg, "Brasil": bra}
    for it in items:
        i = it["chave"]
        for regra in it.get("descartar", []):
            if not regra.get("motivo") or not regra.get("anos"):
                rep.error(f"{i}: cada item de `descartar` precisa de `anos` e `motivo`.")
                continue
            if regra.get("nivel") and regra["nivel"] not in niveis:
                rep.error(f"{i}: `descartar.nivel` '{regra['nivel']}' desconhecido (use um de {', '.join(niveis)}).")
                continue
            n = 0
            for nivel, df in niveis.items():
                if i not in df or regra.get("nivel", nivel) != nivel:
                    continue
                m = df.ano.isin(regra["anos"]) & df[i].notna()
                if regra.get("uf"):
                    m &= df.uf.eq(regra["uf"]) if "uf" in df else False
                if regra.get("cod"):
                    m &= df.cod.isin(regra["cod"] if isinstance(regra["cod"], list) else [regra["cod"]])
                n += int(m.sum())
                df.loc[m, i] = np.nan
            if not n:
                rep.warn(f"{i}: `descartar` ({regra['motivo'][:60]}…) não encontrou nenhum valor.")
            ficha = next((f for f in fichas if f["id"] == i), None)
            if ficha is not None:
                ficha.setdefault("discarded", []).append({"anos": years_text(regra["anos"]), "nivel": regra.get("nivel", ""),
                                                          "uf": regra.get("uf", ""), "motivo": regra["motivo"]})
    amz = amazonia_legal(mun, rules, minimos, rep, razoes=razoes)
    bra0 = bra.copy()  # valores do Recorte Brasil antes de qualquer ajuste (`al_de` lê daqui)
    # soma dos estados: o indicador só é divulgado para parte dos municípios, então o total da Amazônia Legal é a soma dos
    # estados (ex.: migração internacional). O Maranhão entra inteiro, pois o dado municipal não separa a parte da região.
    for i, (rule, _) in rules.items():
        if rule == "taxa_censo" and i in mun:  # a taxa fica no mesmo ano em que a planilha a grava (2022)
            ano_i = int(mun.loc[mun[i].notna(), "ano"].max())
            amz[i] = amz.ano.map({ano_i: taxa_censo(mun.loc[mun.al, "cod"], censo)})
        if rule == "soma_estados" and i in est:
            ea = est[est.al]
            s_est = ea.groupby("ano")[i].sum(min_count=1)
            if not cfg_by_key.get(i, {}).get("ausente_zero"):  # padrão: só soma se os 9 estados têm dado no ano
                s_est = s_est.where(ea.groupby("ano")[i].count() == ea.uf.nunique())
            amz[i] = amz.ano.map(s_est)  # com `ausente_zero`, estado sem valor (sem produção) conta como zero
        if rule == "soma_com_sem_municipio" and i in est and i in mun:
            # soma dos municípios da região mais o que as UFs da região registram sem município identificado (total da UF
            # menos a soma dos seus municípios); o Maranhão entra inteiro nessa segunda parcela, como manda a ficha
            mun_uf = mun.groupby(["uf", "ano"])[i].sum(min_count=1)
            ea = est[est.al].set_index(["uf", "ano"])[i]
            sem = (ea - mun_uf.reindex(ea.index).fillna(0)).clip(lower=0).groupby("ano").sum(min_count=1)
            s_mun = mun[mun.al].groupby("ano")[i].sum(min_count=1)
            tot = pd.concat([s_mun, sem], axis=1).sum(axis=1, min_count=1)
            amz[i] = amz.ano.map(tot)
        if cfg_by_key.get(i, {}).get("al_de"):  # a Amazônia Legal vem de uma coluna do Recorte Brasil (ex.: rotas regionais)
            src = cfg_by_key[i]["al_de"]
            if src in bra0:
                amz[i] = amz.ano.map(bra0.set_index("ano")[src])
        if cfg_by_key.get(i, {}).get("al_soma_menos"):
            # contagem de pares com ao menos uma ponta na região (ex.: rotas aéreas): soma dos municípios da região menos os
            # pares com as duas pontas nela (coluna do Recorte Brasil), que a soma conta duas vezes
            src = cfg_by_key[i]["al_soma_menos"]
            if src in bra0 and i in mun:
                s_mun = mun[mun.al].groupby("ano")[i].sum(min_count=1)
                amz[i] = amz.ano.map(s_mun - bra0.set_index("ano")[src])

    for i in rules:
        if cfg_by_key.get(i, {}).get("sem_brasil"):
            bra[i] = np.nan  # a coluna do Recorte Brasil já é o valor da Amazônia Legal, não do país

    # estados só em parte na Amazônia Legal (ex.: Maranhão): valor da parcela do estado na região, calculado a partir
    # dos municípios marcados como Amazônia Legal, com a mesma regra de agregação de cada indicador. Entra como o
    # nível "Estado (parte AL)"; o valor publicado do estado inteiro continua no nível "Estado".
    parciais = []
    fichas_por_chave = {f["id"]: f for f in fichas}
    for uf in sorted(al_ufs):
        mu = mun[mun.uf == uf]
        if mu.al.all():
            continue
        e = est[est.uf == uf].iloc[0]
        p = amazonia_legal(mu, rules, minimos, rep, f"{e.nome} (parte na Amazônia Legal)", razoes)
        for i, (rule, _) in rules.items():  # a taxa de crescimento da parte do estado na região
            if rule == "taxa_censo" and i in mu:
                ano_i = int(mun.loc[mun[i].notna(), "ano"].max())
                p[i] = p.ano.map({ano_i: taxa_censo(mu.loc[mu.al, "cod"], censo)})
        # orientação da SUDAM (Clique): com dado municipal, o Maranhão entra só com os municípios da Amazônia Legal, e a
        # regra é definida por indicador. Por isso a parcela só sai por decisão no config (`sem_parte_al`, com o motivo).
        # Como conferência, a mesma regra aplicada a TODOS os municípios do estado deveria reproduzir o valor publicado
        # dele; quando não reproduz, o build avisa (ex.: média ponderada por um peso que não é o da fonte)
        inteiro = amazonia_legal(mu.assign(al=True), rules, minimos, Report(), e.nome, razoes).set_index("ano")
        pub = est[est.uf == uf].set_index("ano")
        for i, (rule, _) in rules.items():
            if i not in p or p[i].isna().all():
                continue
            motivo = cfg_by_key.get(i, {}).get("sem_parte_al")  # decisão no config (ex.: série que se lê em conjunto)
            if motivo:
                p[i] = np.nan
                fichas_por_chave[i]["parteAL"] = motivo
                continue
            if i not in pub or i not in inteiro:
                continue
            dif = desvio_estimativa(inteiro[i], pub[i], fichas_por_chave[i]["display"]["format"])
            if dif is not None and dif[0]:  # só avisa: a parcela é o que a orientação manda usar quando há dado municipal
                rep.warn(f"{i}: a regra de agregação aplicada a todos os municípios do estado ({e.nome}) não reproduz o valor "
                         f"publicado do estado ({dif[1]}). Confira o peso; se a parcela não valer, marque `sem_parte_al` "
                         "com o motivo.")
        p["cod"], p["nome"], p["uf"], p["regiao"], p["al"] = (int(e.cod), f"{e.nome} (parte na Amazônia Legal)", uf,
                                                           e.regiao, True)
        parciais.append(p)
        print(f"Estado só em parte na Amazônia Legal: {e.nome} ({int(mu[mu.al].cod.nunique())} de "
              f"{int(mu.cod.nunique())} municípios); parcela calculada para os indicadores agregáveis.")

    parts = []
    for lvl, df in (("Brasil", bra), ("Amazônia Legal", amz), ("Grande Região", reg),
                    ("Estado", est), ("Município", mun), *[("Estado (parte AL)", p) for p in parciais]):
        d = df.copy()
        d["nivel"] = lvl
        for c in ("uf", "regiao", "al"):
            if c not in d:
                d[c] = None
        for i in ind_ids:
            if i not in d:
                d[i] = np.nan
        parts.append(d.melt(id_vars=["nivel", "cod", "nome", "uf", "regiao", "al", "ano"],
                            value_vars=ind_ids, var_name="ind", value_name="valor"))
    long = pd.concat(parts, ignore_index=True)
    long = long[long.valor.notna()].reset_index(drop=True)  # só as células com valor: a base fica bem menor
    # ano ainda incompleto na fonte (`ano_parcial`): um total de meio ano pareceria queda e viraria o "último ano"
    for it in items:
        anos = it.get("ano_parcial")
        if anos is not None:
            anos = anos if isinstance(anos, list) else [anos]
            long = long[~((long.ind == it["chave"]) & long.ano.isin(anos))]
    long = long.reset_index(drop=True)
    long["al"] = long["al"].astype("boolean")
    long["ano"] = long["ano"].astype("int16")
    # categorias: cada texto é gravado uma vez no parquet (o nome do território se repete em milhões de linhas e,
    # como texto puro, triplicava a memória do painel ao ler a base)
    for c in ("nivel", "ind", "uf", "regiao", "nome"):
        long[c] = long[c].astype("category")

    # resumo por indicador
    print("\nIndicadores:")
    for f in fichas:
        i = f["id"]
        d = long[(long.ind == i) & long.valor.notna()]
        yrs = sorted(d.ano.unique().tolist())
        levels = [lv for lv in ("Brasil", "Amazônia Legal", "Grande Região", "Estado", "Município")
                  if (d.nivel == lv).any()]
        n_al = d[(d.nivel == "Município") & d.al.fillna(False)].cod.nunique()
        f["years"], f["levels"] = yrs, levels
        rule, peso = rules[i]
        f["aggregationApplied"] = (
            "Soma dos municípios" if rule == "soma"
            else "Soma dos estados da Amazônia Legal (o Maranhão entra inteiro)" if rule == "soma_estados"
            else "Soma dos municípios da região mais os registros das UFs sem município identificado (o Maranhão entra inteiro "
                 "nessa parcela)" if rule == "soma_com_sem_municipio"
            else f"Razão entre totais: soma de {nome_peso(razoes[i][0])} nos municípios ÷ soma de {nome_peso(peso)}"
                 + (f" × {razoes[i][1]:g}" if razoes[i][1] != 1 else "") if rule == "razao_totais"
            else f"Média simples das razões de cada grupo ({TOTAIS_POR_GRUPO[medias_razoes[i][0]][5]}), com numerador e "
                 "denominador somados nos municípios da região" if rule == "media_razoes"
            else "Taxa recalculada com a população dos Censos 2010 e 2022 somada nos municípios" if rule == "taxa_censo"
            else "Sem valor próprio: a fonte publica o indicador pronto em cada nível e a planilha não traz os totais "
                 "para recalculá-lo a partir dos municípios" if rule == "publicado"
            else "Média simples dos municípios (cada município pesa igual)" if rule == "media_simples"
            else f"Média ponderada dos municípios por {nome_peso(peso)}")
        if rule == "media_ponderada" and cfg_by_key.get(i, {}).get("peso_ano_anterior"):
            f["aggregationApplied"] += " do ano inicial de cada par (o ano anterior)"
        al_de = cfg_by_key.get(i, {}).get("al_de")
        al_soma_menos = cfg_by_key.get(i, {}).get("al_soma_menos")
        if al_de:
            f["aggregationApplied"] = "Valor do Recorte Brasil para as rotas com as duas pontas na Amazônia Legal, como manda a ficha"
        elif al_soma_menos:
            f["aggregationApplied"] = ("Soma dos municípios da Amazônia Legal menos as rotas com as duas pontas na região "
                                       "(Recorte Brasil), que a soma conta duas vezes")
            al_de = al_soma_menos  # a Amazônia Legal tem valor próprio, como no al_de
        if rule not in ("publicado", "soma_estados", "soma_com_sem_municipio", "razao_totais", "media_razoes", "taxa_censo"):
            # na soma, município sem dado não soma nada (vale zero); na média, fica fora da conta
            f["aggregationApplied"] += (f" · exige cobertura mínima de {minimos[i]:g}% dos municípios" if minimos[i]
                                        else " · municípios sem dado contam como zero" if rule == "soma"
                                        else " · sem cobertura mínima: entram só os municípios com dado")
        nota = cfg_by_key.get(i, {}).get("nota_agregacao")  # ex.: aproximação conferida contra os valores estaduais
        if nota and rule == "publicado" and not al_de:
            f["aggregationApplied"] = f"Não calculada para a Amazônia Legal: {nota}"
        elif nota:
            f["aggregationApplied"] += f" · {nota}"
        print(f"  {i}  {f['display']['label'][:45]:45}  anos {yrs[0] if yrs else '—'}–{yrs[-1] if yrs else '—'} "
              f"({len(yrs)})  municípios AL {n_al}  níveis: {len(levels)}/5")
        if not yrs:
            rep.error(f"{i}: nenhum valor encontrado na planilha.")
        else:
            expected = set(SHEETS) | ({"Amazônia Legal"} if rule != "publicado" or al_de else set())
            if cfg_by_key.get(i, {}).get("sem_brasil"):
                expected -= {"Brasil"}
            if expected - set(levels):
                rep.warn(f"{i}: sem dado em {', '.join(sorted(expected - set(levels)))}.")

    return finish(rep, (long, fichas, xlsx))


def finish(rep: Report, result) -> int:
    for w in rep.warnings:
        print(f"  aviso: {w}")
    if rep.errors:
        print("\nErros — nada foi gravado:")
        for e in rep.errors:
            print(f"  ✗ {e}")
        return 1

    long, fichas, xlsx = result
    buf = io.BytesIO()
    long.to_parquet(buf, index=False, compression="zstd")
    data = buf.getvalue()
    fichas_json = json.dumps({"indicadores": fichas}, ensure_ascii=False, indent=1).encode("utf-8")
    versao = hashlib.sha256(data + fichas_json).hexdigest()[:12]
    manifest = {
        "versao": versao,
        "gerado_em": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "planilha": xlsx.name,
        "planilha_modificada_em": datetime.fromtimestamp(xlsx.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
        "indicadores": [f["id"] for f in fichas],
        "linhas": len(long),
        "avisos": rep.warnings,
    }
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "dados.parquet").write_bytes(data)
    (OUT_DIR / "fichas.json").write_bytes(fichas_json)
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nOK — versão {versao}, {len(fichas)} indicadores, {len(long):,} linhas "
          f"({len(data) / 1e6:.1f} MB).".replace(",", "."))
    print(f"Arquivos em {OUT_DIR}:\n  dados.parquet  fichas.json  manifest.json")
    print("Próximo passo: subir os três arquivos para a pasta painel/ do bucket (substituindo os anteriores).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
