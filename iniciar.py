"""Sobe o app de revisao (e o treino) no navegador, sem ativar o venv.

    python iniciar.py            # app completo
    python iniciar.py --demo     # so o treino, como na demo online
    python iniciar.py --porta 8600

Usa o Python do venv do projeto, se existir; senao, o que rodou este script.
"""

import argparse
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def _python() -> str:
    for caminho in (RAIZ / "venv" / "bin" / "python", RAIZ / "venv" / "Scripts" / "python.exe"):
        if caminho.exists():
            return str(caminho)
    return sys.executable


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--demo", action="store_true", help="so o treino (app/demo.py)")
    ap.add_argument("--porta", type=int, help="porta do Streamlit (padrao: a do Streamlit)")
    args = ap.parse_args()
    comando = [_python(), "-m", "streamlit", "run", "app/demo.py" if args.demo else "app/revisao.py"]
    if args.porta:
        comando += ["--server.port", str(args.porta)]
    try:
        return subprocess.call(comando, cwd=RAIZ)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
