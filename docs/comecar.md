# Começar

O uso pelo terminal tem duas partes, uma no terminal e outra no navegador:

| Parte | Onde | Comando | Para quê |
|---|---|---|---|
| Fases 1 a 5 | Terminal | `python pipeline.py` | Baixar o céu, filtrar e montar a lista de candidatos. Leva um bom tempo e roda sozinho |
| Fases 6 e 7 | Navegador | `python iniciar.py` | Olhar as imagens, decidir e baixar o relatório dos confirmados |

O pipeline é um lote longo, sem interação, e o terminal serve bem. A revisão precisa de imagens e de decisão humana, e por isso vive no navegador. O pipeline só precisa ser rodado de novo para varrer outra região ou refazer os cortes.

Sem terminal (Windows e macOS), instale o Python, baixe o ZIP e clique duas vezes em `iniciar_rastro.bat` (Windows) ou `iniciar_rastro.command` (macOS). O passo a passo está em [Instalar sem terminal](instalar.md). A busca de candidatos também roda pelo app, no botão "Buscar mais candidatas".

## Como usar

A partir da raiz do repositório:

```bash
python3 -m venv venv && source venv/bin/activate   # Linux e macOS, se ainda nao existir
pip install -r requirements.txt
python -u pipeline.py       # roda as fases 1 a 5 em sequencia
python -u pipeline.py --proximo  # escolhe sozinho o próximo bloco do céu e roda tudo
```

No Windows (PowerShell), crie e ative o ambiente assim; o resto dos comandos é igual:

```powershell
py -m venv venv; venv\Scripts\Activate.ps1
```

`-u` faz o Python escrever cada `print` na hora. No terminal isso já acontece, mas com a saída redirecionada (`> log.txt`, `| tee log.txt`, `nohup`) o Python junta tudo em blocos e o log fica parado por minutos, parecendo travado, nas fases longas.

As fases 1 a 4 não precisam de chave. A Fase 5 usa uma chave grátis de LLM (veja [Triagem por LLM](#triagem-por-llm-fase-5)). Sem chave, ela é pulada e os candidatos entram na fila como "sem triagem".

Revisar os candidatos (Fases 6 e 7), depois que a Fase 4 tiver rodado:

```bash
python iniciar.py    # sobe o app e abre o navegador; usa o venv do projeto sozinho
```

É o mesmo que `streamlit run app/revisao.py`, sem precisar ativar o venv. `python iniciar.py --demo` abre só o treino, como na demo online, e `--porta 8600` escolhe a porta. O app e a revisão estão descritos em [Revisão e treino](revisao.md).

Rodar uma fase isolada (cada módulo expõe `run()`; precisa da tabela da fase anterior no banco):

```bash
python -c "from src.llm_triage import run; run()"
```

## Triagem por LLM (Fase 5)

Esta é a única fase que precisa de chave, e é opcional: sem chave, a busca pula a triagem e os candidatos entram na fila como "sem triagem". É **provider-agnóstico**: fala o formato OpenAI (`/chat/completions`) via `httpx`, sem SDK. Trocar de provider é mudar `LLM_BASE_URL`, `LLM_MODEL` e de onde vem a chave: `LLM_API_KEY_ENV` e, para o arquivo `auth.json`, `LLM_API_KEY_FILE_PROVIDER`. Há exemplos comentados pra Gemini, OpenRouter, Zhipu e Ollama.

- **Default: Groq free** (`openai/gpt-oss-20b`, modo texto com `reasoning_effort` baixo). Chave grátis, sem cartão, em [console.groq.com](https://console.groq.com). Cota (tokens/min e tokens/dia) é **por modelo**, então dá pra alternar de modelo se um esgotar.
- **Alternativa sem cota diária** (pra iterar bastante): **Zhipu GLM-4.7-Flash**, perpetuamente free (exemplo pronto no `config.py`).
- **Zero cota / offline**: Ollama local.

### Configurar a chave do Groq, passo a passo

1. Crie uma conta em [console.groq.com](https://console.groq.com) (entra com Google ou GitHub, sem cartão).
2. No menu **API Keys**, clique em **Create API Key** e copie a chave (começa com `gsk_`). Ela só aparece uma vez; se perder, crie outra.
3. Guarde a chave numa variável de ambiente, que é de onde o projeto a lê. Para valer em todo terminal novo:

   ```bash
   # Linux (bash); no macOS troque ~/.bashrc por ~/.zshrc
   echo 'export GROQ_API_KEY="gsk_cole_a_sua_chave_aqui"' >> ~/.bashrc
   source ~/.bashrc
   ```

   ```powershell
   # Windows: grava para os próximos terminais; feche e abra o terminal depois
   setx GROQ_API_KEY "gsk_cole_a_sua_chave_aqui"
   ```

   O Rastro aberto antes de gravar a chave não a enxerga: feche a janela do iniciador e abra de novo. No Linux, a chave no `~/.bashrc` vale quando o Rastro é aberto pelo terminal (`./iniciar_rastro.command`); quem abre por atalho, sem terminal, grava o `export` no `~/.profile` e sai e entra na sessão.

   Não coloque a chave em `config.py` nem em nenhum arquivo do repositório: ela iria parar no git.

4. Teste a chave (o mesmo comando nos três sistemas, com o ambiente ativado). Se aparecer uma lista de modelos, está certa; `Invalid API Key` quer dizer chave errada ou incompleta:

   ```bash
   python -c "import os, httpx; print(httpx.get('https://api.groq.com/openai/v1/models', headers={'Authorization': 'Bearer ' + os.environ['GROQ_API_KEY']}).text[:300])"
   ```

5. Rode só a Fase 5 (as fases 1 a 4 precisam já ter rodado):

   ```bash
   python -u -c "from src.llm_triage import run; run()"
   ```

**Quando a cota acaba.** A Fase 5 tria os `LLM_BATCH_SIZE` (60) candidatos de maior movimento próprio, com uma pausa de `LLM_REQUEST_DELAY_S` (8 s) entre chamadas para respeitar o limite por minuto. Se o limite por minuto estourar, ela espera e tenta de novo sozinha. Se a **cota diária** acabar, cada chamada restante falha na hora com a mensagem "cota diaria do free tier esgotada" e o candidato fica com score `erro`. Aí há três saídas: esperar o reset (no dia seguinte, no fuso do Groq), trocar `LLM_MODEL` por outro modelo do Groq (a cota é separada por modelo) ou usar um dos outros provedores abaixo.

**Outro provedor.** Mude em `config.py` as linhas `LLM_BASE_URL`, `LLM_MODEL` e `LLM_API_KEY_ENV` (há exemplos prontos comentados para Gemini, OpenRouter, Zhipu e Ollama) e exporte a chave com o nome que você pôs em `LLM_API_KEY_ENV`. Quem usa o arquivo `auth.json` também muda `LLM_API_KEY_FILE_PROVIDER` para o nome do provider no arquivo. Com Ollama local, use `LLM_API_KEY_ENV = None`: não há chave.

A chave é lida por `load_api_key()` da variável em `LLM_API_KEY_ENV`. Se a variável não existir, há um segundo lugar, conveniente para quem usa o OpenCode: o arquivo `~/.local/share/opencode/auth.json` (campo `<provider>.key`), caminho do Linux e do macOS. No Windows, use a variável. O projeto não lê arquivo `.env`.

A triagem pode usar **saída estruturada** (`response_format` json_schema, `LLM_STRUCTURED=True`), mas o default é o modo texto: o `gpt-oss-20b` no Groq falha o JSON em boa parte das chamadas. Se o modelo rejeitar o formato, cai no modo texto e lê o veredito da resposta. Resposta vazia vira `erro`, nunca um score. Regra do score: **`alta` só sai de um veredito explícito do modelo**; heurística por palavra-chave só rebaixa, nunca promove, pra não gerar falso positivo.

## Como testar

Há dois níveis de teste, do mais rápido ao mais completo:

**1. Testes de unidade (não dependem dos serviços estarem no ar).** Cobrem a lógica pura que quebra calada se alguém mexer: derivação de movimento próprio e de sua significância (`pm_signif`), filtro de `pmcode`, recuo de posição pra J2000 no cross-match, parsing do score da LLM (incluindo a regra "`alta` só via veredito explícito") e a montagem da query da Fase 2. Importar `src/util.py` testa os espelhos do CDS, então a execução pode levar alguns segundos.

```bash
python tests/test_units.py      # runner embutido, sem dependencia
# ou, se tiver pytest:  python -m pytest tests/
```

**2. Teste de sanidade / integração (Fase 1, usa rede).** É o verdadeiro teste de aceite do sistema: redescobre objetos reais conhecidos (Luhman 16 e WISE 0855) no CatWISE2020 e confere se o movimento próprio medido bate com a referência. O IRSA devolve 504 de vez em quando; a Fase 1 tenta de novo até 3 vezes. Se o Luhman 16 não bater com a referência, ela chama `sys.exit(1)` e para tudo: a stack de dados (IRSA/SIMBAD) está com problema e não adianta seguir.

```bash
python -c "from src.sanity_check import run; run()"
```

Não há mocks das APIs externas (IRSA/SIMBAD/LLM): a filosofia aqui é validar contra os serviços reais via Fase 1, já que a corretude depende justamente de os catálogos responderem o esperado.

## Configuração

Tudo centralizado em `config.py`: região do céu (`FIELD_RA_RANGE` e `FIELD_DEC_RANGE`), limiares de PM/SNR/flags, alvos de sanidade, provider/modelo da LLM, caminhos. Mudar comportamento do pipeline é mexer aqui, não nos módulos.
