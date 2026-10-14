import sqlite3
import sys
import pandas as pd
from astropy.table import Table
from astroquery.xmatch import XMatch
import astropy.units as u

from config import SQLITE_PATH, SIMBAD_RADIUS_ARCSEC, SIMBAD_DELAY_S


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
    t["ra"] = df["ra"].values
    t["dec"] = df["dec"].values

    print("Enviando batch p/ CDS XMatch (SIMBAD)...")
    try:
        result = XMatch.query(
            cat1=t,
            cat2="simbad",
            max_distance=SIMBAD_RADIUS_ARCSEC * u.arcsec,
            colRA1="ra",
            colDec1="dec",
        )
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

    conhecidos = df_result[df_result["status"] == "conhecido"]
    candidatos = df_result[df_result["status"] == "candidato"]

    print(f"\nConhecidos (descartados): {len(conhecidos)}")
    print(f"Candidatos (seguem): {len(candidatos)}")

    conn = sqlite3.connect(str(SQLITE_PATH))
    df_result.to_sql("candidatos_fase4", conn, if_exists="replace", index=False)
    conn.close()
    print(f"Salvo em {SQLITE_PATH} (tabela: candidatos_fase4)")

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
                r = Simbad.query_region(coord, radius=SIMBAD_RADIUS_ARCSEC * u.arcsec)
                if r and len(r) > 0:
                    return str(r[0]["main_id"])
                return None
            except Exception as e:
                if attempt < 2:
                    time.sleep(2)
                else:
                    print(f"  Erro ({ra:.4f}, {dec:.4f}): {e}")
                    return None

    match_ids = []
    for i, row in df.iterrows():
        if i > 0 and i % 50 == 0:
            print(f"  {i}/{len(df)}...")
            sys.stdout.flush()
        mid = query_one(row["ra"], row["dec"])
        if mid:
            match_ids.append((i, mid))
        time.sleep(SIMBAD_DELAY_S)

    df_result = df.copy()
    df_result["simbad_match_id"] = None
    df_result["status"] = "candidato"
    for idx, mid in match_ids:
        df_result.at[idx, "simbad_match_id"] = mid
        df_result.at[idx, "status"] = "conhecido"

    df_result.to_sql("candidatos_fase4", conn, if_exists="replace", index=False)
    conn.close()
    return df_result


if __name__ == "__main__":
    run()
