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
  O peso pode ser outro indicador (`peso`) ou uma coluna da planilha que não está no painel (`peso_coluna`). As
  exceções, sempre com o motivo no config e na ficha, são `ano_parcial`, `sem_brasil` e `descartar`; quando um valor
  da planilha está errado, o `descartar` é provisório: a correção vai para a planilha e a linha sai do config.
- **Peso do Censo (`peso_censo`):** indicadores dos Censos (urbanização, razão de dependência, população indígena e
  quilombola) vêm na planilha só como taxa de cada município, sem a população que os originou. Para a Amazônia Legal
  bater com o IBGE (somar os municípios e recalcular a razão, como manda a ficha), o build usa como peso a população dos
  Censos 2010 e 2022 em `assets/censo_municipios.csv`, que o script `python scripts/censo_ibge.py` baixa do SIDRA
  (tabelas 9923, 202, 9514 e 200, as mesmas do Roteiro de Extração). Use `peso_censo = "pop_total"` (ou `pop_urbana`,
  `pop_0_14`, `pop_15_64`, `pop_65_mais`) no bloco do indicador. Se a planilha passar a trazer essa população, o
  `peso_coluna` substitui o arquivo.
- **Totais da RAIS (`numerador_rais`, `peso_rais`):** "Empregos formais com ensino superior" (IND-173) vem na planilha
  só como % de cada município. A ficha manda calcular a Amazônia Legal pela razão de totais (vínculos com superior
  completo, mestrado ou doutorado ÷ vínculos ativos em 31/12), e para isso o build lê os dois totais de
  `assets/rais_vinculos_municipios.csv`, gerado da tabulação dos microdados da RAIS por
  `python scripts/rais_vinculos.py <tabulação.csv> --ano 2025`. O arquivo reproduz os percentuais dos 773 municípios e
  dos estados publicados. A razão só sai nos anos que o arquivo tem (hoje, 2025): para os anteriores, rode o script com
  a tabulação de cada ano e refaça o build. Não use o pessoal assalariado do CEMPRE como peso: dá 30,4% em vez de 29,9%.
- **Totais do SIM/SINASC (`numerador_sim`, `peso_sim`):** mesma lógica para a mortalidade infantil (IND-036): óbitos
  de menores de 1 ano ÷ nascidos vivos × 1.000, lidos de `assets/mortalidade_infantil_municipios.csv`, gerado das duas
  tabulações do TABNET por município e ano com
  `python scripts/sim_sinasc.py <óbitos-infantis.csv> <nascidos-vivos.csv>`. O arquivo reproduz o Brasil e os estados
  publicados (diferença até 0,1, das linhas de município ignorado). Ao atualizar a série, exporte as duas tabulações
  com todos os anos e rode o script de novo (ele refaz o arquivo inteiro). Para outra fonte de totais, acrescente-a em
  `TOTAIS_EXTERNOS` (`scripts/build_data.py`).
- **Valor adicionado (`peso_pib = "va_total"`):** a planilha traz a participação de cada setor só em %. A Amazônia
  Legal é a soma do VA do setor ÷ a soma do VA total dos municípios (o cálculo do IBGE para as UFs), com o VA total
  de `assets/valor_adicionado_municipios.csv`, que `python scripts/valor_adicionado_ibge.py` baixa do SIDRA (tabela
  5938). Reproduz as 27 UFs, e as quatro participações somam 100%. Rode o script quando sair um ano novo do PIB dos
  Municípios.
- **Denominador implícito (`peso_implicito`):** para o PIB per capita, o peso de cada município é PIB ÷ PIB per capita,
  a população que o IBGE usou. A Amazônia Legal vira soma do PIB ÷ soma dessa população e reproduz as 27 UFs.
- **Média de razões (`agregacao = "media_razoes"`, `razoes_de`):** para a cobertura vacinal (IND-038), a ficha tira a
  média simples das coberturas das vacinas. Na Amazônia Legal, cada vacina tem a sua cobertura da região (doses
  aplicadas ÷ população-alvo, somadas nos municípios) e o valor é a média entre elas. Os totais vêm de
  `assets/cobertura_vacinal_municipios.csv`, gerado da planilha do painel do Ministério da Saúde por
  `python scripts/cobertura_vacinal.py <planilha.xlsx> --ano 2025`; o arquivo reproduz o Brasil (85,80%) e os estados
  publicados. Só 2025 por enquanto: a planilha do painel de 2023 e 2024 entra com o mesmo comando, um ano por vez
  (antes de 2023 a fonte era o TABNET, com outras vacinas). Boa Esperança do Norte (MT), criado em 2025, ainda não
  aparece na fonte.
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
- **Ano incompleto (`ano_parcial`):** quando a fonte já traz o ano corrente com só parte do total (ex.: Bolsas do
  ProUni em 2026), `ano_parcial = 2026` tira esse ano do indicador; sem isso, o total parcial vira o "último ano" dos
  cartões e parece uma queda. Indicadores de estoque (posição no mês, como CadÚnico) não precisam.
- **Parcela dos estados só em parte na região:** o build calcula a parte do Maranhão na Amazônia Legal com a mesma
  regra de cada indicador e, para conferir, aplica essa regra a todos os municípios do estado: se o resultado não
  reproduz o valor publicado do estado (desvio mediano acima de 1,5%, o limite da conferência da regra), o build
  avisa. A parcela só deixa de ser usada por decisão no config, indicador a indicador: `sem_parte_al = "<motivo>"`
  (ex.: IDEB anos finais, cujo peso inclui as outras redes); o painel e o relatório passam ao estado inteiro e dizem por
  quê.
- **Valores errados na planilha (`descartar`):** `descartar = [{ anos = [...], motivo = "...", nivel = "...", uf = "...",
  cod = [...] }]` tira esses valores antes de qualquer agregação (ex.: zeros que são falta de dado, um ano com
  classificação trocada na RAIS). O motivo aparece na ficha do Sobre o Painel e no texto do relatório.
- **Quebra de método (`quebra`):** `quebra = { ano = 2025, trecho = "...", motivo = "..." }` faz a variação comparar só
  anos do mesmo trecho; os gráficos do relatório não ligam os dois trechos e o texto explica o motivo.
- **Leitura de magnitude (`leitura = "magnitude"`):** contagens que cruzam territórios (rotas, hidrovias) e
  participações no total do país não se comparam com as referências como uma taxa. No relatório, ficam fora do placar
  e dos destaques, e a posição é lida como magnitude, como nos totais.
- **Peso do ano inicial (`peso_ano_anterior`):** nas taxas de transição do INEP, cada ano é um par (a evasão de 2022 é
  a de 2021/2022), e a ficha pesa pelas matrículas do ano inicial. Com `peso_ano_anterior = true`, a média ponderada
  usa o peso do ano anterior. Em 2015, sem as matrículas de 2014 na planilha, vale o ano mais próximo (o build avisa).
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
  da entrada; o ID da ficha de origem e a planilha são preservados. Campos desconhecidos interrompem o build. Não
  use esse recurso para mudar o método da ficha (polaridade, regra de agregação): isso se decide na planilha.
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
inteiro, com aviso. O mesmo vale para os marcados com `sem_parte_al` (decisão por indicador, como pede a orientação
da SUDAM). Toda tela com esses estados traz uma nota dizendo qual valor está em uso. Quem muda a lista de
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

## Séries com quebra de método

Algumas séries têm anos que não se comparam. Elas ficam listadas em `QUEBRAS` (`src/data.py`), com o ano em que
começa o trecho novo e o motivo. As variações "desde ..." (cartões da Visão Geral e do Perfil do Território, cartões
por eixo e coluna de variação do ranking) só comparam anos do mesmo trecho:

| Indicador | Trecho novo | Motivo |
| --- | --- | --- |
| População total (`IND-001`) e densidade (`IND-002`) | 2022 em diante | as estimativas de 2024 em diante partem do Censo 2022; as de 2015 a 2021, do Censo 2010 |
| Moradores em favelas (`IND-107`) | 2022 | o Censo 2022 mudou a delimitação (em 2010, aglomerados subnormais) |

Assim, em 2026 a população varia "desde 2024", e favelas não mostra variação. Nos gráficos de evolução (Visão Geral,
Perfil do Território, Séries Temporais e Comparações), o **valor** continua com a série inteira, e o **índice**, a
variação anual, o ritmo médio e o mapa de calor usam só o trecho comparável, com aviso sob o gráfico. Quando o trecho
tem um ano só (favelas), essas medidas não aparecem. Para incluir outra quebra, basta acrescentar uma linha em
`QUEBRAS`.

**Valor inicial quase nulo.** Nos cartões da Visão Geral (o quarto cartão e os cartões por eixo), a variação % não
aparece quando o primeiro ano da Amazônia Legal fica abaixo de 10% da mediana da série (`base_quase_nula` em
`main.py`). O cartão mostra o motivo no lugar do número. Hoje isso pega a despesa municipal em P&D (`IND-192`), que em
2015 tinha um só município com gasto e daria "+85.780%", e a área de manejo florestal autorizada (`IND-154`), que daria
"+23.370%".

## Abas
Visão Geral · Mapa e Ranking · Perfil do Território · Séries Temporais · Comparações · Relatório · Sobre.

### Comparações: grupo de municípios × demais e matriz de correlação
As seções 4 e 5 da aba Comparações trabalham com os municípios do recorte (filtros da barra lateral) e com todos os
indicadores municipais de um eixo:

- **Grupo × demais (seção 4):** compara um grupo (municípios da faixa de fronteira, sedes de região imediata, porte, tipologia PNDR,
  classe do IDHM ou região intermediária, todos de `assets/municipios_caracterizacao.csv`) com os demais municípios.
  O gráfico põe lado a lado a mediana de cada grupo, na escala de cada indicador (quando a mediana é zero nos dois,
  mostra o % de municípios em que o fenômeno existe), e a tabela traz também os quartis. A leitura vem do teste de
  Mann-Whitney (`data.mann_whitney`): a diferença é consistente com p < 0,05 e chance de um município do grupo
  superar um dos demais fora da faixa de 45% a 55%.
- **Matriz de correlação (seção 5):** Spearman entre os indicadores do eixo, cada um no seu ano mais recente com dado
  municipal (não há filtro de ano; a nota abaixo da matriz diz o ano de cada indicador). Entram no máximo 15 indicadores, e ficam fora os que têm dado
  em menos de 70% dos municípios. Um par escolhido abaixo da matriz abre a dispersão da seção 6.
- **Regras comuns (`valores_comparaveis` em `main.py`):** indicadores somáveis entram divididos pela população
  (contagens por mil habitantes, valores em R$ por habitante), com a população do Censo em 2010 e 2022 e a estimativa
  do IBGE nos demais anos. Um indicador dividido pela população que repete outro do eixo (correlação de 0,95 ou mais,
  ex.: PIB municipal por habitante e PIB per capita) começa fora da matriz. Quando a regra de agregação diz que
  municípios sem dado contam como zero (ex.: favelas), eles entram com zero. Nos anos de Censo, a densidade é
  recalculada como população do Censo ÷ área, porque não há estimativa em 2022 e a de 2021 vem de outra base
  censitária. População e área entram como publicadas.

### Relatório: PDF de um estado ou município (protótipo)
A aba **Relatório** monta um PDF A4 para imprimir ou anexar. A pessoa escolhe:
1. **Território:** um estado (o Maranhão pode ser só a parte na Amazônia Legal) ou um município;
2. **Comparar com:** uma única UF (ou município) à escolha, rotulada "UF selecionada para comparação", e quais
   referências entram (nível acima, Amazônia Legal, Brasil);
3. **Indicadores:** os eixos e, se quiser, os indicadores um a um;
4. **Partes:** resumo (números-chave e placar por eixo), pontos fortes e de atenção, "Como ler", texto de leitura,
   gráfico da evolução e gráfico de comparação de cada indicador, tabela-resumo do eixo (desligada por padrão),
   mapas dos municípios (estados) e fontes.

Cada indicador vira uma ficha (três por página): valor em destaque, frases com a comparação, a posição e a variação,
e os dois gráficos. A aba mostra uma estimativa de páginas; o PDF é gerado no botão **Gerar relatório** (poucos
segundos) e fica em cache pelas opções escolhidas e pela versão da base.

- Os números vêm de `src/perfil.py`, o mesmo cálculo da tabela do Resumo do Perfil do Território: o painel e o PDF
  mostram os mesmos valores. O layout está em `src/relatorio.py` (reportlab, só Python: gráficos e mapas em vetor,
  fonte Montserrat de `assets/fonts/`).
- Pelo terminal: `python scripts/relatorio.py "Pará" --comparar "Amazonas" --eixos 1 4`,
  `python scripts/relatorio.py "Marabá (PA)" --tabela -o maraba.pdf` ou `python scripts/relatorio.py "Maranhão" --parte`.

## Estrutura
- `main.py`: app e abas · `src/data.py`: carga das bases · `src/charts.py`: gráficos · `src/theme.py`: identidade visual
- `src/perfil.py`: cálculos do Perfil do Território · `src/relatorio.py`: relatório do território em PDF · `src/mosaico.py`: mosaico de ícones (topo do painel e capa do PDF)
- `scripts/build_data.py`: planilha → bases do painel · `scripts/upload_gcs.py`: bases → bucket · `scripts/catalogo.py`: catálogo dos indicadores · `config/indicadores.toml`: indicadores ativos
- `assets/geo/`: malhas do IBGE · `assets/indicators.json`: cores e descrições dos eixos
- `assets/logos/`: a assinatura institucional do topo e do rodapé (`assinatura.png`, recorte de `assina_sudam.png`, enviada pelo design: Publix, PNUD, SUDAM, Ministério da Integração e do Desenvolvimento Regional e bandeira); as logos avulsas (`pnud`, `sudam`, `publix`) valem só se esse arquivo não existir. Também o emblema do projeto (`emblema`), em
  `.svg`, `.png`, `.webp` ou `.jpg`, já recortados e leves; os arquivos de origem ficam em `assets/logos/originais/`.
  Sem arquivo, o nome aparece em texto · `assets/brand/mosaico_topo.webp`: mosaico de ícones do topo, gerado por
  `scripts/mosaico_topo.py` a partir dos ícones da identidade visual em `assets/id_visual/icons/` · `assets/fonts/`:
  Montserrat (licença OFL), usada no PDF
