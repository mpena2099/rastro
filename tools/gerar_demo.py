"""Gera demo/treino_demo.db, o banco da demo online (app/demo.py).

Monta um conjunto grande de casos do treino (mesma regra do app) e guarda junto os
cruzamentos com Gaia, Pan-STARRS e AllWISE, para a demo nao consultar CDS nem IRSA. Usa rede
e o banco real (data/rastro.db). Rodar da raiz:

    python -u tools/gerar_demo.py
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from app import dados, guia
from config import SQLITE_PATH

DESTINO = ROOT / "demo" / "treino_demo.db"
N_POR_CLASSE = 40

with sqlite3.connect(str(SQLITE_PATH)) as conn:
    estrelas = pd.read_sql("SELECT * FROM candidatos_fase4 WHERE status = 'conhecido' "
                           "AND simbad_match_id IS NOT NULL", conn)
    bruto = pd.read_sql("SELECT * FROM campo_bruto", conn)
    fase3 = pd.read_sql("SELECT source_id FROM candidatos_fase3", conn)
    salvos = dados.ler_cruzamentos(conn)
estrelas = estrelas.merge(guia._tipos_simbad(estrelas["simbad_match_id"].tolist()),
                          on="simbad_match_id", how="left")
casos = dados.casos_treino(pd.read_pickle(ROOT / "data" / "recall_conhecidas.pkl"), estrelas,
                           bruto[~bruto["source_id"].isin(fase3["source_id"])],
                           n_por_classe=N_POR_CLASSE, semente=1)
print("casos:", casos["resposta"].value_counts().to_dict())

cruz = salvos[salvos["source_id"].isin(casos["source_id"])]
faltam = casos[~casos["source_id"].isin(cruz["source_id"])]
print(f"cruzamentos ja no banco: {len(cruz)}; faltam: {len(faltam)}")
if len(faltam):
    novos = faltam[["source_id"]].merge(dados.cruzar_gaia_ps1(faltam), on="source_id", how="left")
    novos = novos.merge(dados.cruzar_allwise(faltam), on="source_id", how="left")
    cruz = pd.concat([cruz, novos], ignore_index=True)

DESTINO.parent.mkdir(exist_ok=True)
DESTINO.unlink(missing_ok=True)
with sqlite3.connect(str(DESTINO)) as conn:
    casos.to_sql("casos_treino_demo", conn, index=False)
    cruz.to_sql("cruzamentos_app", conn, index=False)
print(f"gravado {DESTINO} ({DESTINO.stat().st_size // 1024} KB)")
