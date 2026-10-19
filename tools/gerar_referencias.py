"""Gera as folhas de referencia da revisao visual (docs/img/ref_*.jpg).

Cada linha mostra um caso nos mesmos 2 recortes do app (unWISE NEO7 e Legacy
Surveys DR10). Os casos "conhecida" sao anas L/T/Y ja catalogadas; os
demais sao candidatos reais da varredura de RA 148 a 153, Dec +18 a +23,
classificados a olho. Usa rede (Legacy Surveys). Rodar da raiz do repositorio:

    python tools/gerar_referencias.py
"""

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx
from PIL import Image, ImageDraw

from app import dados

CAMADAS = ["unwise-neo7", "ls-dr10"]
LADO = 280

# (ra, dec, rotulo)
CASOS = {
    "confirmar": [
        (52.16177, 1.92045, "Conhecida: ana L5 (WISEA J0328+0155)"),
        (247.162496, 23.138284, "Conhecida: ana T7 (2MASS J1628+2308)"),
        # candidato confirmado fica fora do repositorio publico ate a segunda opiniao
        (149.711708, 20.03125, "Conhecida: ana L2 (2MASS J0958+2001)"),
    ],
    "duvida": [
        (113.680876, -71.962338, "Conhecida: ana Y0 (WISE J0734-7157)"),
        (148.803558, 20.59613, "Suspeito: IR fraco, nada no optico (1)"),
        (149.038225, 21.709273, "Suspeito: IR fraco, nada no optico (2)"),
        (152.815742, 18.53822, "Suspeito: IR fraco, nada no optico (3)"),
    ],
    "descartar": [
        (152.498321, 22.255111, "Suspeito: nada no infravermelho"),
        (151.461587, 19.311219, "Suspeito: estrela clara no optico"),
        (148.989767, 19.42659, "Suspeito: galaxia no optico"),
        (151.514113, 22.673841, "Suspeito: estrela brilhante e saturada"),
    ],
}


def recorte(ra: float, dec: float, camada: str) -> Image.Image:
    for _ in range(3):
        try:
            r = httpx.get(dados.url_recorte(ra, dec, camada), timeout=30)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            break
        except Exception:
            img = None
    if img is None:
        return Image.new("RGB", (LADO, LADO))
    img = img.resize((LADO, LADO), Image.NEAREST if img.size[0] < 100 else Image.LANCZOS)
    d = ImageDraw.Draw(img)
    c, gap, tick = LADO // 2, LADO // 10, LADO // 7
    for a in [(c, c - gap - tick, c, c - gap), (c, c + gap, c, c + gap + tick),
              (c - gap - tick, c, c - gap, c), (c + gap, c, c + gap + tick, c)]:
        d.line(a, fill=(0, 255, 0), width=2)
    return img


def folha(casos, destino: Path):
    faixa = 22
    folha = Image.new("RGB", (len(CAMADAS) * (LADO + 4) - 4, len(casos) * (LADO + faixa + 4)), (0, 0, 0))
    d = ImageDraw.Draw(folha)
    for i, (ra, dec, rotulo) in enumerate(casos):
        y = i * (LADO + faixa + 4)
        d.text((6, y + 5), rotulo, fill=(255, 255, 0))
        for j, camada in enumerate(CAMADAS):
            folha.paste(recorte(ra, dec, camada), (j * (LADO + 4), y + faixa))
    folha.save(destino, quality=88)
    print(f"salvo {destino}")


if __name__ == "__main__":
    for nome, casos in CASOS.items():
        folha(casos, ROOT / "docs" / "img" / f"ref_{nome}.jpg")
