"""Gera docs/img/funil_fases.png (quantas fontes sobram em cada fase) a partir do banco.

Rodar da raiz do repositorio, depois de uma varredura:

    python tools/gerar_funil.py
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config

SAIDA = ROOT / "docs" / "img" / "funil_fases.png"
CONSULTAS = [
    ("Fase 2\nbaixadas do CatWISE", "SELECT COUNT(*) FROM campo_bruto"),
    ("Fase 3\napós filtro de qualidade", "SELECT COUNT(*) FROM candidatos_fase3"),
    ("Fase 4\napós descartar conhecidas",
     "SELECT COUNT(*) FROM candidatos_fase4 WHERE status = 'candidato'"),
]


def main():
    with sqlite3.connect(str(config.SQLITE_PATH)) as conn:
        valores = [conn.execute(q).fetchone()[0] for _, q in CONSULTAS]
    rotulos = [r for r, _ in CONSULTAS]

    fig, ax = plt.subplots(figsize=(9, 4))
    cores = ["#6c8ebf", "#3f6ea8", "#24476e"]
    ax.barh(rotulos[::-1], valores[::-1], color=cores[::-1])
    for i, v in enumerate(valores[::-1]):
        ax.text(v + max(valores) * 0.01, i, f"{v:,}".replace(",", "."), va="center",
                fontsize=14, fontweight="bold")
    ra, dec = config.FIELD_RA_RANGE, config.FIELD_DEC_RANGE
    area = (ra[1] - ra[0]) * (dec[1] - dec[0])
    ax.set_title(f"A peneira na varredura de {area:g} graus quadrados\n"
                 f"(RA {ra[0]:g} a {ra[1]:g}°, Dec {dec[0]:+g} a {dec[1]:+g}°)")
    ax.set_xlabel("fontes que sobram")
    ax.set_xlim(0, max(valores) * 1.2)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(SAIDA, dpi=100)
    print(f"salvo {SAIDA}: {valores}")


if __name__ == "__main__":
    main()
