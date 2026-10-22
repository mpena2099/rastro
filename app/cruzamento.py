"""Gaia, Pan-STARRS e AllWISE de cada objeto, cruzados uma vez e guardados no banco.

Usado pela fila e pelo treino: sem isso o checklist do treino marcava atencao em tudo e a
sugestao saia sempre Duvida.
"""

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import streamlit as st

from app import dados
from config import SQLITE_PATH


ETAPAS = (("Gaia DR3 e Pan-STARRS", dados.cruzar_gaia_ps1, "~10 s", "gaia_detectada"),
          ("AllWISE (teste de movimento)", dados.cruzar_allwise, "~1 min", "allwise_status"))


def _com_relogio(fn, faltam: pd.DataFrame, nome: str, tempo: str) -> pd.DataFrame:
    """fn(faltam) com um relogio na tela: sem ele, uma consulta lenta parece travada."""
    marcador = st.empty()
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        futuro = pool.submit(fn, faltam)
        inicio = time.time()
        while not futuro.done():
            seg = int(time.time() - inicio)
            marcador.write(f"⏳ {nome}: consultando o servidor há {seg // 60} min {seg % 60:02d} s "
                           f"(costuma levar {tempo}). Pode deixar a aba em segundo plano, "
                           "mas não recarregue a página.")
            time.sleep(1)
        marcador.empty()
        return futuro.result()
    finally:
        # sem esperar: se a pagina for recarregada no meio, a consulta lenta nao segura a nova
        pool.shutdown(wait=False)


def cruzar_e_guardar(df: pd.DataFrame, oque: str, item: str) -> tuple[pd.DataFrame, list[str]]:
    """Cruzamentos guardados no banco; cada etapa cruza so quem ainda nao a tem.

    Leva ~1 min por centena. Etapa que falha nao e gravada e volta na proxima abertura;
    a outra etapa e gravada mesmo assim.
    """
    with sqlite3.connect(str(SQLITE_PATH)) as conn:
        salvos = dados.ler_cruzamentos(conn)
    por_id = salvos.set_index("source_id")

    def sem(coluna: str) -> pd.DataFrame:
        if coluna not in por_id:
            return df
        return df[df["source_id"].map(por_id[coluna]).isna()]

    # etapa que falhou nesta sessao nao e tentada de novo a cada clique: esperaria o servidor
    # fora do ar toda vez; volta na proxima sessao
    falhas = st.session_state.setdefault("etapas_falhas", set())
    pendentes = [(e, sem(e[3])) for e in ETAPAS]
    pendentes = [(e, f) for e, f in pendentes if not f.empty]
    erros = [f"{e[0]}: falhou nesta sessão, tento de novo na próxima" for e, _ in pendentes
             if e[0] in falhas]
    pendentes = [(e, f) for e, f in pendentes if e[0] not in falhas]
    if not pendentes:
        return salvos, erros
    novos = []
    total = max(len(f) for _, f in pendentes)
    with st.status(f"Preparando {oque}: cruzando {total} {item}(s) novo(s), só desta vez",
                   expanded=True) as status:
        for (nome, fn, tempo, _), faltam in pendentes:
            if fn is dados.cruzar_gaia_ps1 and not dados.cds_no_ar():
                erros.append(f"{nome}: servidor do CDS (XMatch) fora do ar")
                falhas.add(nome)
                st.write("Servidor do CDS fora do ar: pulo Gaia e Pan-STARRS.")
                continue
            try:
                novos.append(_com_relogio(fn, faltam, nome, tempo))
                st.write(f"✓ {nome}")
            except Exception as e:
                erros.append(f"{nome}: {e}")
                falhas.add(nome)
                st.write(f"✗ {nome}: não respondeu ({e})")
        if novos:
            with sqlite3.connect(str(SQLITE_PATH)) as conn:
                for n in novos:
                    dados.salvar_cruzamentos(conn, n)
                salvos = dados.ler_cruzamentos(conn)
        if erros:
            status.update(label="Cruzamento incompleto: a etapa que falhou volta na próxima abertura",
                          state="error", expanded=False)
        else:
            status.update(label=f"Pronto: {total} {item}(s) cruzado(s) e guardado(s)",
                          state="complete", expanded=False)
    return salvos, erros


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
