"""Extrai as posicoes das 3.086 candidatas L/T de Schneider et al. 2026 (AJ 171, 341).

A tabela ainda nao esta no VizieR; o arquivo Table1.mrt vem no codigo-fonte do arXiv
(2604.01323). A designacao CatWISE2020 (Jhhmmss.ss+ddmmss.s) da a posicao na epoca do
CatWISE, a mesma das colunas ra/dec do pipeline. Grava catalogos/schneider2026.csv, que vai
no git para a Fase 4 nao depender da rede. Quando a tabela entrar no VizieR, troque por ela
em CATALOGOS_ANAS e apague o CSV.

    python tools/baixar_schneider2026.py
"""

import io
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ROOT

URL = "https://arxiv.org/e-print/2604.01323"
SAIDA = ROOT / "catalogos" / "schneider2026.csv"
DESIGNACAO = re.compile(r"J(\d\d)(\d\d)(\d\d\.\d\d)([+-])(\d\d)(\d\d)(\d\d\.\d)")


def posicao(nome: str) -> tuple[float, float]:
    h, m, s, sinal, d, dm, ds = DESIGNACAO.match(nome).groups()
    ra = 15 * (int(h) + int(m) / 60 + float(s) / 3600)
    dec = int(d) + int(dm) / 60 + float(ds) / 3600
    return ra, dec if sinal == "+" else -dec


def main():
    print(f"Baixando {URL} ...")
    req = urllib.request.Request(URL, headers={"User-Agent": "rastro-pipeline"})
    with urllib.request.urlopen(req, timeout=120) as r:
        dados = r.read()
    with tarfile.open(fileobj=io.BytesIO(dados), mode="r:gz") as tar:
        mrt = tar.extractfile("Table1.mrt").read().decode("utf-8")
    nomes = [l.split("\t")[0].strip() for l in mrt.splitlines() if DESIGNACAO.match(l)]
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    with open(SAIDA, "w", encoding="utf-8") as f:
        f.write("nome,ra,dec\n")
        for n in nomes:
            ra, dec = posicao(n)
            f.write(f"CWISE {n},{ra:.6f},{dec:.6f}\n")
    print(f"{len(nomes)} objetos em {SAIDA}")


if __name__ == "__main__":
    main()
