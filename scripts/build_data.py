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
    "Indicador": "name", "Descrição do Indicador": "description", "Eixo P1": "axis", "Tema": "theme",
    "Subtema": "subtheme", "Eixo(s) PRDA Relacionado(s)": "prda", "Unidade de Medida": "unit",
    "Polaridade": "polarity", "Fonte dos Dados": "source", "Periodicidade": "periodicity",
    "Série Histórica Disponível": "series", "Ano de Referência mais Recente": "latest",
    "Código da Tabela/Série": "table", "Link para a Base de Dados": "link",
    "Limitações Metodológicas": "limits", "Menor Unidade Territorial Disponível": "minTerritory",
    "Cobertura Municipal (%)": "coverage", "Regra de Agregação Territorial": "aggregation",
    "Variável de Ponderação": "weight", "Comparabilidade Temporal": "temporal",
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
    ids = [i["id"] for i in items]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        sys.exit(f"{path.name}: IDs repetidos: {', '.join(sorted(dup))}")
    return items


def read_lista(book: pd.ExcelFile) -> pd.DataFrame:
    df = book.parse(LISTA, header=LISTA_HEADER_ROW)
    df = df.dropna(subset=["ID"])
    df["ID"] = df["ID"].astype(str).str.strip()
    return df.set_index("ID")


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
    casas = item.get("casas", {"percentual": 1, "moeda": 0}.get(formato, 0 if rule == "soma" else 2))
    pol = norm(ficha["polarity"])
    return {
        "label": item.get("rotulo", ficha["name"]),
        "unit": unit,
        "format": formato,
        "decimals": int(casas),
        "scale": float(item.get("escala", 1)),
        "log": bool(item.get("log", rule == "soma")),
        "additive": rule == "soma",
        "polarity": 1 if pol.startswith("maior") else -1 if pol.startswith("menor") else 0,
        "icon": item.get("icone", {"percentual": "%", "moeda": "R$"}.get(formato, "●")),
    }


# --------------------------------------------------------------------------- #
# Abas de recorte
# --------------------------------------------------------------------------- #
def resolve_columns(header: list[str], wanted: dict[str, str]) -> dict[str, str | None]:
    """wanted: ID -> nome esperado. Devolve ID -> nome real da coluna (ou None)."""
    by_norm: dict[str, str] = {}
    for c in header:
        by_norm.setdefault(norm(c), c)
    return {i: by_norm.get(norm(name)) for i, name in wanted.items()}


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
            rep.warn(f"{i}: coluna '{wanted[i]}' não encontrada na aba '{sheet}' (indicador fica sem dado neste nível; "
                     "use `coluna` em config/indicadores.toml se o nome for diferente).")
    found = {i: c for i, c in cols.items() if c}
    df = book.parse(sheet, usecols=ids + ["Ano"] + list(found.values()))
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
    for i, c in found.items():
        out[i] = to_numeric(df[c], f"{i} ({sheet})", rep)
        if level == "Município" and factors and i in factors:
            out[i] = out[i] * factors[i]  # ex.: 0/1 por município -> 0/100, como nas abas Estadual/Regional/Brasil
    return out


# --------------------------------------------------------------------------- #
# Amazônia Legal
# --------------------------------------------------------------------------- #
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
                   rep: Report, rotulo: str = "Amazônia Legal") -> pd.DataFrame:
    """Agrega os municípios da Amazônia Legal presentes em `mun`. Em cada ano, só publica o valor se a cobertura
    (municípios com dado ÷ municípios da Amazônia Legal em `mun`) alcançar o mínimo do indicador; abaixo disso
    fica vazio. Passando só os municípios de um estado, calcula a parcela desse estado na região (`rotulo` nomeia
    o recorte nos avisos)."""
    al = mun[mun.al]
    n_al = al.cod.nunique()
    years = sorted(mun.ano.unique())
    out = pd.DataFrame({"ano": years})
    for i, (rule, peso) in rules.items():
        if rule == "publicado":
            out[i] = np.nan
            continue
        if i not in al or al[i].notna().sum() == 0 or (rule == "media_ponderada" and peso not in al):
            out[i] = np.nan  # sem dado municipal (ou sem o peso): o resumo final avisa que falta a Amazônia Legal
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
        out[i] = out.ano.map(s)
    out["cod"], out["nome"], out["uf"] = 0, "Amazônia Legal", None
    return out


# --------------------------------------------------------------------------- #
# Principal
# --------------------------------------------------------------------------- #
def find_xlsx(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    files = [p for p in DATA_DIR.glob("*.xlsx") if not p.name.startswith("~$")]
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
    for it in items:
        i = it["id"]
        if i not in lista.index:
            rep.error(f"{i}: ID não existe na aba '{LISTA}'.")
            continue
        row = lista.loc[i]
        ficha = {"id": i, **{k: cell(row.get(c)) for c, k in FICHA.items()}}
        rule = it.get("agregacao") or agg_rule(ficha["aggregation"])
        peso = it.get("peso")
        if rule not in ("soma", "media_ponderada", "media_simples", "publicado"):
            rep.error(f"{i}: regra de agregação '{ficha['aggregation']}' não reconhecida — defina `agregacao` "
                      "em config/indicadores.toml.")
            continue
        if rule == "media_ponderada" and not peso:
            rep.error(f"{i}: média ponderada exige `peso` em config/indicadores.toml "
                      f"(a ficha cita: '{ficha['weight']}').")
            continue
        if peso and peso not in lista.index:
            rep.error(f"{i}: peso {peso} não existe na aba '{LISTA}'.")
            continue
        rules[i] = (rule, peso if rule == "media_ponderada" else None)
        minimos[i] = float(it.get("cobertura_minima", args.cobertura_minima))
        ficha["display"] = display_spec(it, ficha, rule)
        fichas.append(ficha)

    cfg_by_id = {it["id"]: it for it in items}
    weights = {p for _, p in rules.values() if p}
    wanted = {i: cfg_by_id.get(i, {}).get("coluna", lista.loc[i, "Indicador"]) for i in [*rules, *sorted(weights - set(rules))]}

    factors = {i["id"]: float(i["fator_municipal"]) for i in items if "fator_municipal" in i}
    frames = {lvl: read_level(book, lvl, wanted, rep, factors) for lvl in SHEETS}
    if rep.errors:
        return finish(rep, None)

    mun, est, reg, bra = (frames[k] for k in ("Município", "Estado", "Grande Região", "Brasil"))
    ind_ids = list(rules)

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
    amz = amazonia_legal(mun, rules, minimos, rep)

    # estados só em parte na Amazônia Legal (ex.: Maranhão): valor da parcela do estado na região, calculado a partir
    # dos municípios marcados como Amazônia Legal, com a mesma regra de agregação de cada indicador. Entra como o
    # nível "Estado (parte AL)"; o valor publicado do estado inteiro continua no nível "Estado".
    parciais = []
    for uf in sorted(al_ufs):
        mu = mun[mun.uf == uf]
        if mu.al.all():
            continue
        e = est[est.uf == uf].iloc[0]
        p = amazonia_legal(mu, rules, minimos, rep, f"{e.nome} (parte na Amazônia Legal)")
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
    long["al"] = long["al"].astype("boolean")
    long["ano"] = long["ano"].astype("int16")
    for c in ("nivel", "ind", "uf", "regiao"):
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
            else "Valor publicado pela fonte (sem agregação a partir dos municípios)" if rule == "publicado"
            else "Média simples dos municípios (cada município pesa igual)" if rule == "media_simples"
            else f"Média ponderada dos municípios por {lista.loc[peso, 'Indicador']} ({peso})")
        if rule != "publicado":
            f["aggregationApplied"] += f" · exige cobertura mínima de {minimos[i]:g}% dos municípios"
        print(f"  {i}  {f['display']['label'][:45]:45}  anos {yrs[0] if yrs else '—'}–{yrs[-1] if yrs else '—'} "
              f"({len(yrs)})  municípios AL {n_al}  níveis: {len(levels)}/5")
        if not yrs:
            rep.error(f"{i}: nenhum valor encontrado na planilha.")
        else:
            expected = set(SHEETS) | ({"Amazônia Legal"} if rule != "publicado" else set())
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
