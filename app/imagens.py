"""Recortes e animacao de movimento, compartilhados pelas paginas Streamlit."""

import io

import httpx
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageOps

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


@st.cache_data(show_spinner="Buscando as épocas no WiseView (até 1 min)...")
def _animacao(ra: float, dec: float, tamanho_px: int = 24) -> bytes:
    """Quadros do W2 por época em 330 px, com a mira e o ano escrito (500 ms cada, em loop)."""
    fonte = ImageFont.load_default(size=26)
    quadros = []
    for ano, img in dados.epocas_blink(ra, dec, tamanho_px):
        # o brilho fixo do WiseView deixa fonte fraca quase invisivel; contraste por quadro
        q = ImageOps.autocontrast(img.convert("L"), cutoff=1).convert("RGB").resize((LADO, LADO), Image.NEAREST)
        _mira(q)
        ImageDraw.Draw(q).text((6, 6), f"{ano:.1f}", fill=(0, 255, 0), font=fonte)
        quadros.append(q)
    if not quadros:
        raise ValueError("sem épocas para animar")
    saida = io.BytesIO()
    quadros[0].save(saida, format="GIF", save_all=True, append_images=quadros[1:],
                    duration=500, loop=0, disposal=2)
    return saida.getvalue()


def mostrar(ra: float, dec: float) -> None:
    """Os dois recortes e a animacao lado a lado, com legenda e aviso de falha."""
    colunas = st.columns(len(CAMADAS) + 1)
    for coluna, (camada, titulo) in zip(colunas, CAMADAS):
        coluna.caption(titulo)
        img = recorte(ra, dec, camada)
        if img is None:
            coluna.warning("Recorte indisponível (servidor fora do ar ou sem cobertura).")
        else:
            coluna.image(img, width="stretch")
    colunas[-1].caption("Movimento (unWISE W2 por época, WiseView)")
    gif = animacao(ra, dec)
    if gif is None:
        colunas[-1].warning("Animação indisponível (servidor do WiseView fora do ar).")
    else:
        colunas[-1].image(gif, width="stretch")
