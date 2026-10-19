"""Testes de unidade offline (sem rede) da logica pura do pipeline.

Roda de dois jeitos, a partir da raiz do repo:
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
from src.fetch_field import build_query, make_tiles
from src.quality_filter import pmcode_sem_troca
from src.known_catalog_match import posicao_j2000, MJD_J2000
import config


def test_add_pm_columns():
    df = pd.DataFrame({"pmra": [3.0], "pmdec": [4.0], "w1mpro": [10.0], "w2mpro": [8.0]})
    out = add_pm_columns(df)
    assert abs(out["pm_total"].iloc[0] - 5.0) < 1e-9      # sqrt(3^2 + 4^2)
    assert abs(out["cor_w1w2"].iloc[0] - 2.0) < 1e-9      # w1 - w2
    assert "pm_signif" not in out                          # sem sigpm, nao calcula


def test_pm_signif():
    # pm=5, sigpm iguais a 0.5 nos dois eixos -> sigma(pm)=0.5 -> 10 sigma
    df = pd.DataFrame({"pmra": [3.0], "pmdec": [4.0], "sigpmra": [0.5], "sigpmdec": [0.5],
                       "w1mpro": [10.0], "w2mpro": [8.0]})
    assert abs(add_pm_columns(df)["pm_signif"].iloc[0] - 10.0) < 1e-9


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


def test_pmcode_sem_troca():
    # ABCCC: so B importa ('Y' = secundario substituiu o primario). A (componentes
    # do blend) nao filtra: derrubava o recall de anas reais de 75% pra 25%.
    s = pd.Series(["1N000", "3N013", "2N000", "1Y000", "3Y001", None, ""])
    assert pmcode_sem_troca(s).tolist() == [True, True, True, False, False, False, False]


def test_build_query_filtros_server_side():
    q = build_query(149.5, 150.5, 19.5, 20.5)
    assert f"TOP {config.ROW_LIMIT}" in q
    assert "ra BETWEEN" in q and "dec BETWEEN" in q
    assert "ka = 3 AND km = 3" in q
    assert "SQRT(POWER(pmra" in q                 # filtro de movimento proprio
    assert "w2snr >=" in q and "w2flg < 8" in q    # SNR e flag de W2 server-side
    where = q.split("WHERE")[1]
    assert "w1snr" not in where and "w1flg" not in where  # sem corte em W1 (anas Y)


def test_make_tiles_cobre_regiao():
    tiles = make_tiles()
    n_ra = round((config.FIELD_RA_RANGE[1] - config.FIELD_RA_RANGE[0]) / config.FIELD_STEP_DEG)
    n_dec = round((config.FIELD_DEC_RANGE[1] - config.FIELD_DEC_RANGE[0]) / config.FIELD_STEP_DEG)
    assert len(tiles) == n_ra * n_dec
    assert min(t[0] for t in tiles) == config.FIELD_RA_RANGE[0]
    assert max(t[1] for t in tiles) == config.FIELD_RA_RANGE[1]
    assert min(t[2] for t in tiles) == config.FIELD_DEC_RANGE[0]
    assert max(t[3] for t in tiles) == config.FIELD_DEC_RANGE[1]


def test_revisao_humana_persiste_e_valida():
    import sqlite3
    from app import dados
    conn = sqlite3.connect(":memory:")
    dados.salvar_revisao(conn, "A", "confirmado", "parece real")
    dados.salvar_revisao(conn, "B", "descartado")
    dados.salvar_revisao(conn, "A", "duvida", "olhar de novo")        # regrava, nao duplica
    r = dados.ler_revisoes(conn).set_index("source_id")
    assert len(r) == 2 and r.loc["A", "decisao"] == "duvida" and r.loc["A", "nota"] == "olhar de novo"
    dados.apagar_revisao(conn, "B")
    assert dados.ler_revisoes(conn)["source_id"].tolist() == ["A"]
    try:
        dados.salvar_revisao(conn, "C", "talvez")
        assert False, "devia rejeitar decisao invalida"
    except ValueError:
        pass


def test_marcar_catalogos():
    from src.known_catalog_match import marcar_catalogos
    df = pd.DataFrame({"source_id": ["a", "b", "c"],
                       "status": ["candidato", "conhecido", "candidato"]})
    out = marcar_catalogos(df, {"a": "Karpov+2025 (unTimely)", "b": "X"})
    assert out["status"].tolist() == ["conhecido", "conhecido", "candidato"]
    # so rebaixa candidato; quem o SIMBAD ja marcou fica sem catalogo_match
    assert out["catalogo_match"].tolist()[:2] == ["Karpov+2025 (unTimely)", None]


def test_lista_de_anas():
    from app.dados import eh_lista_de_anas, resumo_vizier
    assert eh_lista_de_anas("New high-proper-motion objects detected in this work")
    assert eh_lista_de_anas("New L, T, and Y dwarf candidates")
    assert not eh_lista_de_anas("Gaia EDR3 white dwarf candidates")
    assert not eh_lista_de_anas("the CatWISE2020 catalog")
    achados = pd.DataFrame({"catalogo": ["II/365/catwise", "J/A+A/695/A195/table2"],
                            "descricao": ["the CatWISE2020 catalog", "New high-proper-motion objects"],
                            "dist_arcsec": [0.1, 0.18], "lista_anas": [False, True]})
    assert "J/A+A/695/A195/table2" in resumo_vizier(achados) and "0.2\"" in resumo_vizier(achados)
    assert resumo_vizier(achados[~achados["lista_anas"]]).startswith("nenhuma lista")


def test_url_recorte():
    from app import dados
    u = dados.url_recorte(150.0, 20.0, "unwise-neo2")
    assert "layer=unwise-neo2" in u and "pixscale=1.375" in u and "size=44" in u
    assert "pixscale=0.262" in dados.url_recorte(150.0, 20.0, "ls-dr10")


def test_relatorio():
    from src.relatorio import nome_iau, montar_html
    assert nome_iau(150.0, 20.0) == "J100000.00+200000.0"
    assert nome_iau(15.0, -0.5) == "J010000.00-003000.0"
    df = pd.DataFrame([{
        "source_id": "x", "ra": 150.0, "dec": 20.0, "decisao": "confirmado", "nota": "<b>",
        "w1mpro": 15.0, "w2mpro": 13.5, "cor_w1w2": 1.5, "pm_total": 0.4, "pmra": 0.3, "pmdec": 0.2,
        "pm_signif": 10.0, "w2snr": 12.0, "meanobsmjd": 57170.0, "allwise_status": "consistente",
        "allwise_sep_prevista": 0.5, "allwise_sep_atual": 4.0, "allwise_desloc_esperado": 2.0,
        "gaia_detectada": pd.NA, "ps1_detectada": False}])
    h = montar_html(df, {"x": {"ls-dr10": b"\xff\xd8"}})
    assert "J100000.00+200000.0" in h and "&lt;b&gt;" in h and "sem dado" in h
    assert "data:image/jpeg;base64," in h and "recorte indisponivel" in h


def test_classificar_allwise():
    from app.dados import classificar_allwise as c
    assert c(5.0, 0.4, 5.0) == "consistente"      # esta onde o PM preve, longe da atual
    assert c(5.0, 5.0, 0.4) == "parado"           # esta na posicao atual: nao se moveu
    assert c(5.0, 9.0, 8.0) == "sem fonte"        # nada perto de nenhuma das duas
    assert c(5.0, None, None) == "sem fonte"      # nenhuma fonte AllWISE na vizinhanca
    assert c(0.8, 0.1, 0.5) == "sem teste"        # PM baixo: as duas posicoes se confundem
    assert c(5.0, 2.5, 2.8) == "ambiguo"          # perto das duas, sem desempate


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
