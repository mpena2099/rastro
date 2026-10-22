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


def test_checklist_e_sugestao():
    from app import dados
    ok = {"pm_signif": 20.0, "allwise_status": "consistente", "gaia_detectada": False,
          "ps1_detectada": False, "cor_w1w2": 1.2}
    itens = dados.checklist(ok)
    assert [i["estado"] for i in itens] == ["ok"] * 5
    assert all(set(i) == {"estado", "titulo", "explicacao"} for i in itens)
    assert dados.sugestao(itens) == "confirmado"
    assert dados.sugestao(dados.checklist({**ok, "allwise_status": "parado"})) == "descartado"
    # G-W2 < 5: estrela comum; G-W2 >= 5: pode ser ana M tardia ou L (mesmo com G < 19)
    g15 = dados.checklist({**ok, "gaia_detectada": True, "gaia_g": 15.0, "w2mpro": 12.0})
    assert any(i["estado"] == "problema" for i in g15)
    l_proxima = dados.checklist({**ok, "gaia_detectada": True, "gaia_g": 18.0, "w2mpro": 10.5})
    assert not any(i["estado"] == "problema" for i in l_proxima)
    assert dados.sugestao(dados.checklist({**ok, "gaia_g": 20.0, "gaia_detectada": True,
                                           "w2mpro": 13.0})) == "duvida"
    assert dados.sugestao(dados.checklist({**ok, "cor_w1w2": 0.2})) == "duvida"
    # chave ausente nao pode quebrar (casos do treino nao tem Gaia/PS1/AllWISE)
    faltando = dados.checklist({})
    assert len(faltando) == 5 and all(i["estado"] == "atencao" for i in faltando)


def test_url_blink():
    from app import dados
    u = dados.url_blink(150.0, 20.0)
    assert "ra=150.0" in u and "dec=20.0" in u and "band=2" in u and "size=24" in u


def test_casos_treino():
    from app import dados
    conhecidas = pd.DataFrame({
        "main_id": ["Ana 1", "Ana 2", "Ana 3", "Ana 4", "Ana 5", "Ana 6", "Ana 7"],
        "sp_type": ["L5", "T2", "Y0", "L8", "T7", "Y1", "Y2"],
        "tipo": ["L", "T", "Y", "L", "T", "Y", "Y"],
        "ra": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0], "dec": [0.0] * 7,
        "pmra": [0.5] * 7, "pmdec": [0.1] * 7,
        # Ana 7: movimento abaixo do erro (PM/sigma ~2), nao passaria na fila real
        "sigpmra": [0.01] * 6 + [0.2], "sigpmdec": [0.01] * 6 + [0.2],
        "w1mpro": [15.0] * 7, "w2mpro": [13.5] * 7,
        "ka": [3] * 7, "km": [3] * 7, "w2snr": [20.0] * 7, "w2flg": [0] * 7, "n_aw": [0] * 7,
        "cc_flags": ["0000"] * 7, "ab_flags": ["00"] * 7, "pmcode": ["1N000"] * 7})
    estrelas = pd.DataFrame({
        "ra": [20.0, 21.0, 22.0], "dec": [1.0] * 3,
        "pmra": [0.3] * 3, "pmdec": [0.1] * 3,
        "sigpmra": [0.01] * 3, "sigpmdec": [0.01] * 3,
        "w1mpro": [12.0] * 3, "w2mpro": [11.9] * 3,
        "simbad_match_id": ["LSPM J1", "HD 2", "TYC 3"]})
    rejeitados = pd.DataFrame({
        "ra": [30.0, 31.0], "dec": [2.0, 2.0],
        "pmra": [0.4, 0.05], "pmdec": [0.0, 0.0],
        "sigpmra": [0.01] * 2, "sigpmdec": [0.01] * 2,
        "w1mpro": [16.0] * 2, "w2mpro": [15.0] * 2})
    casos = dados.casos_treino(conhecidas, estrelas, rejeitados, n_por_classe=2)
    assert list(casos.columns) == ["ra", "dec", "pm_total", "pm_signif", "cor_w1w2", "w2mpro",
                                   "source_id", "pmra", "pmdec", "meanobsmjd",
                                   "resposta", "explicacao"]
    assert casos["source_id"].str.startswith("treino:").all()
    # 2 por tipo conhecido + 2 estrelas + 1 rejeitado (o de PM 0.05 e cortado)
    assert len(casos) == 9
    assert casos["resposta"].value_counts().to_dict() == {"confirmado": 6, "descartado": 3}
    assert casos["explicacao"].str.startswith("Anã L5 conhecida: Ana 1").any()
    # metade dos confirmados vem da metade de menor PM/sigma de cada tipo
    assert casos["explicacao"].str.contains("caso difícil").sum() == 3
    assert not casos["explicacao"].str.contains("Ana 7").any()
    assert casos.equals(dados.casos_treino(conhecidas, estrelas, rejeitados, n_por_classe=2))
    assert not casos.equals(dados.casos_treino(conhecidas, estrelas, rejeitados, n_por_classe=3))


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


def test_guia_pista_e_exemplos():
    from app.guia import exemplos, pista
    assert "nada no óptico" in pista({"explicacao": "Anã T5.5 conhecida: X", "pm_total": 1.0})
    assert "vermelho fraco" in pista({"explicacao": "Anã L2 conhecida: X", "pm_total": 0.5})
    assert "SIMBAD" in pista({"explicacao": "Estrela já catalogada no SIMBAD (LP 1, PM*)"})
    assert "difusa" in pista({"explicacao": "Galáxia catalogada no SIMBAD (SDSS J1)"})
    from app.dados import explicar_catalogado
    assert explicar_catalogado("X", "G", None).startswith("Galáxia")
    assert "não é descoberta" in explicar_catalogado("X", "", None)
    assert "M6V" in explicar_catalogado("X", "PM*", "M6V")
    assert "significância" in pista({"explicacao": "O filtro de qualidade da Fase 3 rejeitou", "pm_signif": 6.0})
    casos = pd.DataFrame({
        "ra": [1.0, 2.0, 3.0, 4.0], "dec": [0.0] * 4, "pm_total": [2.0, 1.0, 0.4, 0.5],
        "pm_signif": [30, 20, 5, 9], "w2mpro": [15, 15, 9, 16],
        "explicacao": ["Anã T8 conhecida: A", "Anã T5 conhecida: B",
                       "Estrela já catalogada no SIMBAD (C, PM*)",
                       "O filtro de qualidade da Fase 3 rejeitou: x"]})
    ex = exemplos(casos)
    assert ex["movimento"][0]["ra"] == 1.0 and ex["ls-dr10"][1]["ra"] == 3.0
    assert exemplos(casos, excluir=(1.0, 0.0))["movimento"][0]["ra"] == 2.0


def test_guia_pista_casos_limite():
    from app.guia import exemplos, pista
    # 1"/ano em 14 anos = 14", ~5 pixels de 2,75"
    assert '14"' in pista({"explicacao": "Anã T5 conhecida: X", "pm_total": 1.0})
    assert "~5 pixels" in pista({"explicacao": "Anã T5 conhecida: X", "pm_total": 1.0})
    for pm in (None, float("nan")):
        txt = pista({"explicacao": "Anã Y0 conhecida: X", "pm_total": pm})
        assert "anda" not in txt and "nan" not in txt
    assert "nada no óptico" in pista({"explicacao": "Anã", "pm_total": None})
    txt = pista({"explicacao": "O filtro de qualidade da Fase 3 rejeitou", "pm_signif": float("nan")})
    assert "significância" not in txt and "nan" not in txt
    assert "6.0" in pista({"explicacao": "O filtro de qualidade da Fase 3 rejeitou", "pm_signif": 6.0})
    assert pista({}).startswith("Compare")
    assert pista({"explicacao": "outra coisa"}).startswith("Compare")
    # galaxia nunca recebe a pista de estrela
    assert "SIMBAD" not in pista({"explicacao": "Galáxia catalogada no SIMBAD (X, G)"})
    base = {"dec": [0.0] * 3, "pm_signif": [30, 20, 9], "w2mpro": [15, 15, 9]}
    # sem ana T: o bom vem de qualquer confirmado (o de maior PM)
    casos = pd.DataFrame({**base, "ra": [1.0, 2.0, 3.0], "pm_total": [0.5, 0.9, 0.3],
                          "resposta": ["confirmado", "confirmado", "descartado"],
                          "explicacao": ["Anã L2 conhecida: A", "Anã L5 conhecida: B",
                                         "Estrela já catalogada no SIMBAD (C, PM*)"]})
    ex = exemplos(casos)
    assert ex["movimento"][0]["ra"] == 2.0
    assert ex["movimento"][1] is None  # sem rejeitado da Fase 3, sem exemplo ruim
    assert ex["ls-dr10"][1]["ra"] == 3.0
    assert exemplos(casos.iloc[2:])["movimento"][0] is None


def test_resumo_treino():
    import sqlite3
    from app.dados import ler_tentativas, resumo_treino, salvar_tentativa
    conn = sqlite3.connect(":memory:")
    assert resumo_treino(ler_tentativas(conn)) == {}
    for escolha, certa, pontos in [("confirmado", "confirmado", 1.0),
                                   ("confirmado", "descartado", 0.0),
                                   ("duvida", "descartado", 0.5)]:
        salvar_tentativa(conn, "1.00000,2.00000", escolha, certa, pontos)
    r = resumo_treino(ler_tentativas(conn), recentes=2)
    assert r["respostas"] == 3 and r["dias"] == 1
    assert abs(r["geral"] - 0.5) < 1e-9 and abs(r["recentes"] - 0.25) < 1e-9
    assert r["n_recentes"] == 2
    assert r["por_certa"] == {"confirmado": (1.0, 1), "descartado": (0.25, 2)}
    assert "periodo" not in r


def test_com_prazo():
    import time
    from src.util import com_prazo
    assert com_prazo(lambda: 7, 1) == 7
    try:
        com_prazo(lambda: time.sleep(5), 0.2)
        assert False, "devia estourar o prazo"
    except TimeoutError:
        pass
    try:
        com_prazo(lambda: 1 / 0, 1)
        assert False
    except ZeroDivisionError:
        pass


def test_campos_grade():
    from astropy.coordinates import SkyCoord
    from src import campos
    g = campos.grade()
    inicial = g[0]
    assert inicial["nome"] == "ra148-153_dec+18+23"
    assert (inicial["ra_min"], inicial["ra_max"]) == tuple(config.FIELD_RA_RANGE)
    assert (inicial["dec_min"], inicial["dec_max"]) == tuple(config.FIELD_DEC_RANGE)
    assert len({b["nome"] for b in g}) == len(g)
    assert all(b["dec_min"] >= campos.DEC_MIN and b["dec_max"] <= campos.DEC_MAX for b in g)
    # ordenada pela distancia angular ao centro do bloco inicial
    centro = SkyCoord(sum(config.FIELD_RA_RANGE) / 2,
                      sum(config.FIELD_DEC_RANGE) / 2, unit="deg")
    dist = [SkyCoord((b["ra_min"] + b["ra_max"]) / 2,
                     (b["dec_min"] + b["dec_max"]) / 2, unit="deg").separation(centro).deg
            for b in g]
    assert dist == sorted(dist)


def test_campos_proximo():
    from src import campos
    g = campos.grade()
    inicial = g[0]
    assert campos.proximo([])["nome"] == inicial["nome"]
    assert campos.proximo([inicial])["nome"] != inicial["nome"]
    # tudo antes do primeiro bloco do plano galactico feito: ele e pulado
    plano = next(i for i, b in enumerate(g)
                 if campos.latitude_galactica(b) < campos.B_GALACTICO_MIN)
    saltado = campos.proximo(g[:plano + 1])
    esperado = next(b for b in g[plano + 1:]
                    if campos.latitude_galactica(b) >= campos.B_GALACTICO_MIN)
    assert saltado["nome"] == esperado["nome"]
    assert campos.latitude_galactica(saltado) >= campos.B_GALACTICO_MIN
    assert campos.proximo(g) is None


def test_campos_feitos_sqlite():
    import sqlite3
    from src import campos
    conn = sqlite3.connect(":memory:")
    assert campos.ler_feitos(conn) == []
    inicial = campos.grade()[0]
    campos.registrar(conn, inicial, 120)
    linhas = campos.ler_feitos(conn)
    assert len(linhas) == 1 and linhas[0]["nome"] == inicial["nome"]
    assert linhas[0]["candidatos"] == 120
    campos.registrar(conn, inicial, 300)  # mesmo nome: regrava, nao duplica
    assert campos.ler_feitos(conn)[0]["candidatos"] == 300


def test_estado_execucao():
    from app.execucao import estado
    vazio = estado("")
    assert vazio["fase"] is None and not vazio["terminou"] and vazio["erro"] is None
    log = """  Proximo campo: ra148-153_dec+18+23 (RA 148-153, Dec +18 a +23)
  Executando: Fase 4 - SIMBAD cross-match
  120/500 (0 erros)
  Executando: Fase 5 - LLM triage
"""
    e = estado(log)
    assert e["campo"].startswith("ra148-153") and e["fase"] == "Fase 5 - LLM triage"
    assert e["progresso"] is None  # fase nova zera o progresso da anterior
    assert estado(log + "  50/500\n")["progresso"] == (50, 500)
    assert estado(log + "\nERRO em Fase 5 - LLM triage: timeout\n")["erro"].startswith("ERRO em")
    assert estado(log + "  Campo x registrado em campos_feitos.\n")["terminou"]
    assert estado("  A grade de campos acabou: todos\n")["fim_da_grade"]
    assert not e["cancelada"] and estado(log + "\nBusca cancelada pelo app.\n")["cancelada"]


def test_acumular_fase4():
    from src.known_catalog_match import acumular
    antiga = pd.DataFrame({"source_id": ["a", "b"], "pm_total": [1.0, 2.0]})
    nova = pd.DataFrame({"source_id": ["b", "c"], "pm_total": [9.0, 3.0]})
    out = acumular(antiga, nova)
    assert out["source_id"].tolist() == ["a", "b", "c"]
    assert out.set_index("source_id").loc["b", "pm_total"] == 9.0
    assert acumular(None, nova).equals(nova)
    assert acumular(pd.DataFrame(), nova).equals(nova)


def _historico(linhas):
    """treino_historico em memoria: (certa, pontos) em ordem."""
    return pd.DataFrame([{"respondido_em": f"2026-10-21T10:{i:02d}:00", "caso": str(i),
                          "pergunta": "decisao", "escolha": certa, "certa": certa, "pontos": p}
                         for i, (certa, p) in enumerate(linhas)])


def test_nivel_treino():
    import sqlite3
    from app import dados as dados_
    assert dados_.nivel_treino(dados_.ler_tentativas(sqlite3.connect(":memory:")))[0] == "Aprendiz"
    # menos de 20 respostas: Aprendiz mesmo acertando tudo
    nivel, falta = dados_.nivel_treino(_historico([("confirmado", 1.0)] * 10))
    assert nivel == "Aprendiz" and "faltam 10" in falta
    # 60% nas ultimas 20: Revisor, e o que falta e o acerto recente
    nivel, falta = dados_.nivel_treino(_historico(
        [("confirmado", 1.0)] * 12 + [("descartado", 0.0)] * 8))
    assert nivel == "Revisor" and "60%" in falta and "80%" in falta, (nivel, falta)
    # 80% no total, mas so 60% nos casos Descartado: vies de confirmar demais
    nivel, falta = dados_.nivel_treino(_historico(
        [("confirmado", 1.0)] * 10 + [("descartado", 1.0)] * 6 + [("descartado", 0.0)] * 4))
    assert nivel == "Revisor" and "Descartado" in falta and "confirmar demais" in falta
    # 85% no total e pelo menos 70% em cada resposta certa
    nivel, falta = dados_.nivel_treino(_historico(
        [("confirmado", 1.0)] * 10 + [("descartado", 1.0)] * 7 + [("descartado", 0.0)] * 3))
    assert nivel == "Revisor confiável" and falta == ""


def test_marcos():
    import sqlite3
    from app import dados as dados_
    conn = sqlite3.connect(":memory:")
    m = dados_.marcos(conn)
    assert [x["nome"] for x in m] == ["Treino em dia", "Fila revisada", "Confirmado defensável",
                                      "Segunda opinião pedida", "Descoberta publicada"]
    assert not any(x["feito"] for x in m)
    dados_.marcar(conn, "Segunda opinião pedida", True)
    assert dados_.marcos(conn)[3]["feito"]
    dados_.marcar(conn, "Segunda opinião pedida", False)
    assert not dados_.marcos(conn)[3]["feito"]


if __name__ == "__main__":
    _main()
