"""Acesso a dados da Fase 6 (revisao visual): sem Streamlit, testavel offline."""

import sqlite3
from datetime import datetime
from urllib.parse import urlencode

import numpy as np
import pandas as pd

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
    """Teste de movimento independente: o AllWISE mediu ~5 anos antes do CatWISE.

    Se o PM do CatWISE for real, a fonte tem de estar no AllWISE na posicao recuada
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
