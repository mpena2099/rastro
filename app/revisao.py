"""Fase 6: revisao visual dos candidatos (app local em Streamlit).

    streamlit run app/revisao.py

Le os candidatos da Fase 4 (com a nota da LLM da Fase 5, quando houver), mostra
recortes de imagem e os numeros de cada um, e grava a decisao humana na tabela
revisao_humana do mesmo banco. Rodar a partir da raiz do repositorio.
"""

import io
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw

from app import dados
from config import SQLITE_PATH

CAMADAS = [
    ("unwise-neo2", "unWISE NEO2 (infravermelho)"),
    ("unwise-neo7", "unWISE NEO7 (infravermelho)"),
    ("ls-dr10", "Óptico (Legacy Surveys DR10, grz)"),
]
ORDENACOES = {
    "Significância do PM (maior primeiro)": ("pm_signif", False),
    "Movimento próprio (maior primeiro)": ("pm_total", False),
    "Cor W1-W2 (mais vermelho primeiro)": ("cor_w1w2", False),
}
ROTULOS = {"confirmado": "Confirmado", "duvida": "Dúvida", "descartado": "Descartado"}

st.set_page_config(page_title="Rastro: revisão visual", layout="wide")


@st.cache_data(show_spinner=False)
def recorte(ra: float, dec: float, camada: str):
    """Baixa o recorte e marca a posicao do candidato (mira com folga no centro)."""
    url = dados.url_recorte(ra, dec, camada)
    for _ in range(2):
        try:
            r = httpx.get(url, timeout=30)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            break
        except Exception:
            img = None
    if img is None:
        return None
    lado = 330
    img = img.resize((lado, lado), Image.NEAREST if img.size[0] < 100 else Image.LANCZOS)
    d = ImageDraw.Draw(img)
    c, gap, tick = lado // 2, lado // 10, lado // 7
    for x0, y0, x1, y1 in [(c, c - gap - tick, c, c - gap), (c, c + gap, c, c + gap + tick),
                           (c - gap - tick, c, c - gap, c), (c + gap, c, c + gap + tick, c)]:
        d.line((x0, y0, x1, y1), fill=(0, 255, 0), width=2)
    return img


@st.cache_data(show_spinner="Cruzando com Gaia e Pan-STARRS (uma vez)...")
def cruzamentos(df: pd.DataFrame):
    try:
        return dados.cruzar_gaia_ps1(df[["source_id", "ra", "dec", "pmra", "pmdec"]])
    except Exception as e:
        return str(e)


def conectar() -> sqlite3.Connection:
    return sqlite3.connect(str(SQLITE_PATH))


def mover(delta: int, total: int):
    st.session_state.pos = max(0, min(total - 1, st.session_state.pos + delta))


def registrar(source_id: str, decisao: str, total: int):
    nota = st.session_state.get(f"nota_{source_id}", "")
    with conectar() as conn:
        dados.salvar_revisao(conn, source_id, decisao, nota)
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

cruz = cruzamentos(todos)
if isinstance(cruz, str):
    st.sidebar.warning(f"Sem cruzamento com Gaia/Pan-STARRS: {cruz}")
    todos["gaia_detectada"] = pd.NA
    todos["ps1_detectada"] = pd.NA
    todos["gaia_g"] = pd.NA
else:
    todos = todos.merge(cruz, on="source_id", how="left")

todos["decisao"] = todos["decisao"].fillna("pendente")

# ---------------------------------------------------------------- filtros
st.sidebar.header("Fila de revisão")
sel_decisao = st.sidebar.multiselect(
    "Situação", ["pendente", *dados.DECISOES], default=["pendente"],
    format_func=lambda x: ROTULOS.get(x, "Pendente"))
gaia = st.sidebar.radio("Contraparte no Gaia", ["Qualquer", "Sem Gaia", "Com Gaia"], index=1,
                        help="Com Gaia costuma ser estrela comum já conhecida.")
ps1 = st.sidebar.radio("Detecção óptica (Pan-STARRS)", ["Qualquer", "Sem detecção", "Com detecção"],
                       help="Anãs T e Y somem no óptico, mas anãs L aparecem. Use pra ordenar, não pra descartar.")
sig_min = st.sidebar.slider("PM/σ mínimo", float(todos["pm_signif"].min()),
                            float(min(todos["pm_signif"].max(), 40)),
                            float(todos["pm_signif"].min()), step=0.5)
scores = sorted(todos["llm_triage_score"].unique())
sel_scores = st.sidebar.multiselect("Nota da LLM", scores, default=scores,
                                    help="A LLM marcou 44% como 'alta': é só um comentário.")
ordem = st.sidebar.selectbox("Ordenar por", list(ORDENACOES))

fila = todos[todos["decisao"].isin(sel_decisao) & (todos["pm_signif"] >= sig_min)
             & todos["llm_triage_score"].isin(sel_scores)]
if gaia != "Qualquer" and todos["gaia_detectada"].notna().any():
    fila = fila[fila["gaia_detectada"] == (gaia == "Com Gaia")]
if ps1 != "Qualquer" and todos["ps1_detectada"].notna().any():
    fila = fila[fila["ps1_detectada"] == (ps1 == "Com detecção")]
col, asc = ORDENACOES[ordem]
fila = fila.sort_values(col, ascending=asc).reset_index(drop=True)
total = len(fila)

assinatura = (tuple(sel_decisao), gaia, ps1, sig_min, tuple(sel_scores), ordem)
if st.session_state.get("assinatura") != assinatura:
    st.session_state.assinatura = assinatura
    st.session_state.pos = 0
st.session_state.setdefault("pos", 0)

revisados = int((todos["decisao"] != "pendente").sum())
st.sidebar.metric("Revisados", f"{revisados} de {len(todos)}")
st.sidebar.caption({d: int((todos['decisao'] == d).sum()) for d in dados.DECISOES})

# ---------------------------------------------------------------- tela
st.title("Rastro: revisão visual")
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

m = st.columns(6)
m[0].metric("Movimento próprio", f"{r['pm_total']:.3f} \"/ano")
m[1].metric("PM/σ", f"{r['pm_signif']:.1f}")
m[2].metric("Cor W1-W2", f"{r['cor_w1w2']:.2f}")
m[3].metric("W2", f"{r['w2mpro']:.2f} mag", f"SNR {r['w2snr']:.0f}", delta_color="off")
gaia_flag = None if pd.isna(r["gaia_detectada"]) else bool(r["gaia_detectada"])
ps1_flag = None if pd.isna(r["ps1_detectada"]) else bool(r["ps1_detectada"])
m[4].metric("Gaia", "?" if gaia_flag is None
            else (f"G={r['gaia_g']:.1f}" if gaia_flag else "sem contraparte"))
m[5].metric("Pan-STARRS", "?" if ps1_flag is None else ("detectada" if ps1_flag else "sem detecção"))

imgs = st.columns(len(CAMADAS))
for coluna, (camada, titulo) in zip(imgs, CAMADAS):
    img = recorte(float(r["ra"]), float(r["dec"]), camada)
    coluna.caption(titulo)
    if img is None:
        coluna.warning("Recorte indisponível (servidor fora do ar ou sem cobertura).")
    else:
        coluna.image(img, width="stretch")
st.caption("Recortes de 60\" x 60\", norte pra cima e leste à esquerda. A mira verde marca a "
           "posição do CatWISE (~2015). Um objeto real e próximo aparece no infravermelho; "
           "um ponto só no óptico é fonte comum. Imagens: unWISE (NASA/WISE) e Legacy Surveys (DESI).")

st.markdown(f"[Abrir no Legacy Surveys]({dados.link_legacy_viewer(r['ra'], r['dec'])})  |  "
            f"[Abrir no WiseView (movimento em épocas)]({dados.link_wiseview(r['ra'], r['dec'])})")

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
- **Confirmar** não é descoberta: quer dizer "passa no olho". O teste decisivo é abrir o link do WiseView e ver o ponto andando sempre na mesma direção ao longo dos anos. Quem não anda é ruído.
- **Descartar** não apaga nada: a decisão fica gravada com a nota e dá pra rever no filtro "Situação".
""")

st.subheader("Sua decisão")
if r["decisao"] != "pendente":
    st.success(f"Já marcado como **{ROTULOS[r['decisao']]}**."
               + (f" Nota: {r['nota']}" if pd.notna(r["nota"]) and r["nota"] else ""))
    st.button("Limpar decisão", on_click=limpar, args=(sid,))
st.text_area("Nota (opcional)", key=f"nota_{sid}", value=r["nota"] if pd.notna(r["nota"]) else "",
             height=70)
b = st.columns(3)
b[0].button("Confirmar (parece real)", type="primary", on_click=registrar,
            args=(sid, "confirmado", total), width="stretch")
b[1].button("Dúvida", on_click=registrar, args=(sid, "duvida", total), width="stretch")
b[2].button("Descartar (falso alarme)", on_click=registrar, args=(sid, "descartado", total),
            width="stretch")
