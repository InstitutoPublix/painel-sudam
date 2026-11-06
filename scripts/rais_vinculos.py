"""Converte a tabulação dos microdados da RAIS (vínculos por município e escolaridade) em
assets/rais_vinculos_municipios.csv.

Uso:
    python scripts/rais_vinculos.py <tabulacao.csv> --ano 2025

Por que existe: a planilha traz "Empregos formais com ensino superior" (IND-173) só como percentual de cada município,
sem o número de vínculos. A ficha manda calcular a Amazônia Legal pela razão de totais (vínculos com superior completo,
mestrado ou doutorado ÷ vínculos ativos em 31/12), e para isso são precisos os dois totais. O build os usa como
numerador e denominador (`numerador_rais` e `peso_rais` em config/indicadores.toml).

Entrada: CSV separado por ";" com as colunas municipio (código IBGE de 6 dígitos), escolaridade (grau de instrução da
RAIS, 1 a 11) e vinculos. Linhas de município não identificado (999999) ficam de fora.
Saída: cod (IBGE, 7 dígitos), ano, total (todos os vínculos), superior (graus 9, 10 e 11: superior completo, mestrado
e doutorado). Rodar com outro --ano acrescenta o ano ao arquivo; o mesmo ano é substituído.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "rais_vinculos_municipios.csv"
MUNICIPIOS = ROOT / "assets" / "municipios_caracterizacao.csv"  # códigos de 7 dígitos de todos os municípios
SUPERIOR = {9, 10, 11}  # superior completo, mestrado, doutorado


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tabulacao", type=Path)
    ap.add_argument("--ano", type=int, required=True)
    args = ap.parse_args()

    raw = pd.read_csv(args.tabulacao, sep=";", usecols=["municipio", "escolaridade", "vinculos"])
    raw = raw[raw.municipio != 999999]
    total = raw.groupby("municipio").vinculos.sum()
    sup = raw[raw.escolaridade.isin(SUPERIOR)].groupby("municipio").vinculos.sum().reindex(total.index, fill_value=0)

    # código de 6 dígitos (sem o verificador) -> 7 dígitos
    cods = pd.read_csv(MUNICIPIOS, usecols=["cod"]).cod
    seis = pd.Series(cods.to_numpy(), index=cods // 10)
    sem_cod = sorted(set(total.index) - set(seis.index))
    if sem_cod:
        raise SystemExit(f"{len(sem_cod)} códigos sem correspondência no IBGE (ex.: {sem_cod[:5]}).")

    novo = pd.DataFrame({"cod": seis.reindex(total.index).to_numpy(), "ano": args.ano,
                         "total": total.to_numpy(), "superior": sup.to_numpy()})
    if OUT.exists():
        antigo = pd.read_csv(OUT)
        novo = pd.concat([antigo[antigo.ano != args.ano], novo])
    novo.sort_values(["ano", "cod"]).to_csv(OUT, index=False)
    num = lambda v: f"{int(v):,}".replace(",", ".")  # noqa: E731
    print(f"{OUT.relative_to(ROOT)}: {len(total)} municípios em {args.ano}, "
          f"{num(total.sum())} vínculos ({num(sup.sum())} com superior).")


if __name__ == "__main__":
    main()
