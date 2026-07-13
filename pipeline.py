import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from src.sanity_check import run as fase1
from src.fetch_field import run as fase2
from src.quality_filter import run as fase3
from src.known_catalog_match import run as fase4
from src.llm_triage import run as fase5


def run_all():
    fases = [
        ("Fase 1 - Sanity check", fase1),
        ("Fase 2 - Fetch field", fase2),
        ("Fase 3 - Quality filter", fase3),
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


if __name__ == "__main__":
    run_all()
