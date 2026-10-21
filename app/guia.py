"""O que procurar em cada imagem: roteiro, exemplos bom x ruim e a pista de cada caso.

Os exemplos saem dos casos do treino (anãs conhecidas, estrelas comuns e rejeitados da
Fase 3). As imagens vêm da rede, então o guia desenha quadros "carregando" e devolve a
função que os preenche: a página chama no fim, como a animação.
"""

import sqlite3

import pandas as pd
import streamlit as st

from app import dados, imagens
from config import REDE_PRAZO_S, ROOT, SQLITE_PATH
from src.util import com_prazo

# Como ler as imagens, mostrado no topo do guia
LEITURA = ("**Como ler as imagens.** Uma anã marrom é fria (abaixo de ~2000 °C) e brilha quase só "
           "no infravermelho. O satélite WISE fotografa o céu em dois infravermelhos, W1 e W2; "
           "quanto mais fria, mais ela brilha em W2 do que em W1 (cor W1-W2 alta). Na imagem 1, "
           "W1 vira azul e W2 vira laranja, então um objeto frio aparece laranja ou avermelhado. "
           "A imagem 2 é luz visível: anã T ou Y quase não aparece, e estrela comum aparece "
           "brilhante. A imagem 3 junta fotos do W2 tiradas em anos diferentes: uma anã perto do "
           "Sol anda no céu, e o ponto escuro muda de lugar quadro a quadro.\n\n"
           "**O que decide.** As três imagens juntas: ponto compacto e laranja no infravermelho "
           "(1), nada ou quase nada no óptico (2) e movimento contínuo (3). Se faltar uma, "
           "Dúvida ou Descartar. No checklist, dois itens pesam contra de verdade: Gaia (a "
           "contraparte brilha demais no visível para ser fria, G-W2 abaixo de 5) e Teste do "
           "AllWISE parado (em 2010 o objeto já estava no mesmo lugar, então o movimento era "
           "falso). Cor W1-W2, significância do movimento e óptico do Pan-STARRS só reforçam.")

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


def _tipos_simbad(nomes: list[str]) -> pd.DataFrame:
    """otype e sp_type de cada nome; vazio se o SIMBAD falhar (o treino usa texto generico)."""
    try:
        from astroquery.simbad import Simbad
        s = Simbad()
        s.add_votable_fields("otype", "sp_type")
        t = com_prazo(lambda: s.query_objects(nomes), REDE_PRAZO_S).to_pandas()
        return (t.rename(columns={"user_specified_id": "simbad_match_id"})
                [["simbad_match_id", "otype", "sp_type"]].drop_duplicates("simbad_match_id"))
    except Exception:
        return pd.DataFrame(columns=["simbad_match_id", "otype", "sp_type"])


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
    estrelas = estrelas.merge(_tipos_simbad(estrelas["simbad_match_id"].tolist()),
                              on="simbad_match_id", how="left")
    return dados.casos_treino(pd.read_pickle(ROOT / "data" / "recall_conhecidas.pkl"),
                              estrelas, rejeitados)


def exemplos(casos: pd.DataFrame, excluir: tuple[float, float] | None = None) -> dict:
    """Imagem -> (caso bom, caso ruim). O caso na tela nunca vira exemplo (entregaria a resposta)."""
    if excluir is not None:
        mesmo = ((casos["ra"] - excluir[0]).abs() < 1e-6) & ((casos["dec"] - excluir[1]).abs() < 1e-6)
        casos = casos[~mesmo]
    anas_t = casos[casos["explicacao"].str.contains("Anã T", na=False)]
    anas = anas_t if not anas_t.empty else casos[casos["resposta"] == "confirmado"]
    estrelas = casos[casos["explicacao"].str.contains("Estrela já catalogada", na=False)]
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
    # NaN vem do pandas (to_dict): conta como ausente, senao o texto sai com "nan"
    pm = None if pd.isna(c.get("pm_total")) else c.get("pm_total")
    if "Anã" in explicacao:
        tipo = explicacao.split()[1][0] if len(explicacao.split()) > 1 else ""
        otico = ("um pontinho vermelho fraco no óptico" if tipo == "L"
                 else "nada no óptico")
        anda = "" if pm is None else (f" Em 14 anos ela anda {pm * 14:.0f}\" "
                                      f"(~{pm * 14 / 2.75:.0f} pixels do unWISE).")
        return f"Ponto compacto no infravermelho e {otico}.{anda}"
    if "Galáxia" in explicacao:
        return ("Olhe o óptico: mancha difusa com estrutura, não um ponto. Galáxia não se move; "
                "no blink nada anda de forma contínua.")
    if "Estrela já catalogada" in explicacao:
        return ("O SIMBAD já tem este objeto como estrela. Nas imagens, compare o óptico: estrela "
                "comum costuma aparecer no visível, e a cor W1-W2 fica abaixo da de uma anã fria.")
    if "filtro de qualidade" in explicacao:
        sig = None if pd.isna(c.get("pm_signif")) else c.get("pm_signif")
        extra = "" if sig is None else f" A significância do movimento é só {sig:.1f}."
        return ("Olhe o movimento: nenhum ponto anda de forma contínua, e no infravermelho "
                f"não há uma fonte compacta e isolada.{extra}")
    return "Compare cada imagem com o roteiro acima."


def mostrar_guia(casos: pd.DataFrame | None, aberto: bool,
                 excluir: tuple[float, float] | None = None):
    """Expander com o roteiro e os exemplos; devolve a função que baixa as imagens."""
    lugares = []
    with st.expander("O que procurar em cada imagem (com exemplos)", expanded=aberto):
        st.markdown(LEITURA)
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
