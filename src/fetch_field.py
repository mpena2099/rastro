import sqlite3
import time

import pandas as pd
from astroquery.ipac.irsa import Irsa

from config import (
    CATWISE_TABLE,
    CATWISE_COLUMNS,
    FIELD_RA_RANGE,
    FIELD_DEC_RANGE,
    FIELD_STEP_DEG,
    PM_THRESHOLD_ARCSEC,
    W2SNR_MIN,
    REDE_PRAZO_S,
    ROW_LIMIT,
    SQLITE_PATH,
)
from src.util import com_prazo

MAX_SPLIT_DEPTH = 4
QUERY_RETRIES = 3
QUERY_RETRY_DELAY_S = 10.0


def build_query(ra_min: float, ra_max: float, dec_min: float, dec_max: float) -> str:
    cols = ",\n       ".join(CATWISE_COLUMNS)
    # Cortes de qualidade grosseiros (SNR + flag de W2) ficam no servidor pra o
    # campo inteiro caber sob o TOP e nao truncar (spec 10.1). Sem corte em W1:
    # anas Y sao fracas em W1 (metade tem w1snr < 5) e cortar la derrubava o
    # recall delas de 85% pra 42% sem reduzir os candidatos do campo. A Fase 3
    # faz os cortes finos (cc_flags/ab_flags/pmcode/n_aw).
    return f"""
SELECT TOP {ROW_LIMIT}
       {cols}
FROM {CATWISE_TABLE}
WHERE ra BETWEEN {ra_min} AND {ra_max}
  AND dec BETWEEN {dec_min} AND {dec_max}
  AND ka = 3 AND km = 3
  AND SQRT(POWER(pmra,2) + POWER(pmdec,2)) > {PM_THRESHOLD_ARCSEC}
  AND w2snr >= {W2SNR_MIN} AND w2flg < 8
"""


def make_tiles(ra_range=None, dec_range=None) -> list[tuple[float, float, float, float]]:
    """Ladrilhos (ra_min, ra_max, dec_min, dec_max) que cobrem a regiao pedida."""
    ra_range = ra_range or FIELD_RA_RANGE
    dec_range = dec_range or FIELD_DEC_RANGE
    tiles = []
    ra = ra_range[0]
    while ra < ra_range[1] - 1e-9:
        dec = dec_range[0]
        while dec < dec_range[1] - 1e-9:
            tiles.append((
                round(ra, 6), round(min(ra + FIELD_STEP_DEG, ra_range[1]), 6),
                round(dec, 6), round(min(dec + FIELD_STEP_DEG, dec_range[1]), 6),
            ))
            dec += FIELD_STEP_DEG
        ra += FIELD_STEP_DEG
    return tiles


def _query_retry(query: str) -> pd.DataFrame:
    for attempt in range(QUERY_RETRIES):
        try:
            return com_prazo(lambda: Irsa.query_tap(query).to_table().to_pandas(), REDE_PRAZO_S)
        except Exception as e:
            if attempt < QUERY_RETRIES - 1:
                print(f"    IRSA retry {attempt+1}/{QUERY_RETRIES}: {e}")
                time.sleep(QUERY_RETRY_DELAY_S)
            else:
                raise


def fetch_tile(ra_min, ra_max, dec_min, dec_max, depth: int = 0) -> pd.DataFrame:
    df = _query_retry(build_query(ra_min, ra_max, dec_min, dec_max))
    if len(df) < ROW_LIMIT:
        return df

    # Guarda contra truncagem silenciosa (armadilha da spec 10.4): veio exatamente
    # ROW_LIMIT, entao o TOP provavelmente cortou. Divide em 4 e refaz.
    if depth >= MAX_SPLIT_DEPTH:
        raise RuntimeError(
            f"Ladrilho [{ra_min}, {ra_max}] x [{dec_min}, {dec_max}] ainda bate "
            f"ROW_LIMIT ({ROW_LIMIT}) apos {MAX_SPLIT_DEPTH} divisoes. Suba "
            "ROW_LIMIT ou aperte os filtros (PM/SNR) em config.py."
        )
    print(f"    {len(df)} = ROW_LIMIT: ladrilho truncado, dividindo em 4")
    ra_mid, dec_mid = (ra_min + ra_max) / 2, (dec_min + dec_max) / 2
    partes = [
        fetch_tile(a, b, c, d, depth + 1)
        for a, b in ((ra_min, ra_mid), (ra_mid, ra_max))
        for c, d in ((dec_min, dec_mid), (dec_mid, dec_max))
    ]
    return pd.concat(partes, ignore_index=True)


def run(campo=None):
    print("=" * 50)
    print("Fase 2 — Query CatWISE2020 via TAP")
    print("=" * 50)

    ra_range = (campo["ra_min"], campo["ra_max"]) if campo else FIELD_RA_RANGE
    dec_range = (campo["dec_min"], campo["dec_max"]) if campo else FIELD_DEC_RANGE
    tiles = make_tiles(ra_range, dec_range)
    if campo:
        print(f"Campo: {campo['nome']}")
    print(f"RA: {ra_range}  Dec: {dec_range}  ladrilho: {FIELD_STEP_DEG} grau")
    print(f"Ladrilhos: {len(tiles)}")
    print(f"PM threshold: {PM_THRESHOLD_ARCSEC} arcsec/ano")
    print(f"Row limit por consulta: {ROW_LIMIT}")

    partes = []
    for i, (ra_min, ra_max, dec_min, dec_max) in enumerate(tiles, 1):
        print(f"\n  [{i}/{len(tiles)}] RA [{ra_min}, {ra_max}] Dec [{dec_min}, {dec_max}]")
        df = fetch_tile(ra_min, ra_max, dec_min, dec_max)
        print(f"    fontes: {len(df)}")
        partes.append(df)

    df = pd.concat(partes, ignore_index=True)
    # Fontes exatamente na borda entre ladrilhos (BETWEEN e inclusivo) aparecem 2x.
    df = df.drop_duplicates(subset="source_id").reset_index(drop=True)
    print(f"\nFontes retornadas: {len(df)}")

    if len(df) == 0:
        print("Nenhuma fonte encontrada. Tente relaxar filtros.")
        return

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SQLITE_PATH))
    df.to_sql("campo_bruto", conn, if_exists="replace", index=False)
    conn.close()

    print(f"Salvo em: {SQLITE_PATH} (tabela: campo_bruto)")
    return df


if __name__ == "__main__":
    run()
