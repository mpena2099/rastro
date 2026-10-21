"""Proximo campo do ceu a varrer: blocos de 5x5 graus em RA/Dec.

O bloco inicial e o FIELD_RA_RANGE/FIELD_DEC_RANGE do config; os demais ficam
alinhados a ele (passo de 5 graus, Dec de -85 a +85) e sao ordenados pela
distancia angular ao centro do inicial. `proximo` pula o que ja esta em
campos_feitos e os blocos perto do plano galactico, onde a confusao de fontes
e grande demais.

    python -u pipeline.py --proximo
"""

import sqlite3
from datetime import datetime

import numpy as np
from astropy.coordinates import SkyCoord

from config import FIELD_DEC_RANGE, FIELD_RA_RANGE

PASSO_GRAU = 5.0
DEC_MIN, DEC_MAX = -85.0, 85.0
B_GALACTICO_MIN = 20.0

_SCHEMA = """
CREATE TABLE IF NOT EXISTS campos_feitos (
    nome TEXT PRIMARY KEY,
    ra_min REAL NOT NULL,
    ra_max REAL NOT NULL,
    dec_min REAL NOT NULL,
    dec_max REAL NOT NULL,
    candidatos INTEGER,
    feito_em TEXT NOT NULL
)"""


def _nome(ra_min: float, ra_max: float, dec_min: float, dec_max: float) -> str:
    return f"ra{ra_min:.0f}-{ra_max:.0f}_dec{dec_min:+.0f}{dec_max:+.0f}"


def _blocos_ra():
    # ancorado no inicio do campo inicial; o bloco que cruzaria RA=0 fica de
    # fora porque a consulta usa BETWEEN e nao atravessa 360 graus
    inicio = FIELD_RA_RANGE[0]
    for k in range(int(round(360 / PASSO_GRAU))):
        ra_min = (inicio + k * PASSO_GRAU) % 360.0
        if ra_min + PASSO_GRAU > 360.0:
            continue
        yield ra_min, ra_min + PASSO_GRAU


def _blocos_dec():
    dec = FIELD_DEC_RANGE[0]
    while dec > DEC_MIN:
        dec -= PASSO_GRAU
    while dec < DEC_MAX:
        yield max(dec, DEC_MIN), min(dec + PASSO_GRAU, DEC_MAX)
        dec += PASSO_GRAU


def grade() -> list[dict]:
    """Blocos 5x5 alinhados ao inicial, do mais perto ao mais longe do centro dele."""
    blocos = [
        {"nome": _nome(ra_min, ra_max, dec_min, dec_max),
         "ra_min": round(ra_min, 6), "ra_max": round(ra_max, 6),
         "dec_min": round(dec_min, 6), "dec_max": round(dec_max, 6)}
        for ra_min, ra_max in _blocos_ra()
        for dec_min, dec_max in _blocos_dec()
    ]
    centros = SkyCoord(
        [(b["ra_min"] + b["ra_max"]) / 2 for b in blocos],
        [(b["dec_min"] + b["dec_max"]) / 2 for b in blocos], unit="deg")
    inicial = SkyCoord((FIELD_RA_RANGE[0] + FIELD_RA_RANGE[1]) / 2,
                       (FIELD_DEC_RANGE[0] + FIELD_DEC_RANGE[1]) / 2, unit="deg")
    ordem = np.argsort(centros.separation(inicial).deg, kind="stable")
    return [blocos[i] for i in ordem]


def latitude_galactica(campo: dict) -> float:
    c = SkyCoord((campo["ra_min"] + campo["ra_max"]) / 2,
                 (campo["dec_min"] + campo["dec_max"]) / 2, unit="deg")
    return abs(c.galactic.b.deg)


def proximo(feitos: list[dict]) -> dict | None:
    """Primeiro bloco nao feito e com |b| >= B_GALACTICO_MIN; None se a grade acabou."""
    usados = {f["nome"] for f in feitos}
    for campo in grade():
        if campo["nome"] in usados or latitude_galactica(campo) < B_GALACTICO_MIN:
            continue
        return campo
    return None


def ler_feitos(con: sqlite3.Connection) -> list[dict]:
    con.execute(_SCHEMA)
    cur = con.execute("SELECT nome, ra_min, ra_max, dec_min, dec_max, candidatos "
                      "FROM campos_feitos")
    colunas = ("nome", "ra_min", "ra_max", "dec_min", "dec_max", "candidatos")
    return [dict(zip(colunas, linha)) for linha in cur]


def registrar(con: sqlite3.Connection, campo: dict, candidatos: int | None) -> None:
    con.execute(_SCHEMA)
    con.execute("INSERT OR REPLACE INTO campos_feitos VALUES (?, ?, ?, ?, ?, ?, ?)",
                (campo["nome"], float(campo["ra_min"]), float(campo["ra_max"]),
                 float(campo["dec_min"]), float(campo["dec_max"]), candidatos,
                 datetime.now().isoformat(timespec="seconds")))
    con.commit()
