# PRDA · Painel do Diagnóstico Quantitativo da Amazônia Legal

Painel Streamlit (SUDAM · PNUD · Instituto Publix) construído a partir das bases em `data/` e do protótipo em `concept/`.

```bash
pip install -r requirements.txt
python3 -m streamlit run main.py   # ou `streamlit run main.py`, se estiver no PATH
```

## Como as bases são lidas
Cada CSV é um recorte (Brasil, Regional, Estadual, Municipal). As colunas até **Ano** identificam território/período;
**cada coluna depois de Ano é um indicador** (nome da coluna = nome do indicador). Novos indicadores ao final dos CSVs
aparecem sozinhos no painel. A **Amazônia Legal** é a soma dos municípios com `Amazônia Legal = SIM`.
`PIB per capita` é derivado (PIB ÷ população do mesmo ano).

## Abas
Visão Geral · Mapa Territorial · Perfil do Território · Séries Temporais · Ranking · Comparações · Sobre.

## Estrutura
- `main.py` — app e abas · `src/data.py` — carga/padronização · `src/charts.py` — gráficos
- `src/theme.py` — identidade visual · `assets/geo/` — malhas do IBGE
- `assets/indicators.json` — fichas dos indicadores extraídas do protótipo HTML
