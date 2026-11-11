"""Extrai da planilha do Atlas Águas (ANA) a população urbana de 2020 por município, em
assets/seguranca_hidrica_ana_municipios.csv.

Uso:
    python scripts/seguranca_hidrica_ana.py [assets/IND-059_seguranca-hidrica_atlasaguas.xlsx]

Por que existe: a ficha da segurança hídrica urbana (IND-059) manda ponderar o índice de cada município pela coluna
"População Urbana 2020 (hab)" da própria planilha da ANA, que não está na base do painel. O build usa este arquivo como
peso (`peso_ana` em config/indicadores.toml); com ele, a média ponderada reproduz os valores das 27 UFs.

Saída: cod (IBGE, 7 dígitos), pop_urbana. Sem coluna de ano: o mesmo peso vale para todos os anos do indicador.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ENTRADA = ROOT / "assets" / "IND-059_seguranca-hidrica_atlasaguas.xlsx"
OUT = ROOT / "assets" / "seguranca_hidrica_ana_municipios.csv"
COL_COD, COL_POP = "Código IBGE", "População Urbana 2020 (hab)"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("planilha", type=Path, nargs="?", default=ENTRADA)
    args = ap.parse_args()

    df = pd.read_excel(args.planilha, sheet_name="Indicadores_ISH_metadados", header=2, usecols=[COL_COD, COL_POP])
    df = df[pd.to_numeric(df[COL_COD], errors="coerce").notna()]
    out = pd.DataFrame({"cod": df[COL_COD].astype(int), "pop_urbana": pd.to_numeric(df[COL_POP], errors="coerce")})
    out = out.dropna().astype({"pop_urbana": int}).sort_values("cod")
    out.to_csv(OUT, index=False)
    total = f"{int(out.pop_urbana.sum()):,}".replace(",", ".")
    print(f"{OUT.relative_to(ROOT)}: {len(out)} municípios, {total} habitantes urbanos em 2020.")


if __name__ == "__main__":
    main()
