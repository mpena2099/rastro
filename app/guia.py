"""O que procurar em cada imagem: roteiro, exemplos bom x ruim e a pista de cada caso.

Os exemplos saem dos casos do treino (anãs conhecidas, estrelas comuns e rejeitados da
Fase 3). As imagens vêm da rede, então o guia desenha quadros "carregando" e devolve a
função que os preenche: a página chama no fim, como a animação.
"""

import sqlite3

import pandas as pd
import streamlit as st

from app import dados, imagens
from config import ROOT, SQLITE_PATH

# imagem -> (titulo, pergunta que o revisor responde olhando)
ROTEIRO = {
    "unwise-neo7": ("1. Infravermelho",
                    "Tem um ponto compacto e nítido dentro da mira, laranja ou avermelhado? "
                    "Mancha larga, rastro ou só granulado não contam."),
    "ls-dr10": ("2. Óptico",
                "Na mira não aparece nada (anã T ou Y) ou só um pontinho vermelho fraco (anã L)? "
                "Estrela branca, amarela ou azul brilhante é estrela comum."),
    "movimento": ("3. Movimento",
                  "Um ponto escuro anda sempre na mesma direção ao longo dos anos? Ponto parado "
                  "ou que pisca em lugares diferentes não é movimento."),
}

# imagem -> (o que ver no exemplo bom, o que ver no exemplo ruim)
CONTRASTE = {
    "unwise-neo7": ("Bolha compacta e alaranjada na mira: fonte fria e real.",
                    "Nada definido na mira: o pipeline viu movimento em ruído ou numa mistura."),
    "ls-dr10": ("Mira vazia no óptico: a anã é fria demais para aparecer no visível.",
                "Estrela brilhante na mira: estrela comum, só que próxima e rápida."),
    "movimento": ("O ponto escuro atravessa a mira com o passar dos anos.",
                  "Nenhum ponto que se desloque de forma contínua: o movimento era falso."),
}


@st.cache_data(show_spinner=False)
def casos_de_treino() -> pd.DataFrame:
    """Anãs conhecidas, estrelas comuns do SIMBAD e rejeitados da Fase 3, com resposta."""
    with sqlite3.connect(str(SQLITE_PATH)) as conn:
        # so quem tem nome no SIMBAD: catalogo_match sem SIMBAD pode ser ana ja publicada
        estrelas = pd.read_sql(
            "SELECT * FROM candidatos_fase4 WHERE status = 'conhecido' "
            "AND simbad_match_id IS NOT NULL", conn)
        bruto = pd.read_sql("SELECT * FROM campo_bruto", conn)
        fase3 = pd.read_sql("SELECT source_id FROM candidatos_fase3", conn)
    rejeitados = bruto[~bruto["source_id"].isin(fase3["source_id"])]
    return dados.casos_treino(pd.read_pickle(ROOT / "data" / "recall_conhecidas.pkl"),
                              estrelas, rejeitados)


def exemplos(casos: pd.DataFrame, excluir: tuple[float, float] | None = None) -> dict:
    """Imagem -> (caso bom, caso ruim). O caso na tela nunca vira exemplo (entregaria a resposta)."""
    if excluir is not None:
        mesmo = ((casos["ra"] - excluir[0]).abs() < 1e-6) & ((casos["dec"] - excluir[1]).abs() < 1e-6)
        casos = casos[~mesmo]
    anas_t = casos[casos["explicacao"].str.contains("Anã T", na=False)]
    anas = anas_t if not anas_t.empty else casos[casos["resposta"] == "confirmado"]
    estrelas = casos[casos["explicacao"].str.contains("Estrela comum", na=False)]
    rejeitados = casos[casos["explicacao"].str.contains("filtro de qualidade", na=False)]

    def um(df, coluna, maior):
        return None if df.empty else df.sort_values(coluna, ascending=not maior).iloc[0]

    rapida = um(anas, "pm_total", True)  # movimento grande se vê melhor
    ruim = um(rejeitados, "pm_signif", False)
    return {"unwise-neo7": (rapida, ruim),
            "ls-dr10": (rapida, um(estrelas, "w2mpro", False)),
            "movimento": (rapida, ruim)}


def pista(c: dict) -> str:
    """Em qual imagem estava a resposta deste caso, com os números dele."""
    explicacao = str(c.get("explicacao", ""))
    pm = c.get("pm_total")
    if "Anã" in explicacao:
        tipo = explicacao.split()[1][0] if len(explicacao.split()) > 1 else ""
        otico = ("um pontinho vermelho fraco no óptico" if tipo == "L"
                 else "nada no óptico")
        anda = "" if pm is None else (f" Em 14 anos ela anda {pm * 14:.0f}\" "
                                      f"(~{pm * 14 / 2.75:.0f} pixels do unWISE).")
        return f"Ponto compacto no infravermelho e {otico}.{anda}"
    if "Estrela comum" in explicacao:
        return ("Olhe o óptico: uma estrela clara e brilhante na mira. O movimento é real, "
                "mas é uma estrela comum próxima, não uma anã fria.")
    if "filtro de qualidade" in explicacao:
        sig = c.get("pm_signif")
        extra = "" if sig is None else f" A significância do movimento é só {sig:.1f}."
        return ("Olhe o movimento: nenhum ponto anda de forma contínua, e no infravermelho "
                f"não há uma fonte compacta e isolada.{extra}")
    return "Compare cada imagem com o roteiro acima."


def mostrar_guia(casos: pd.DataFrame | None, aberto: bool,
                 excluir: tuple[float, float] | None = None):
    """Expander com o roteiro e os exemplos; devolve a função que baixa as imagens."""
    lugares = []
    with st.expander("O que procurar em cada imagem (com exemplos)", expanded=aberto):
        figs = exemplos(casos, excluir) if casos is not None and not casos.empty else {}
        for chave, (titulo, pergunta) in ROTEIRO.items():
            st.markdown(f"**{titulo}.** {pergunta}")
            bom, ruim = figs.get(chave, (None, None))
            cols = st.columns(3)  # a terceira fica vazia: exemplos menores
            for col, caso, rotulo, texto in ((cols[0], bom, "✅ Bom", CONTRASTE[chave][0]),
                                             (cols[1], ruim, "❌ Ruim", CONTRASTE[chave][1])):
                if caso is None:
                    continue
                lugar = col.empty()
                lugar.markdown(imagens.carregando("Carregando o exemplo"), unsafe_allow_html=True)
                col.caption(f"**{rotulo}.** {texto}")
                lugares.append((lugar, chave, float(caso["ra"]), float(caso["dec"])))

    def completar():
        for lugar, chave, ra, dec in lugares:
            img = (imagens.animacao(ra, dec) if chave == "movimento"
                   else imagens.recorte(ra, dec, chave))
            if img is None:
                lugar.warning("Imagem indisponível.")
            else:
                lugar.image(img, width="stretch")
    return completar
