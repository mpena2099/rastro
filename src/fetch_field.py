from astroquery.ipac.irsa import Irsa

from config import (
    CATWISE_TABLE,
    CATWISE_COLUMNS,
    FIELD_RA_MIN,
    FIELD_RA_MAX,
    FIELD_DEC_MIN,
    FIELD_DEC_MAX,
    PM_THRESHOLD_ARCSEC,
    W1SNR_MIN,
    W2SNR_MIN,
    ROW_LIMIT,
    SQLITE_PATH,
)


def build_query() -> str:
    cols = ",\n       ".join(CATWISE_COLUMNS)
    # Cortes de qualidade grosseiros (SNR + flags) ficam no servidor pra o campo
    # inteiro caber sob o TOP e nao truncar (spec 10.1). A Fase 3 faz os cortes
    # finos (cc_flags/ab_flags/pmcode/n_aw) que exigem logica no cliente.
    return f"""
SELECT TOP {ROW_LIMIT}
       {cols}
FROM {CATWISE_TABLE}
WHERE ra BETWEEN {FIELD_RA_MIN} AND {FIELD_RA_MAX}
  AND dec BETWEEN {FIELD_DEC_MIN} AND {FIELD_DEC_MAX}
  AND ka = 3 AND km = 3
  AND SQRT(POWER(pmra,2) + POWER(pmdec,2)) > {PM_THRESHOLD_ARCSEC}
  AND w1snr >= {W1SNR_MIN} AND w2snr >= {W2SNR_MIN}
  AND w1flg < 8 AND w2flg < 8
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

    # Guarda contra truncagem silenciosa: se veio exatamente ROW_LIMIT, o TOP
    # provavelmente cortou o resultado (o campo tem mais fontes que o teto) e a
    # cobertura fica espacialmente incompleta. Para e avisa em vez de seguir com
    # meio campo (armadilha da spec 10.4).
    if len(df) >= ROW_LIMIT:
        raise RuntimeError(
            f"Fase 2 retornou {len(df)} = ROW_LIMIT ({ROW_LIMIT}): resultado "
            "provavelmente TRUNCADO (campo incompleto). Suba ROW_LIMIT, encolha "
            "o campo, ou aperte os filtros (PM/SNR) em config.py."
        )

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)

    import sqlite3

    conn = sqlite3.connect(str(SQLITE_PATH))
    df.to_sql("campo_bruto", conn, if_exists="replace", index=False)
    conn.close()

    print(f"Salvo em: {SQLITE_PATH} (tabela: campo_bruto)")
    return df


if __name__ == "__main__":
    run()
