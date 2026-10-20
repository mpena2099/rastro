"""Acesso a dados da Fase 6 (revisao visual): sem Streamlit, testavel offline."""

import io
import sqlite3
from datetime import datetime
from urllib.parse import urlencode

import httpx
import numpy as np
import pandas as pd
from PIL import Image

DECISOES = ("confirmado", "duvida", "descartado")

# Cada revisao fica numa tabela propria: candidatos_fase5 e refeita a cada
# execucao do pipeline (to_sql replace) e apagaria as decisoes humanas.
_SCHEMA_REVISAO = """
CREATE TABLE IF NOT EXISTS revisao_humana (
    source_id TEXT PRIMARY KEY,
    decisao TEXT NOT NULL,
    nota TEXT,
    atualizado_em TEXT NOT NULL
)"""


def carregar_candidatos(conn: sqlite3.Connection) -> pd.DataFrame:
    """Todos os candidatos da Fase 4 (nao so os triados pela LLM), com score e revisao."""
    df = pd.read_sql("SELECT * FROM candidatos_fase4 WHERE status = 'candidato'", conn)
    try:
        llm = pd.read_sql(
            "SELECT source_id, llm_triage_score, llm_triage_notes FROM candidatos_fase5", conn)
    except Exception:
        llm = pd.DataFrame(columns=["source_id", "llm_triage_score", "llm_triage_notes"])
    df = df.merge(llm, on="source_id", how="left")
    df["llm_triage_score"] = df["llm_triage_score"].fillna("sem triagem")
    return df.merge(ler_revisoes(conn), on="source_id", how="left")


def ler_revisoes(conn: sqlite3.Connection) -> pd.DataFrame:
    conn.execute(_SCHEMA_REVISAO)
    return pd.read_sql("SELECT source_id, decisao, nota FROM revisao_humana", conn)


def salvar_revisao(conn: sqlite3.Connection, source_id: str, decisao: str, nota: str = "") -> None:
    if decisao not in DECISOES:
        raise ValueError(f"decisao invalida: {decisao!r} (use {DECISOES})")
    conn.execute(_SCHEMA_REVISAO)
    conn.execute(
        "INSERT OR REPLACE INTO revisao_humana VALUES (?, ?, ?, ?)",
        (source_id, decisao, nota, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()


def apagar_revisao(conn: sqlite3.Connection, source_id: str) -> None:
    conn.execute(_SCHEMA_REVISAO)
    conn.execute("DELETE FROM revisao_humana WHERE source_id = ?", (source_id,))
    conn.commit()


def url_recorte(ra: float, dec: float, camada: str, tamanho_arcsec: float = 60.0) -> str:
    """Recorte do visualizador do Legacy Surveys (unWISE e DR10 no mesmo servico)."""
    pixscale = 1.375 if camada.startswith("unwise") else 0.262
    size = int(round(tamanho_arcsec / pixscale))
    q = urlencode({"ra": ra, "dec": dec, "layer": camada, "pixscale": pixscale, "size": size})
    return f"https://www.legacysurvey.org/viewer/cutout.jpg?{q}"


def link_legacy_viewer(ra: float, dec: float) -> str:
    return f"https://www.legacysurvey.org/viewer?ra={ra}&dec={dec}&layer=ls-dr10&zoom=16"


def link_wiseview(ra: float, dec: float) -> str:
    return f"http://byw.tools/wiseview#ra={ra}&dec={dec}&size=100&band=2"


# Descricao de catalogo VizieR que indica lista de anas frias ou de movimento proprio: e onde
# um candidato "novo" pode ja estar publicado sem o SIMBAD saber (caso do Karpov+2025)
PALAVRAS_ANAS = ("dwarf", "brown", "ultracool", "ultra-cool", "proper motion", "proper-motion",
                 "low-mass", "motion")


def eh_lista_de_anas(descricao: str) -> bool:
    d = descricao.lower()
    return "white dwarf" not in d and any(p in d for p in PALAVRAS_ANAS)


def buscar_vizier(ra: float, dec: float, pm_total: float) -> pd.DataFrame:
    """Todos os catalogos do VizieR perto do candidato, com a distancia da fonte mais proxima.

    O raio cobre o quanto o objeto andou entre J2000 e a epoca do CatWISE (~2015), porque cada
    catalogo usa a sua epoca. Leva de 20 s a 1 min (consulta o VizieR inteiro).
    """
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from astroquery.vizier import Vizier

    raio = max(10.0, 16 * float(pm_total) + 5)
    res = Vizier(columns=["_r"], row_limit=5, timeout=180).query_region(
        SkyCoord(ra, dec, unit="deg"), radius=raio * u.arcsec)
    linhas = []
    for nome in res.keys():
        t = res[nome]
        descricao = str(t.meta.get("description", ""))
        linhas.append({"catalogo": nome, "descricao": descricao,
                       "dist_arcsec": float(np.min(t["_r"])) if "_r" in t.colnames else np.nan,
                       "lista_anas": eh_lista_de_anas(descricao)})
    df = pd.DataFrame(linhas, columns=["catalogo", "descricao", "dist_arcsec", "lista_anas"])
    return df.sort_values(["lista_anas", "dist_arcsec"], ascending=[False, True]).reset_index(drop=True)


def resumo_vizier(achados: pd.DataFrame) -> str:
    """Texto curto: as listas de anas/movimento proprio encontradas, ou que nao ha nenhuma."""
    anas = achados[achados["lista_anas"]]
    if anas.empty:
        return f"nenhuma lista de anas ou de movimento proprio ({len(achados)} catalogos gerais)"
    return "; ".join(f"{a.catalogo} ({a.descricao[:60]}) a {a.dist_arcsec:.1f}\""
                     for a in anas.itertuples())


def cruzar_gaia_ps1(df: pd.DataFrame) -> pd.DataFrame:
    """Marca candidatos com contraparte no Gaia DR3 (3") e no Pan-STARRS (2").

    Gaia no centro da posicao CatWISE (diferenca de epoca < 1 ano). Pan-STARRS DR1
    mede ~3 anos antes, entao a posicao e recuada pelo movimento proprio. So pra
    ordenar e filtrar a fila de revisao: anas L tambem aparecem no Pan-STARRS.
    """
    import astropy.units as u
    from astropy.table import Table
    from astroquery.xmatch import XMatch

    def xmatch(ra, dec, cat, raio_arcsec):
        t = Table({"source_id": df["source_id"].values, "ra": ra, "dec": dec})
        r = XMatch.query(cat1=t, cat2=cat, max_distance=raio_arcsec * u.arcsec,
                         colRA1="ra", colDec1="dec").to_pandas()
        return r.sort_values("angDist").drop_duplicates("source_id")

    out = df[["source_id"]].copy()
    g = xmatch(df["ra"].values, df["dec"].values, "vizier:I/355/gaiadr3", 3)
    out = out.merge(g[["source_id", "Gmag", "Plx"]].rename(
        columns={"Gmag": "gaia_g", "Plx": "gaia_plx"}), on="source_id", how="left")

    dt = -3.0
    ra_ps = df["ra"] + df["pmra"] * dt / 3600 / np.cos(np.radians(df["dec"]))
    dec_ps = df["dec"] + df["pmdec"] * dt / 3600
    p = xmatch(ra_ps.values, dec_ps.values, "vizier:II/349/ps1", 2)
    p = p[["source_id", "rmag", "zmag", "ymag"]].rename(
        columns={"rmag": "ps1_r", "zmag": "ps1_z", "ymag": "ps1_y"})
    out = out.merge(p, on="source_id", how="left")
    out["ps1_detectada"] = out[["ps1_r", "ps1_z", "ps1_y"]].notna().any(axis=1)
    out["gaia_detectada"] = out["gaia_g"].notna()
    return out


# Limites do teste de movimento contra o AllWISE (~2010), em segundos de arco.
ALLWISE_TOLERANCIA = 2.0        # fonte "no lugar" se estiver a ate isso da posicao
ALLWISE_SEPARACAO_MIN = 1.0     # e a outra posicao tem de estar pelo menos isso mais longe
ALLWISE_VIZINHANCA = 3.0        # sem fonte a menos que isso de qualquer das duas posicoes
ALLWISE_DESLOC_MIN = 1.5        # deslocamento esperado abaixo disso: sem poder de teste


def classificar_allwise(deslocamento: float, sep_prev: float | None, sep_atual: float | None) -> str:
    """Compara onde o AllWISE viu uma fonte com onde o movimento proprio manda ela estar.

    deslocamento: quanto o objeto deveria ter andado entre as duas epocas (arcsec).
    sep_prev / sep_atual: distancia da fonte AllWISE mais proxima a posicao prevista
    (CatWISE recuada pelo PM) e a posicao atual do CatWISE; None se nao ha fonte.
    'consistente' = a fonte esta onde o PM preve e longe da posicao atual (se moveu);
    'parado' = esta na posicao atual e longe da prevista (nao se moveu).
    """
    if deslocamento < ALLWISE_DESLOC_MIN:
        return "sem teste"
    if sep_prev is None or sep_atual is None or min(sep_prev, sep_atual) > ALLWISE_VIZINHANCA:
        return "sem fonte"
    if sep_prev <= ALLWISE_TOLERANCIA and sep_atual - sep_prev >= ALLWISE_SEPARACAO_MIN:
        return "consistente"
    if sep_atual <= ALLWISE_TOLERANCIA and sep_prev - sep_atual >= ALLWISE_SEPARACAO_MIN:
        return "parado"
    return "ambiguo"


def cruzar_allwise(df: pd.DataFrame, lote: int = 100) -> pd.DataFrame:
    """Teste de consistencia do movimento: o AllWISE mediu ~5 anos antes do CatWISE.

    Nao e totalmente independente: o CatWISE usa as mesmas exposicoes de 2010 no
    ajuste do movimento. Mas o AllWISE e outra reducao (outro pipeline, so a epoca
    antiga), entao pega PM espurio de casamento errado entre epocas. Se o PM do CatWISE for real, a fonte tem de estar no AllWISE na posicao recuada
    pelo PM, e nao na atual. O AllWISE e mais raso (W2 ~ 15,6 contra ~ 16,8): candidato
    fraco quase sempre cai em 'sem fonte', o que nao prova nada.
    Precisa de: source_id, ra, dec, pmra, pmdec, meanobsmjd.
    """
    import time
    import pyvo
    from astropy.table import Table

    svc = pyvo.dal.TAPService("https://irsa.ipac.caltech.edu/TAP")
    q = """SELECT TAP_UPLOAD.t.rid AS rid, a.ra AS a_ra, a.dec AS a_dec, a.w2mjdmean AS a_mjd
FROM allwise_p3as_psd AS a, TAP_UPLOAD.t
WHERE 1=CONTAINS(POINT('ICRS',a.ra,a.dec), CIRCLE('ICRS',TAP_UPLOAD.t.ra,TAP_UPLOAD.t.dec,15.0/3600.0))"""
    d = df.reset_index(drop=True).copy()
    d["rid"] = range(len(d))
    partes = []
    for i in range(0, len(d), lote):
        up = Table.from_pandas(d[["rid", "ra", "dec"]].iloc[i:i + lote])
        for tent in range(3):
            try:
                partes.append(svc.run_sync(q, uploads={"t": up}).to_table().to_pandas())
                break
            except Exception:
                if tent == 2:
                    raise
                time.sleep(8)
    viz = pd.concat(partes, ignore_index=True)

    linhas = []
    for x in d.itertuples():
        n = viz[viz["rid"] == x.rid]
        dt = (n["a_mjd"].median() - x.meanobsmjd) / 365.25 if len(n) else (55400.0 - x.meanobsmjd) / 365.25
        desloc = float(np.hypot(x.pmra, x.pmdec) * abs(dt))
        sp = sa = None
        if len(n):
            cosd = np.cos(np.radians(x.dec))
            ra_p = x.ra + x.pmra * dt / 3600 / cosd
            dec_p = x.dec + x.pmdec * dt / 3600
            sp = float(np.hypot((n["a_ra"] - ra_p) * cosd, n["a_dec"] - dec_p).min() * 3600)
            sa = float(np.hypot((n["a_ra"] - x.ra) * cosd, n["a_dec"] - x.dec).min() * 3600)
        linhas.append((x.source_id, classificar_allwise(desloc, sp, sa), sp, sa, desloc))
    return pd.DataFrame(linhas, columns=["source_id", "allwise_status", "allwise_sep_prevista",
                                         "allwise_sep_atual", "allwise_desloc_esperado"])


# ---------------------------------------------------------------- checklist e sugestao
ICONES_CHECKLIST = {"ok": "✅", "atencao": "⚠️", "problema": "❌"}


def checklist(r: dict) -> list[dict]:
    """Le os numeros do candidato em linguagem simples, um item por teste.

    Chave ausente ou vazia vira 'atencao': sem dado nao da para avaliar.
    """
    def item(estado, titulo, explicacao):
        return {"estado": estado, "titulo": titulo, "explicacao": explicacao}

    def valor(chave):
        v = r.get(chave)
        if v is None:
            return None
        try:
            return None if pd.isna(v) else v
        except (TypeError, ValueError):
            return v

    itens = []
    pm = valor("pm_signif")
    if pm is None:
        itens.append(item("atencao", "Movimento significativo",
                          "Sem medida de movimento próprio para avaliar."))
    elif pm >= 15:
        itens.append(item("ok", "Movimento significativo",
                          f"PM/σ = {pm:.1f}: o movimento é {pm:.1f} vezes maior que o erro da medida "
                          "(o mínimo é 15)."))
    else:
        itens.append(item("atencao", "Movimento significativo",
                          f"PM/σ = {pm:.1f}: abaixo de 15, o movimento pode ser só erro de medida."))

    allwise = valor("allwise_status")
    if allwise == "consistente":
        itens.append(item("ok", "Teste do AllWISE",
                          "Em ~2010 a fonte estava onde o movimento próprio prevê: o movimento é real."))
    elif allwise == "parado":
        itens.append(item("problema", "Teste do AllWISE",
                          "Em ~2010 a fonte estava no mesmo lugar de hoje: não se moveu."))
    elif allwise == "ambiguo":
        itens.append(item("atencao", "Teste do AllWISE",
                          "O AllWISE (~2010) vê fonte perto das duas posições e não decide."))
    else:
        itens.append(item("atencao", "Teste do AllWISE",
                          "Sem teste no AllWISE (~2010), porque o candidato é fraco demais ou falta "
                          "o dado. Isso não prova nada."))

    detectada, g = valor("gaia_detectada"), valor("gaia_g")
    if detectada is not None and not bool(detectada):
        itens.append(item("ok", "Gaia", "Sem contraparte no Gaia: não é uma estrela comum brilhante."))
    elif detectada is not None and g is not None and g < 19:
        itens.append(item("problema", "Gaia",
                          f"Contraparte no Gaia com G = {g:.1f}: estrela comum."))
    elif detectada is not None and g is not None:
        itens.append(item("atencao", "Gaia",
                          f"Contraparte no Gaia com G = {g:.1f}, bem fraca: anãs L também podem "
                          "aparecer. Confira a imagem."))
    else:
        itens.append(item("atencao", "Gaia",
                          "Sem cruzamento com o Gaia: não dá para descartar estrela comum."))

    cor = valor("cor_w1w2")
    if cor is None:
        itens.append(item("atencao", "Cor W1-W2",
                          "Sem as magnitudes W1 e W2: não dá para avaliar a cor."))
    elif cor >= 1.0:
        itens.append(item("ok", "Cor W1-W2",
                          f"Cor W1-W2 = {cor:.2f}: bem avermelhada, como as anãs T e Y."))
    elif cor >= 0.3:
        itens.append(item("ok", "Cor W1-W2", f"Cor W1-W2 = {cor:.2f}: faixa das anãs L."))
    else:
        itens.append(item("atencao", "Cor W1-W2",
                          f"Cor W1-W2 = {cor:.2f}: pouco vermelha, pode ser uma anã M comum."))

    ps1 = valor("ps1_detectada")
    if ps1 is None:
        itens.append(item("atencao", "Óptico Pan-STARRS",
                          "Sem cruzamento com o Pan-STARRS: não dá para avaliar o óptico."))
    elif not bool(ps1):
        itens.append(item("ok", "Óptico Pan-STARRS",
                          "Não aparece no óptico: some no visível, como as anãs T e Y."))
    elif cor is not None and cor < 0.5:
        itens.append(item("atencao", "Óptico Pan-STARRS",
                          "Aparece no óptico e a cor é pouco vermelha: pode ser estrela comum."))
    else:
        itens.append(item("ok", "Óptico Pan-STARRS",
                          "Aparece no óptico: anãs L também aparecem, então não descarta sozinho."))
    return itens


def sugestao(itens: list[dict]) -> str:
    """Resumo do checklist: um problema descarta, uma atencao vira duvida."""
    estados = {i["estado"] for i in itens}
    if "problema" in estados:
        return "descartado"
    return "duvida" if "atencao" in estados else "confirmado"


# ---------------------------------------------------------------- animacao do WiseView
BLINK_API = "https://moo23y1au0.execute-api.us-west-2.amazonaws.com/default/png-animation"
BLINK_S3 = "https://amnh-citsci-public.s3-us-west-2.amazonaws.com"


def url_blink(ra: float, dec: float, tamanho_px: int = 24) -> str:
    """Animacao de epocas do W2 do WiseView: devolve JSON com os quadros (ims) e os MJDs."""
    q = urlencode({"ra": ra, "dec": dec, "band": 2, "size": tamanho_px, "max_dyr": 0,
                   "minbright": -50, "maxbright": 500, "invert": 1, "stretch": 1, "diff": 0,
                   "scandir": 0, "outer": 0, "neowise": 0, "window": 0.5, "diff_window": 1,
                   "unique": 1, "smooth_scan": 0, "shift": 0, "pmx": 0, "pmy": 0,
                   "synth_a": 0, "synth_b": 0})
    return f"{BLINK_API}?{q}"


def epocas_blink(ra: float, dec: float, tamanho_px: int = 24) -> list[tuple[float, Image.Image]]:
    """(ano, imagem) de cada epoca do W2, em ordem. Uma nova tentativa se falhar.

    O servidor leva ate ~1 min; os quadros vem de graca do S3 do WiseView.
    """
    for tentativa in range(2):
        try:
            r = httpx.get(url_blink(ra, dec, tamanho_px), timeout=120)
            r.raise_for_status()
            d = r.json()
            saida = []
            for caminho, mjd in zip(d["ims"], d["mjds"]):
                img = httpx.get(f"{BLINK_S3}/{caminho}", timeout=120)
                img.raise_for_status()
                ano = 2000.0 + (float(np.median(mjd)) - 51544.5) / 365.25
                saida.append((ano, Image.open(io.BytesIO(img.content))))
            return sorted(saida, key=lambda x: x[0])
        except Exception:
            if tentativa == 1:
                raise


# ---------------------------------------------------------------- modo treino
def casos_treino(conhecidas: pd.DataFrame, estrelas: pd.DataFrame, rejeitados: pd.DataFrame,
                 n_por_classe: int = 10, semente: int = 42) -> pd.DataFrame:
    """Casos rotulados do modo treino, sorteados por classe e misturados.

    conhecidas: anas L/T/Y confirmadas (data/recall_conhecidas.pkl), estratificadas por tipo.
    estrelas: candidatos_fase4 com status='conhecido' (estrela comum de alto movimento).
    rejeitados: campo_bruto fora de candidatos_fase3; o corte de PM >= 0.3 e feito aqui.
    """
    from src.proper_motion import add_pm_columns

    def preparar(df):
        df = add_pm_columns(df) if {"pmra", "pmdec", "w1mpro", "w2mpro"} <= set(df) else df.copy()
        for col in ("pm_total", "pm_signif", "cor_w1w2"):
            if col not in df:
                df[col] = np.nan
        # sem posicao ou sem os numeros nao da para mostrar o caso no treino
        return df.dropna(subset=["ra", "dec", "pm_total", "pm_signif", "cor_w1w2", "w2mpro"])

    def linha(x):
        return {"ra": x.ra, "dec": x.dec, "pm_total": x.pm_total, "pm_signif": x.pm_signif,
                "cor_w1w2": x.cor_w1w2, "w2mpro": x.w2mpro}

    linhas = []
    for _, grupo in preparar(conhecidas).groupby("tipo"):
        for x in grupo.sample(min(n_por_classe, len(grupo)), random_state=semente).itertuples():
            linhas.append({**linha(x), "resposta": "confirmado",
                           "explicacao": f"Anã {x.sp_type} conhecida: {x.main_id}"})
    e = preparar(estrelas)
    for x in e.sample(min(n_por_classe, len(e)), random_state=semente).itertuples():
        nome = getattr(x, "simbad_match_id", "sem nome")
        linhas.append({**linha(x), "resposta": "descartado",
                       "explicacao": f"Estrela comum de alto movimento já catalogada ({nome}): "
                                     "brilha no óptico."})
    rej = preparar(rejeitados)
    rej = rej[rej["pm_total"] >= 0.3]
    for x in rej.sample(min(n_por_classe, len(rej)), random_state=semente).itertuples():
        linhas.append({**linha(x), "resposta": "descartado",
                       "explicacao": "O filtro de qualidade da Fase 3 rejeitou: movimento provavelmente "
                                     "falso (artefato, mistura de fontes ou ajuste ruim)."})
    colunas = ["ra", "dec", "pm_total", "pm_signif", "cor_w1w2", "w2mpro", "resposta", "explicacao"]
    return pd.DataFrame(linhas, columns=colunas).sample(frac=1, random_state=semente).reset_index(
        drop=True)
