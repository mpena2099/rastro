import os
from pathlib import Path

ROOT = Path(__file__).parent
# RASTRO_DB aponta para outra copia do banco: testes do app (AppTest) clicam em botoes que
# gravam decisoes, e no banco real elas viravam revisao de verdade
SQLITE_PATH = Path(os.environ.get("RASTRO_DB", ROOT / "data" / "rastro.db"))
# demo online (app/demo.py): so o treino, com banco pequeno no repo e historico por sessao
DEMO = os.environ.get("RASTRO_DEMO") == "1"

CATWISE_TABLE = "catwise_2020"

# prazo de relogio de uma chamada de rede (util.com_prazo); um ladrilho de 1 grau no IRSA
# leva alguns minutos, por isso folgado
REDE_PRAZO_S = 600
# o XMatch do CDS responde em segundos quando esta no ar; fora do ar nao responde nunca
CDS_PRAZO_S = 90
CATWISE_COLUMNS = [
    "source_id", "ra", "dec",
    "w1mpro", "w2mpro", "w1snr", "w2snr",
    "pmra", "pmdec", "sigpmra", "sigpmdec",
    "par_pm", "par_pmsig",
    "pmcode", "ka", "km",
    "w1flg", "w2flg",
    "ab_flags", "cc_flags", "n_aw",
    "meanobsmjd",
]

# Fase 1 — sanity check targets
SANITY_TARGETS = {
    "WISE_0855": {
        "ra": 133.795125,
        "dec": -7.245139,
        "pm_total_ref": 8.08,
        "pm_tolerance": 2.0,
    },
    "LUHMAN_16": {
        "ra": 162.305,
        "dec": -53.327,
        "pm_total_ref": 2.78,
        "pm_tolerance": 0.5,
    },
}

# Fase 2 — field query
# A regiao e varrida em ladrilhos quadrados de FIELD_STEP_DEG graus (em RA/Dec,
# sem cruzar RA=0/360). O default cobre 25 graus quadrados em alta latitude
# galactica (b ~ +50), onde ha pouca confusao de fontes.
FIELD_RA_RANGE = (148.0, 153.0)
FIELD_DEC_RANGE = (18.0, 23.0)
FIELD_STEP_DEG = 1.0
PM_THRESHOLD_ARCSEC = 0.15
# Teto de linhas do TOP por consulta na Fase 2. Alto de proposito: serve so de
# guarda contra truncagem. Se um ladrilho bater o teto, ele e dividido em 4 e
# refeito, em vez de seguir com meio ladrilho.
ROW_LIMIT = 20000

# Fase 3 — quality filter
# W2 e a banda onde ana T/Y brilha; SNR baixo aqui deixa passar deteccao no
# nivel do ruido com PM espurio (W2SNR_MIN=3 gerava "candidatos" invisiveis no
# unWISE). 8 corta pra ~300 fontes no campo de teste.
W2SNR_MIN = 8.0
# Significancia minima do movimento proprio: pm_total / sigma(pm_total). Medido
# contra 772 anas L/T/Y conhecidas: 5 mantem 96% mas deixava 1370 candidatos em
# 25 graus quadrados (mediana 5.97, colados no corte); 8 mantem 94% e deixa 239;
# 10 mantem 91% e deixa 118.
PM_SIGNIF_MIN = 8.0
N_AW_MAX = 1

# Fase 4 — cross-match
SIMBAD_RADIUS_ARCSEC = 5
SIMBAD_DELAY_S = 0.3
# Listas de anas frias no VizieR (via CDS XMatch) que o SIMBAD nao cobre por inteiro:
# Karpov+2025 trouxe 2 dos 239 candidatos da varredura, um deles ja confirmado a olho.
# Cada uma e cruzada na posicao J2000 e na da epoca do CatWISE (as epocas variam).
# J/ApJ/899/123 (Meisner+2020b) nao esta no servidor do XMatch.
CATALOGOS_ANAS = {
    "J/A+A/695/A195/table2": "Karpov+2025 (unTimely)",
    "J/ApJS/253/7/tablea1": "Kirkpatrick+2021 (20 pc)",
    "J/ApJS/253/7/table1": "Kirkpatrick+2021 (novas L/T/Y)",
    "J/ApJS/271/55/table2": "Kirkpatrick+2024 (20 pc)",
    "J/ApJ/889/74/bdcand": "Meisner+2020 (Backyard Worlds)",
    "J/ApJS/234/1/dwarfs": "Best+2018 (Pan-STARRS)",
    "J/A+A/619/L8/table2": "Reyle 2018 (Gaia DR2)",
    "J/MNRAS/485/4423/table3": "Smart+2019 (Gaia DR2)",
    "J/A+A/589/A49/table3": "Skrzypek+2016 (L)",
    "J/A+A/589/A49/table4": "Skrzypek+2016 (T)",
    "J/MNRAS/489/5301/desy3-lt": "Carnero Rosell+2019 (DES)",
}
CATALOGOS_RAIO_ARCSEC = 5

# Fase 5 — LLM triage (provider-agnostico, endpoint OpenAI-compativel)
#
# Funciona com qualquer provider que exponha /chat/completions no formato
# OpenAI: Gemini (via camada OpenAI-compat), OpenRouter, Groq, Ollama local.
# Trocar de provider = mudar LLM_BASE_URL + LLM_MODEL + de onde vem a chave.
#
# Default: Groq free tier. Pegue a chave (sem cartao) em https://console.groq.com
# e exporte  export GROQ_API_KEY=...  (ou adicione um provider "groq" no
# auth.json estilo opencode). Ollama local nao precisa de chave.
LLM_BASE_URL = "https://api.groq.com/openai/v1"
# A cota do Groq (TPM e TPD) e POR MODELO; se esgotar, troque aqui pra outro
# modelo com cota propria (ex: openai/gpt-oss-120b, qwen/qwen3.8-27b) e ajuste
# LLM_REQUEST_DELAY_S ao TPM dele. Lista atual: GET {LLM_BASE_URL}/models.
LLM_MODEL = "openai/gpt-oss-20b"

# Chave da API: lida da env var abaixo; se ausente, cai no arquivo auth.json
# (data[<provider>]["key"]). Deixe LLM_API_KEY_ENV = None p/ providers sem
# chave, como Ollama local.
LLM_API_KEY_ENV = "GROQ_API_KEY"
LLM_API_KEY_FILE = Path.home() / ".local" / "share" / "opencode" / "auth.json"
LLM_API_KEY_FILE_PROVIDER = "groq"

# Structured output via response_format json_schema. No Groq o gpt-oss-20b
# aceita o param, mas devolve 400 json_validate_failed em ~44% das chamadas
# (mesmo com max_tokens alto), entao aqui fica False e a Fase 5 usa o modo texto
# (parse do "VEREDITO:" na resposta), que deu 9/9 ok. Com True e modelo que nao
# suporta, o codigo remove o param e cai pro texto (custa 1 req a mais).
LLM_STRUCTURED = False
# 0 reduz a variacao mas nao zera: no Groq o gpt-oss-20b ainda muda o score de
# ~1/3 dos candidatos entre rodadas. Trate o score como prioridade, nao veredito.
LLM_TEMPERATURE = 0
LLM_MAX_TOKENS = 1500
# Esforco de raciocinio de modelos gpt-oss (low|medium|high). "low" corta pela
# metade os tokens por chamada e evita o raciocinio consumir o max_tokens e
# devolver resposta vazia. None = nao envia o param (use em providers que o
# rejeitam, como Ollama ou Gemini).
LLM_REASONING_EFFORT = "low"

# Pausa entre chamadas na Fase 5, pra ficar sob o rate limit do free tier.
# No Groq free o gargalo NAO e requisicoes/min e sim TOKENS/min (TPM). Cada
# triagem gasta ~0.8k tokens. gpt-oss-20b tem TPM 8k -> ~6s minimo; 8s da
# folga. 0 = sem pausa.
LLM_REQUEST_DELAY_S = 8

# Exemplos de outros providers (descomente e ajuste a chave):
# Gemini:     LLM_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai"; LLM_MODEL="gemini-2.5-flash-lite"; LLM_API_KEY_ENV="GEMINI_API_KEY"; LLM_API_KEY_FILE_PROVIDER="gemini"
# OpenRouter: LLM_BASE_URL="https://openrouter.ai/api/v1"; LLM_MODEL="openai/gpt-oss-20b:free"; LLM_API_KEY_FILE_PROVIDER="openrouter"
# Zhipu:      LLM_BASE_URL="https://api.z.ai/api/paas/v4"; LLM_MODEL="glm-4.7-flash"; LLM_API_KEY_ENV="ZHIPU_API_KEY"; LLM_API_KEY_FILE_PROVIDER="zhipu"
# Ollama:     LLM_BASE_URL="http://localhost:11434/v1"; LLM_MODEL="qwen2.5:7b"; LLM_API_KEY_ENV=None
# Teto de candidatos triados (os de maior PM primeiro). A cota diaria do Groq
# (gpt-oss-20b: 200k tokens/dia, ~800 por chamada) acaba em ~250 chamadas, e na
# varredura de 25 graus quadrados a LLM marcou 44% como "alta": ela nao serve de
# filtro, so de comentario. Mantem baixo pra nao gastar a cota a toa.
LLM_BATCH_SIZE = 60
