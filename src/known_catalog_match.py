import sqlite3
import sys
import numpy as np
import pandas as pd
from astropy.table import Table
from astroquery.xmatch import XMatch
import astropy.units as u

from config import (CATALOGOS_ANAS, CATALOGOS_RAIO_ARCSEC, REDE_PRAZO_S, SQLITE_PATH,
                    SIMBAD_DELAY_S, SIMBAD_RADIUS_ARCSEC)
from src.util import com_prazo


MJD_J2000 = 51544.5


def posicao_j2000(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    # SIMBAD da coordenadas na epoca J2000; CatWISE mede em ~2015 (meanobsmjd).
    # Sem voltar a posicao pelo PM, fonte com PM > ~0.3"/ano anda mais que o
    # raio do match em 15 anos e escapa como "candidato" (ex: anas L conhecidas).
    # pmra do CatWISE ja e movimento no ceu (inclui cos dec).
    dt_anos = (df["meanobsmjd"] - MJD_J2000) / 365.25
    dec = df["dec"] - df["pmdec"] * dt_anos / 3600.0
    ra = df["ra"] - df["pmra"] * dt_anos / 3600.0 / np.cos(np.radians(df["dec"]))
    return ra % 360.0, dec


def marcar_catalogos(df: pd.DataFrame, achados: dict[str, str]) -> pd.DataFrame:
    """Marca como conhecido o candidato que aparece numa lista de anas (source_id -> nome)."""
    df = df.copy()
    if "catalogo_match" not in df:
        df["catalogo_match"] = None
    mask = (df["status"] == "candidato") & df["source_id"].isin(achados)
    df.loc[mask, "catalogo_match"] = df.loc[mask, "source_id"].map(achados)
    df.loc[mask, "status"] = "conhecido"
    return df


def _cruzar_catalogos(df: pd.DataFrame) -> pd.DataFrame:
    cand = df[df["status"] == "candidato"]
    if cand.empty:
        return marcar_catalogos(df, {})
    print(f"\nCruzando {len(cand)} candidatos com {len(CATALOGOS_ANAS)} listas de anas (VizieR)...")
    ra2000, dec2000 = posicao_j2000(cand)
    posicoes = ((cand["ra"], cand["dec"]), (ra2000, dec2000))
    achados = {}
    for tabela, nome in CATALOGOS_ANAS.items():
        ids = set()
        try:
            for ra, dec in posicoes:
                t = Table({"source_id": cand["source_id"].values, "ra": ra.values,
                           "dec": dec.values})
                r = com_prazo(lambda: XMatch.query(
                    cat1=t, cat2=f"vizier:{tabela}", max_distance=CATALOGOS_RAIO_ARCSEC * u.arcsec,
                    colRA1="ra", colDec1="dec"), REDE_PRAZO_S)
                ids |= {str(s) for s in r["source_id"]}
        except Exception as e:
            # uma lista fora do ar nao derruba a fase; o SIMBAD ja filtrou o grosso
            print(f"  AVISO {nome}: {str(e)[:100]}")
            continue
        for s in ids:
            achados.setdefault(s, nome)
        if ids:
            print(f"  {nome}: {len(ids)}")
    return marcar_catalogos(df, achados)


def run():
    print("=" * 50)
    print("Fase 4 — Cross-match SIMBAD (via CDS XMatch)")
    print("=" * 50)

    conn = sqlite3.connect(str(SQLITE_PATH))
    df = pd.read_sql("SELECT * FROM candidatos_fase3", conn)
    conn.close()

    print(f"Candidatos: {len(df)}")

    t = Table()
    t["source_id"] = df["source_id"].values
    ra2000, dec2000 = posicao_j2000(df)
    t["ra"] = ra2000.values
    t["dec"] = dec2000.values

    print("Enviando batch p/ CDS XMatch (SIMBAD)...")
    try:
        result = com_prazo(lambda: XMatch.query(
            cat1=t,
            cat2="simbad",
            max_distance=SIMBAD_RADIUS_ARCSEC * u.arcsec,
            colRA1="ra",
            colDec1="dec",
        ), REDE_PRAZO_S)
    except Exception as e:
        print(f"XMatch falhou: {e}")
        print("Caindo p/ consulta individual lenta...")
        return _fallback_sequential(df)

    if result is None or len(result) == 0:
        print("Nenhum match SIMBAD encontrado.")
        df_result = df.copy()
        df_result["simbad_match_id"] = None
        df_result["status"] = "candidato"
    else:
        print(f"Matches retornados: {len(result)}")
        print(f"Colunas: {result.colnames}")

        match_df = result.to_pandas()

        # Um source_id pode casar com varios objetos SIMBAD: fica com o mais
        # proximo (XMatch devolve a separacao em angDist, arcsec).
        nearest = match_df.loc[match_df.groupby("source_id")["angDist"].idxmin()]
        known_ids = dict(zip(nearest["source_id"], nearest["main_id"]))

        df_result = df.copy()
        df_result["simbad_match_id"] = None
        df_result["status"] = "candidato"
        for src_id, simbad_id in known_ids.items():
            mask = df_result["source_id"] == src_id
            df_result.loc[mask, "simbad_match_id"] = simbad_id
            df_result.loc[mask, "status"] = "conhecido"

    return _gravar(df_result)


def ler_tabela(conn: sqlite3.Connection, nome: str) -> pd.DataFrame | None:
    """Tabela do banco, ou None se ainda nao existe (primeira rodada)."""
    try:
        return pd.read_sql(f"SELECT * FROM {nome}", conn)
    except Exception:
        return None


def acumular(antiga: pd.DataFrame | None, nova: pd.DataFrame) -> pd.DataFrame:
    """Junta a tabela antiga com a nova; a linha nova substitui a mesma source_id."""
    if antiga is None or antiga.empty:
        return nova
    return pd.concat([antiga[~antiga["source_id"].isin(nova["source_id"])], nova],
                     ignore_index=True)


def _gravar(df_result: pd.DataFrame) -> pd.DataFrame:
    df_result = _cruzar_catalogos(df_result)
    conhecidos = df_result[df_result["status"] == "conhecido"]
    candidatos = df_result[df_result["status"] == "candidato"]

    print(f"\nConhecidos (descartados): {len(conhecidos)} "
          f"({conhecidos['catalogo_match'].notna().sum()} so nas listas de anas)")
    print(f"Candidatos (seguem): {len(candidatos)}")

    conn = sqlite3.connect(str(SQLITE_PATH))
    salvos = acumular(ler_tabela(conn, "candidatos_fase4"), df_result)
    salvos.to_sql("candidatos_fase4", conn, if_exists="replace", index=False)
    conn.close()
    print(f"Salvo em {SQLITE_PATH} (tabela: candidatos_fase4: {len(df_result)} deste "
          f"campo, {len(salvos)} no total)")

    return df_result


def _fallback_sequential(df):
    import time
    from astroquery.simbad import Simbad
    from astropy.coordinates import SkyCoord

    conn = sqlite3.connect(str(SQLITE_PATH))

    def query_one(ra, dec):
        coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")
        for attempt in range(3):
            try:
                r = com_prazo(lambda: Simbad.query_region(coord, radius=SIMBAD_RADIUS_ARCSEC * u.arcsec),
                              REDE_PRAZO_S)
                if r and len(r) > 0:
                    return str(r[0]["main_id"])
                return None
            except Exception as e:
                if attempt < 2:
                    time.sleep(2)
                else:
                    print(f"  Erro ({ra:.4f}, {dec:.4f}): {e}")
                    return None

    ra2000, dec2000 = posicao_j2000(df)
    match_ids = []
    for i, row in df.iterrows():
        if i > 0 and i % 50 == 0:
            print(f"  {i}/{len(df)}...")
            sys.stdout.flush()
        mid = query_one(ra2000[i], dec2000[i])
        if mid:
            match_ids.append((i, mid))
        time.sleep(SIMBAD_DELAY_S)

    df_result = df.copy()
    df_result["simbad_match_id"] = None
    df_result["status"] = "candidato"
    for idx, mid in match_ids:
        df_result.at[idx, "simbad_match_id"] = mid
        df_result.at[idx, "status"] = "conhecido"

    conn.close()
    return _gravar(df_result)


if __name__ == "__main__":
    run()
