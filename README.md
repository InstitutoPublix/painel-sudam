# PRDA · Painel do Diagnóstico Quantitativo da Amazônia Legal

Painel Streamlit (SUDAM · PNUD · Instituto Publix) construído a partir da planilha do Banco de Indicadores
do PRDA e do protótipo em `concept/`.

```bash
pip install -r requirements.txt
python scripts/build_data.py          # gera as bases em build/
python -m streamlit run main.py
```

## Como o painel recebe novos dados

O painel **não lê a planilha Excel diretamente**. A alimentação acontece em quatro etapas:

1. a equipe atualiza a planilha-base em `data/`;
2. `scripts/build_data.py` seleciona os indicadores, valida os dados e calcula a Amazônia Legal;
3. o script gera `dados.parquet`, `fichas.json` e `manifest.json` em `build/`;
4. `scripts/upload_gcs.py` publica esses três arquivos na pasta `painel/` do bucket. O painel identifica a nova versão e recarrega
   os dados em até 10 minutos, sem precisar alterar ou reiniciar a aplicação.

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
- **Indicador só estadual:** a coluna municipal é opcional. Sem ela, o indicador aparece em Brasil, Regiões e
  Estados (se houver) e o build avisa que não há Município nem Amazônia Legal.
- **Cobertura mínima:** em cada ano, a Amazônia Legal só é calculada se pelo menos 90% dos municípios da região
  tiverem dado; abaixo disso o ano fica vazio e o build avisa. Ajuste com `cobertura_minima` (%) no
  `config/indicadores.toml` ou com `--cobertura-minima` para todos.
- **Média simples e `fator_municipal`:** para indicadores de existência (sim/não por município), use
  `agregacao = "media_simples"`; a Amazônia Legal vira o % de municípios. Se a aba municipal vem em 0/1 e as demais
  em %, use `fator_municipal = 100` para alinhar as escalas. Confira sempre o peso ou a regra reproduzindo o valor
  estadual da planilha a partir dos municípios.
- **"Dado já publicado":** indicadores com essa regra na ficha não são agregados; a Amazônia Legal fica vazia.
- **Validação:** coluna ausente, ID sem ficha, regra de agregação desconhecida, texto em coluna numérica ou
  território repetido interrompem a geração; nada é gravado.
- **Atualização no painel:** a cada 10 minutos o painel confere o `manifest.json`; se a versão mudou, recarrega.
  Sem a seção `[gcs]` em `.streamlit/secrets.toml`, o painel lê direto de `build/`.

## Procedimento de atualização

### Quando chegaram novos valores ou anos

1. Atualize as abas `Recorte Municipal`, `Recorte Estadual`, `Recorte Regional` e `Recorte Brasil` da planilha.
   Preserve os códigos territoriais, a coluna `Ano` e os nomes das colunas de indicadores.
2. Salve o novo `.xlsx` em `data/`.
3. Na raiz do projeto, indique explicitamente a planilha que deve ser processada:

   ```bash
   python scripts/build_data.py "data/NOME_DA_PLANILHA.xlsx"
   ```

4. Confira o relatório. Se houver **erros**, nada é gravado. Se aparecer **OK**, revise também os avisos.
5. Publique no bucket:

   ```bash
   gcloud auth application-default login      # uma vez; precisa de conta com permissão de escrita no bucket
   python scripts/upload_gcs.py --dry-run     # confere e mostra o que muda
   python scripts/upload_gcs.py               # pede confirmação e envia
   ```

   O script lê o bucket de `[gcs]` em `.streamlit/secrets.toml`, confere se os três arquivos de `build/` são da
   mesma versão, guarda a versão anterior em `painel/anteriores/<versão>/` e envia o `manifest.json` por último.
   A conta de leitura usada pelo painel não serve para o envio; use `--credenciais chave.json` se preferir uma
   conta de serviço de escrita. Para voltar a uma versão, copie os três arquivos de `anteriores/<versão>/` de volta
   para `painel/`.

Não é necessário alterar `config/indicadores.toml` para atualizar um indicador que já aparece no painel.

### Quando entrou um indicador novo

Antes de executar os passos acima:

1. cadastre o indicador, com ID único e metadados, na aba `Lista de Indicadores`;
2. inclua uma coluna com seus valores nas abas de recorte — a aba municipal é obrigatória; as demais são
   recomendadas e, quando ausentes, geram um aviso;
3. acrescente um bloco `[[indicador]]` com o mesmo ID em `config/indicadores.toml`. Só o `id` é obrigatório;
   use `coluna`, `agregacao` e `peso` quando a associação ou o cálculo não puder ser deduzido da ficha.

Por padrão, executar `python scripts/build_data.py` sem caminho usa o `.xlsx` modificado mais recentemente em
`data/`. Em rotinas de publicação, prefira sempre informar o arquivo explicitamente para evitar ambiguidades.

### Estados só em parte na Amazônia Legal

Hoje, o Maranhão: 181 dos 217 municípios fazem parte da região. Além do valor publicado para o estado inteiro (nível
`Estado`), `build_data.py` calcula, a partir dos municípios da região e com a mesma regra de agregação de cada indicador,
o valor da **parcela do estado na Amazônia Legal** (nível `Estado (parte AL)`). O painel usa a parcela nas telas com
abrangência Amazônia Legal e o estado inteiro na abrangência Brasil inteiro; a aba Território permite alternar. Os
indicadores publicados só para o estado todo (regra `publicado`, ex.: IDHM) ficam sem parcela e mantêm o valor do estado
inteiro, com aviso. Toda tela com esses estados traz uma nota dizendo qual valor está em uso. Quem muda a lista de
municípios da região deve rodar de novo `scripts/geo_al_parcial.py` (contorno no mapa) e `scripts/build_data.py`.

## Catálogo dos indicadores (fora do repositório)

`python scripts/catalogo.py` gera `catalogo/catalogo_indicadores.xlsx` (pasta ignorada pelo git) com os 172
indicadores da planilha: o que já está no painel, o que é candidato e por que cada um está parado. As colunas em
amarelo (Situação, Pendência, Decisão, Responsável, Observações) são preenchidas à mão e preservadas quando o
catálogo é gerado de novo; as demais são recalculadas a partir da planilha e do `config/indicadores.toml`.

## Abas
Visão Geral · Mapa e Ranking · Território · Séries Temporais · Comparações · Sobre.

## Estrutura
- `main.py`: app e abas · `src/data.py`: carga das bases · `src/charts.py`: gráficos · `src/theme.py`: identidade visual
- `scripts/build_data.py`: planilha → bases do painel · `scripts/upload_gcs.py`: bases → bucket · `scripts/catalogo.py`: catálogo dos indicadores · `config/indicadores.toml`: indicadores ativos
- `assets/geo/`: malhas do IBGE · `assets/indicators.json`: cores e descrições dos eixos
- `assets/logos/`: logos do topo e do rodapé (`pnud`, `sudam`, `publix`) e o emblema do projeto (`emblema`), em
  `.svg`, `.png`, `.webp` ou `.jpg`, já recortados e leves; os arquivos de origem ficam em `assets/logos/originais/`.
  Sem arquivo, o nome aparece em texto · `assets/brand/ilustracao.*`: arte da capa (opcional; sem ela, usa um mosaico)
