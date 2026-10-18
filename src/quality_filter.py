import sqlite3
import pandas as pd

from config import SQLITE_PATH, N_AW_MAX, PM_SIGNIF_MIN
from src.proper_motion import add_pm_columns


def pmcode_sem_troca(pmcode: pd.Series) -> pd.Series:
    # pmcode = ABCCC (spec de colunas CatWISE2020): A = n de componentes no grupo
    # de blend passivo, B = 'Y' se um secundario substituiu o primario, CCC =
    # distancia entre as solucoes com e sem movimento. Filtrar A == 1 foi testado
    # contra 949 anas L/T/Y conhecidas e derrubava o recall de 75% pra 25%: A
    # reflete a vizinhanca (blend com fonte proxima), nao a qualidade, e tem a
    # mesma distribuicao em anas reais e no campo. Mantem so o corte de B (troca
    # de primario), que nao custa recall.
    s = pmcode.fillna("").astype(str)
    return s.str[1] == "N"


def run():
    print("=" * 50)
    print("Fase 3 — Filtragem de qualidade")
    print("=" * 50)

    conn = sqlite3.connect(str(SQLITE_PATH))
    df = pd.read_sql("SELECT * FROM campo_bruto", conn)

    print(f"Antes do filtro: {len(df)} fontes")

    df = add_pm_columns(df)

    filtros = []

    # w1flg/w2flg/SNR ja sao cortados no servidor na Fase 2
    f5 = df["n_aw"] <= N_AW_MAX
    filtros.append((f"n_aw <= {N_AW_MAX}", f5.sum()))

    cc_clean = df["cc_flags"].isin(["", "0000"])
    filtros.append(("cc_flags vazio/0000 (sem contaminacao)", cc_clean.sum()))

    ab_clean = df["ab_flags"] == "00"
    filtros.append(("ab_flags == '00' (sem artefato)", ab_clean.sum()))

    pmcode_good = pmcode_sem_troca(df["pmcode"])
    filtros.append(("pmcode B=N (primario nao foi trocado)", pmcode_good.sum()))

    pm_signif = df["pm_signif"] >= PM_SIGNIF_MIN
    filtros.append((f"pm_total/sigma >= {PM_SIGNIF_MIN}", pm_signif.sum()))

    mask = f5 & cc_clean & ab_clean & pmcode_good & pm_signif
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
