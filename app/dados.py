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
