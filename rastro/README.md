# Rastro

Pipeline pessoal de mineração de dados astronômicos que caça **anãs marrons e estrelas frias próximas ao Sol** ainda não catalogadas, procurando por **movimento próprio anômalo** no catálogo público **CatWISE2020**.

## Do que se trata

Anãs marrons são objetos "quase estrelas": massa insuficiente pra fundir hidrogênio de forma estável, então são frias e apagadas, quase invisíveis em luz visível mas detectáveis no infravermelho. As mais frias e próximas estão entre os objetos mais difíceis de achar do céu, e ainda há vizinhas do Sol não descobertas.

O truque pra encontrá-las é o **movimento próprio**: objetos próximos parecem se deslocar contra o fundo de estrelas distantes ao longo dos anos. Um movimento próprio alto é uma assinatura de proximidade. Foi assim que Kevin Luhman descobriu a **WISE 0855-0714** (a anã marrom mais fria conhecida, ~2,3 parsecs, movimento próprio de ~8"/ano) comparando imagens WISE de épocas diferentes.

O CatWISE2020 (1,89 bilhão de fontes, combinando WISE + NEOWISE, 12 épocas em 8 anos) já traz o **movimento próprio calculado nativamente** por fonte, com precisão muito superior à de gerações anteriores. Ou seja: não é preciso cruzar dois catálogos de épocas diferentes na mão. O ajuste já está feito, e melhor. Este projeto minera esse campo pronto.

Não há telescópio nem observação ao vivo. É garimpo de arquivo público, na linha do que voluntários de ciência cidadã (como Frank Kiwy, no Backyard Worlds) já fizeram pra descobrir dezenas de anãs ultrafrias sozinhos.

## Que dado é esse (importante: é tabela, não imagem)

O CatWISE2020 é um **catálogo tabular**: uma tabela gigante com ~1,89 bilhão de linhas, onde **cada linha é uma fonte detectada** no infravermelho (uma detecção pontual do céu), não uma foto. As colunas são medições numéricas já reduzidas dessa fonte:

| Coluna | O que é |
|--------|---------|
| `ra`, `dec` | posição no céu (graus) |
| `w1mpro`, `w2mpro` | brilho nas bandas infravermelhas W1 (3,4 µm) e W2 (4,6 µm), em magnitudes |
| `w1snr`, `w2snr` | razão sinal-ruído da medida em cada banda |
| `pmra`, `pmdec` | **movimento próprio** já calculado pelo catálogo (arcsec/ano) |
| `pmcode`, `ka`, `km` | qualidade da solução de movimento e astrometria |
| `w1flg`, `w2flg`, `cc_flags`, `ab_flags`, `n_aw` | flags de qualidade/contaminação (artefato, confusão de fontes) |

Ou seja, o pipeline **não processa imagens FITS**: ele consulta e filtra linhas dessa tabela. A Fase 2 é literalmente uma query `SELECT ... WHERE ...` (em **ADQL**, uma linguagem tipo SQL) rodada no servidor do IRSA via **TAP**, um protocolo de consulta a catálogos astronômicos. Cada "candidato" que avança pelas fases é uma **linha** dessa tabela.

Imagens só aparecem no fim, na **Fase 6** (inspeção visual humana), onde cada candidato finalista é aberto no visualizador de imagens do IRSA por um link, pra o olho humano confirmar (ou descartar) o que os números sugeriram.

## O que conta como sucesso (honesto)

| Nível | O que é | Prometido? |
|------|---------|-----------|
| **Mínimo** | Pipeline rodando ponta a ponta e **redescobrindo um objeto conhecido** (o teste de sanidade) | Sim, é o critério de aceite |
| **Bom** | Lista curta e defensável de candidatos não catalogados numa região real, sem artefatos óbvios | Sim, com esforço razoável |
| **Moonshot** | Um candidato genuinamente novo, validado por segunda opinião | Não, é o horizonte |

A maioria dos candidatos que sobram no funil cai em "já catalogado", "artefato instrumental" ou "fonte mal medida". Isso é normal, inclusive em pipelines profissionais. O valor entregue está no pipeline funcionar corretamente, não no achado em si.

## Como o pipeline funciona

Fases sequenciais. Cada uma lê a tabela produzida pela anterior no SQLite e grava a sua, então elas se comunicam pelo banco, não por memória.

| Fase | O que faz | Status |
|------|-----------|--------|
| 1 | **Teste de sanidade**: redescobre Luhman 16 (PM ~2,7"/ano) via CatWISE2020 + SIMBAD. Se falhar, o pipeline aborta, porque não faz sentido caçar objetos novos com uma stack que não acha os conhecidos | ✅ |
| 2 | **Query ao CatWISE2020** (ADQL/TAP) numa região do céu, filtrando no servidor por movimento próprio, astrometria (ka=km=3) e qualidade fotométrica (SNR, flags) | ✅ |
| 3 | **Filtragem fina de qualidade**: remove contaminação/artefatos por `cc_flags`/`ab_flags`, qualidade do movimento (`pmcode`), e confusão de fontes (`n_aw`) | ✅ |
| 4 | **Cross-match contra SIMBAD** (via CDS XMatch em lote): descarta o que já é catalogado | ✅ |
| 5 | **Triagem assistida por LLM**: prioriza os candidatos por consistência com uma anã T/Y. A LLM ordena esforço humano, **nunca dá o veredito final** | ✅ |
| 6 | **Inspeção visual humana** (notebook com links do IRSA Finder Chart): blink de imagem, checar fantasma de difração | 🟡 template |
| 7 | **Segunda opinião** com astrônomo | ⬜ |

## Como usar

```bash
cd rastro
python3 -m venv venv && source venv/bin/activate   # se ainda nao existir
pip install -r requirements.txt
export PYTHONUNBUFFERED=1
python pipeline.py          # roda as fases 1 a 5 em sequencia
```

Rodar uma fase isolada (cada módulo expõe `run()`; precisa da tabela da fase anterior no banco):

```bash
python -c "from src.llm_triage import run; run()"
```

A **Fase 1 é o portão de aceite**: se o movimento próprio de Luhman 16 não bater com a referência, ela chama `sys.exit(1)` e para tudo. Use-a pra validar que IRSA/SIMBAD estão respondendo.

## Como testar

Há dois níveis de teste, do mais rápido ao mais completo:

**1. Testes de unidade (offline, sem rede, instantâneos).** Cobrem a lógica pura que quebra calada se alguém mexer: derivação de movimento próprio, parsing do score da LLM (incluindo a regra "`alta` só via veredito explícito") e a montagem da query da Fase 2.

```bash
python tests/test_units.py      # runner embutido, sem dependencia
# ou, se tiver pytest:  python -m pytest tests/
```

**2. Teste de sanidade / integração (Fase 1, usa rede).** É o verdadeiro teste de aceite do sistema: redescobre um objeto real conhecido (Luhman 16) no CatWISE2020 e confere se o movimento próprio medido bate com a referência. Se isso falhar, a stack de dados está com problema e não adianta seguir.

```bash
python -c "from src.sanity_check import run; run()"
```

Para exercitar só a triagem da LLM (precisa de chave configurada, ver abaixo) sem rodar as fases de dados:

```bash
python -c "from src.llm_triage import run; run()"
```

Não há mocks das APIs externas (IRSA/SIMBAD/LLM): a filosofia aqui é validar contra os serviços reais via Fase 1, já que a corretude depende justamente de os catálogos responderem o esperado.

## Triagem por LLM (Fase 5)

É **provider-agnóstico**: fala o formato OpenAI (`/chat/completions`) via `httpx`, sem SDK. Trocar de provider é só mudar três coisas em `config.py`: `LLM_BASE_URL`, `LLM_MODEL` e de onde vem a chave. Há exemplos comentados pra Gemini, OpenRouter, Zhipu e Ollama.

- **Default: Groq free** (`llama-3.1-8b-instant`). Chave grátis, sem cartão, em [console.groq.com](https://console.groq.com). Cota (tokens/min e tokens/dia) é **por modelo**, então dá pra alternar de modelo se um esgotar.
- **Alternativa sem cota diária** (pra iterar bastante): **Zhipu GLM-4.7-Flash**, perpetuamente free (exemplo pronto no `config.py`).
- **Zero cota / offline**: Ollama local.

A chave é resolvida por `load_api_key()`: primeiro a env var (ex: `GROQ_API_KEY`), senão o arquivo `~/.local/share/opencode/auth.json` (campo `<provider>.key`).

Quando o modelo suporta, a triagem usa **saída estruturada** (`response_format` json_schema). Quando não suporta, cai automaticamente no modo texto e lê o veredito da resposta. Regra do score: **`alta` só sai de um veredito explícito do modelo**; heurística por palavra-chave só rebaixa, nunca promove, pra não gerar falso positivo.

## Dados

Tudo em `data/rastro.db` (SQLite). Tabelas, em ordem de fase:

- `campo_bruto` — resultado da query TAP (Fase 2)
- `candidatos_fase3` — após filtro de qualidade
- `candidatos_fase4` — após cross-match SIMBAD (com `status` e `simbad_match_id`)
- `candidatos_fase5` — após triagem LLM (com `llm_triage_score` e `llm_triage_notes`)

## Configuração

Tudo centralizado em `config.py`: região do céu, limiares de PM/SNR/flags, alvos de sanidade, provider/modelo da LLM, caminhos. Mudar comportamento do pipeline é mexer aqui, não nos módulos.

## Estrutura

```
rastro/
├── pipeline.py              # entrypoint (roda as fases 1-5)
├── config.py                # toda a parametrizacao
├── requirements.txt
├── src/
│   ├── sanity_check.py      # Fase 1
│   ├── fetch_field.py       # Fase 2
│   ├── quality_filter.py    # Fase 3
│   ├── known_catalog_match.py # Fase 4
│   ├── llm_triage.py        # Fase 5
│   └── proper_motion.py     # util (pm_total, cor_w1w2)
├── notebooks/
│   └── inspecao_visual.ipynb # Fase 6
└── data/
    └── rastro.db
```

## Projeto conceitual

A especificação técnica completa (motivação, fundamentação, armadilhas, referências) está em [`../projeto-rastro-especificacao-tecnica.md`](../projeto-rastro-especificacao-tecnica.md).
