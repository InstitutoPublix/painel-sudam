"""Baixa do IBGE (SIDRA, tabela 5938 — PIB dos Municípios) o valor adicionado bruto total de cada município e grava
assets/valor_adicionado_municipios.csv.

Uso:
    python scripts/valor_adicionado_ibge.py

Por que existe: a planilha traz a participação de cada setor no valor adicionado (agropecuária, indústria, serviços e
administração pública, IND-070 a IND-073) só em %, sem o valor adicionado em reais. A ficha manda calcular a Amazônia
Legal como o IBGE faz para as UFs: soma do valor adicionado do setor nos municípios ÷ soma do valor adicionado total
× 100. Como a participação de cada município é VA do setor ÷ VA total, a média das participações ponderada pelo VA total
dá exatamente essa razão — e as quatro participações somam 100%. O build usa este arquivo como peso (`peso_pib =
"va_total"` em config/indicadores.toml).

Colunas: cod (IBGE, 7 dígitos), ano, va_total (R$ mil, a preços correntes).
Rode de novo quando o IBGE publicar um novo ano do PIB dos Municípios; o arquivo é pequeno e fica no repositório.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "valor_adicionado_municipios.csv"
API = "https://apisidra.ibge.gov.br/values"
UFS = [11, 12, 13, 14, 15, 16, 17, 21, 22, 23, 24, 25, 26, 27, 28, 29, 31, 32, 33, 35, 41, 42, 43, 50, 51, 52, 53]
VA_TOTAL = 498  # Valor adicionado bruto a preços correntes total (Mil Reais)
ANO_INICIAL = 2015


def consulta(caminho: str, tentativas: int = 4) -> list[dict]:
    for t in range(tentativas):
        try:
            with urllib.request.urlopen(f"{API}/{caminho}", timeout=120) as r:
                return json.load(r)[1:]  # a 1ª linha é o cabeçalho
        except Exception as e:  # rede instável: tenta de novo
            if t == tentativas - 1:
                raise
            print(f"  nova tentativa ({e})", file=sys.stderr)
            time.sleep(3 * (t + 1))
    return []


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    linhas = []
    for n3 in UFS:
        print(f"UF {n3}…", flush=True)
        for r in consulta(f"t/5938/n6/in%20n3%20{n3}/v/{VA_TOTAL}/p/all"):
            if int(r["D3C"]) >= ANO_INICIAL and r["V"] not in ("-", "..", "...", "X"):
                linhas.append((int(r["D1C"]), int(r["D3C"]), float(r["V"])))
    df = pd.DataFrame(linhas, columns=["cod", "ano", "va_total"]).sort_values(["ano", "cod"])
    # conferência: ~5.570 municípios por ano
    print("municípios por ano:", df.groupby("ano").cod.nunique().to_dict())
    df.to_csv(OUT, index=False, float_format="%.0f")
    print(f"gravado {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
