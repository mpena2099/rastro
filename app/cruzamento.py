"""Gaia, Pan-STARRS e AllWISE de cada objeto, cruzados uma vez e guardados no banco.

Usado pela fila e pelo treino: sem isso o checklist do treino marcava atencao em tudo e a
sugestao saia sempre Duvida.
"""

import sqlite3

import pandas as pd
import streamlit as st

from app import dados
from config import SQLITE_PATH


def cruzar_e_guardar(df: pd.DataFrame, oque: str, item: str) -> tuple[pd.DataFrame, list[str]]:
    """Cruzamentos guardados no banco; so os candidatos novos vao ao Gaia/PS1/AllWISE.

    Leva ~1 min por centena. Cruzamento que falha nao e gravado e volta na proxima abertura.
    """
    with sqlite3.connect(str(SQLITE_PATH)) as conn:
        salvos = dados.ler_cruzamentos(conn)
    faltam = df[~df["source_id"].isin(salvos["source_id"])]
    if faltam.empty:
        return salvos, []
    novos, erros = faltam[["source_id"]].copy(), []
    with st.status(f"Preparando {oque}: cruzando {len(faltam)} {item}(s) novo(s), só desta vez",
                   expanded=True) as status:
        for nome, fn, tempo in (("Gaia DR3 e Pan-STARRS", dados.cruzar_gaia_ps1, "~10 s"),
                                ("AllWISE (teste de movimento)", dados.cruzar_allwise, "~1 min")):
            st.write(f"{nome} ({tempo})")
            try:
                novos = novos.merge(fn(faltam), on="source_id", how="left")
            except Exception as e:
                erros.append(f"{nome}: {e}")
        if erros:
            status.update(label="Cruzamento incompleto: tento de novo na próxima abertura",
                          state="error", expanded=False)
            return pd.concat([salvos, novos], ignore_index=True), erros
        with sqlite3.connect(str(SQLITE_PATH)) as conn:
            dados.salvar_cruzamentos(conn, novos)
        status.update(label=f"Pronto: {len(faltam)} {item}(s) cruzado(s) e guardado(s)",
                      state="complete", expanded=False)
    return pd.concat([salvos, novos], ignore_index=True), []


def completar(df: pd.DataFrame, oque: str, item: str) -> tuple[pd.DataFrame, list[str]]:
    """df com as colunas dos cruzamentos (cruza so quem ainda nao esta no banco)."""
    cruz, erros = cruzar_e_guardar(df[["source_id", "ra", "dec", "pmra", "pmdec", "meanobsmjd"]],
                                   oque, item)
    df = df.merge(cruz, on="source_id", how="left")
    for coluna, padrao in (("gaia_detectada", pd.NA), ("ps1_detectada", pd.NA), ("gaia_g", pd.NA),
                           ("allwise_status", "sem dados")):
        if coluna not in df:
            df[coluna] = padrao
    df["allwise_status"] = df["allwise_status"].fillna("sem dados")
    return df, erros
