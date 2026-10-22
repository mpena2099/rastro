# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é

Pipeline pessoal de mineração de dados astronômicos. Busca candidatos a anãs marrons/estrelas frias próximas ao Sol via movimento próprio anômalo no catálogo **CatWISE2020** (acessado por TAP/IRSA), filtra por qualidade, descarta objetos já conhecidos (cross-match SIMBAD e listas de anãs do VizieR) e faz triagem final com LLM.

O código fica na raiz do repositório.

## Comandos

Rodar a partir da raiz do repositório (o `sys.path` e os caminhos em `config.py` assumem a raiz do projeto):

```bash
python3 -m venv venv && source venv/bin/activate   # se ainda não existir
pip install -r requirements.txt
python -u pipeline.py               # -u: print sai na hora mesmo com saída redirecionada
python -u pipeline.py --proximo     # próximo bloco 5x5 do céu, escolhido por src/campos.py
```

Rodar uma fase isolada (cada módulo expõe `run()`):

```bash
python -c "from src.quality_filter import run; run()"
```

Cada `src/*.py` também tem `if __name__ == "__main__"`, então `python src/quality_filter.py` funciona (contanto que o cwd seja a raiz do projeto).

**Testes:** há testes de unidade offline em `tests/test_units.py` (`python tests/test_units.py`, ou `pytest` se instalado) cobrindo a lógica pura (movimento próprio, scorer da LLM, montagem da query). Além deles, a **Fase 1 (`sanity_check`) é o teste de integração/aceite**: redescobre Luhman 16 via CatWISE2020 + SIMBAD e compara o PM medido com o valor de referência. Se falhar, chama `sys.exit(1)` e aborta o pipeline inteiro. Use-a para validar que a stack de dados (IRSA/SIMBAD) está respondendo.

## Arquitetura

**Fases sequenciais que se comunicam por tabelas SQLite**, não por memória. Este é o ponto central: cada fase lê a tabela produzida pela anterior em `data/rastro.db` e grava a sua com `to_sql(..., if_exists="replace")`. Rodar uma fase isolada exige que a tabela de entrada já exista no banco.

```
Fase 2 fetch_field        → campo_bruto
Fase 3 quality_filter     → candidatos_fase3   (lê campo_bruto)
Fase 4 known_catalog_match→ candidatos_fase4   (lê candidatos_fase3; adiciona status/simbad_match_id)
Fase 5 llm_triage         → candidatos_fase5   (lê candidatos_fase4 WHERE status='candidato')
```

A Fase 1 não grava no banco; só valida e imprime. `candidatos_fase4` e `candidatos_fase5` acumulam entre campos (`known_catalog_match.acumular`, troca só o mesmo `source_id`), e a Fase 5 só manda à LLM quem ainda não está em `candidatos_fase5`. O `pipeline.py` grava o campo em `campos_feitos` no fim; `--proximo` usa `src/campos.py` (blocos 5x5 alinhados ao campo do config, do mais perto ao mais longe, pulando |b| < 20°). O botão "Buscar mais candidatas" da fila (`app/execucao.py`, mesmo código do Vagalume) roda o `--proximo` em segundo plano, com confirmação, progresso e cancelamento.

**`config.py` é a fonte única de toda parametrização** (coordenadas do campo, limiares de PM/SNR/flags, alvos de sanidade, modelo LLM, caminhos). Alterar comportamento do pipeline = editar `config.py`, não os módulos. Os caminhos derivam de `ROOT = config.py.parent`, ou seja, a raiz do repositório.

**`proper_motion.add_pm_columns(df)`** deriva `pm_total` (√(pmra²+pmdec²)), `cor_w1w2` (w1mpro−w2mpro) e, se houver `sigpmra`/`sigpmdec`, `pm_signif` (pm_total/σ). Precisa ser chamada antes de qualquer filtro ou ordenação que dependa dessas colunas; elas não vêm do catálogo.

**Fonte de dados:** CatWISE2020 via `astroquery.ipac.irsa.Irsa` (cone search na Fase 1, query ADQL/TAP na Fase 2). Cross-match da Fase 4 usa CDS `XMatch` em batch contra SIMBAD, com fallback sequencial linha-a-linha (`_fallback_sequential`) se o batch falhar. Depois do SIMBAD, `_cruzar_catalogos` cruza os candidatos com as tabelas VizieR de `CATALOGOS_ANAS` (também via XMatch, na posição J2000 e na da época do CatWISE) e marca `status='conhecido'` com o nome da lista em `catalogo_match`; lista que falha só gera aviso. Chamadas a SIMBAD/IRSA têm retry com `time.sleep` porque os serviços são instáveis; preserve esse padrão ao mexer nelas.

**LLM (Fase 5):** provider-agnóstico via `httpx` direto (sem SDK), falando o formato **OpenAI-compatible** (`/chat/completions`). Trocar de provider = mudar `LLM_BASE_URL` + `LLM_MODEL` + de onde vem a chave, tudo em `config.py` (há exemplos comentados de Gemini/OpenRouter/Zhipu/Ollama). Default: **Groq free** (`openai/gpt-oss-20b`, modo texto, `LLM_STRUCTURED=False` e `LLM_REASONING_EFFORT="low"`; a cota do Groq é **por-modelo**, então dá pra alternar de modelo se um esgotar o TPD, ajustando `LLM_REQUEST_DELAY_S` ao TPM do modelo). Alternativa free sem cota diária pra iteração pesada: **Zhipu GLM-4.7-Flash** (perpétuo, concorrência 1, endpoint intl `https://api.z.ai/api/paas/v4`) — exemplo pronto no `config.py`. A chave vem de `load_api_key()`: primeiro da env var em `LLM_API_KEY_ENV` (`GROQ_API_KEY`), senão do `auth.json` estilo opencode (`data[LLM_API_KEY_FILE_PROVIDER]["key"]`); `LLM_API_KEY_ENV=None` = provider sem chave (Ollama local).

O `score` (`alta`/`baixa`/`incerta`/`media`) vem do modo texto (default) ou, com `LLM_STRUCTURED=True`, de saída **estruturada** (`response_format` json_schema): `interpret_response` parseia o JSON `{veredito, raciocinio}`. O `gpt-oss-20b` no Groq falha o JSON em ~44% das chamadas (400 `json_validate_failed`), por isso o default é texto. Degradação graciosa: no HTTP 400 `call_llm` remove o `response_format` e refaz; resposta vazia levanta erro (vira `erro`, nunca score); conteúdo quebrado cai em `parse_score` (VEREDITO na 1ª linha, senão keyword). Regra do `parse_score`: **`alta` só sai do VEREDITO/JSON explícito**; o fallback por keyword só rebaixa (baixa/incerta) ou fica neutro (media), nunca promove, pra evitar falso positivo. Rate limit (429) tem retry com backoff lendo `X-RateLimit-Reset`.

## Convenções

Código, prints e nomes de tabela/coluna são em português. Ao adicionar uma fase nova, siga o contrato existente: função `run()` que lê a tabela anterior do SQLite, processa com pandas e grava a próxima tabela. Mantenha os prints de progresso (o pipeline é interativo e longo).

**Fases manuais (fora do `pipeline.py`):** Fase 6 é o app Streamlit `app/revisao.py` (grava `revisao_humana`, tabela que o pipeline não recria, e `cruzamentos_app`, o Gaia/Pan-STARRS/AllWISE de cada candidato: só candidato novo é cruzado ao abrir o app, e `treino_historico`, uma linha por resposta do treino); recortes e animação do WiseView ficam em `data/cache_imagens/` (`app/imagens.py`), e cada página pré-carrega em segundo plano os 3 itens seguintes; `app/guia.py` tem a pergunta de cada imagem (legenda), os exemplos bom x ruim tirados dos casos do treino e a pista mostrada depois de responder. Fase 7 é `src/relatorio.py`: no app, o botão "Gerar relatório" chama `relatorio.gerar_html` sobre o DataFrame que o app já cruzou e oferece o HTML por download (`gerar_html` também roda `dados.buscar_vizier`, a busca no VizieR inteiro que destaca catálogos de anãs ou de movimento próprio, e o app tem o mesmo botão por candidato); pela linha de comando, `python src/relatorio.py [--duvidas]` lê `revisao_humana`, refaz Gaia/Pan-STARRS/AllWISE só pros escolhidos e grava `data/relatorio/relatorio.html` (imagens embutidas) e `candidatos.csv`. O app também tem o modo treino em `app/paginas/treino.py` (casos com resposta), com as duas páginas roteadas por `app/revisao.py` e o tema escuro em `app/estilo.py` e `.streamlit/config.toml`, e a animação do movimento (quadros do W2 por época do WiseView, em `app/imagens.py`), mostrada ao lado dos dois recortes. O treino só usa anãs conhecidas que passariam na fila (`quality_filter.passaria_na_fila`: cortes do servidor da Fase 2 mais a Fase 3), senão o caso fica impossível de acertar; os casos são cruzados com Gaia/Pan-STARRS/AllWISE pelo mesmo `app/cruzamento.py` da fila (`source_id` "treino:ra,dec" em `cruzamentos_app`), uma tentativa por sessão. A fila mostra a trilha de marcos (`dados.marcos`, dois deles marcados à mão) e o treino só a linha de nível (`dados.nivel_treino`); nada pontua confirmação, para não incentivar confirmar. O cruzamento grava cada etapa (Gaia/Pan-STARRS, AllWISE) separada: a que falha volta na próxima abertura. Gaia e Pan-STARRS vêm do XMatch do CDS, que às vezes cai: `dados.cds_no_ar()` testa antes (8 s) e o prazo da chamada é `CDS_PRAZO_S` (90 s).

**Testar o app:** com `streamlit.testing.v1.AppTest`, rode contra uma cópia do banco (`RASTRO_DB=/tmp/copia.db`, lido em `config.SQLITE_PATH`). Os botões de decisão e do treino gravam em `revisao_humana` e `treino_historico`; no banco real, o clique de teste vira revisão de verdade.

**Demo online:** `app/demo.py` (Streamlit Community Cloud) roda só o treino com `RASTRO_DEMO=1` e o banco `demo/treino_demo.db`, que vai no git: tabela `casos_treino_demo` (conjunto grande, sorteado por sessão em `guia.casos_de_treino`) e `cruzamentos_app` prontos, para a demo não consultar CDS nem IRSA. O histórico de cada visitante vai para um arquivo temporário da sessão (`treino.conectar_historico`). Mudou a regra dos casos do treino? Rode `python -u tools/gerar_demo.py` e commite o banco: o Community Cloud reimplanta sozinho a cada push no `main`.
