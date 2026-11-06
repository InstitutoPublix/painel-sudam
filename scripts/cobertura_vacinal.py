"""Converte a planilha do painel de cobertura vacinal do Ministério da Saúde (doses e população-alvo por vacina e
município) em assets/cobertura_vacinal_municipios.csv.

Uso:
    python scripts/cobertura_vacinal.py <planilha.xlsx> --ano 2025

Por que existe: a planilha do PRDA traz a cobertura vacinal (IND-038) só como % de cada município. A ficha calcula a
cobertura como média simples das coberturas das vacinas do calendário; para a Amazônia Legal, cada vacina tem a sua
cobertura da região (doses aplicadas ÷ população-alvo, somadas nos municípios) e depois se tira a média entre as
vacinas. O build faz essa conta (`agregacao = "media_razoes"` em config/indicadores.toml) com os totais deste arquivo.

Entrada: a exportação do painel, com duas linhas de cabeçalho (vacina; "Cobertura Vacinal (%)", "Numerador",
"Denominador") e linhas de totais por região, UF e região de saúde, que ficam de fora; só entram as linhas de
município ("<código IBGE de 6 dígitos> - <nome>").
Saída: cod (IBGE, 7 dígitos), ano, vacina, doses, populacao_alvo. Rodar com outro --ano acrescenta o ano ao arquivo;
o mesmo ano é substituído.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "cobertura_vacinal_municipios.csv"
MUNICIPIOS = ROOT / "assets" / "municipios_caracterizacao.csv"  # códigos de 7 dígitos de todos os municípios


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("planilha", type=Path)
    ap.add_argument("--ano", type=int, required=True)
    args = ap.parse_args()

    raw = pd.read_excel(args.planilha, header=None)
    vacinas, medidas = raw.iloc[0].ffill(), raw.iloc[1].astype(str).str.strip()
    col_mun = medidas[medidas == "Município"].index[0]
    linhas = raw.iloc[2:]
    linhas = linhas[linhas[col_mun].astype(str).str.match(r"^\d{6} ")]
    cod6 = linhas[col_mun].str[:6].astype(int)

    partes = []
    for vacina in dict.fromkeys(vacinas[medidas == "Numerador"]):
        num = medidas.index[(vacinas == vacina) & (medidas == "Numerador")][0]
        den = medidas.index[(vacinas == vacina) & (medidas == "Denominador")][0]
        partes.append(pd.DataFrame({"cod6": cod6.to_numpy(), "vacina": vacina,
                                    "doses": pd.to_numeric(linhas[num], errors="coerce").to_numpy(),
                                    "populacao_alvo": pd.to_numeric(linhas[den], errors="coerce").to_numpy()}))
    novo = pd.concat(partes, ignore_index=True)

    # código de 6 dígitos (sem o verificador) -> 7 dígitos
    cods = pd.read_csv(MUNICIPIOS, usecols=["cod"]).cod
    seis = pd.Series(cods.to_numpy(), index=cods // 10)
    sem_cod = sorted(set(novo.cod6) - set(seis.index))
    if sem_cod:
        raise SystemExit(f"{len(sem_cod)} códigos sem correspondência no IBGE (ex.: {sem_cod[:5]}).")
    novo.insert(0, "cod", seis.reindex(novo.pop("cod6")).to_numpy())
    novo.insert(1, "ano", args.ano)

    if OUT.exists():
        antigo = pd.read_csv(OUT)
        novo = pd.concat([antigo[antigo.ano != args.ano], novo])
    novo.sort_values(["ano", "cod", "vacina"]).to_csv(OUT, index=False)
    print(f"{OUT.relative_to(ROOT)}: {cod6.nunique()} municípios e {novo[novo.ano == args.ano].vacina.nunique()} "
          f"vacinas em {args.ano}.")


if __name__ == "__main__":
    main()
