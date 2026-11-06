"""Converte as tabulações do TABNET/DATASUS (óbitos infantis do SIM e nascidos vivos do SINASC, por município e ano) em
assets/mortalidade_infantil_municipios.csv.

Uso:
    python scripts/sim_sinasc.py <obitos-infantis.csv> <nascidos-vivos.csv>

Por que existe: a planilha traz a mortalidade infantil (IND-036) só como taxa de cada município, sem óbitos nem
nascimentos. A ficha manda calcular a Amazônia Legal pela razão de totais (óbitos de menores de 1 ano ÷ nascidos vivos
× 1.000), e para isso são precisos os dois totais. O build os usa como numerador e denominador (`numerador_sim` e
`peso_sim` em config/indicadores.toml).

Entrada: o CSV exportado pelo TABNET (Latin-1, separado por ";", uma coluna por ano, "-" para zero), com as linhas
"<código IBGE de 6 dígitos> <NOME>". Linhas de município ignorado, exterior e total ficam de fora.
Saída: cod (IBGE, 7 dígitos), ano, obitos, nascidos. O arquivo é refeito por inteiro a cada execução.
"""
from __future__ import annotations

import argparse
import io
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "mortalidade_infantil_municipios.csv"
MUNICIPIOS = ROOT / "assets" / "municipios_caracterizacao.csv"  # códigos de 7 dígitos de todos os municípios


def le_tabnet(arquivo: Path, nome: str) -> pd.Series:
    """Série (código de 6 dígitos, ano) -> valor de uma tabulação do TABNET."""
    linhas = arquivo.read_text(encoding="latin-1").splitlines()
    cabecalho = next(i for i, l in enumerate(linhas) if l.startswith('"Munic'))
    corpo = [linhas[cabecalho]] + [l for l in linhas[cabecalho + 1:] if re.match(r'^"\d{6} ', l)]
    df = pd.read_csv(io.StringIO("\n".join(corpo)), sep=";", na_values="-").fillna(0)
    df.index = df.pop(df.columns[0]).str[:6].astype(int).rename("cod6")
    df = df[df.index != 0].drop(columns="Total", errors="ignore")  # 000000: ignorado ou exterior
    df.columns = df.columns.astype(int).rename("ano")
    return df.stack().astype(int).rename(nome)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("obitos", type=Path)
    ap.add_argument("nascidos", type=Path)
    args = ap.parse_args()

    tab = pd.concat([le_tabnet(args.obitos, "obitos"), le_tabnet(args.nascidos, "nascidos")], axis=1).fillna(0)

    # código de 6 dígitos (sem o verificador) -> 7 dígitos
    cods = pd.read_csv(MUNICIPIOS, usecols=["cod"]).cod
    seis = pd.Series(cods.to_numpy(), index=cods // 10)
    cod6 = tab.index.get_level_values("cod6")
    sem_cod = sorted(set(cod6) - set(seis.index))
    if sem_cod:
        raise SystemExit(f"{len(sem_cod)} códigos sem correspondência no IBGE (ex.: {sem_cod[:5]}).")

    out = tab.astype(int).reset_index()
    out.insert(0, "cod", seis.reindex(out.pop("cod6")).to_numpy())
    out[["cod", "ano", "obitos", "nascidos"]].sort_values(["ano", "cod"]).to_csv(OUT, index=False)
    anos = sorted(out.ano.unique())
    ult = out[out.ano == anos[-1]]
    num = lambda v: f"{int(v):,}".replace(",", ".")  # noqa: E731
    print(f"{OUT.relative_to(ROOT)}: {out.cod.nunique()} municípios, {anos[0]}–{anos[-1]}; no último ano, "
          f"{num(ult.obitos.sum())} óbitos infantis e {num(ult.nascidos.sum())} nascidos vivos.")


if __name__ == "__main__":
    main()
