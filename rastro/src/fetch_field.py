from astroquery.ipac.irsa import Irsa

from config import (
    CATWISE_TABLE,
    CATWISE_COLUMNS,
    FIELD_RA_MIN,
    FIELD_RA_MAX,
    FIELD_DEC_MIN,
    FIELD_DEC_MAX,
    PM_THRESHOLD_ARCSEC,
    ROW_LIMIT,
    SQLITE_PATH,
)


def build_query() -> str:
    cols = ",\n       ".join(CATWISE_COLUMNS)
    return f"""
SELECT TOP {ROW_LIMIT}
       {cols}
FROM {CATWISE_TABLE}
WHERE ra BETWEEN {FIELD_RA_MIN} AND {FIELD_RA_MAX}
  AND dec BETWEEN {FIELD_DEC_MIN} AND {FIELD_DEC_MAX}
  AND ka = 3 AND km = 3
  AND SQRT(POWER(pmra,2) + POWER(pmdec,2)) > {PM_THRESHOLD_ARCSEC}
"""


def run():
    print("=" * 50)
    print("Fase 2 — Query CatWISE2020 via TAP")
    print("=" * 50)

    query = build_query()
    print(f"RA: [{FIELD_RA_MIN}, {FIELD_RA_MAX}]")
    print(f"Dec: [{FIELD_DEC_MIN}, {FIELD_DEC_MAX}]")
    print(f"PM threshold: {PM_THRESHOLD_ARCSEC} arcsec/ano")
    print(f"Row limit: {ROW_LIMIT}")

    result = Irsa.query_tap(query)

    if result is None or len(result) == 0:
        print("Nenhuma fonte encontrada. Tente relaxar filtros.")
        return

    df = result.to_table().to_pandas()
    print(f"Fontes retornadas: {len(df)}")

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)

    import sqlite3

    conn = sqlite3.connect(str(SQLITE_PATH))
    df.to_sql("campo_bruto", conn, if_exists="replace", index=False)
    conn.close()

    print(f"Salvo em: {SQLITE_PATH} (tabela: campo_bruto)")
    return df


if __name__ == "__main__":
    run()
