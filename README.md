# PRDA · Painel do Diagnóstico Quantitativo da Amazônia Legal

Painel Streamlit (SUDAM · PNUD · Instituto Publix) construído a partir da planilha do Banco de Indicadores
do PRDA e do protótipo em `concept/`.

```bash
pip install -r requirements.txt
python scripts/build_data.py          # gera as bases em build/
python -m streamlit run main.py
```

## De onde vêm os dados
```
data/<planilha>.xlsx  ──  scripts/build_data.py  ──►  build/            ──►  gs://<bucket>/painel/
  abas de recorte +          lê, filtra, valida          dados.parquet           (o painel lê daqui)
  "Lista de Indicadores"     e calcula a Amazônia Legal  fichas.json
                                                         manifest.json
```
- **Indicadores ativos:** `config/indicadores.toml`. Só o ID da ficha é obrigatório; rótulo, unidade, formato,
  regra de agregação e peso podem ser ajustados ali.
- **Ligação coluna → ficha:** pelo nome do indicador (ignorando acentos, caixa e pontuação). Se a coluna tiver outro
  nome, informe `coluna` no config.
- **Amazônia Legal:** calculada a partir dos municípios com `Amazônia Legal = SIM`, pela regra da ficha: soma, ou
  média ponderada (razão entre totais) com o `peso` do config. Brasil, Regiões e Estados vêm prontos da planilha.
- **Validação:** coluna ausente, ID sem ficha, regra de agregação desconhecida, texto em coluna numérica ou
  território repetido interrompem a geração; nada é gravado.
- **Atualização no painel:** a cada 10 minutos o painel confere o `manifest.json`; se a versão mudou, recarrega.
  Sem a seção `[gcs]` em `.streamlit/secrets.toml`, o painel lê direto de `build/`.

## Atualizar o painel
1. Salve a planilha nova em `data/` (o script usa o `.xlsx` mais recente).
2. Para incluir indicadores, acrescente blocos `[[indicador]]` em `config/indicadores.toml`.
3. Rode `python scripts/build_data.py` e confira o relatório.
4. No Console do Google Cloud, abra o bucket, entre na pasta `painel/` e envie os três arquivos de `build/`,
   substituindo os anteriores.

## Abas
Visão Geral · Mapa Territorial · Perfil do Território · Séries Temporais · Ranking · Comparações · Sobre.

## Estrutura
- `main.py`: app e abas · `src/data.py`: carga das bases · `src/charts.py`: gráficos · `src/theme.py`: identidade visual
- `scripts/build_data.py`: planilha → bases do painel · `config/indicadores.toml`: indicadores ativos
- `assets/geo/`: malhas do IBGE · `assets/indicators.json`: cores e descrições dos eixos
