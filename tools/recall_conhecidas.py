"""Mede o recall dos cortes do pipeline contra anas L/T/Y ja conhecidas.

Pega do SIMBAD as anas L/T/Y com PM > PM_THRESHOLD_ARCSEC, acha a contraparte de
cada uma no CatWISE2020 (posicao propagada pra epoca CatWISE) e conta quantas
sobrevivem aos cortes das Fases 2 e 3, um a um e acumulados. Usa rede (SIMBAD e
IRSA) e leva ~8 min; o resultado da busca fica em data/recall_conhecidas.pkl.

    python tools/recall_conhecidas.py            # usa o cache se existir
    python tools/recall_conhecidas.py --refetch  # refaz a busca

Limite: as conhecidas sao as mais brilhantes e faceis de achar; o recall pra
anas ainda nao descobertas tende a ser menor.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import pyvo
from astropy.table import Table

import config as C
from src.proper_motion import add_pm_columns
from src.quality_filter import pmcode_sem_troca

CACHE = C.ROOT / "data" / "recall_conhecidas.pkl"
EPOCA_CATWISE_MJD = 57170.0
MJD_J2000 = 51544.5
LOTE = 100


def buscar() -> pd.DataFrame:
    simbad = pyvo.dal.TAPService("https://simbad.cds.unistra.fr/simbad/sim-tap")
    pm_min_mas = C.PM_THRESHOLD_ARCSEC * 1000
    ref = simbad.search(f"""SELECT main_id, ra, dec, pmra, pmdec, sp_type FROM basic
WHERE (sp_type LIKE 'L%' OR sp_type LIKE 'T%' OR sp_type LIKE 'Y%')
  AND pmra IS NOT NULL AND pmdec IS NOT NULL AND ra IS NOT NULL
  AND SQRT(pmra*pmra + pmdec*pmdec) > {pm_min_mas} AND sp_type NOT LIKE 'L%V%'""",
                        maxrec=5000).to_table().to_pandas()
    ref["tipo"] = ref["sp_type"].str.strip().str[0]
    ref = ref[ref["tipo"].isin(list("LTY"))].reset_index(drop=True)
    print(f"SIMBAD L/T/Y com PM > {C.PM_THRESHOLD_ARCSEC}: {len(ref)}")

    # Posicao J2000 do SIMBAD -> epoca CatWISE (pmra do SIMBAD ja inclui cos dec).
    dt = (EPOCA_CATWISE_MJD - MJD_J2000) / 365.25
    ref["ra15"] = (ref["ra"] + ref["pmra"] * dt / 3.6e6 / np.cos(np.radians(ref["dec"]))) % 360
    ref["dec15"] = ref["dec"] + ref["pmdec"] * dt / 3.6e6
    ref["rid"] = np.arange(len(ref))

    # O IRSA nao aceita DISTANCE() no ADQL com upload: a separacao e calculada aqui.
    cols = ",\n".join(f"c.{x}" for x in C.CATWISE_COLUMNS)
    adql = f"""SELECT TAP_UPLOAD.t.rid AS rid, {cols}
FROM {C.CATWISE_TABLE} AS c, TAP_UPLOAD.t
WHERE 1=CONTAINS(POINT('ICRS',c.ra,c.dec), CIRCLE('ICRS',TAP_UPLOAD.t.ra15,TAP_UPLOAD.t.dec15,4.0/3600.0))"""
    irsa = pyvo.dal.TAPService("https://irsa.ipac.caltech.edu/TAP")
    partes = []
    for i in range(0, len(ref), LOTE):
        up = Table.from_pandas(ref[["rid", "ra15", "dec15"]].iloc[i:i + LOTE])
        for tent in range(4):
            try:
                job = irsa.submit_job(adql, uploads={"t": up})
                job.run()
                job.wait(phases=["COMPLETED", "ERROR", "ABORTED"], timeout=300)
                job.raise_if_error()
                partes.append(job.fetch_result().to_table().to_pandas())
                print(f"  lote {i}-{i + LOTE} ok", flush=True)
                break
            except Exception as e:
                print(f"  lote {i} tentativa {tent + 1}: {str(e)[:80]}", flush=True)
                time.sleep(10)
        else:
            raise RuntimeError(f"lote {i} falhou 4 vezes; rode de novo")
    res = pd.concat(partes, ignore_index=True).merge(ref[["rid", "ra15", "dec15"]], on="rid")
    res["sep"] = np.hypot((res["ra"] - res["ra15"]) * np.cos(np.radians(res["dec"])),
                          res["dec"] - res["dec15"]) * 3600
    res = res.sort_values("sep").drop_duplicates("rid").drop(columns=["ra15", "dec15"])
    out = ref.merge(res, on="rid", how="left", suffixes=("_simbad", ""))
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    out.to_pickle(CACHE)
    return out


def main():
    d = buscar() if ("--refetch" in sys.argv or not CACHE.exists()) else pd.read_pickle(CACHE)
    d = add_pm_columns(d[d["source_id"].notna()].copy())
    tipos = list("LTY")
    n = {t: int((d["tipo"] == t).sum()) for t in tipos}
    print(f"\nCom contraparte no CatWISE: {n} (total {sum(n.values())})\n")

    cortes = [
        ("ka=km=3", (d.ka == 3) & (d.km == 3)),
        (f"pm > {C.PM_THRESHOLD_ARCSEC}", d.pm_total > C.PM_THRESHOLD_ARCSEC),
        (f"w2snr >= {C.W2SNR_MIN}", d.w2snr >= C.W2SNR_MIN),
        ("w2flg < 8", d.w2flg < 8),
        (f"n_aw <= {C.N_AW_MAX}", d.n_aw <= C.N_AW_MAX),
        ("cc_flags limpo", d.cc_flags.isin(["", "0000"])),
        ("ab_flags 00", d.ab_flags == "00"),
        ("pmcode B=N", pmcode_sem_troca(d.pmcode)),
        (f"pm/sigma >= {C.PM_SIGNIF_MIN}", d.pm_signif >= C.PM_SIGNIF_MIN),
    ]
    m = pd.Series(True, index=d.index)
    print(f"{'corte':20} recall acumulado L / T / Y / total | so este corte L / T / Y")
    for nome, c in cortes:
        m &= c
        acc = [100 * (m & (d.tipo == t)).sum() / n[t] for t in tipos]
        so = [100 * (c & (d.tipo == t)).sum() / n[t] for t in tipos]
        print(f"{nome:20} {acc[0]:4.0f} {acc[1]:4.0f} {acc[2]:4.0f} {100 * m.sum() / len(d):5.1f}% | "
              f"{so[0]:4.0f} {so[1]:4.0f} {so[2]:4.0f}")


if __name__ == "__main__":
    main()
