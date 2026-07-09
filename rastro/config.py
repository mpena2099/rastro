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
ROW_LIMIT = 5000

# Fase 3 — quality filter
W1SNR_MIN = 5.0
W2SNR_MIN = 3.0
N_AW_MAX = 1

# Fase 4 — cross-match
SIMBAD_RADIUS_ARCSEC = 5
SIMBAD_DELAY_S = 0.3

# Fase 5 — LLM triage
OPENROUTER_API_KEY_PATH = Path.home() / ".local" / "share" / "opencode" / "auth.json"
LLM_MODEL = "openai/gpt-4o-mini"
LLM_TEMPERATURE = 0.3
LLM_MAX_TOKENS = 512
LLM_BATCH_SIZE = 30
