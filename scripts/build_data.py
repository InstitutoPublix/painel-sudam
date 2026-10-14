"""Gera as bases do painel a partir da planilha Excel do PRDA.

Uso:
    python scripts/build_data.py                  # usa o .xlsx mais recente de data/
    python scripts/build_data.py caminho.xlsx

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
def load_config() -> list[dict]:
    cfg = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    items = cfg.get("indicador", [])
    ids = [i["id"] for i in items]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        sys.exit(f"config/indicadores.toml: IDs repetidos: {', '.join(sorted(dup))}")
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


def read_level(book: pd.ExcelFile, level: str, wanted: dict[str, str], rep: Report) -> pd.DataFrame:
    sheet = SHEETS[level]
    header = [str(c) for c in book.parse(sheet, nrows=0).columns]
    if "Ano" not in header:
        rep.error(f"Aba '{sheet}': coluna 'Ano' não encontrada.")
        return pd.DataFrame()
    ids = header[:header.index("Ano")]
    cols = resolve_columns(header[header.index("Ano") + 1:], wanted)
    for i, c in cols.items():
        if c is None:
            msg = f"{i}: coluna '{wanted[i]}' não encontrada na aba '{sheet}'"
            if level == "Município":
                rep.error(msg + " — use `coluna` em config/indicadores.toml se o nome for diferente.")
            else:
                rep.warn(msg + " (indicador fica sem dado neste nível).")
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
    return out


# --------------------------------------------------------------------------- #
# Amazônia Legal
# --------------------------------------------------------------------------- #
def interpolated(mun: pd.DataFrame, col: str) -> pd.DataFrame:
    """Peso por município × ano, com anos sem dado interpolados (linear) ou repetidos nas pontas."""
    p = mun.pivot(index="cod", columns="ano", values=col).sort_index(axis=1)
    return p.interpolate(axis=1, method="index", limit_direction="both")


def amazonia_legal(mun: pd.DataFrame, rules: dict[str, tuple[str, str | None]], rep: Report) -> pd.DataFrame:
    al = mun[mun.al]
    years = sorted(mun.ano.unique())
    out = pd.DataFrame({"ano": years})
    for i, (rule, peso) in rules.items():
        if rule == "soma":
            s = al.groupby("ano")[i].sum(min_count=1)
        else:
            v = al.pivot(index="cod", columns="ano", values=i)
            w_raw = mun.pivot(index="cod", columns="ano", values=peso).reindex(index=v.index, columns=v.columns)
            w = interpolated(al, peso).reindex(index=v.index, columns=v.columns)
            ok = v.notna() & w.notna()
            s = (v * w).where(ok).sum(min_count=1) / w.where(ok).sum(min_count=1)
            filled = sorted(int(y) for y in v.columns if (v[y].notna() & w_raw[y].isna() & w[y].notna()).any())
            if filled:
                rep.warn(f"{i}: peso {peso} interpolado para calcular a Amazônia Legal em {filled}.")
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
    xlsx = find_xlsx(ap.parse_args().planilha)
    items = load_config()
    rep = Report()

    print(f"Planilha: {xlsx.name}\nLendo abas (pode levar alguns minutos)…")
    book = pd.ExcelFile(xlsx, engine="openpyxl")
    lista = read_lista(book)

    # fichas, regras de agregação e colunas a ler
    rules: dict[str, tuple[str, str | None]] = {}
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
        if rule not in ("soma", "media_ponderada"):
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
        ficha["display"] = display_spec(it, ficha, rule)
        fichas.append(ficha)

    cfg_by_id = {it["id"]: it for it in items}
    weights = {p for _, p in rules.values() if p}
    wanted = {i: cfg_by_id.get(i, {}).get("coluna", lista.loc[i, "Indicador"]) for i in [*rules, *sorted(weights - set(rules))]}

    frames = {lvl: read_level(book, lvl, wanted, rep) for lvl in SHEETS}
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
    amz = amazonia_legal(mun, rules, rep)

    parts = []
    for lvl, df in (("Brasil", bra), ("Amazônia Legal", amz), ("Grande Região", reg),
                    ("Estado", est), ("Município", mun)):
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
        f["aggregationApplied"] = ("Soma dos municípios" if rule == "soma"
                                   else f"Média ponderada dos municípios por {lista.loc[peso, 'Indicador']} ({peso})")
        print(f"  {i}  {f['display']['label'][:45]:45}  anos {yrs[0] if yrs else '—'}–{yrs[-1] if yrs else '—'} "
              f"({len(yrs)})  municípios AL {n_al}  níveis: {len(levels)}/5")
        if not yrs:
            rep.error(f"{i}: nenhum valor encontrado na planilha.")
        elif len(levels) < 5:
            rep.warn(f"{i}: sem dado em {', '.join(sorted((set(SHEETS) | {'Amazônia Legal'}) - set(levels)))}.")

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
