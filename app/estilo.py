"""Estilo e componentes visuais compartilhados pelas paginas Streamlit."""

import html

import streamlit as st

from app import dados

PROJECT = "Rastro"
ICON = "🔭"
TAGLINE = "Anãs marrons e estrelas frias perto do Sol, no CatWISE2020"
ACCENT = "#FF8A3D"

_ROTULOS_SUGESTAO = {"confirmado": "Confirmado", "duvida": "Dúvida", "descartado": "Descartado"}

_CSS = """
:root {
    --rastro-acento: __ACCENT__;
    --rastro-fundo: #0B0F17;
    --rastro-cartao: #151B26;
    --rastro-texto: #E6E9EF;
    --rastro-suave: #9AA4B5;
    --rastro-borda: #232C3B;
}
.block-container { padding-top: 1rem; max-width: 1400px; }
/* texto branco sobre o laranja fica com pouco contraste */
button[kind="primary"], button[kind="primary"] p { color: var(--rastro-fundo) !important; font-weight: 600; }
[data-testid="stAppDeployButton"], #MainMenu { display: none; }
[data-testid="stMetricValue"] { font-size: 1.15rem; }
[data-testid="stSidebar"] h2 {
    font-size: .8rem; text-transform: uppercase; letter-spacing: .08em; color: var(--rastro-suave);
}
.rastro-cabecalho {
    display: flex; align-items: center; justify-content: space-between; gap: 1.5rem;
    padding: .9rem 1.2rem; margin-bottom: .8rem;
    background: var(--rastro-cartao); border: 1px solid var(--rastro-borda); border-radius: 12px;
}
.rastro-marca { display: flex; flex-direction: column; gap: .1rem; }
.rastro-nome {
    font-size: 1.6rem; font-weight: 700; color: var(--rastro-acento); line-height: 1.2;
}
.rastro-tagline { margin-left: .7rem; font-size: .85rem; color: var(--rastro-suave); }
.rastro-subtitulo { font-size: .95rem; color: var(--rastro-texto); }
.rastro-trilha { display: flex; align-items: flex-start; background: var(--rastro-cartao);
  border: 1px solid var(--rastro-borda); border-radius: .8rem; padding: .55rem .4rem;
  margin-bottom: .8rem; }
.rastro-etapa { flex: 1; min-width: 0; text-align: center; padding: 0 .35rem; position: relative; }
.rastro-etapa + .rastro-etapa::before { content: ""; position: absolute; top: .36rem; left: -50%;
  width: 100%; height: 2px; background: var(--rastro-borda); }
.rastro-etapa.feito::before { background: var(--rastro-acento); }
.rastro-ponto { width: .72rem; height: .72rem; border-radius: 50%; margin: 0 auto .3rem;
  border: 2px solid var(--rastro-suave); position: relative; z-index: 1; }
.rastro-etapa.feito .rastro-ponto { background: var(--rastro-acento); border-color: var(--rastro-acento); }
.rastro-etapa-nome { font-size: .76rem; font-weight: 600; }
.rastro-etapa-detalhe { color: var(--rastro-suave); font-size: .68rem; overflow-wrap: anywhere; }
.rastro-descricao { font-size: .85rem; color: var(--rastro-suave); margin-top: .2rem; max-width: 46rem; }
.rastro-progresso { min-width: 190px; text-align: right; }
.rastro-progresso-texto {
    font-size: .85rem; color: var(--rastro-texto); margin-bottom: .35rem; white-space: nowrap;
}
.rastro-barra { height: 4px; border-radius: 2px; background: var(--rastro-borda); overflow: hidden; }
.rastro-barra > span { display: block; height: 100%; background: var(--rastro-acento); }
.rastro-ficha {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: .5rem; margin-bottom: .8rem;
}
.rastro-ficha-item {
    background: var(--rastro-cartao); border: 1px solid var(--rastro-borda);
    border-radius: 10px; padding: .5rem .65rem;
}
.rastro-rotulo {
    font-size: .68rem; text-transform: uppercase; letter-spacing: .06em;
    color: var(--rastro-suave);
}
.rastro-valor {
    font-size: 1.15rem; font-weight: 600; color: var(--rastro-texto);
    line-height: 1.25; overflow-wrap: anywhere;
}
.rastro-detalhe { font-size: .72rem; color: var(--rastro-suave); }
.rastro-checklist {
    background: var(--rastro-cartao); border: 1px solid var(--rastro-borda);
    border-radius: 10px; padding: .6rem .8rem;
}
.rastro-checklist-item { font-size: .82rem; line-height: 1.45; margin-bottom: .18rem; }
.rastro-checklist-item strong { color: var(--rastro-texto); }
.rastro-checklist-item span { color: var(--rastro-suave); }
.rastro-pilula {
    display: inline-block; margin-top: .45rem; padding: .12rem .55rem;
    border-radius: 999px; font-size: .75rem; font-weight: 600;
}
.rastro-pilula-confirmado { background: rgba(63, 185, 80, .16); color: #56D364; }
.rastro-pilula-duvida { background: rgba(210, 153, 34, .18); color: #E3B341; }
.rastro-pilula-descartado { background: rgba(248, 81, 73, .16); color: #FF7B72; }
.rastro-nota { font-size: .7rem; color: var(--rastro-suave); margin-top: .35rem; }
"""


def css() -> str:
    """CSS global do app, com as cores do tema definidas uma vez nas variaveis."""
    return f"<style>{_CSS.replace('__ACCENT__', ACCENT)}</style>"


def _numero(valor) -> str:
    """Numero com virgula decimal, sem casa decimal quando ela e zero."""
    if isinstance(valor, float) and not valor.is_integer():
        return f"{valor:.1f}".replace(".", ",")
    return str(int(valor))


def cabecalho(subtitulo: str, progresso: tuple[int, int] | None = None,
              rotulo_progresso: str = "{atual} de {total} revisados", descricao: str = "") -> None:
    """Banner do topo: marca, tagline, subtitulo, descricao da pagina e progresso com barra."""
    partes = [
        '<div class="rastro-cabecalho">',
        '<div class="rastro-marca">',
        f'<div><span class="rastro-nome">{ICON} {PROJECT}</span>'
        f'<span class="rastro-tagline">{html.escape(TAGLINE)}</span></div>',
        f'<div class="rastro-subtitulo">{html.escape(subtitulo)}</div>',
        f'<div class="rastro-descricao">{html.escape(descricao)}</div>' if descricao else "",
        '</div>',
    ]
    if progresso:
        atual, total = progresso
        texto = rotulo_progresso.format(atual=_numero(atual), total=_numero(total))
        pct = 100 * atual / total if total else 0
        partes.append(
            '<div class="rastro-progresso">'
            f'<div class="rastro-progresso-texto">{html.escape(texto)}</div>'
            f'<div class="rastro-barra"><span style="width: {max(0, min(100, pct)):.1f}%"></span>'
            '</div></div>')
    partes.append('</div>')
    st.markdown("".join(partes), unsafe_allow_html=True)


def ficha(itens: list[tuple[str, str, str | None]]) -> None:
    """Grade compacta de cartoes (rotulo, valor, detalhe opcional). O valor nunca e cortado."""
    cartoes = []
    for rotulo, valor, detalhe in itens:
        extra = f'<div class="rastro-detalhe">{html.escape(detalhe)}</div>' if detalhe else ""
        cartoes.append(
            '<div class="rastro-ficha-item">'
            f'<div class="rastro-rotulo">{html.escape(rotulo)}</div>'
            f'<div class="rastro-valor">{html.escape(str(valor))}</div>{extra}</div>')
    st.markdown(f'<div class="rastro-ficha">{"".join(cartoes)}</div>', unsafe_allow_html=True)


def checklist_html(itens: list[dict], sugestao: str) -> None:
    """Checklist em linhas compactas, com a sugestao do pipeline numa pilula colorida."""
    linhas = []
    for item in itens:
        icone = dados.ICONES_CHECKLIST.get(item["estado"], "")
        linhas.append(
            '<div class="rastro-checklist-item">'
            f'{icone} <strong>{html.escape(item["titulo"])}</strong> '
            f'<span>{html.escape(item["explicacao"])}</span></div>')
    chave = sugestao if sugestao in _ROTULOS_SUGESTAO else "duvida"
    st.markdown(
        '<div class="rastro-checklist">' + "".join(linhas)
        + f'<div><span class="rastro-pilula rastro-pilula-{chave}">Sugestão do pipeline: '
          f'{_ROTULOS_SUGESTAO[chave]}</span></div>'
          '<div class="rastro-nota">Ela só vale se os dois testes humanos passarem: tem um ponto '
          'nítido no infravermelho, dentro da mira? e na animação o ponto anda sempre na mesma '
          'direção?</div></div>',
        unsafe_allow_html=True)


def trilha_html(marcos: list[dict]) -> None:
    etapas = "".join(
        f'<div class="rastro-etapa{" feito" if m["feito"] else ""}"><div class="rastro-ponto"></div>'
        f'<div class="rastro-etapa-nome">{html.escape(str(m["nome"]))}</div>'
        f'<div class="rastro-etapa-detalhe">{html.escape(str(m["detalhe"]))}</div></div>'
        for m in marcos)
    st.markdown(f'<div class="rastro-trilha">{etapas}</div>', unsafe_allow_html=True)
