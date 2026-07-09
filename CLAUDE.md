# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é

Pipeline pessoal de mineração de dados astronômicos. Busca candidatos a anãs marrons/estrelas frias próximas ao Sol via movimento próprio anômalo no catálogo **CatWISE2020** (acessado por TAP/IRSA), filtra por qualidade, descarta objetos já conhecidos (cross-match SIMBAD) e faz triagem final com LLM.

O código-fonte fica em `rastro/`. A especificação conceitual completa está em `projeto-rastro-especificacao-tecnica.md` (raiz).

## Comandos

Sempre rodar a partir de `rastro/` (o `sys.path` e os caminhos em `config.py` assumem esse diretório como raiz):

```bash
cd rastro
source venv/bin/activate            # venv já existe no repo
pip install -r requirements.txt
export PYTHONUNBUFFERED=1
python pipeline.py                  # roda as 5 fases em sequência
```

Rodar uma fase isolada (cada módulo expõe `run()`):

```bash
python -c "from src.quality_filter import run; run()"
```

Cada `src/*.py` também tem `if __name__ == "__main__"`, então `python src/quality_filter.py` funciona (contanto que o cwd seja `rastro/`).

Não há suíte de testes automatizados. A **Fase 1 (`sanity_check`) é o teste de validação**: redescobre Luhman 16 via CatWISE2020 + SIMBAD e compara o PM medido com o valor de referência. Se falhar, chama `sys.exit(1)` e aborta o pipeline inteiro. Use-a para validar que a stack de dados (IRSA/SIMBAD) está respondendo corretamente.

## Arquitetura

**Fases sequenciais que se comunicam por tabelas SQLite**, não por memória. Este é o ponto central: cada fase lê a tabela produzida pela anterior em `data/rastro.db` e grava a sua com `to_sql(..., if_exists="replace")`. Rodar uma fase isolada exige que a tabela de entrada já exista no banco.

```
Fase 2 fetch_field        → campo_bruto
Fase 3 quality_filter     → candidatos_fase3   (lê campo_bruto)
Fase 4 known_catalog_match→ candidatos_fase4   (lê candidatos_fase3; adiciona status/simbad_match_id)
Fase 5 llm_triage         → candidatos_fase5   (lê candidatos_fase4 WHERE status='candidato')
```

A Fase 1 não grava no banco; só valida e imprime.

**`config.py` é a fonte única de toda parametrização** (coordenadas do campo, limiares de PM/SNR/flags, alvos de sanidade, modelo LLM, caminhos). Alterar comportamento do pipeline = editar `config.py`, não os módulos. Os caminhos derivam de `ROOT = config.py.parent`, ou seja, `rastro/`.

**`proper_motion.add_pm_columns(df)`** deriva `pm_total` (√(pmra²+pmdec²)) e `cor_w1w2` (w1mpro−w2mpro). Precisa ser chamada antes de qualquer filtro ou ordenação que dependa dessas colunas; elas não vêm do catálogo.

**Fonte de dados:** CatWISE2020 via `astroquery.ipac.irsa.Irsa` (cone search na Fase 1, query ADQL/TAP na Fase 2). Cross-match da Fase 4 usa CDS `XMatch` em batch contra SIMBAD, com fallback sequencial linha-a-linha (`_fallback_sequential`) se o batch falhar. Chamadas a SIMBAD/IRSA têm retry com `time.sleep` porque os serviços são instáveis; preserve esse padrão ao mexer nelas.

**LLM (Fase 5):** provider-agnóstico via `httpx` direto (sem SDK), falando o formato **OpenAI-compatible** (`/chat/completions`). Trocar de provider = mudar `LLM_BASE_URL` + `LLM_MODEL` + de onde vem a chave, tudo em `config.py` (há exemplos comentados de Gemini/OpenRouter/Zhipu/Ollama). Default: **Groq free** (`llama-3.3-70b-versatile`). Alternativa free sem cota diária pra iteração pesada: **Zhipu GLM-4.7-Flash** (perpétuo, concorrência 1, endpoint intl `https://api.z.ai/api/paas/v4`) — exemplo pronto no `config.py`. A chave vem de `load_api_key()`: primeiro da env var em `LLM_API_KEY_ENV` (`GEMINI_API_KEY`), senão do `auth.json` estilo opencode (`data[LLM_API_KEY_FILE_PROVIDER]["key"]`); `LLM_API_KEY_ENV=None` = provider sem chave (Ollama local).

O `score` (`alta`/`baixa`/`incerta`/`media`) vem de saída **estruturada** (`response_format` json_schema, `LLM_STRUCTURED=True`) quando o modelo suporta: `interpret_response` parseia o JSON `{veredito, raciocinio}`. Degradação graciosa: no HTTP 400 (modelo não suporta o param) `call_llm` remove o `response_format` e refaz; se o conteúdo vier `None`/quebrado, cai em `parse_score` (VEREDITO na 1ª linha, senão keyword). Regra do `parse_score`: **`alta` só sai do VEREDITO/JSON explícito**; o fallback por keyword só rebaixa (baixa/incerta) ou fica neutro (media), nunca promove, pra evitar falso positivo. Rate limit (429) tem retry com backoff lendo `X-RateLimit-Reset`.

## Convenções

Código, prints e nomes de tabela/coluna são em português. Ao adicionar uma fase nova, siga o contrato existente: função `run()` que lê a tabela anterior do SQLite, processa com pandas e grava a próxima tabela. Mantenha os prints de progresso (o pipeline é interativo e longo).
