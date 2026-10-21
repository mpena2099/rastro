"""Modo treino: casos com resposta, pra aprender a olhar as imagens."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from app import cruzamento, dados, estilo, imagens, guia
from config import ROOT, SQLITE_PATH

DESCRICAO = ("Casos de resposta conhecida (anãs já catalogadas, estrelas comuns e rejeitados pelo "
             "filtro de qualidade), para aprender a decidir antes da revisão de verdade. Você "
             "responde e vê a resposta certa, a explicação e onde estava a pista. Nada muda nos "
             "candidatos; só o seu histórico de acertos é gravado.")
ROTULOS = {"confirmado": "Confirmado", "duvida": "Dúvida", "descartado": "Descartado"}


def responder(i: int, decisao: str):
    if i in st.session_state.respostas:
        return
    st.session_state.respostas[i] = decisao
    c = st.session_state.casos.iloc[i]
    certa = c["resposta"]
    pontos = 1.0 if decisao == certa else (0.5 if decisao == "duvida" else 0.0)
    st.session_state.pontos += pontos
    with sqlite3.connect(str(SQLITE_PATH)) as conn:
        dados.salvar_tentativa(conn, f"{c['ra']:.5f},{c['dec']:.5f}", decisao, certa, pontos)


def mostrar_historico():
    """Aproveitamento de todas as sessoes, gravado no banco."""
    with sqlite3.connect(str(SQLITE_PATH)) as conn:
        r = dados.resumo_treino(dados.ler_tentativas(conn))
    if not r:
        return
    with st.expander(f"Seu histórico: {r['geral']:.0%} de acerto em {r['respostas']} "
                     f"{'resposta' if r['respostas'] == 1 else 'respostas'}"):
        cols = st.columns(2 + len(r["por_certa"]))
        cols[0].metric("Geral", f"{r['geral']:.0%}",
                       help=f"{r['respostas']} respostas em {r['dias']} dia(s)")
        cols[1].metric(f"Últimas {r['n_recentes']}", f"{r['recentes']:.0%}",
                       delta=f"{(r['recentes'] - r['geral']) * 100:+.0f} pontos")
        for col, (certa, (taxa, n)) in zip(cols[2:], r["por_certa"].items()):
            col.metric(f"Quando era {ROTULOS[certa]}", f"{taxa:.0%}", help=f"{n} casos")
        st.caption("Acerto muito diferente entre as colunas \"Quando era\" indica viés, por "
                   "exemplo confirmar quase tudo. Dúvida vale meio ponto.")


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
if not st.session_state.get("casos_cruzados"):
    # mesmos cruzamentos da fila: sem eles o checklist marcava atencao em tudo
    st.session_state.casos, _erros = cruzamento.completar(st.session_state.casos, "o treino", "caso")
    # uma tentativa por sessao: repetir a cada clique esperaria o servidor fora do ar toda vez
    st.session_state.casos_cruzados = True
    st.session_state.erros_cruzamento = _erros
if st.session_state.get("erros_cruzamento"):
    st.warning("Algum catálogo não respondeu (Gaia, Pan-STARRS ou AllWISE): o checklist marca "
               "atenção onde falta o dado. Na próxima sessão do treino ele tenta de novo.")

pos = max(0, min(st.session_state.pos, len(st.session_state.casos) - 1))
c = st.session_state.casos.iloc[pos]
respondidos = len(st.session_state.respostas)

estilo.cabecalho("Treino", (st.session_state.pontos, respondidos),
                 "Acertos {atual} de {total}", DESCRICAO)
# no treino so importa a primeira etapa da trilha: uma linha com o nivel e o que falta
with sqlite3.connect(str(SQLITE_PATH)) as _conn:
    _etapa = dados.marcos(_conn)[0]
    _nivel, _falta = dados.nivel_treino(dados.ler_tentativas(_conn))
st.info(f"**Nível: {_nivel}.** "
        + ("Treino em dia ✅" if _etapa["feito"]
           else f"Para \"Treino em dia\" (80% nas últimas 20): {_etapa['detalhe']}.")
        # com poucas respostas a dica do nivel repete o que falta para a etapa
        + (f" {_falta[0].upper()}{_falta[1:]}." if _falta and not _falta.startswith("faltam") else ""))
mostrar_historico()

# guia antes da navegacao: logo acima do caso ele parecia fazer parte dele
completar_guia = guia.mostrar_guia(st.session_state.casos, aberto=pos == 0,
                                   excluir=(float(c["ra"]), float(c["dec"])))
nav = st.columns([1, 1, 1, 5])
nav[0].button("◀ Anterior", on_click=mover, args=(-1,), disabled=pos == 0, width="stretch")
nav[1].button("Próximo ▶", on_click=mover, args=(+1,),
              disabled=pos >= len(st.session_state.casos) - 1, width="stretch")
if pos >= len(st.session_state.casos) - 1:
    nav[2].button("Recomeçar", on_click=recomecar, width="stretch")
nav[3].markdown(f"**Caso {pos + 1} de {len(st.session_state.casos)}**")

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
            st.button("Próximo ▶", type="primary", on_click=mover, args=(+1,), key="proximo_baixo",
                      disabled=pos >= len(st.session_state.casos) - 1)

# a animacao do WiseView e a parte lenta: carrega por ultimo
completar_animacao()
completar_guia()
