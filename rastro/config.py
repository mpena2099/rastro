from pathlib import Path

ROOT = Path(__file__).parent
DATA_RAW = ROOT / "data" / "raw"
DATA_CANDIDATES = ROOT / "data" / "candidates"
NOTEBOOKS = ROOT / "notebooks"
SQLITE_PATH = ROOT / "data" / "rastro.db"

CATWISE_TABLE = "catwise_2020"
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
        "pm_ra_ref": -8.05,
        "pm_dec_ref": 0.68,
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
FIELD_RA_MIN = 149.5
FIELD_RA_MAX = 150.5
FIELD_DEC_MIN = 19.5
FIELD_DEC_MAX = 20.5
PM_THRESHOLD_ARCSEC = 0.15
# Teto de linhas do TOP na Fase 2. Alto de proposito: serve so de guarda contra
# runaway, nao pra "caber" o campo. Com os filtros server-side (PM + SNR + flags)
# o campo 1x1 volta ~4.6k fontes completo; se bater ROW_LIMIT, a Fase 2 aborta
# avisando de truncagem em vez de seguir com meio campo.
ROW_LIMIT = 20000

# Fase 3 — quality filter
W1SNR_MIN = 5.0
W2SNR_MIN = 3.0
N_AW_MAX = 1

# Fase 4 — cross-match
SIMBAD_RADIUS_ARCSEC = 5
SIMBAD_DELAY_S = 0.3

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
LLM_MODEL = "llama-3.3-70b-versatile"

# Chave da API: lida da env var abaixo; se ausente, cai no arquivo auth.json
# (data[<provider>]["key"]). Deixe LLM_API_KEY_ENV = None p/ providers sem
# chave, como Ollama local.
LLM_API_KEY_ENV = "GROQ_API_KEY"
LLM_API_KEY_FILE = Path.home() / ".local" / "share" / "opencode" / "auth.json"
LLM_API_KEY_FILE_PROVIDER = "groq"

# Structured output via response_format json_schema. Atencao: nem todo modelo
# suporta. llama-3.3-70b no Groq NAO suporta (retorna 400), entao aqui fica
# False e a Fase 5 usa o modo texto (parse do "VEREDITO:" na resposta). Modelos
# que suportam json_schema (Gemini, gpt-oss, GLM): pode por True. Se True e o
# modelo nao suportar, o codigo remove o param e cai pro texto (custa 1 req a mais).
LLM_STRUCTURED = False
LLM_TEMPERATURE = 0.3
LLM_MAX_TOKENS = 800

# Pausa entre chamadas na Fase 5, pra ficar sob o rate limit do free tier.
# No Groq free (llama-3.3-70b) o gargalo NAO e requisicoes/min e sim TOKENS/min
# (TPM = 12k). Cada triagem gasta ~1.1k tokens, entao ~6.5s por chamada mantem
# < 12k TPM (a cota diaria de requisicoes, 1000/dia, sobra). 0 = sem pausa.
LLM_REQUEST_DELAY_S = 6.5

# Exemplos de outros providers (descomente e ajuste a chave):
# Gemini:     LLM_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai"; LLM_MODEL="gemini-2.5-flash-lite"; LLM_API_KEY_ENV="GEMINI_API_KEY"; LLM_API_KEY_FILE_PROVIDER="gemini"
# OpenRouter: LLM_BASE_URL="https://openrouter.ai/api/v1"; LLM_MODEL="openai/gpt-oss-20b:free"; LLM_API_KEY_FILE_PROVIDER="openrouter"
# Zhipu:      LLM_BASE_URL="https://api.z.ai/api/paas/v4"; LLM_MODEL="glm-4.7-flash"; LLM_API_KEY_ENV="ZHIPU_API_KEY"; LLM_API_KEY_FILE_PROVIDER="zhipu"
# Ollama:     LLM_BASE_URL="http://localhost:11434/v1"; LLM_MODEL="qwen2.5:7b"; LLM_API_KEY_ENV=None
LLM_BATCH_SIZE = 30
