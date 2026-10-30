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
- **Indicadores com várias colunas:** a planilha detalha alguns indicadores em colunas `Nome do indicador — categoria`
  (ex.: rebanho por tipo, lavoura por produto). Cada entrada do painel usa uma delas com `categoria`, ou soma todas com
  `somar_categorias = true`. Uma mesma ficha pode gerar várias entradas; cada uma recebe uma `chave` própria
  (ex.: `IND-185-soja`), e a ficha no Sobre o Painel mostra o ID original e a categoria.
- **Amazônia Legal:** calculada a partir dos municípios com `Amazônia Legal = SIM`, pela regra da ficha: soma, ou
  média ponderada (razão entre totais) com o `peso` do config. Brasil, Regiões e Estados vêm prontos da planilha.
  O peso pode ser outro indicador (`peso`) ou uma coluna da planilha que não está no painel (`peso_coluna`).
- **Peso do Censo (`peso_censo`):** indicadores dos Censos (urbanização, razão de dependência, população indígena e
  quilombola) vêm na planilha só como taxa de cada município, sem a população que os originou. Para a Amazônia Legal
  bater com o IBGE (somar os municípios e recalcular a razão, como manda a ficha), o build usa como peso a população dos
  Censos 2010 e 2022 em `assets/censo_municipios.csv`, que o script `python scripts/censo_ibge.py` baixa do SIDRA
  (tabelas 9923, 202, 9514 e 200, as mesmas do Roteiro de Extração). Use `peso_censo = "pop_total"` (ou `pop_urbana`,
  `pop_0_14`, `pop_15_64`, `pop_65_mais`) no bloco do indicador. Se a planilha passar a trazer essa população, o
  `peso_coluna` substitui o arquivo.
- **Soma dos estados (`agregacao = "soma_estados"`):** quando o dado municipal é parcial (o IBGE suprime municípios
  pequenos na amostra, como na migração internacional), a Amazônia Legal é a soma dos estados dela, e o Maranhão entra
  inteiro. O painel avisa isso na nota do indicador.
- **Conferência da regra:** antes de incluir um indicador, aplique a regra aos municípios de cada estado e compare com
  a aba Estadual. Quando a planilha não traz o denominador exato, o painel aceita uma aproximação só se a diferença
  for pequena (mediana até 1,5%) e a registra em `nota_agregacao`, que aparece no painel. Quando nenhuma regra
  reproduz os estados, use `agregacao = "publicado"`: a Amazônia Legal fica sem valor e `nota_agregacao` diz por quê.
  Os comentários de cada bloco no `config/indicadores.toml` registram o resultado da conferência.
- **Indicador só estadual:** a coluna municipal é opcional. Sem ela, o indicador aparece em Brasil, Regiões e
  Estados (se houver) e o build avisa que não há Município nem Amazônia Legal. Use `agregacao = "publicado"` com
  uma `nota_agregacao`: somar os estados incluiria o Maranhão inteiro. No painel, a Visão Geral troca os cartões e
  gráficos de municípios pelos de estados, e o Mapa e Ranking oferece só os níveis que o indicador tem.
- **Seções com muitos indicadores:** os cartões da Visão Geral, o Resumo do Perfil do Território, a comparação A × B
  e o gráfico de todos os indicadores em Séries Temporais mostram um eixo por vez (começando no eixo do indicador
  escolhido), para o painel continuar leve com mais de 200 indicadores.
- **Cobertura mínima:** em cada ano, a Amazônia Legal só é calculada se pelo menos 90% dos municípios da região
  tiverem dado; abaixo disso o ano fica vazio e o build avisa. Ajuste com `cobertura_minima` (%) no
  `config/indicadores.toml` ou com `--cobertura-minima` para todos. Em contagens esparsas (aeroportos, portos,
  CFEM…), célula vazia quer dizer zero: use `cobertura_minima = 0` depois de conferir que a soma bate com os estados.
- **Média simples e `fator_municipal`:** para indicadores de existência (sim/não por município), use
  `agregacao = "media_simples"`; a Amazônia Legal vira o % de municípios. Se a aba municipal vem em 0/1 e as demais
  em %, use `fator_municipal = 100` para alinhar as escalas. Confira sempre o peso ou a regra reproduzindo o valor
  estadual da planilha a partir dos municípios.
- **"Dado já publicado":** indicadores com essa regra na ficha não são agregados; a Amazônia Legal fica vazia.
- **Observação da planilha:** a coluna `Observação` da `Lista de Indicadores` (quebras de série, anos ausentes) aparece
  na legenda "Sobre o indicador" de cada aba e na ficha do Sobre o Painel.
- **Metadados por série:** quando uma ficha reúne fontes distintas, cada entrada pode usar `[indicador.ficha]`
  no `config/indicadores.toml`, com os nomes exatos dos campos da `Lista de Indicadores` (por exemplo,
  `"Fonte dos Dados"`, `"Periodicidade"` e `"Série Histórica Disponível"`). Esses campos substituem apenas os metadados
  da entrada; o ID da ficha de origem e a planilha são preservados. Campos desconhecidos interrompem o build.
- **Base enxuta:** `dados.parquet` guarda só as células com valor; o painel recompõe os anos vazios nas séries.
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
`data/`, ignorando arquivos temporários do Excel e os que têm `ANTIGA` no nome. Em rotinas de publicação, prefira
sempre informar o arquivo explicitamente para evitar ambiguidades.

### Estados só em parte na Amazônia Legal

Hoje, o Maranhão: 181 dos 217 municípios fazem parte da região. Além do valor publicado para o estado inteiro (nível
`Estado`), `build_data.py` calcula, a partir dos municípios da região e com a mesma regra de agregação de cada indicador,
o valor da **parcela do estado na Amazônia Legal** (nível `Estado (parte AL)`). O painel usa a parcela nas telas com
abrangência Amazônia Legal e o estado inteiro na abrangência Brasil inteiro; a aba Perfil do Território permite alternar. Os
indicadores publicados só para o estado todo (regra `publicado`, ex.: IDHM) ficam sem parcela e mantêm o valor do estado
inteiro, com aviso. Toda tela com esses estados traz uma nota dizendo qual valor está em uso. Quem muda a lista de
municípios da região deve rodar de novo `scripts/geo_al_parcial.py` (contorno no mapa) e `scripts/build_data.py`.

## Catálogo dos indicadores (fora do repositório)

`python scripts/catalogo.py` gera `catalogo/catalogo_indicadores.xlsx` (pasta ignorada pelo git) com os 172
indicadores da planilha: o que já está no painel, o que é candidato e por que cada um está parado. As colunas em
amarelo (Situação, Pendência, Decisão, Responsável, Observações) são preenchidas à mão e preservadas quando o
catálogo é gerado de novo; as demais são recalculadas a partir da planilha e do `config/indicadores.toml`.

## IDHM: duas fontes, duas séries

Conforme o Roteiro de Extração da ficha IND-007, o seletor de indicadores oferece:

| Entrada | Chave na base | Anos carregados | Níveis disponíveis |
| --- | --- | --- | --- |
| IDHM — Censo | `IND-007` | 2010 | Município, Estado e Brasil |
| Radar IDHM — PNAD Contínua | `IND-007-radar` | 2015–2024 | Estado e Brasil |

A primeira usa a coluna principal do IDHM; a segunda usa a coluna própria do Radar IDHM, ambas da mesma ficha.
As fontes não são emendadas: anos, gráficos e variações são consultados pela chave de cada série. O IDHM do Censo
tem um único ano no painel e não oferece variação anual. O Radar não oferece recorte municipal. Grandes Regiões
e Amazônia Legal não têm índice próprio em nenhuma das duas séries; não se calcula soma ou média desses índices.
Para o Maranhão, o valor é sempre o do estado inteiro, inclusive na abrangência Amazônia Legal, com aviso.

Os metadados de cada entrada identificam sua fonte, periodicidade e cobertura. Os CSVs de ranking e séries também
identificam o indicador e a fonte. A separação preserva os valores municipais de 2010 usados na caracterização
dos municípios (classe do IDHM).

Após gerar a base, execute `.venv/bin/python -m unittest discover -s tests -v` para conferir a separação das fontes,
os recortes e a troca entre séries no painel. Os testes de interface usam a base local, sem acessar o bucket.

## Abas
Visão Geral · Mapa e Ranking · Perfil do Território · Séries Temporais · Comparações · Sobre.

## Estrutura
- `main.py`: app e abas · `src/data.py`: carga das bases · `src/charts.py`: gráficos · `src/theme.py`: identidade visual
- `scripts/build_data.py`: planilha → bases do painel · `scripts/upload_gcs.py`: bases → bucket · `scripts/catalogo.py`: catálogo dos indicadores · `config/indicadores.toml`: indicadores ativos
- `assets/geo/`: malhas do IBGE · `assets/indicators.json`: cores e descrições dos eixos
- `assets/logos/`: a assinatura institucional do topo e do rodapé (`assinatura.png`, recorte de `assina_sudam.png`, enviada pelo design: Publix, PNUD, SUDAM, Ministério da Integração e do Desenvolvimento Regional e bandeira); as logos avulsas (`pnud`, `sudam`, `publix`) valem só se esse arquivo não existir. Também o emblema do projeto (`emblema`), em
  `.svg`, `.png`, `.webp` ou `.jpg`, já recortados e leves; os arquivos de origem ficam em `assets/logos/originais/`.
  Sem arquivo, o nome aparece em texto · `assets/brand/ilustracao.*`: arte da capa (opcional; sem ela, usa um mosaico)
