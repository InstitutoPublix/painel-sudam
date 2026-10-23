"""Gera a tabela de caracterização dos municípios usada nos filtros territoriais do painel.

Uso:
    python scripts/caracterizacao.py                          # lê docs/agrupamentos.xlsx
    python scripts/caracterizacao.py caminho/agrupamentos.xlsx

Lê a aba CARACTERIZAÇÃO (um município por linha, código IBGE de 7 dígitos), valida e grava
assets/municipios_caracterizacao.csv. O painel só usa esses campos como filtros de municípios: nenhum
valor de indicador vem daqui e nenhum agregado é calculado para os grupos.

Campos gravados:
    cod, uf, al                      código IBGE, UF e pertença à Amazônia Legal
    rg_intermediaria, rg_imediata    Regiões Geográficas Intermediárias e Imediatas do IBGE (nome)
    sede_imediata, fronteira         cidade-sede de região imediata e cidade de fronteira (bool)
    pndr                             Tipologia da PNDR
    porte                            classe de porte populacional (população de 2025, ver PORTES)
    idhm, idsc, ips                  classes do IDHM (2010), do IDSC-BR (2025) e do IPS (2026)

O IEGM fica de fora: mais da metade dos municípios da Amazônia Legal não tem classificação.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "agrupamentos.xlsx"
OUT = ROOT / "assets" / "municipios_caracterizacao.csv"
SHEET = "CARACTERIZAÇÃO"

COLS = {
    "Código": "cod", "Estado": "uf", "Amazônia Legal": "al",
    "Regiões Intermediárias do IBGE": "rg_intermediaria", "Regiões Geográficas Imediatas do IBGE": "rg_imediata",
    "Cidades-sedes das regiões geográficas imediatas": "sede_imediata", "Cidades de Fronteira": "fronteira",
    "Tipologia PNDR": "pndr", "CLASSIFICAÇÃO POPULAÇÃO": "porte", "Classificação do IDHM": "idhm",
    "Classificação do IDSC": "idsc", "Classificação do IPS": "ips",
}
POP = "POPULAÇÃO - 2025"
# classes de porte (PNAS/IBGE): limite superior de cada classe, população de 2025
PORTES = [("Pequeno Porte I", 20_000), ("Pequeno Porte II", 50_000), ("Médio Porte", 100_000),
          ("Grande Porte", 900_000), ("Metrópole", np.inf)]
SEM_CLASSE = {"Não se aplica", "", "nan"}


def _classe(v: pd.Series, limites: list[tuple[str, float]]) -> pd.Series:
    """Classe pelo limite inferior de cada faixa (limites em ordem crescente)."""
    nomes, cortes = [n for n, _ in limites], [c for _, c in limites]
    return pd.cut(v, cortes + [np.inf], right=False, labels=nomes).astype(object).where(v.notna())


# faixas que a própria planilha aplica (conferidas nas linhas sem erro): IDHM = faixas do PNUD
IDHM_FAIXAS = [("Muito baixo", 0), ("Baixo", .5), ("Médio", .6), ("Alto", .7), ("Muito alto", .8)]
IPS_FAIXAS = [("Muito baixo", 0), ("Baixo", 51.98), ("Médio", 56.79), ("Alto", 62.92)]
IDX = {"idhm": ("Índice de Desenvolvimento Humano Municipal (IDHM) - 2010", "IND-007", 2010, IDHM_FAIXAS),
       "ips": ("Índice de Progresso Social (IPS) - 2026", "IND-146", 2026, IPS_FAIXAS)}


def corrigir_indices(df: pd.DataFrame, raw: pd.DataFrame):
    """A planilha traz, para parte dos municípios homônimos (ex.: Belém do PA recebeu o IDHM de outra Belém),
    índices de outro município — sinal de busca pelo nome em vez do código. Quando a base do painel existe
    (build/dados.parquet), as classes de IDHM e IPS são recalculadas a partir dos valores oficiais da base, ligados
    pelo código IBGE (municípios sem classe na planilha, mas com valor oficial, também passam a ter classe). O erro
    ocorre coluna a coluna, sem padrão por linha; por isso o IDSC-BR, que não tem como ser conferido, fica sem classe
    em todos os municípios homônimos."""
    base = ROOT / "build" / "dados.parquet"
    if not base.exists():
        print("  aviso: build/dados.parquet ausente; classes de IDHM, IDSC-BR e IPS mantidas como na planilha.")
        return
    long = pd.read_parquet(base, columns=["nivel", "cod", "ind", "ano", "valor"])
    mun = long[long.nivel == "Município"]
    homon = raw["Município"].astype(str).str.strip().str.upper().duplicated(keep=False).values
    for col, (coluna, ind, ano, faixas) in IDX.items():
        oficial = mun[(mun.ind == ind) & (mun.ano == ano)].set_index("cod").valor.reindex(df.cod).values
        planilha = pd.to_numeric(raw[coluna], errors="coerce").values
        dif = ~np.isnan(oficial) & ~np.isnan(planilha) & (np.abs(oficial - planilha) > 1e-3)
        nova = _classe(pd.Series(oficial, index=df.index), faixas)
        mudou = int((nova.fillna("") != df[col].fillna("")).sum())
        df[col] = nova.where(nova.notna(), df[col])  # sem valor oficial: mantém a classe da planilha
        print(f"  {col}: {int(dif.sum())} municípios com índice de outro município na planilha "
              f"({int((dif & homon).sum())} homônimos); classe recalculada pelo {ind} ({mudou} classes mudaram)")
    df.loc[homon, "idsc"] = None
    print(f"  idsc: classe retirada dos {int(homon.sum())} municípios homônimos (não há como conferir); "
          "corrigir na planilha de origem")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC
    raw = pd.read_excel(src, sheet_name=SHEET)
    raw.columns = [" ".join(str(c).split()) for c in raw.columns]  # quebras de linha nos cabeçalhos
    falta = [c for c in [*COLS, POP] if c not in raw.columns]
    if falta:
        sys.exit(f"Colunas ausentes na aba {SHEET}: {falta}")
    df = raw[list(COLS)].rename(columns=COLS)
    erros = []

    df["cod"] = pd.to_numeric(df.cod, errors="coerce")
    if df.cod.isna().any() or not df.cod.between(1_000_000, 9_999_999).all():
        erros.append("há códigos IBGE vazios ou fora do formato de 7 dígitos")
    if df.cod.duplicated().any():
        erros.append(f"códigos repetidos: {sorted(df.cod[df.cod.duplicated()].astype(int))[:5]}")
    df["cod"] = df.cod.astype("int64")
    if (df.cod // 100_000).groupby(df.uf).nunique().gt(1).any():
        erros.append("a UF não corresponde aos dois primeiros dígitos do código em algum município")

    for c in ("al", "sede_imediata", "fronteira"):
        v = df[c].astype(str).str.strip().str.upper()
        if not v.isin(["SIM", "NÃO", "NAO"]).all():
            erros.append(f"valores inesperados em '{c}': {sorted(set(v) - {'SIM', 'NÃO', 'NAO'})}")
        df[c] = v.eq("SIM")

    for c in ("rg_intermediaria", "rg_imediata", "pndr", "porte", "idhm", "idsc", "ips"):
        v = df[c].astype(str).str.strip()
        df[c] = v.where(~v.isin(SEM_CLASSE)).str.capitalize() if c in ("idhm", "idsc", "ips") else v.where(~v.isin(SEM_CLASSE))
    if df.rg_imediata.isna().any() or df.rg_intermediaria.isna().any():
        erros.append("há municípios sem região imediata ou intermediária")

    # porte: confere a classe da planilha com a população de 2025 e os limites oficiais
    pop = pd.to_numeric(raw[POP], errors="coerce")
    esperado = pd.cut(pop, [0] + [b for _, b in PORTES], labels=[n for n, _ in PORTES]).astype(str)
    dif = df.porte != esperado
    if dif.any():
        erros.append(f"{int(dif.sum())} municípios com classe de porte diferente da população de 2025 "
                     f"(ex.: {df.cod[dif].tolist()[:5]})")

    corrigir_indices(df, raw)

    # região imediata contida numa única intermediária (nomes se repetem entre UFs, por isso a chave inclui a UF)
    chave = df.rg_imediata + " (" + df.uf + ")"
    if df.groupby(chave).rg_intermediaria.nunique().gt(1).any():
        erros.append("há região imediata em mais de uma região intermediária")

    if erros:
        print("Erros — nada foi gravado:")
        for e in erros:
            print(f"  ✗ {e}")
        return 1
    df = df.sort_values("cod")
    df.to_csv(OUT, index=False, encoding="utf-8")
    al = df[df.al]
    print(f"OK — {len(df)} municípios ({len(al)} na Amazônia Legal) gravados em {OUT.relative_to(ROOT)}")
    print(f"  regiões intermediárias: {df.rg_intermediaria.nunique()} · imediatas: {chave.nunique()}")
    for c in ("porte", "pndr", "idhm", "idsc", "ips"):
        print(f"  {c}: {al[c].value_counts(dropna=False).to_dict()}  (Amazônia Legal)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
