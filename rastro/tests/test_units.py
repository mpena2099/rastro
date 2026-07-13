"""Testes de unidade offline (sem rede) da logica pura do pipeline.

Roda de dois jeitos, a partir de rastro/:
    python tests/test_units.py       # runner embutido, sem dependencia
    python -m pytest tests/          # se pytest estiver instalado

Cobre as regras que dao errado calado se quebrarem: derivacao de movimento
proprio, parsing do score da LLM (incluindo a regra "alta so via veredito
explicito") e a montagem da query da Fase 2. NAO testa as chamadas de rede
(IRSA/SIMBAD/LLM) -- pra isso use a Fase 1 (sanity check).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from src.proper_motion import add_pm_columns
from src.llm_triage import parse_score, interpret_response
from src.fetch_field import build_query
import config


def test_add_pm_columns():
    df = pd.DataFrame({"pmra": [3.0], "pmdec": [4.0], "w1mpro": [10.0], "w2mpro": [8.0]})
    out = add_pm_columns(df)
    assert abs(out["pm_total"].iloc[0] - 5.0) < 1e-9      # sqrt(3^2 + 4^2)
    assert abs(out["cor_w1w2"].iloc[0] - 2.0) < 1e-9      # w1 - w2


def test_parse_score_veredito_explicito():
    assert parse_score("VEREDITO: alta") == "alta"
    assert parse_score("bla\nVEREDITO: baixa") == "baixa"
    # tolera markdown/pontuacao entre o rotulo e o valor
    assert parse_score("**Veredito:** Baixa\n\nraciocinio...") == "baixa"


def test_parse_score_alta_so_via_veredito():
    # Sem veredito explicito, mesmo com termos positivos, NAO promove a alta
    # (regra anti-falso-positivo). Deve cair em 'media'.
    assert parse_score("consistente com ana marrom tipo T e tipo Y") == "media"


def test_parse_score_fallback_keyword_rebaixa():
    assert parse_score("provavel artefato de fundo mal medida") == "baixa"
    assert parse_score("evidencia insuficiente para opinar") == "incerta"
    assert parse_score("texto neutro qualquer") == "media"


def test_interpret_response_json():
    notes, score = interpret_response('{"veredito":"alta","raciocinio":"consistente"}')
    assert score == "alta"
    assert notes == "consistente"


def test_interpret_response_none_e_texto():
    assert interpret_response(None) == ("", "media")
    notes, score = interpret_response("analise...\nVEREDITO: incerta")
    assert score == "incerta"


def test_build_query_filtros_server_side():
    q = build_query()
    assert f"TOP {config.ROW_LIMIT}" in q
    assert "ra BETWEEN" in q and "dec BETWEEN" in q
    assert "ka = 3 AND km = 3" in q
    assert "SQRT(POWER(pmra" in q                 # filtro de movimento proprio
    assert "w1snr >=" in q and "w2snr >=" in q     # SNR server-side
    assert "w1flg < 8" in q and "w2flg < 8" in q   # flags server-side


def test_load_api_key_env():
    from src.llm_triage import load_api_key
    if config.LLM_API_KEY_ENV:
        os.environ[config.LLM_API_KEY_ENV] = "chave-de-teste"
        try:
            assert load_api_key() == "chave-de-teste"
        finally:
            del os.environ[config.LLM_API_KEY_ENV]


def _main():
    testes = [v for k, v in sorted(globals().items())
              if k.startswith("test_") and callable(v)]
    falhas = 0
    for t in testes:
        try:
            t()
            print(f"  PASS {t.__name__}")
        except AssertionError as e:
            falhas += 1
            print(f"  FAIL {t.__name__}: {e}")
        except Exception as e:
            falhas += 1
            print(f"  ERRO {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(testes) - falhas}/{len(testes)} passaram")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    _main()
