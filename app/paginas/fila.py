"""Revisao visual dos candidatos (pagina principal do app em Streamlit)."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from app import dados, estilo, imagens
from config import ROOT, SQLITE_PATH
from src import relatorio

ORDENACOES = {
    "AllWISE consistente primeiro, depois PM/σ": [("allwise_ordem", True), ("pm_signif", False)],
    "Significância do PM (maior primeiro)": [("pm_signif", False)],
    "Movimento próprio (maior primeiro)": [("pm_total", False)],
    "Cor W1-W2 (mais vermelho primeiro)": [("cor_w1w2", False)],
}
ALLWISE_ORDEM = {"consistente": 0, "ambiguo": 1, "sem fonte": 2, "sem teste": 2, "parado": 3}
ALLWISE_ROTULO = {
    "consistente": "se moveu (confere)", "parado": "não se moveu", "ambiguo": "ambíguo",
    "sem fonte": "sem fonte (fraco?)", "sem teste": "PM baixo demais",
}
ROTULOS = {"confirmado": "Confirmado", "duvida": "Dúvida", "descartado": "Descartado"}


@st.cache_data(show_spinner="Consultando o VizieR inteiro (20 s a 1 min)...")
def vizier(ra: float, dec: float, pm_total: float) -> pd.DataFrame:
    return dados.buscar_vizier(ra, dec, pm_total)


@st.cache_data(show_spinner="Cruzando com Gaia, Pan-STARRS e AllWISE (uma vez)...")
def cruzamentos(df: pd.DataFrame):
    out, erros = df[["source_id"]].copy(), []
    for nome, fn in (("Gaia/Pan-STARRS", dados.cruzar_gaia_ps1), ("AllWISE", dados.cruzar_allwise)):
        try:
            out = out.merge(fn(df), on="source_id", how="left")
        except Exception as e:
            erros.append(f"{nome}: {e}")
    return out, erros


def conectar() -> sqlite3.Connection:
    return sqlite3.connect(str(SQLITE_PATH))


def mover(delta: int, total: int):
    st.session_state.pos = max(0, min(total - 1, st.session_state.pos + delta))


def registrar(source_id: str, decisao: str, total: int, fica_na_fila: bool):
    nota = st.session_state.get(f"nota_{source_id}", "")
    with conectar() as conn:
        dados.salvar_revisao(conn, source_id, decisao, nota)
    # Se a decisao tira o candidato da fila (ex: fila de pendentes), o proximo sobe
    # pra posicao atual: avancar aqui pularia um candidato sem mostrar.
    if fica_na_fila:
        mover(+1, total)


def limpar(source_id: str):
    with conectar() as conn:
        dados.apagar_revisao(conn, source_id)


# ---------------------------------------------------------------- dados
try:
    with conectar() as conn:
        todos = dados.carregar_candidatos(conn)
except Exception as e:
    st.error(f"Não consegui ler os candidatos em {SQLITE_PATH}: {e}\n\n"
             "Rode `python pipeline.py` (ou as fases 2 a 4) antes de abrir o app.")
    st.stop()

if todos.empty:
    st.warning("A tabela candidatos_fase4 não tem candidatos.")
    st.stop()

cruz, erros_cruz = cruzamentos(
    todos[["source_id", "ra", "dec", "pmra", "pmdec", "meanobsmjd"]])
todos = todos.merge(cruz, on="source_id", how="left")
for coluna, padrao in (("gaia_detectada", pd.NA), ("ps1_detectada", pd.NA), ("gaia_g", pd.NA),
                       ("allwise_status", "sem dados")):
    if coluna not in todos:
        todos[coluna] = padrao
todos["allwise_status"] = todos["allwise_status"].fillna("sem dados")
todos["allwise_ordem"] = todos["allwise_status"].map(ALLWISE_ORDEM).fillna(2)

todos["decisao"] = todos["decisao"].fillna("pendente")

# ---------------------------------------------------------------- filtros
st.sidebar.header("Filtros")
busca = st.sidebar.text_input("Buscar por código", placeholder="ex: 002585 ou 1506p181_b0-002585",
                              help="Acha o candidato em qualquer situação e ignora os outros filtros.").strip()
contagem = todos["decisao"].value_counts()
# Rotulos fixos: com a contagem no rotulo, cada decisao mudava as opcoes e o
# Streamlit voltava o radio pra primeira opcao.
OPCOES_SITUACAO = {
    "Pendentes": ["pendente"],
    "Confirmados": ["confirmado"],
    "Dúvidas": ["duvida"],
    "Descartados": ["descartado"],
    "Todos": ["pendente", *dados.DECISOES],
}
situacao = st.sidebar.radio("Situação", list(OPCOES_SITUACAO), index=0, key="situacao",
                            captions=[str(int(sum(contagem.get(d, 0) for d in v)))
                                      for v in OPCOES_SITUACAO.values()])
sel_decisao = OPCOES_SITUACAO[situacao]
gaia = st.sidebar.radio("Contraparte no Gaia", ["Qualquer", "Sem Gaia", "Com Gaia"], index=1,
                        help="Com Gaia costuma ser estrela comum já conhecida.")
ps1 = st.sidebar.radio("Detecção óptica (Pan-STARRS)", ["Qualquer", "Sem detecção", "Com detecção"],
                       help="Anãs T e Y somem no óptico, mas anãs L aparecem. Use pra ordenar, não pra descartar.")
allwise = st.sidebar.selectbox(
    "Movimento no AllWISE (2010)", ["Qualquer", "Consistente", "Ambíguo", "Sem fonte ou sem teste", "Parado"],
    help="Compara com o AllWISE, ~5 anos mais antigo. 'Consistente': a fonte estava onde o movimento "
         "próprio prevê. 'Parado': estava no mesmo lugar de hoje. Candidato fraco costuma ficar em "
         "'sem fonte', porque o AllWISE é mais raso: isso não prova nada.")
sig_min = st.sidebar.slider("PM/σ mínimo", float(todos["pm_signif"].min()),
                            float(min(todos["pm_signif"].max(), 40)),
                            float(todos["pm_signif"].min()), step=0.5)
scores = sorted(todos["llm_triage_score"].unique())
sel_scores = st.sidebar.multiselect("Nota da LLM", scores, default=scores,
                                    help="A LLM marcou 44% como 'alta': é só um comentário.")
ordem = st.sidebar.selectbox("Ordenar por", list(ORDENACOES))

if busca:
    # A busca vale pra qualquer situacao e ignora os demais filtros.
    fila = todos[todos["source_id"].str.contains(busca, case=False, regex=False)]
    st.sidebar.info(f"Busca ativa: {len(fila)} resultado(s), outros filtros ignorados.")
else:
    fila = todos[todos["decisao"].isin(sel_decisao) & (todos["pm_signif"] >= sig_min)
                 & todos["llm_triage_score"].isin(sel_scores)]
    if gaia != "Qualquer" and todos["gaia_detectada"].notna().any():
        fila = fila[fila["gaia_detectada"] == (gaia == "Com Gaia")]
    if ps1 != "Qualquer" and todos["ps1_detectada"].notna().any():
        fila = fila[fila["ps1_detectada"] == (ps1 == "Com detecção")]
if allwise != "Qualquer" and not busca:
    alvo = {"Consistente": ["consistente"], "Ambíguo": ["ambiguo"], "Parado": ["parado"],
            "Sem fonte ou sem teste": ["sem fonte", "sem teste", "sem dados"]}[allwise]
    fila = fila[fila["allwise_status"].isin(alvo)]
chaves = ORDENACOES[ordem]
fila = fila.sort_values([c for c, _ in chaves], ascending=[a for _, a in chaves]).reset_index(drop=True)
total = len(fila)

assinatura = (busca, tuple(sel_decisao), gaia, ps1, allwise, sig_min, tuple(sel_scores), ordem)
if st.session_state.get("assinatura") != assinatura:
    st.session_state.assinatura = assinatura
    st.session_state.pos = 0
    st.session_state.sel_aplicada = None
st.session_state.setdefault("pos", 0)

# Clique numa linha da tabela da fila: abre aquele candidato (so quando a selecao muda,
# pra nao brigar com os botoes Anterior/Proximo).
_tab = st.session_state.get("tabela_fila")
_linhas = list(_tab["selection"]["rows"]) if _tab else []
if _linhas and _linhas != st.session_state.get("sel_aplicada") and _linhas[0] < total:
    st.session_state.pos = _linhas[0]
    st.session_state.sel_aplicada = _linhas

revisados = int((todos["decisao"] != "pendente").sum())

# ---------------------------------------------------------------- tela
estilo.cabecalho("Revisão visual", (revisados, len(todos)))
for e in erros_cruz:
    st.warning(f"Sem cruzamento, {e}")
if total == 0:
    st.info("Nenhum candidato na fila com esses filtros.")
    st.stop()

st.session_state.pos = max(0, min(total - 1, st.session_state.pos))
r = fila.iloc[st.session_state.pos]
sid = r["source_id"]

nav = st.columns([1, 1, 6])
nav[0].button("◀ Anterior", on_click=mover, args=(-1, total), disabled=st.session_state.pos == 0,
              width="stretch")
nav[1].button("Próximo ▶", on_click=mover, args=(+1, total),
              disabled=st.session_state.pos >= total - 1, width="stretch")
nav[2].markdown(f"**{st.session_state.pos + 1} de {total}** na fila  |  `{sid}`  |  "
                f"RA {r['ra']:.5f}, Dec {r['dec']:+.5f}")

imagens.mostrar(float(r["ra"]), float(r["dec"]))
st.caption("Recortes de 60\" x 60\", norte pra cima e leste à esquerda. A mira verde marca a "
           "posição do CatWISE (~2015). Um objeto real e próximo aparece no infravermelho; "
           "um ponto só no óptico é fonte comum. Na animação, as fontes aparecem escuras e cada quadro é uma época do W2 "
           "(WiseView) e o ano está no canto. Imagens: unWISE (NASA/WISE), Legacy Surveys (DESI) "
           "e WiseView.")
st.markdown(f"[Abrir no Legacy Surveys]({dados.link_legacy_viewer(r['ra'], r['dec'])})  |  "
            f"[Abrir no WiseView (movimento em épocas)]({dados.link_wiseview(r['ra'], r['dec'])})")

gaia_flag = None if pd.isna(r["gaia_detectada"]) else bool(r["gaia_detectada"])
ps1_flag = None if pd.isna(r["ps1_detectada"]) else bool(r["ps1_detectada"])


def fica(decisao: str) -> bool:
    return bool(busca) or decisao in sel_decisao


esquerda, direita = st.columns([3, 2])
with esquerda:
    estilo.ficha([
        ("Movimento próprio", f"{r['pm_total']:.3f} \"/ano", None),
        ("Significância", f"{r['pm_signif']:.1f}", None),
        ("Cor W1-W2", f"{r['cor_w1w2']:.2f}", None),
        ("W2", f"{r['w2mpro']:.2f} mag", f"SNR {r['w2snr']:.0f}"),
        ("Gaia", "?" if gaia_flag is None
         else (f"G={r['gaia_g']:.1f}" if gaia_flag else "sem contraparte"), None),
        ("Pan-STARRS", "?" if ps1_flag is None else ("detectada" if ps1_flag else "sem detecção"), None),
        ("AllWISE (2010)", ALLWISE_ROTULO.get(r["allwise_status"], "sem dados"),
         "Ver o filtro 'Movimento no AllWISE'"),
    ])
    itens = dados.checklist(r.to_dict())
    estilo.checklist_html(itens, dados.sugestao(itens))

with direita:
    with st.container(border=True):
        st.markdown("**Sua decisão**")
        st.caption("Tem um ponto nítido no infravermelho, dentro da mira? Na animação, o ponto "
                   "anda sempre na mesma direção?")
        if r["decisao"] != "pendente":
            st.success(f"Já marcado como **{ROTULOS[r['decisao']]}**."
                       + (f" Nota: {r['nota']}" if pd.notna(r["nota"]) and r["nota"] else ""))
            st.button("Limpar decisão", on_click=limpar, args=(sid,))
        st.text_area("Nota (opcional)", key=f"nota_{sid}",
                     value=r["nota"] if pd.notna(r["nota"]) else "", height=70)
        st.button("Confirmar (parece real)", type="primary", on_click=registrar,
                  args=(sid, "confirmado", total, fica("confirmado")), width="stretch")
        st.button("Dúvida", on_click=registrar, args=(sid, "duvida", total, fica("duvida")),
                  width="stretch")
        st.button("Descartar (falso alarme)", on_click=registrar,
                  args=(sid, "descartado", total, fica("descartado")), width="stretch")

with st.expander(f"Fila completa ({total}): clique numa linha pra abrir o candidato"):
    tabela = fila.assign(
        gaia=fila["gaia_g"].map(lambda v: "sem" if pd.isna(v) else f"G={v:.1f}"),
        allwise=fila["allwise_status"].map(lambda v: ALLWISE_ROTULO.get(v, v)),
    )[["source_id", "decisao", "pm_total", "pm_signif", "cor_w1w2", "w2mpro", "allwise", "gaia",
       "llm_triage_score"]]
    st.dataframe(tabela, hide_index=True, on_select="rerun", selection_mode="single-row",
                 key="tabela_fila", height=260)

# ---------------------------------------------------------------- relatorio (Fase 7)
with st.expander("Relatório (Fase 7): página HTML com os confirmados"):
    com_duvidas = st.checkbox("Incluir dúvidas", value=False)
    n_rel = int(todos["decisao"].isin(["confirmado"] + (["duvida"] if com_duvidas else [])).sum())
    if st.button(f"Gerar relatório ({n_rel})", disabled=n_rel == 0,
                 help="Página HTML com recortes e números dos confirmados, para enviar a um astrônomo."):
        with st.spinner("Baixando recortes..."):
            st.session_state.relatorio = (
                relatorio.gerar_html(relatorio.filtrar_revisados(todos, com_duvidas)), n_rel)
    if "relatorio" in st.session_state:
        html_rel, n_gerado = st.session_state.relatorio
        st.download_button(f"Baixar relatório ({n_gerado})", html_rel,
                           file_name="rastro_relatorio.html", mime="text/html")

with st.expander("Já foi publicado? (busca no VizieR inteiro)"):
    st.caption("A Fase 4 já cruza o SIMBAD e as listas de anãs de `CATALOGOS_ANAS`. Esta busca "
               "olha todos os catálogos do VizieR, e é como se acha um catálogo novo que ainda não "
               "entrou na lista. Faça antes de confirmar um candidato.")
    if st.button("Buscar no VizieR", key=f"vizier_{sid}"):
        try:
            achados = vizier(float(r["ra"]), float(r["dec"]), float(r["pm_total"]))
            anas = achados[achados["lista_anas"]]
            if anas.empty:
                st.success(dados.resumo_vizier(achados))
            else:
                st.warning(f"Aparece em {len(anas)} lista(s) de anãs ou de movimento próprio. "
                           "Confira se é o mesmo objeto (distância pequena) antes de confirmar.")
            st.dataframe(achados, hide_index=True, width="stretch")
        except Exception as e:
            st.error(f"VizieR falhou: {e}")

with st.expander(f"Nota da LLM: {r['llm_triage_score']}"):
    st.write(r["llm_triage_notes"] if pd.notna(r["llm_triage_notes"]) else "Sem triagem da LLM.")

with st.expander("Como decidir (o que procurar nas imagens)"):
    st.markdown("""| O que você vê | Decisão |
|---|---|
| Nada no centro das imagens de infravermelho, só ruído | **Descartar** |
| Mancha larga e difusa (galáxia), ou colada numa estrela brilhante, ou no meio dos "raios" de uma estrela | **Descartar** |
| No óptico, uma estrela clara (branca, amarela ou azul) no centro | **Descartar** (estrela comum) |
| Ponto nítido no infravermelho, laranja ou avermelhado, e **nada** no óptico | **Confirmar** (compatível com anã T ou Y) |
| Ponto nítido no infravermelho e um ponto **vermelho fraco** no óptico | **Confirmar** (compatível com anã L), mas com cor W1-W2 abaixo de ~0,3 pode ser só uma anã M comum, então prefira **Dúvida** |
| Ponto no infravermelho, mas fraco, colado numa vizinha, ou você não conseguiu conferir o movimento | **Dúvida** |

**Detalhes que ajudam**
- O objeto se move. No óptico, ele pode estar um pouco deslocado da mira, na direção do movimento (movimento próprio x anos de diferença entre as imagens). Dentro do espaço vazio da mira (cerca de 6") ainda conta como no lugar.
- No unWISE, cor avermelhada ou alaranjada é o que se espera de uma anã fria. Azul ou branco é estrela comum.
- O app compara cada candidato com o AllWISE (~2010): "se moveu (confere)" reforça o caso, "não se moveu" pesa contra, e "sem fonte" não diz nada (o candidato é fraco demais pra aparecer lá).
- **Confirmar** não é descoberta: quer dizer "passa no olho". O teste decisivo é a animação "Movimento" ao lado dos recortes: o ponto tem de andar sempre na mesma direção, ano após ano. O link do WiseView abre a mesma animação em tamanho maior.
- **Descartar** não apaga nada: a decisão fica gravada com a nota e dá pra rever no filtro "Situação".
""")

with st.expander("Casos de referência (como são os confirmar, dúvida e descartar)"):
    abas = st.tabs(["Confirmar", "Dúvida", "Descartar"])
    textos = {
        "confirmar": """Em cada linha: infravermelho (unWISE NEO7) e óptico (Legacy Surveys). As três primeiras linhas desta folha são exemplos de **confirmar**.

1. **Anã L5 conhecida.** Bolha nítida no infravermelho e um ponto vermelho no óptico, os dois na mira.
2. **Anã T7 conhecida.** Bolha alaranjada no infravermelho, na borda da mira (o objeto andou desde 2015) e nada no óptico naquela posição. O ponto vermelho à direita, no óptico, é outra fonte.
3. **Suspeito do campo.** Bolha nítida no infravermelho e um pontinho vermelho exatamente na mira (cor W1-W2 0,56). É o tipo de caso que vale levar ao WiseView.""",
        "duvida": """1. **Anã Y0 conhecida.** Um borrão marrom fraquíssimo no infravermelho, nada no óptico, vizinhas brilhantes por perto. **Uma anã Y real parece isso.**
2. **Três suspeitos do campo** com a mesma cara: fraco no infravermelho, nada no óptico. Sem ver o movimento no WiseView não dá pra distingui-los de ruído, e é por isso que o certo é **dúvida** (e não descartar).""",
        "descartar": """1. **Nada no infravermelho.** Só um rastro difuso e sem forma, sem a bolha compacta de um objeto real.
2. **Estrela clara no óptico.** Ponto brilhante, com núcleo estourado, bem na mira.
3. **Galáxia.** No óptico aparece uma galáxia grande e amarela, com estrutura.
4. **Estrela brilhante e saturada.** O "estouro" azul-lilás é típico de estrela forte demais pra câmera.""",
    }
    for aba, chave in zip(abas, ("confirmar", "duvida", "descartar")):
        with aba:
            st.image(str(ROOT / "docs" / "img" / f"ref_{chave}.jpg"))
            st.markdown(textos[chave])
