# Rastro

Pipeline pessoal de mineração de dados astronômicos que caça **anãs marrons e estrelas frias próximas ao Sol** ainda não catalogadas, procurando por **movimento próprio anômalo** no catálogo público **CatWISE2020**.

![Ilustração artística de uma anã marrom](docs/img/eso1404c.jpg)

*Ilustração artística de uma anã marrom (Luhman 16B), parte do terceiro sistema mais próximo do Sol. Crédito: ESO/I. Crossfield/N. Risinger (skysurvey.org), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).*

## Em palavras simples

**A pergunta:** existem objetos frios e escuros perto do Sol que ninguém descobriu ainda?

**O que se procura:** as *anãs marrons*, "estrelas fracassadas". Têm massa demais pra serem planetas e de menos pra acender como uma estrela. Quase não emitem luz visível, mas emitem calor (infravermelho), então um telescópio infravermelho consegue enxergá-las.

**Como achar:** as estrelas parecem paradas no céu, mas as que estão perto se mexem devagar, ano após ano. É como olhar a paisagem pela janela do carro: o poste ao lado passa rápido, a montanha ao longe parece parada. Esse deslocamento no céu se chama *movimento próprio*. Um objeto que se move muito pra um ponto tão apagado é um forte suspeito de estar perto de nós.

![Movimento próprio de WISE 0855-0714 contra as estrelas de fundo](docs/img/movimento_proprio_wise0855.png)

*Quase tudo no fundo (cinza) fica no lugar. A WISE 0855-0714 (laranja), a anã marrom mais fria que se conhece, anda cerca de 80 segundos de arco em 10 anos. É esse tipo de movimento que o projeto procura.*

**Onde estão os dados:** o telescópio espacial WISE fotografou o céu todo várias vezes ao longo de 8 anos. Astrônomos já transformaram essas fotos numa enorme tabela pública, o *CatWISE2020*, com 1,89 bilhão de linhas. Cada linha é um ponto de luz, com sua posição, seu brilho e o quanto ele se mexeu. **O projeto não olha fotos nem usa telescópio: ele lê essa tabela e filtra.**

**O que o programa faz, passo a passo.** Pense numa peneira com várias malhas, cada uma deixando passar menos gente:

1. **Confere as ferramentas.** Procura dois objetos famosos que já se conhece. Se não os achar, algo está errado e o programa para.
2. **Baixa um pedaço do céu.** Hoje, uma área de 1 grau por 1 grau (cerca de 5 vezes a Lua cheia), só com pontos que se movem rápido.
3. **Joga fora medidas duvidosas.** Defeitos do instrumento, pontos colados em vizinhos e movimentos pequenos demais pra distinguir de erro de medida.
4. **Joga fora o que já é conhecido.** Compara com o SIMBAD, o grande cadastro de objetos astronômicos.
5. **Pede a nota de uma IA.** Uma IA lê os números de cada sobrevivente e dá uma nota de prioridade. Ela só ajuda a ordenar, nunca decide.
6. **Olhar humano.** As imagens dos finalistas são conferidas à mão. Esse passo ainda é um modelo por preencher.
7. **Segunda opinião** de um astrônomo, ainda por fazer.

![Quantas fontes sobram em cada fase](docs/img/funil_fases.png)

**O que esperar:** quase tudo que passa pela peneira é falso alarme ou já era conhecido, e isso é normal até em projetos profissionais. No campo de teste, o programa reencontrou sozinho uma anã marrom que já estava catalogada, sinal de que os filtros funcionam. Os candidatos que sobraram parecem falsos alarmes. Uma descoberta nova é o horizonte, não a promessa.

## O que entra, o que sai e o que fazer com isso

**O que alimenta o programa**
- **Uma região do céu**, dada por coordenadas (RA e Dec) em `config.py`, e os limiares dos filtros (quão rápido o ponto tem de se mover, quão nítida a medida precisa ser).
- **Dois bancos de dados públicos**, baixados da internet na hora: a tabela CatWISE2020 (NASA/IPAC) e o cadastro SIMBAD (CDS, Estrasburgo).
- **Uma chave grátis de IA** (Groq), só pra nota da última fase.

**O que ele devolve**

Uma tabela, `candidatos_fase5`, no arquivo `data/rastro.db`. Cada linha é um **suspeito**: código da fonte, posição no céu, brilho e cor no infravermelho, movimento próprio (e quantas vezes ele é maior que o erro de medida), a nota da IA (`alta`, `media`, `baixa` ou `incerta`) e um parágrafo curto com o motivo da nota. Pra ver a lista, ordenada pelos que mais se movem:

```bash
python -c "import sqlite3, pandas as pd; print(pd.read_sql('SELECT source_id, ra, dec, pm_total, llm_triage_score FROM candidatos_fase5 ORDER BY pm_total DESC', sqlite3.connect('data/rastro.db')))"
```

**O que fazer com o resultado**

A lista é de *suspeitos*, não de descobertas. O caminho depois dela:
1. **Olhar as imagens** dos suspeitos de nota `alta` ou `media`. O notebook `notebooks/inspecao_visual.ipynb` monta os links do IRSA Finder Chart. O que se quer ver é um ponto real no céu que **mude de lugar** entre fotos de épocas diferentes. Ferramentas como o [WiseView](http://byw.tools/wiseview) mostram isso em animação.
2. **Descartar os falsos alarmes.** Na prática, quase todos caem aqui: ruído, defeito do instrumento ou ponto mal medido.
3. **Levar os que sobrarem a um astrônomo**, que pode confirmar com outras observações (um espectro, por exemplo) e, se for novo de verdade, publicar.

![Exemplo real: uma anã L já conhecida (embaixo) e um falso alarme (em cima)](docs/img/resultado_exemplo.jpg)

*Cada linha tem 3 recortes de 60" x 60" (unWISE em dois empilhamentos, NEO2 e NEO7, e Legacy Surveys no óptico). Embaixo, a anã L2 já catalogada 2MASS J09585080+2001525: nítida no infravermelho e vermelha no óptico. Em cima, um suspeito que a IA chegou a marcar como `alta`: quase nada aparece no centro, sinal de falso alarme. Imagens: unWISE (NASA/WISE) e Legacy Surveys (DESI), via visualizador do Legacy Surveys.*

## Contexto científico

O método não é novo. Kevin Luhman descobriu a **WISE 0855-0714** (a anã marrom mais fria conhecida, a ~2,3 parsecs, com movimento próprio de ~8"/ano) comparando imagens WISE de épocas diferentes. Voluntários de ciência cidadã, como os do projeto Backyard Worlds, também já acharam anãs ultrafrias vasculhando dados públicos.

O que muda aqui é o catálogo. O CatWISE2020 (1,89 bilhão de fontes, combinando WISE e NEOWISE, 12 épocas em 8 anos) já traz o **movimento próprio calculado por fonte**, com precisão muito superior à de gerações anteriores. Não é preciso cruzar dois catálogos de épocas diferentes na mão: o ajuste já está feito, e melhor. Este projeto minera esse campo pronto.

## Que dado é esse

O CatWISE2020 é um **catálogo tabular**: cada linha é uma fonte detectada no infravermelho (um ponto no céu), não uma foto. As colunas são medições já reduzidas:

| Coluna | O que é |
|--------|---------|
| `ra`, `dec` | posição no céu (graus) |
| `w1mpro`, `w2mpro` | brilho nas bandas infravermelhas W1 (3,4 µm) e W2 (4,6 µm), em magnitudes |
| `w1snr`, `w2snr` | razão sinal-ruído da medida em cada banda |
| `pmra`, `pmdec` | **movimento próprio** já calculado pelo catálogo (arcsec/ano) |
| `pmcode`, `ka`, `km` | blend da fonte (`pmcode` = ABCCC, A = nº de componentes) e uso de astrometria/movimento |
| `w1flg`, `w2flg`, `cc_flags`, `ab_flags`, `n_aw` | flags de qualidade/contaminação (artefato, confusão de fontes) |

O pipeline **não processa imagens**. A Fase 2 é uma consulta `SELECT ... WHERE ...` em **ADQL** (uma linguagem tipo SQL), rodada no servidor do IRSA via **TAP**, um protocolo de consulta a catálogos astronômicos. Cada candidato que avança é uma linha dessa tabela. Imagens só entram no fim, na inspeção humana (Fase 6).

## O que conta como sucesso (honesto)

| Nível | O que é | Prometido? |
|------|---------|-----------|
| **Mínimo** | Pipeline rodando ponta a ponta e **redescobrindo um objeto conhecido** (o teste de sanidade) | Sim, é o critério de aceite |
| **Bom** | Lista curta e defensável de candidatos não catalogados numa região real, sem artefatos óbvios | Sim, com esforço razoável |
| **Moonshot** | Um candidato genuinamente novo, validado por segunda opinião | Não, é o horizonte |

O valor entregue está no pipeline funcionar corretamente, não no achado em si.

## Como o pipeline funciona

Fases sequenciais. Cada uma lê a tabela produzida pela anterior no SQLite e grava a sua, então elas se comunicam pelo banco, não por memória.

| Fase | O que faz | Status |
|------|-----------|--------|
| 1 | **Teste de sanidade**: redescobre Luhman 16 (PM ~2,7"/ano) e WISE 0855 (PM ~8"/ano) via CatWISE2020 + SIMBAD. Se Luhman 16 falhar, o pipeline aborta, porque não faz sentido caçar objetos novos com uma stack que não acha os conhecidos. WISE 0855 só gera aviso | ✅ |
| 2 | **Query ao CatWISE2020** (ADQL/TAP) numa região do céu, filtrando no servidor por movimento próprio, astrometria (ka=km=3) e qualidade fotométrica (SNR, flags) | ✅ |
| 3 | **Filtragem fina de qualidade**: remove contaminação/artefatos por `cc_flags`/`ab_flags`, fontes em blend (`pmcode`, só passa A=1 e B=N), confusão de fontes (`n_aw`) e movimento próprio pouco significativo (PM/σ < 5) | ✅ |
| 4 | **Cross-match contra SIMBAD** (via CDS XMatch em lote): descarta o que já é catalogado. O SIMBAD usa posições em J2000 e o CatWISE mede em ~2015, então a posição é recuada pelo movimento próprio antes do match. Sem isso, fontes com PM acima de ~0,3"/ano escapam como "novas" | ✅ |
| 5 | **Triagem assistida por LLM**: prioriza os candidatos por consistência com uma anã L, T ou Y. A LLM ordena esforço humano, **nunca dá o veredito final**. O score varia entre rodadas (cerca de 1/3 dos candidatos mudam), então vale só como prioridade | ✅ |
| 6 | **Inspeção visual humana** (notebook com links do IRSA Finder Chart): blink de imagem, checar fantasma de difração | 🟡 template |
| 7 | **Segunda opinião** com astrônomo | ⬜ |

## Como usar

A partir da raiz do repositório:

```bash
python3 -m venv venv && source venv/bin/activate   # se ainda nao existir
pip install -r requirements.txt
export PYTHONUNBUFFERED=1
python pipeline.py          # roda as fases 1 a 5 em sequencia
```

As fases 1 a 4 não precisam de chave. A Fase 5 precisa de uma chave grátis de LLM (veja [Triagem por LLM](#triagem-por-llm-fase-5)). Sem chave, ela falha e as tabelas das fases anteriores continuam no banco.

Rodar uma fase isolada (cada módulo expõe `run()`; precisa da tabela da fase anterior no banco):

```bash
python -c "from src.llm_triage import run; run()"
```

## Como testar

Há dois níveis de teste, do mais rápido ao mais completo:

**1. Testes de unidade (offline, sem rede, instantâneos).** Cobrem a lógica pura que quebra calada se alguém mexer: derivação de movimento próprio e de sua significância (`pm_signif`), filtro de `pmcode`, recuo de posição pra J2000 no cross-match, parsing do score da LLM (incluindo a regra "`alta` só via veredito explícito") e a montagem da query da Fase 2.

```bash
python tests/test_units.py      # runner embutido, sem dependencia
# ou, se tiver pytest:  python -m pytest tests/
```

**2. Teste de sanidade / integração (Fase 1, usa rede).** É o verdadeiro teste de aceite do sistema: redescobre objetos reais conhecidos (Luhman 16 e WISE 0855) no CatWISE2020 e confere se o movimento próprio medido bate com a referência. O IRSA devolve 504 de vez em quando; a Fase 1 tenta de novo até 3 vezes. Se o Luhman 16 não bater com a referência, ela chama `sys.exit(1)` e para tudo: a stack de dados (IRSA/SIMBAD) está com problema e não adianta seguir.

```bash
python -c "from src.sanity_check import run; run()"
```

Não há mocks das APIs externas (IRSA/SIMBAD/LLM): a filosofia aqui é validar contra os serviços reais via Fase 1, já que a corretude depende justamente de os catálogos responderem o esperado.

## Triagem por LLM (Fase 5)

Esta é a única fase que precisa de chave. É **provider-agnóstico**: fala o formato OpenAI (`/chat/completions`) via `httpx`, sem SDK. Trocar de provider é só mudar três coisas em `config.py`: `LLM_BASE_URL`, `LLM_MODEL` e de onde vem a chave. Há exemplos comentados pra Gemini, OpenRouter, Zhipu e Ollama.

- **Default: Groq free** (`openai/gpt-oss-20b`, modo texto com `reasoning_effort` baixo). Chave grátis, sem cartão, em [console.groq.com](https://console.groq.com). Cota (tokens/min e tokens/dia) é **por modelo**, então dá pra alternar de modelo se um esgotar.
- **Alternativa sem cota diária** (pra iterar bastante): **Zhipu GLM-4.7-Flash**, perpetuamente free (exemplo pronto no `config.py`).
- **Zero cota / offline**: Ollama local.

A chave é resolvida por `load_api_key()`: primeiro a env var (ex: `export GROQ_API_KEY=...`), senão o arquivo `~/.local/share/opencode/auth.json` (campo `<provider>.key`). O projeto não lê arquivo `.env`.

A triagem pode usar **saída estruturada** (`response_format` json_schema, `LLM_STRUCTURED=True`), mas o default é o modo texto: o `gpt-oss-20b` no Groq falha o JSON em boa parte das chamadas. Se o modelo rejeitar o formato, cai no modo texto e lê o veredito da resposta. Resposta vazia vira `erro`, nunca um score. Regra do score: **`alta` só sai de um veredito explícito do modelo**; heurística por palavra-chave só rebaixa, nunca promove, pra não gerar falso positivo.

## Dados

Tudo em `data/rastro.db` (SQLite). Tabelas, em ordem de fase:

- `campo_bruto`: resultado da query TAP (Fase 2)
- `candidatos_fase3`: após filtro de qualidade
- `candidatos_fase4`: após cross-match SIMBAD (com `status` e `simbad_match_id`)
- `candidatos_fase5`: após triagem LLM (com `llm_triage_score` e `llm_triage_notes`)

## Configuração

Tudo centralizado em `config.py`: região do céu, limiares de PM/SNR/flags, alvos de sanidade, provider/modelo da LLM, caminhos. Mudar comportamento do pipeline é mexer aqui, não nos módulos.

## Estrutura

```
.
├── pipeline.py              # entrypoint (roda as fases 1-5)
├── config.py                # toda a parametrizacao
├── requirements.txt
├── README.md
├── projeto-rastro-especificacao-tecnica.md   # spec conceitual
├── src/
│   ├── sanity_check.py      # Fase 1
│   ├── fetch_field.py       # Fase 2
│   ├── quality_filter.py    # Fase 3
│   ├── known_catalog_match.py # Fase 4
│   ├── llm_triage.py        # Fase 5
│   └── proper_motion.py     # util (pm_total, cor_w1w2)
├── tests/
│   └── test_units.py        # testes de unidade offline
├── docs/img/                # figuras usadas neste README
├── notebooks/
│   └── inspecao_visual.ipynb # Fase 6
└── data/
    └── rastro.db            # resultados (gitignored)
```

## Projeto conceitual

A especificação técnica completa (motivação, fundamentação, armadilhas, referências) está em [`projeto-rastro-especificacao-tecnica.md`](projeto-rastro-especificacao-tecnica.md).

## Licença

Código sob a licença [MIT](LICENSE). Imagens de terceiros mantêm a licença indicada na legenda.
