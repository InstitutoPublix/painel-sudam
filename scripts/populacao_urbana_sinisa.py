"""Extrai da planilha de indicadores do SINISA (Manejo de Resíduos Sólidos Urbanos) a população urbana de cada município,
em assets/populacao_urbana_sinisa_municipios.csv.

Uso:
    python scripts/populacao_urbana_sinisa.py [assets/IND-120_disposicao-adequada-residuos_sinisa.xlsx]

Por que existe: a ficha do atendimento urbano de água (IND-119) manda ponderar a taxa de cada município pela população
urbana que o próprio SINISA usa (coluna "POPULAÇÃO URBANA", campo DFE0002), que não está na base do painel. Com ela, a
média ponderada reproduz os valores das UFs (diferença de até 0,006). O build usa este arquivo como peso (`peso_sinisa =
"pop_urbana"` em config/indicadores.toml).

Saída: cod (IBGE, 7 dígitos), ano (o do Diagnóstico, lido do título da planilha), pop_urbana. O peso só vale no ano do
Diagnóstico: para outro ano, rode o script com a planilha daquele ano e junte as saídas.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ENTRADA = ROOT / "assets" / "IND-120_disposicao-adequada-residuos_sinisa.xlsx"
OUT = ROOT / "assets" / "populacao_urbana_sinisa_municipios.csv"
COL_COD, COL_POP = "CÓDIGO DO IBGE", "POPULAÇÃO URBANA"
LINHA_CABECALHO = 10  # as linhas acima são título, legenda e grupos de colunas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("planilha", type=Path, nargs="?", default=ENTRADA)
    args = ap.parse_args()

    titulo = " ".join(str(v) for v in pd.read_excel(args.planilha, header=None, nrows=LINHA_CABECALHO).stack())
    anos = re.findall(r"Diagnóstico[^\n]*?(\d{4})", titulo)
    if not anos:
        raise SystemExit("Ano do Diagnóstico não encontrado no título da planilha.")
    df = pd.read_excel(args.planilha, header=LINHA_CABECALHO, usecols=[COL_COD, COL_POP])
    df = df[pd.to_numeric(df[COL_COD], errors="coerce").notna()]
    out = pd.DataFrame({"cod": df[COL_COD].astype(int), "ano": int(anos[0]),
                        "pop_urbana": pd.to_numeric(df[COL_POP], errors="coerce")})
    out = out.dropna().astype({"pop_urbana": int}).sort_values("cod")
    out.to_csv(OUT, index=False)
    total = f"{int(out.pop_urbana.sum()):,}".replace(",", ".")
    print(f"{OUT.relative_to(ROOT)}: {len(out)} municípios, {total} habitantes urbanos em {anos[0]}.")


if __name__ == "__main__":
    main()
