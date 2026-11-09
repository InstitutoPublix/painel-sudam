"""Gera o relatório em PDF de um território, pelo terminal (o mesmo da aba Relatório do painel).

Exemplos:
  python scripts/relatorio.py "Pará"
  python scripts/relatorio.py "Pará" --comparar "Amazonas" "Tocantins" --eixos 1 4
  python scripts/relatorio.py "Marabá (PA)" -o maraba.pdf --tabela
  python scripts/relatorio.py "Maranhão" --parte        # só a parte do estado na Amazônia Legal
  python scripts/relatorio.py Estado:15                 # pelo código

Lê as bases como o painel (bucket, se houver .streamlit/secrets.toml na pasta atual; senão build/).
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

from src import data, relatorio  # noqa: E402


def achar(D: dict, nome: str) -> str:
    if ":" in nome and nome.split(":", 1)[1].isdigit():
        return nome
    for nivel in ("Estado", "Município", "Grande Região"):
        t = data.territories(D, nivel)
        hit = t[(t.label.str.casefold() == nome.casefold())]
        if len(hit):
            return hit.tid.iloc[0]
    sys.exit(f"Território não encontrado: {nome!r} (use o nome do painel, ex.: 'Pará' ou 'Marabá (PA)')")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("territorio")
    ap.add_argument("-o", "--saida")
    ap.add_argument("--parte", action="store_true", help="estado só em parte na Amazônia Legal: usa a parcela na região")
    ap.add_argument("--comparar", nargs="*", default=[], help="outros territórios do mesmo tipo (até 4)")
    ap.add_argument("--eixos", nargs="*", type=int, default=[], help="números dos eixos (padrão: todos)")
    ap.add_argument("--tabela", action="store_true", help="inclui a tabela-resumo no início de cada eixo")
    a = ap.parse_args()
    D = data.load()
    tid = achar(D, a.territorio)
    REG = D["registry"]
    inds = (tuple(k for k in D["indicators"] if int(REG[k].axis.split(".")[0]) in a.eixos) if a.eixos else None)
    secoes = relatorio.Opcoes(tid).secoes + (("tabela",) if a.tabela else ())
    op = relatorio.Opcoes(tid, a.parte, tuple(achar(D, c) for c in a.comparar[:4]), inds=inds, secoes=secoes)
    t0 = time.time()
    pdf = relatorio.gerar(D, op)
    saida = Path(a.saida or f"relatorio_{tid.replace(':', '_').replace(' ', '_')}.pdf")
    saida.write_bytes(pdf)
    print(f"{saida}: {relatorio.n_paginas(pdf)} páginas, {len(pdf) / 1024:.0f} KB em {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
