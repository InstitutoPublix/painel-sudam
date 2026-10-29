"""Baixa do IBGE (SIDRA) a população dos Censos 2010 e 2022 por município e grava assets/censo_municipios.csv.

Uso:
    python scripts/censo_ibge.py

Por que existe: a planilha traz a taxa de urbanização, a razão de dependência e outros indicadores dos Censos já como
taxa de cada município, mas não a população do Censo que as originou. Para calcular a Amazônia Legal corretamente (somar
os municípios e recalcular a razão, como manda a ficha) é preciso essa população. O build usa este arquivo como peso
(`peso_censo` em config/indicadores.toml). Os números são os mesmos que o Roteiro de Extração manda extrair:

    2022  Tabela 9923 (população total e urbana) e Tabela 9514 (população por idade)
    2010  Tabela 202  (população total e urbana) e Tabela 200  (população por idade)

Colunas: cod (IBGE, 7 dígitos), ano, pop_total, pop_urbana, pop_0_14, pop_15_64, pop_65_mais.
Rode de novo só se o IBGE revisar os dados dos Censos; o arquivo é pequeno e fica no repositório.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "censo_municipios.csv"
API = "https://apisidra.ibge.gov.br/values"
UFS = [11, 12, 13, 14, 15, 16, 17, 21, 22, 23, 24, 25, 26, 27, 28, 29, 31, 32, 33, 35, 41, 42, 43, 50, 51, 52, 53]
QUINQUENAL = re.compile(r"^(\d+) a (\d+) anos$")


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


def faixa(rotulo: str) -> str | None:
    """'0 a 4 anos' -> '0_14'; '65 a 69 anos' e '100 anos ou mais' -> '65_mais'; outros rótulos (idade simples, meses) -> None."""
    if rotulo == "100 anos ou mais":
        return "65_mais"
    m = QUINQUENAL.match(rotulo)
    if not m:
        return None
    ini = int(m.group(1))
    return "0_14" if ini <= 10 else "15_64" if ini <= 60 else "65_mais"


_CODIGOS: dict[int, str] = {}
# (consulta de descoberta, nº da coluna da faixa de idade na resposta) por Censo; o Acre é pequeno e basta para listar as faixas
_IDADE = {2022: ("t/9514/n6/in%20n3%2012/v/93/p/2022/c2/0/c287/all", "D5"),
          2010: ("t/200/n6/in%20n3%2012/v/93/p/2010/c1/0/c2/0/c58/all", "D6")}


def codigos_idade(ano: int) -> str:
    """Códigos SIDRA só das faixas quinquenais (0 a 4 … 95 a 99 e 100 ou mais). Pedir todas as idades estoura o limite de
    100 mil valores por consulta nos estados com muitos municípios; com as faixas quinquenais cabe em qualquer estado."""
    if ano not in _CODIGOS:
        caminho, col = _IDADE[ano]
        cods = sorted({r[f"{col}C"] for r in consulta(caminho) if faixa(r[f"{col}N"])})
        _CODIGOS[ano] = ",".join(cods)
    return _CODIGOS[ano]


def uf(n3: int) -> pd.DataFrame:
    base = f"n6/in%20n3%20{n3}/v/93"
    linhas = []
    # total e urbana
    t22 = consulta(f"t/9923/{base}/p/2022/c1/0,1")
    t10 = consulta(f"t/202/{base}/p/2010/c1/0,1/c2/0")
    for ano, rs, col_sit in ((2022, t22, "D4N"), (2010, t10, "D4N")):
        for r in rs:
            sit = "urbana" if r[col_sit] == "Urbana" else "total"
            linhas.append((int(r["D1C"]), ano, "pop_" + sit, float(r["V"]) if r["V"] not in ("-", "..", "...", "X") else None))
    # idade (grupos quinquenais)
    i22 = consulta(f"t/9514/{base}/p/2022/c2/0/c287/{codigos_idade(2022)}")
    i10 = consulta(f"t/200/{base}/p/2010/c1/0/c2/0/c58/{codigos_idade(2010)}")
    for ano, rs, col in ((2022, i22, "D5N"), (2010, i10, "D6N")):
        for r in rs:
            f = faixa(r[col])
            if f and r["V"] not in ("-", "..", "...", "X"):
                linhas.append((int(r["D1C"]), ano, "pop_" + f, float(r["V"])))
    df = pd.DataFrame(linhas, columns=["cod", "ano", "campo", "valor"])
    return df.groupby(["cod", "ano", "campo"], as_index=False).valor.sum().pivot(
        index=["cod", "ano"], columns="campo", values="valor").reset_index()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    partes = []
    for n3 in UFS:
        print(f"UF {n3}…", flush=True)
        partes.append(uf(n3))
    df = pd.concat(partes, ignore_index=True)
    df.columns.name = None
    df = df.rename(columns={"pop_0_14": "pop_0_14", "pop_15_64": "pop_15_64", "pop_65_mais": "pop_65_mais"})
    cols = ["cod", "ano", "pop_total", "pop_urbana", "pop_0_14", "pop_15_64", "pop_65_mais"]
    df = df[cols].sort_values(["ano", "cod"])
    # conferências: a soma das faixas etárias reproduz o total, e há ~5.570 municípios em cada Censo
    soma = df[["pop_0_14", "pop_15_64", "pop_65_mais"]].sum(axis=1)
    dif = (soma - df.pop_total).abs() / df.pop_total
    print(f"municípios por Censo: {df.groupby('ano').cod.nunique().to_dict()} · soma das faixas etárias difere do total "
          f"em até {dif.max():.4%}")
    for ano, g in df.groupby("ano"):
        print(f"  {ano}: população do Brasil = {int(g.pop_total.sum()):,}".replace(",", "."))
    df.astype({"cod": "int64", "ano": "int64"}).to_csv(OUT, index=False, float_format="%.0f")
    print(f"gravado {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
