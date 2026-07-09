import sqlite3
import pandas as pd

from config import SQLITE_PATH, W1SNR_MIN, W2SNR_MIN, N_AW_MAX
from src.proper_motion import add_pm_columns


def run():
    print("=" * 50)
    print("Fase 3 — Filtragem de qualidade")
    print("=" * 50)

    conn = sqlite3.connect(str(SQLITE_PATH))
    df = pd.read_sql("SELECT * FROM campo_bruto", conn)

    print(f"Antes do filtro: {len(df)} fontes")

    df = add_pm_columns(df)

    filtros = []

    f1 = df["w1flg"] < 8
    filtros.append(("w1flg < 8 (exclui corrompido/saturado/limite)", f1.sum()))

    f2 = df["w2flg"] < 8
    filtros.append(("w2flg < 8 (exclui corrompido/saturado/limite)", f2.sum()))

    f3 = df["w1snr"] >= W1SNR_MIN
    filtros.append((f"w1snr >= {W1SNR_MIN}", f3.sum()))

    f4 = df["w2snr"] >= W2SNR_MIN
    filtros.append((f"w2snr >= {W2SNR_MIN}", f4.sum()))

    f5 = df["n_aw"] <= N_AW_MAX
    filtros.append((f"n_aw <= {N_AW_MAX}", f5.sum()))

    cc_clean = df["cc_flags"].isin(["", "0000"])
    filtros.append(("cc_flags vazio/0000 (sem contaminacao)", cc_clean.sum()))

    ab_clean = df["ab_flags"] == "00"
    filtros.append(("ab_flags == '00' (sem artefato)", ab_clean.sum()))

    pmcode_good = df["pmcode"].str[0].astype(int) >= 2
    filtros.append(("pmcode com qualidade >= 2 (bom/excelente)", pmcode_good.sum()))

    mask = f1 & f2 & f3 & f4 & f5 & cc_clean & ab_clean & pmcode_good
    filtrado = df[mask].copy()

    print("\nFiltros aplicados:")
    for desc, passed in filtros:
        print(f"  {desc}: {passed}/{len(df)}")

    print(f"\nDepois do filtro: {len(filtrado)} fontes")

    filtrado.to_sql("candidatos_fase3", conn, if_exists="replace", index=False)
    conn.close()
    print(f"Salvo em {SQLITE_PATH} (tabela: candidatos_fase3)")

    return filtrado


if __name__ == "__main__":
    run()
