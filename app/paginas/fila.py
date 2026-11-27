"""Revisao visual dos candidatos (pagina principal do app em Streamlit)."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from datetime import date

from app import cruzamento, dados, envio, estilo, execucao, imagens, guia
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
DESCRICAO = ("Candidatos a anã marrom: objetos que andam rápido no céu infravermelho e não estão "
             "no SIMBAD nem nas listas de anãs. Para cada um, olhe as três imagens e o checklist "
             "e decida: Confirmar, Dúvida ou Descartar. A decisão fica gravada, e as confirmadas "
             "entram no relatório.")
ROTULOS = {"confirmado": "Confirmado", "duvida": "Dúvida", "descartado": "Descartado"}


@st.cache_data(show_spinner=False)
def vizier(ra: float, dec: float, pm_total: float) -> pd.DataFrame:
    return dados.buscar_vizier(ra, dec, pm_total)


def conectar() -> sqlite3.Connection:
    return sqlite3.connect(str(SQLITE_PATH))


def marcar_enviado(source_id: str):
    with conectar() as conn:
        envio.marcar_enviado(conn, source_id, st.session_state.get(f"destino_{source_id}", ""))
    st.toast(f"{source_id} marcado como enviado. Ele aparece no filtro Envio > Enviados.")


def registrar_resposta(source_id: str):
    with conectar() as conn:
        envio.registrar_resposta(
            conn, source_id, st.session_state.get(f"aceito_{source_id}") == "Aceito",
            st.session_state.get(f"resposta_{source_id}", ""),
            st.session_state.get(f"ident_{source_id}", ""))
    st.toast(f"Resposta de {source_id} registrada.")


def desfazer_envio(source_id: str):
    with conectar() as conn:
        envio.desfazer_envio(conn, source_id)


def checar_publicados(todos: pd.DataFrame, envios: pd.DataFrame):
    """Uma vez por sessao e por dia: o enviado sem resposta ja aparece no SIMBAD como ana?"""
    if st.session_state.get("checou_publicados"):
        return
    st.session_state.checou_publicados = True
    hoje = date.today().isoformat()
    abertos = envios[envios["respondido_em"].isna() & (envios["checado_em"].fillna("") != hoje)]
    for e in abertos.itertuples():
        linha = todos[todos["source_id"] == e.source_id]
        if linha.empty:
            continue
        c = linha.iloc[0]
        try:
            achado = envio.ja_no_simbad(float(c["ra"]), float(c["dec"]), float(c["pm_total"]),
                                        c.get("meanobsmjd"))
        except Exception:
            continue  # SIMBAD fora: tenta na proxima sessao
        with conectar() as conn:
            envio.marcar_checado(conn, e.source_id)
        if achado:
            st.toast(f"{e.source_id} agora aparece no SIMBAD como {achado[0]} ({achado[1]}). "
                     "Registre a resposta no painel de envio.", icon="🔭")


def marcar_marco(nome: str):
    with conectar() as conn:
        dados.marcar(conn, nome, bool(st.session_state.get(f"marco_{nome}")))


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
    else:
        # a lista encolheu: conta as decisoes para o numero da posicao seguir avancando
        st.session_state.decididos = st.session_state.get("decididos", 0) + 1
    st.session_state.subir = True


def limpar(source_id: str):
    with conectar() as conn:
        dados.apagar_revisao(conn, source_id)


def buscar():
    st.session_state.confirmar_busca = False
    if not execucao.rodando():  # clique duplo nao abre duas buscas
        execucao.iniciar()


def pedir_confirmacao(sim: bool):
    st.session_state.confirmar_busca = sim


def esquecer_busca():
    execucao.LOG.unlink(missing_ok=True)


def botao_buscar(chave: str):
    # dois passos: um clique sem querer nao dispara horas de rede e de LLM
    if st.session_state.get("confirmar_busca"):
        st.warning("A busca leva algumas horas, porque a Fase 5 chama a LLM para cada "
                   "candidato novo. Começar agora?")
        sim, nao = st.columns(2)
        sim.button("Sim, buscar", type="primary", on_click=buscar, key=f"{chave}_sim",
                   width="stretch")
        nao.button("Não", on_click=pedir_confirmacao, args=(False,), key=f"{chave}_nao",
                   width="stretch")
    else:
        st.button("Buscar mais candidatas", type="primary", on_click=pedir_confirmacao,
                  args=(True,), key=chave)
    st.caption("Escolhe sozinho uma região do céu ainda não varrida e roda o pipeline "
               "inteiro (algumas horas, por causa da triagem com LLM). Pode fechar a "
               "página: a busca continua. Pelo terminal, na pasta do projeto:")
    st.code(execucao.COMANDO, language="bash")


@st.fragment(run_every=5)
def progresso():
    if not execucao.rodando():
        st.rerun()  # terminou: recarrega a pagina inteira com os candidatos novos
    log = execucao.ler_log()
    e = execucao.estado(log)
    if not log or e["terminou"] or e["erro"] or e["cancelada"]:  # log antigo: veio do terminal
        st.info("Uma busca de candidatos está rodando, iniciada pelo terminal: o progresso "
                "aparece lá. Os candidatos novos entram na fila quando ela terminar.")
        return
    minutos = execucao.minutos_desde_inicio()
    with st.container(border=True):
        st.markdown("**Buscando mais candidatos**"
                    + (f" no campo {e['campo']}" if e["campo"] else ""))
        texto = e["fase"] or "Escolhendo o campo"
        if e["progresso"]:
            i, n = e["progresso"]
            st.progress(min(i / n, 1.0), text=f"{texto}: {i} de {n}")
        else:
            st.progress(0.0, text=texto)
        st.caption(("" if minutos is None else f"{minutos:.0f} min desde o início. ")
                   + "Pode fechar a página: a busca continua e os candidatos novos entram "
                   "na fila.")
        with st.expander("Ver o log"):
            st.code("\n".join(execucao.ler_log().splitlines()[-15:]) or "(vazio)")
        st.button("Cancelar busca", on_click=execucao.cancelar,
                  help="Encerra agora. Esta região é refeita do início na próxima busca; "
                       "suas decisões não são tocadas.")


def painel_busca(pendentes: int):
    """Busca de mais candidatos: progresso se roda; resultado da ultima; botao se a fila acabou."""
    if execucao.rodando():
        progresso()
        return
    e = execucao.estado(execucao.ler_log())
    if e["fim_da_grade"]:
        st.info("A grade de regiões do céu acabou: todas foram varridas. Para continuar, "
                "ajuste a grade em `src/campos.py`.")
    elif e["erro"]:
        st.error(f"A última busca parou ({e['erro']}). Tentar de novo refaz a mesma região.")
        botao_buscar("buscar_erro")
        return
    elif e["cancelada"]:
        st.info("Busca cancelada. A região interrompida é refeita do início na próxima busca.")
        st.button("Ok", on_click=esquecer_busca)
    elif e["terminou"]:
        st.success(f"Busca terminou{' no campo ' + e['campo'] if e['campo'] else ''}. "
                   "Os candidatos novos já estão na fila.")
        st.button("Ok", on_click=esquecer_busca)
    if pendentes == 0:
        st.success("Fila revisada: nenhum candidato pendente.")
        botao_buscar("buscar_fim")
    elif pendentes < 0:  # banco vazio: primeira busca
        botao_buscar("buscar_primeira")


# ---------------------------------------------------------------- dados
try:
    with conectar() as conn:
        todos = dados.carregar_candidatos(conn)
except Exception:
    # primeiro uso: ainda nao ha banco; quem instalou pelo iniciador nao tem terminal
    todos = pd.DataFrame()

if todos.empty:
    estilo.cabecalho("Revisão visual", (0, 0), descricao=DESCRICAO)
    if not execucao.rodando():
        st.info("Ainda não há candidatos. A primeira busca baixa uma região do céu do "
                "CatWISE2020, filtra e descarta os objetos já conhecidos; os que sobram "
                "aparecem aqui. Enquanto ela roda, faça o Treino para aprender a revisar.")
    painel_busca(-1)
    st.stop()

todos["decisao"] = todos["decisao"].fillna("pendente")
pendentes = int((todos["decisao"] == "pendente").sum())
estilo.cabecalho("Revisão visual", (int((todos["decisao"] != "pendente").sum()), len(todos)),
                 descricao=DESCRICAO)
with conectar() as conn:
    estilo.trilha_html(dados.marcos(conn))
    manuais = dados.ler_marcos_manuais(conn)
with st.expander("Marcar segunda opinião e publicação"):
    for nome in dados.MARCOS_MANUAIS:
        st.checkbox(nome, value=nome in manuais, key=f"marco_{nome}",
                    on_change=marcar_marco, args=(nome,))
painel_busca(pendentes)
if pendentes and not execucao.rodando():
    with st.sidebar.expander("Buscar mais candidatas"):
        st.caption(f"Ainda há {pendentes} pendente(s): o ideal é revisar antes.")
        botao_buscar("buscar_lateral")
todos, erros_cruz = cruzamento.completar(todos, "a fila", "candidato")
todos["allwise_ordem"] = todos["allwise_status"].map(ALLWISE_ORDEM).fillna(2)

todos["decisao"] = todos["decisao"].fillna("pendente")
with conectar() as conn:
    envios = envio.ler_envios(conn)
_envios = {e["source_id"]: e for e in envios.to_dict("records")}
todos["envio"] = [envio.situacao_envio(d, _envios.get(s))
                  for s, d in zip(todos["source_id"], todos["decisao"])]
checar_publicados(todos, envios)

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
OPCOES_ENVIO = {"Qualquer": None, "A enviar": "a enviar", "Enviados": "enviado",
                "Aceitos": "aceito", "Recusados": "recusado"}
sel_envio = st.sidebar.selectbox(
    "Envio", list(OPCOES_ENVIO), key="envio_filtro",
    help="Confirmados a enviar a um astrônomo e os já enviados. Fora de 'Qualquer', vale no "
         "lugar da Situação.")
# Abre em "Sem Gaia" so enquanto houver pendente sem Gaia; senao a fila abria vazia.
_sem_gaia_pendente = bool(((todos["decisao"] == "pendente") & (todos["gaia_detectada"] == False)).any())  # noqa: E712
gaia = st.sidebar.radio("Contraparte no Gaia", ["Qualquer", "Sem Gaia", "Com Gaia"],
                        index=1 if _sem_gaia_pendente else 0,
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
    base = (todos["decisao"].isin(sel_decisao) if OPCOES_ENVIO[sel_envio] is None
            else todos["envio"] == OPCOES_ENVIO[sel_envio])
    fila = todos[base & (todos["pm_signif"] >= sig_min)
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

assinatura = (busca, tuple(sel_decisao), sel_envio, gaia, ps1, allwise, sig_min, tuple(sel_scores), ordem)
if st.session_state.get("assinatura") != assinatura:
    st.session_state.assinatura = assinatura
    st.session_state.pos = 0
    st.session_state.decididos = 0
    st.session_state.sel_aplicada = None
st.session_state.setdefault("pos", 0)

# Clique numa linha da tabela da fila: abre aquele candidato (so quando a selecao muda,
# pra nao brigar com os botoes Anterior/Proximo).
_tab = st.session_state.get("tabela_fila")
_linhas = list(_tab["selection"]["rows"]) if _tab else []
if _linhas and _linhas != st.session_state.get("sel_aplicada") and _linhas[0] < total:
    st.session_state.pos = _linhas[0]
    st.session_state.sel_aplicada = _linhas

# ---------------------------------------------------------------- tela
for e in erros_cruz:
    st.warning(f"Sem cruzamento, {e}")
if total == 0:
    escondidos = pendentes if not busca and "pendente" in sel_decisao else 0
    if escondidos:
        st.info(f"Nenhum candidato na fila com esses filtros. Os {escondidos} pendente(s) estão "
                "escondidos pelos filtros da lateral (o de Gaia começa em 'Sem Gaia'): "
                "ponha 'Qualquer' para vê-los.")
    else:
        st.info("Nenhum candidato na fila com esses filtros.")
    st.stop()

st.session_state.pos = max(0, min(total - 1, st.session_state.pos))
r = fila.iloc[st.session_state.pos]
sid = r["source_id"]

estilo.ancora_caso()
if st.session_state.pop("subir", False):
    estilo.subir_ao_caso()
nav = st.columns([1, 1, 6])
nav[0].button("◀ Anterior", on_click=mover, args=(-1, total), disabled=st.session_state.pos == 0,
              width="stretch")
nav[1].button("Próximo ▶", on_click=mover, args=(+1, total),
              disabled=st.session_state.pos >= total - 1, width="stretch")
_ja = st.session_state.get("decididos", 0)
nav[2].markdown(f"**{_ja + st.session_state.pos + 1} de {_ja + total}** na fila  |  `{sid}`  |  "
                f"RA {r['ra']:.5f}, Dec {r['dec']:+.5f}")

try:
    _casos = guia.casos_de_treino()
except Exception:  # sem data/recall_conhecidas.pkl o guia fica so com o roteiro
    _casos = None
completar_guia = guia.mostrar_guia(_casos, aberto=False)
completar_animacao = imagens.mostrar(float(r["ra"]), float(r["dec"]),
                                     [f"**{t}.** {q}" for t, q in guia.ROTEIRO.values()])
_pos = st.session_state.pos
imagens.pre_carregar([(float(x.ra), float(x.dec)) for x in fila.iloc[_pos + 1:_pos + 4].itertuples()])
st.caption("Recortes de 60\" x 60\", norte pra cima e leste à esquerda. A mira verde marca a "
           "posição do CatWISE (~2015). Um objeto real e próximo aparece no infravermelho; "
           "um ponto só no óptico é fonte comum. Na animação, as fontes aparecem escuras e cada quadro é uma época do W2 "
           "(WiseView) e o ano está no canto. Imagens: unWISE (NASA/WISE), Legacy Surveys (DESI) "
           "e WiseView.")
st.markdown(f"[Abrir no Legacy Surveys]({dados.link_legacy_viewer(r['ra'], r['dec'])})  |  "
            f"[WiseView (para dúvidas: campo maior, contraste e diferença entre épocas)]({dados.link_wiseview(r['ra'], r['dec'])})")

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

# ---------------------------------------------------------------- envio (conferencia e resposta)
if r["decisao"] == "confirmado" or r["envio"]:
    with conectar() as conn:
        viz = envio.ler_vizier(conn, sid)
    e = _envios.get(sid)
    with st.expander("Enviar a um astrônomo: conferência e acompanhamento",
                     expanded=r["envio"] == "a enviar"):
        itens_envio = envio.pendencias(r.to_dict(), viz, enviado=r["envio"] == "enviado")
        if envio.pode_enviar(itens_envio):
            st.success("**Pode enviar.** Conferido: "
                       + ", ".join(i["titulo"].lower() for i in itens_envio) + ".")
        else:
            st.warning("**Ainda não envie.** " + envio.proximo_passo(itens_envio))
        st.markdown("\n".join(f"- {envio.ICONES[i['nivel']]} **{i['titulo']}**: {i['texto']}"
                              for i in itens_envio))
        if viz is None or viz.attrs.get("parcial"):
            if st.button("Buscar no VizieR", key=f"vizier_envio_{sid}"):
                with st.spinner("Consultando o VizieR (20 s a 1 min)..."):
                    try:
                        achados = vizier(float(r["ra"]), float(r["dec"]), float(r["pm_total"]))
                        with conectar() as conn:
                            envio.salvar_vizier(conn, sid, achados)
                        st.rerun()
                    except Exception as erro:
                        st.error(f"VizieR falhou: {erro}")
        st.markdown("**Resumo em inglês**, para colar no e-mail ou no formulário:")
        st.code(envio.resumo_ingles(r.to_dict(), viz), language=None)
        if not e:
            st.text_input("Para quem ou onde vai enviar",
                          placeholder="ex.: e-mail a um astrônomo, fórum do Backyard Worlds",
                          key=f"destino_{sid}")
            bloqueado = any(i["nivel"] == "bloqueia" for i in itens_envio)
            st.button("Marquei como enviado hoje", on_click=marcar_enviado, args=(sid,),
                      disabled=bloqueado or not st.session_state.get(f"destino_{sid}", "").strip(),
                      help="Desligado enquanto algum item da conferência bloqueia.")
        elif r["envio"] == "enviado":
            st.info(f"Enviado em {e['enviado_em']} para {e['destino']}. O app confere no SIMBAD, "
                    "uma vez por dia, se o objeto já apareceu como anã.")
            st.radio("Resposta", ["Aceito", "Recusado"], horizontal=True, key=f"aceito_{sid}",
                     help="Aceito: a segunda opinião confirmou, ou o objeto foi publicado.")
            st.text_input("O que responderam (opcional)", key=f"resposta_{sid}")
            st.text_input("Identificador externo (opcional)", placeholder="ex.: nome no catálogo",
                          key=f"ident_{sid}")
            esq, dir_ = st.columns(2)
            esq.button("Registrar resposta", type="primary", on_click=registrar_resposta,
                       args=(sid,), key=f"resp_{sid}")
            dir_.button("Desfazer envio", on_click=desfazer_envio, args=(sid,), key=f"desf_{sid}")
        else:
            texto = (f"Resposta em {e['respondido_em']}: **{'aceito' if r['envio'] == 'aceito' else 'recusado'}**"
                     + (f". {e['resposta']}" if e.get("resposta") else "")
                     + (f" ({e['identificador']})" if e.get("identificador") else ""))
            (st.success if r["envio"] == "aceito" else st.error)(texto)
            st.button("Desfazer envio", on_click=desfazer_envio, args=(sid,), key=f"desf_{sid}")

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
        aguarde = st.empty()
        aguarde.markdown(imagens.carregando("Consultando o VizieR inteiro (20 s a 1 min)", False),
                         unsafe_allow_html=True)
        try:
            achados = vizier(float(r["ra"]), float(r["dec"]), float(r["pm_total"]))
            with conectar() as conn:
                envio.salvar_vizier(conn, sid, achados)
            aguarde.empty()
            anas = achados[achados["lista_anas"]]
            if achados.attrs.get("parcial"):
                st.info(dados.AVISO_VIZIER_PARCIAL)
            if anas.empty:
                st.success(dados.resumo_vizier(achados))
            else:
                st.warning(f"Aparece em {len(anas)} lista(s) de anãs ou de movimento próprio. "
                           "Confira se é o mesmo objeto (distância pequena) antes de confirmar.")
            st.dataframe(achados, hide_index=True, width="stretch")
        except Exception as e:
            aguarde.empty()
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
3. **Anã L2 conhecida, do próprio campo varrido.** Bolha nítida no infravermelho e um pontinho vermelho no óptico, os dois logo abaixo da mira: a posição do catálogo é de 2000 e o objeto andou desde então. Um suspeito com essa cara vale levar ao WiseView.""",
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

# a animacao do WiseView e a parte lenta: carrega por ultimo
completar_animacao()
completar_guia()
