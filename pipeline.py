import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from config import FIELD_DEC_RANGE, FIELD_RA_RANGE, SQLITE_PATH
from src import campos
from src.sanity_check import run as fase1
from src.fetch_field import run as fase2
from src.quality_filter import run as fase3
from src.known_catalog_match import run as fase4
from src.llm_triage import run as fase5


def run_all(campo: dict | None = None):
    resultado = {}
    fases = [
        ("Fase 1 - Sanity check", fase1),
        ("Fase 2 - Fetch field", lambda: resultado.update(campo=fase2(campo))),
        ("Fase 3 - Quality filter", lambda: resultado.update(candidatos=len(fase3()))),
        ("Fase 4 - SIMBAD cross-match", fase4),
        ("Fase 5 - LLM triage", fase5),
    ]

    for nome, fn in fases:
        print(f"\n{'=' * 60}")
        print(f"  Executando: {nome}")
        print(f"{'=' * 60}")
        try:
            fn()
        except Exception as e:
            print(f"\nERRO em {nome}: {e}")
            sys.exit(1)

    # so campo completo entra em campos_feitos: o que falhou volta na proxima rodada
    # o campo do config usa o mesmo nome da grade: senao o --proximo o escolheria de novo
    feito = campo or {"nome": campos._nome(*FIELD_RA_RANGE, *FIELD_DEC_RANGE),
                      "ra_min": FIELD_RA_RANGE[0], "ra_max": FIELD_RA_RANGE[1],
                      "dec_min": FIELD_DEC_RANGE[0], "dec_max": FIELD_DEC_RANGE[1]}
    with sqlite3.connect(SQLITE_PATH) as con:
        campos.registrar(con, feito, resultado.get("candidatos"))
    print(f"\n  Campo {feito['nome']} registrado em campos_feitos.")
    print("  Revisao: streamlit run app/revisao.py")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Pipeline do Rastro (fases 1 a 5)")
    ap.add_argument("--proximo", action="store_true",
                    help="escolhe sozinho o proximo campo do ceu ainda nao varrido")
    a = ap.parse_args()
    campo = None
    if a.proximo:
        with sqlite3.connect(SQLITE_PATH) as con:
            feitos = campos.ler_feitos(con)
        print(f"  {len(feitos)} campo(s) ja feito(s). Procurando o proximo...")
        campo = campos.proximo(feitos)
        if campo is None:
            print("  A grade de campos acabou: todos os pontos de src/campos.py foram "
                  "varridos. Para continuar, ajuste a grade em src/campos.py.")
            sys.exit(0)
        print(f"  Proximo campo: {campo['nome']} (RA {campo['ra_min']}-{campo['ra_max']}, "
              f"Dec {campo['dec_min']:+.0f} a {campo['dec_max']:+.0f})")
    run_all(campo)
