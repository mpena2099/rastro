"""Modo treino: casos com resposta, pra aprender a olhar as imagens."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from app import dados, estilo, imagens, guia
from config import ROOT, SQLITE_PATH

ROTULOS = {"confirmado": "Confirmado", "duvida": "Dúvida", "descartado": "Descartado"}


def responder(i: int, decisao: str):
    if i in st.session_state.respostas:
        return
    st.session_state.respostas[i] = decisao
    certa = st.session_state.casos.iloc[i]["resposta"]
    st.session_state.pontos += 1.0 if decisao == certa else (0.5 if decisao == "duvida" else 0.0)


def mover(delta: int):
    st.session_state.pos = max(0, min(len(st.session_state.casos) - 1,
                                      st.session_state.pos + delta))


def recomecar():
    st.session_state.pos, st.session_state.pontos, st.session_state.respostas = 0, 0.0, {}


if "casos" not in st.session_state:
    try:
        casos = guia.casos_de_treino()
        # mesmo numero de casos por resposta: senao responder sempre a classe maior pontua bem
        n = int(casos["resposta"].value_counts().min())
        st.session_state.casos = (casos.groupby("resposta", group_keys=False)
                                  .sample(n=n, random_state=42)
                                  .sample(frac=1, random_state=42).reset_index(drop=True))
    except Exception as e:
        st.error(f"Não consegui montar os casos (o banco precisa das fases 2 a 4): {e}")
        st.stop()
    st.session_state.pos, st.session_state.pontos, st.session_state.respostas = 0, 0.0, {}
if st.session_state.casos.empty:
    st.warning("Não há casos de treino.")
    st.stop()

pos = max(0, min(st.session_state.pos, len(st.session_state.casos) - 1))
c = st.session_state.casos.iloc[pos]
respondidos = len(st.session_state.respostas)

estilo.cabecalho("Treino", (st.session_state.pontos, respondidos),
                 "Acertos {atual} de {total}")
st.caption("O caso vem sem a resposta. Decida olhando as imagens e os números, como na revisão. "
           "Gaia, Pan-STARRS e AllWISE não entram aqui: o checklist marca como atenção o que falta. "
           "Nada é gravado, é só treino.")

nav = st.columns([1, 1, 1, 5])
nav[0].button("◀ Anterior", on_click=mover, args=(-1,), disabled=pos == 0, width="stretch")
nav[1].button("Próximo ▶", on_click=mover, args=(+1,),
              disabled=pos >= len(st.session_state.casos) - 1, width="stretch")
if pos >= len(st.session_state.casos) - 1:
    nav[2].button("Recomeçar", on_click=recomecar, width="stretch")
nav[3].markdown(f"**Caso {pos + 1} de {len(st.session_state.casos)}**")

completar_guia = guia.mostrar_guia(st.session_state.casos, aberto=pos == 0,
                                   excluir=(float(c["ra"]), float(c["dec"])))
completar_animacao = imagens.mostrar(float(c["ra"]), float(c["dec"]),
                                     [f"**{t}.** {q}" for t, q in guia.ROTEIRO.values()])
imagens.pre_carregar([(float(x.ra), float(x.dec))
                      for x in st.session_state.casos.iloc[pos + 1:pos + 4].itertuples()])

esquerda, direita = st.columns([3, 2])
with esquerda:
    estilo.ficha([
        ("Movimento próprio", f"{c['pm_total']:.3f} \"/ano", None),
        ("Significância", f"{c['pm_signif']:.1f}", None),
        ("Cor W1-W2", f"{c['cor_w1w2']:.2f}", None),
        ("W2", f"{c['w2mpro']:.2f} mag", None),
    ])
    itens = dados.checklist(c.to_dict())
    estilo.checklist_html(itens, dados.sugestao(itens))

with direita:
    with st.container(border=True):
        st.markdown("**Sua resposta**")
        if pos not in st.session_state.respostas:
            st.button("Confirmar", type="primary", on_click=responder, args=(pos, "confirmado"),
                      width="stretch")
            st.button("Dúvida", on_click=responder, args=(pos, "duvida"), width="stretch")
            st.button("Descartar", on_click=responder, args=(pos, "descartado"), width="stretch")
        else:
            escolha = st.session_state.respostas[pos]
            certa = c["resposta"]
            st.markdown(f"**Resposta: {ROTULOS[certa]}.** {c['explicacao']}")
            st.info(f"**Onde estava a pista.** {guia.pista(c.to_dict())}")
            if escolha == certa:
                st.success("Você acertou.")
            elif escolha == "duvida":
                st.warning("Meio ponto: a dúvida vale metade.")
            else:
                st.error(f"Errou: você marcou {ROTULOS[escolha]}.")

# a animacao do WiseView e a parte lenta: carrega por ultimo
completar_animacao()
completar_guia()
