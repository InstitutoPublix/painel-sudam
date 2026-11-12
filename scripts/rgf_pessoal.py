"""Converte o arquivo da equipe com a despesa total com pessoal e a receita corrente líquida ajustada de cada município
(RGF, Anexo 01, Poder Executivo) em assets/rgf_pessoal_municipios.csv.

Uso:
    python scripts/rgf_pessoal.py [assets/IND-095_componentes_despesa-pessoal_rcl_municipios_2015-2025.csv]

Por que existe: a planilha traz o gasto com pessoal sobre a RCL (IND-095) só como % de cada município. A ficha manda
calcular a Amazônia Legal pela razão entre totais: soma da despesa total com pessoal ÷ soma da RCL ajustada × 100
(ver assets/LEIA-ME_IND-095.txt). O build usa os dois totais (`numerador_rgf` e `peso_rgf`, regra "razao_totais").

Entra só o que a equipe marcou com entra_no_calculo = SIM (percentual publicado entre 0 e 100, com despesa e RCL), que é
também o que a planilha grava para o município. Saída: cod (IBGE, 7 dígitos), ano, despesa_pessoal, rcl (R$).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ENTRADA = ROOT / "assets" / "IND-095_componentes_despesa-pessoal_rcl_municipios_2015-2025.csv"
OUT = ROOT / "assets" / "rgf_pessoal_municipios.csv"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("arquivo", type=Path, nargs="?", default=ENTRADA)
    args = ap.parse_args()
    df = pd.read_csv(args.arquivo)
    df = df[df.entra_no_calculo.eq("SIM")]
    out = pd.DataFrame({"cod": df.codigo_ibge.astype(int), "ano": df.ano.astype(int),
                        "despesa_pessoal": df.despesa_total_pessoal, "rcl": df.rcl_ajustada})
    out = out.sort_values(["ano", "cod"])
    out.to_csv(OUT, index=False, float_format="%.2f")
    print(f"{OUT.relative_to(ROOT)}: {len(out)} município-anos; municípios por ano:",
          out.groupby("ano").cod.nunique().to_dict())
    return 0


if __name__ == "__main__":
    sys.exit(main())
