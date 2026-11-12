"""Converte a tabulação da população residente da RIPSA (TABNET/DATASUS, por município e ano) em
assets/populacao_ripsa_municipios.csv.

Uso:
    python scripts/populacao_ripsa.py <populacao-residente.csv>
    (hoje: assets/IND-040+041+048+062+113+188+190+197_populacao-residente_ripsa_municipios.csv, 2015–2025)

Por que existe: as emissões de CO2e per capita (IND-056) de cada município foram calculadas com a população da RIPSA
(Estudo de Estimativas Populacionais por Município, Idade e Sexo 2000-2025), não com a "População Total" do Recorte
Municipal. As duas diferem em vários anos, e a da planilha não tem 2022 nem 2023. A Amazônia Legal, então, é a soma de
(per capita × população RIPSA) ÷ a soma da população RIPSA: o build usa este arquivo como peso (`peso_ripsa` em
config/indicadores.toml).

Entrada: o CSV exportado pelo TABNET (Latin-1, separado por ";", uma coluna por ano), com as linhas
"<código IBGE de 6 dígitos> <NOME>". A linha de total e as notas de rodapé ficam de fora.
Saída: cod (IBGE, 7 dígitos), ano, pop. O arquivo é refeito por inteiro a cada execução.
"""
from __future__ import annotations

import argparse
import io
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "populacao_ripsa_municipios.csv"
MUNICIPIOS = ROOT / "assets" / "municipios_caracterizacao.csv"  # códigos de 7 dígitos de todos os municípios


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tabulacao", type=Path)
    args = ap.parse_args()

    linhas = args.tabulacao.read_text(encoding="latin-1").splitlines()
    cabecalho = next(i for i, l in enumerate(linhas) if l.startswith('"Munic'))
    corpo = [linhas[cabecalho]] + [l for l in linhas[cabecalho + 1:] if re.match(r'^"\d{6} ', l)]
    df = pd.read_csv(io.StringIO("\n".join(corpo)), sep=";", na_values="-")
    df.index = df.pop(df.columns[0]).str[:6].astype(int).rename("cod6")
    df = df.drop(columns="Total", errors="ignore")
    df.columns = df.columns.astype(int).rename("ano")
    tab = df.stack().dropna().astype(int).rename("pop")  # município criado depois (ex.: Boa Esperança do Norte, 2025) fica sem os anos anteriores

    # código de 6 dígitos (sem o verificador) -> 7 dígitos
    cods = pd.read_csv(MUNICIPIOS, usecols=["cod"]).cod
    seis = pd.Series(cods.to_numpy(), index=cods // 10)
    cod6 = tab.index.get_level_values("cod6")
    sem_cod = sorted(set(cod6) - set(seis.index))
    if sem_cod:
        raise SystemExit(f"{len(sem_cod)} códigos sem correspondência no IBGE (ex.: {sem_cod[:5]}).")

    out = tab.reset_index()
    out.insert(0, "cod", seis.reindex(out.pop("cod6")).to_numpy())
    out[["cod", "ano", "pop"]].sort_values(["ano", "cod"]).to_csv(OUT, index=False)
    anos = sorted(out.ano.unique())
    ult = out[out.ano == anos[-1]]
    total = f"{int(ult['pop'].sum()):,}".replace(",", ".")
    print(f"{OUT.relative_to(ROOT)}: {out.cod.nunique()} municípios, {anos[0]}–{anos[-1]}; em {anos[-1]}, {total} habitantes.")


if __name__ == "__main__":
    main()
