"""Recortes e animacao de movimento, compartilhados pelas paginas Streamlit."""

import io

import httpx
import streamlit as st
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app import dados

LADO = 330

# NEO7 empilha todas as epocas do WISE (2010 a 2020), entao nao mostra movimento:
# camadas mais antigas (NEO2, NEO4) sao quase identicas a ela. Movimento se ve na
# animacao do W2 por epoca e no teste do AllWISE.
CAMADAS = [
    ("unwise-neo7", "Infravermelho (unWISE NEO7, W1+W2)"),
    ("ls-dr10", "Óptico (Legacy Surveys DR10, grz)"),
]


def recorte(ra: float, dec: float, camada: str):
    """Recorte com a mira, ou None se o servidor falhar (a falha nao fica no cache)."""
    try:
        return _recorte(ra, dec, camada)
    except Exception:
        return None


def _mira(img: Image.Image) -> Image.Image:
    """Mira verde no centro, com folga (mesmo desenho no recorte e na animacao)."""
    d = ImageDraw.Draw(img)
    c, gap, tick = LADO // 2, LADO // 10, LADO // 7
    for x0, y0, x1, y1 in [(c, c - gap - tick, c, c - gap), (c, c + gap, c, c + gap + tick),
                           (c - gap - tick, c, c - gap, c), (c + gap, c, c + gap + tick, c)]:
        d.line((x0, y0, x1, y1), fill=(0, 255, 0), width=2)
    return img


@st.cache_data(show_spinner=False)
def _recorte(ra: float, dec: float, camada: str):
    """Baixa o recorte e marca a posicao do candidato (mira com folga no centro)."""
    url = dados.url_recorte(ra, dec, camada)
    for tentativa in range(2):
        try:
            r = httpx.get(url, timeout=30)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            break
        except Exception:
            if tentativa == 1:
                raise
    img = img.resize((LADO, LADO), Image.NEAREST if img.size[0] < 100 else Image.LANCZOS)
    return _mira(img)


def animacao(ra: float, dec: float, tamanho_px: int = 24):
    """GIF do movimento, ou None se o WiseView falhar (a falha nao fica no cache)."""
    try:
        return _animacao(ra, dec, tamanho_px)
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def _animacao(ra: float, dec: float, tamanho_px: int = 24) -> bytes:
    """Quadros do W2 por época em 330 px, com a mira e o ano escrito (500 ms cada, em loop)."""
    fonte = ImageFont.load_default(size=26)
    quadros = []
    epocas = dados.epocas_blink(ra, dec, tamanho_px)
    # o brilho fixo do WiseView some com fonte fraca, e contraste por quadro vira chuvisco:
    # esticamento unico para a pilha toda e suavizacao leve antes de ampliar
    pilha = np.stack([np.asarray(img.convert("L"), dtype=float) for _, img in epocas]) if epocas else None
    lo, hi = np.percentile(pilha, [1, 99.5]) if pilha is not None else (0, 1)
    for (ano, _), px in zip(epocas, pilha if pilha is not None else []):
        q = Image.fromarray(np.clip((px - lo) / max(hi - lo, 1e-6) * 255, 0, 255).astype("uint8"))
        q = q.filter(ImageFilter.GaussianBlur(0.8)).resize((LADO, LADO), Image.BICUBIC).convert("RGB")
        _mira(q)
        ImageDraw.Draw(q).text((6, 6), f"{ano:.1f}", fill=(0, 255, 0), font=fonte)
        quadros.append(q)
    if not quadros:
        raise ValueError("sem épocas para animar")
    saida = io.BytesIO()
    # 900 ms por epoca e pausa no ultimo quadro, pra dar tempo de seguir o ponto
    duracoes = [900] * (len(quadros) - 1) + [1800]
    quadros[0].save(saida, format="GIF", save_all=True, append_images=quadros[1:],
                    duration=duracoes, loop=0, disposal=2)
    return saida.getvalue()


def carregando(texto: str, quadrado: bool = True) -> str:
    """HTML de "carregando" (circulo girando e texto), no lugar de conteudo que vem da rede."""
    forma = "aspect-ratio:1;" if quadrado else "min-height:120px;"
    return (f'<div style="{forma}display:flex;flex-direction:column;align-items:center;'
            'justify-content:center;gap:12px;border:1px solid #232C3B;border-radius:6px;'
            'background:#151B26;color:#9AA4B5;font-size:0.9rem;text-align:center;padding:12px">'
            '<div style="width:36px;height:36px;border:3px solid #232C3B;border-top-color:#FF8A3D;'
            'border-radius:50%;animation:giro 0.9s linear infinite"></div>'
            f'{texto}</div><style>@keyframes giro{{to{{transform:rotate(360deg)}}}}</style>')


def mostrar(ra: float, dec: float):
    """Os tres quadros com "carregando" na hora; devolve a funcao que baixa e preenche.

    A pagina chama a funcao no fim, pra numeros, checklist e botoes aparecerem antes:
    recortes levam alguns segundos e o WiseView ate 1 min na primeira vez.
    """
    colunas = st.columns(len(CAMADAS) + 1)
    lugares = []
    for coluna, titulo, texto in zip(
            colunas, [t for _, t in CAMADAS] + ["Movimento (unWISE W2 por época, WiseView)"],
            ["Carregando o recorte"] * len(CAMADAS) + ["Carregando o movimento<br>(WiseView, até 1 min)"]):
        coluna.caption(titulo)
        lugar = coluna.empty()
        lugar.markdown(carregando(texto), unsafe_allow_html=True)
        lugares.append(lugar)

    def completar():
        for lugar, (camada, _) in zip(lugares, CAMADAS):
            img = recorte(ra, dec, camada)
            if img is None:
                lugar.warning("Recorte indisponível (servidor fora do ar ou sem cobertura).")
            else:
                lugar.image(img, width="stretch")
        gif = animacao(ra, dec)
        if gif is None:
            lugares[-1].warning("Animação indisponível (servidor do WiseView fora do ar).")
        else:
            lugares[-1].image(gif, width="stretch")
    return completar
