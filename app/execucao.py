"""Rodar `pipeline.py --proximo` pelo app, em segundo plano, e ler o progresso no log.

Sem Streamlit (testavel offline). O processo roda em sessao propria: fechar a pagina ou
parar o Streamlit nao o interrompe. O log fica em data/pipeline.log; a pagina rele o
log a cada poucos segundos.
"""

import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "pipeline.log"
COMANDO = "python -u pipeline.py --proximo"
FIM = "registrado em campos_feitos"
CANCELADA = "Busca cancelada pelo app."


def _processos() -> list[int]:
    """PIDs de pipeline.py rodando a partir deste projeto (do app ou do terminal)."""
    achados = []
    for d in Path("/proc").glob("[0-9]*"):
        try:
            cmd = (d / "cmdline").read_bytes().split(b"\0")
            if any(p.endswith(b"pipeline.py") for p in cmd) and Path(os.readlink(d / "cwd")) == ROOT:
                achados.append(int(d.name))
        except (OSError, ValueError):
            continue
    return achados


def rodando() -> bool:
    return bool(_processos())


def iniciar() -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as saida:
        subprocess.Popen([sys.executable, "-u", "pipeline.py", "--proximo"], cwd=ROOT,
                         stdout=saida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         start_new_session=True)


def cancelar() -> None:
    """Encerra a busca e o que ela abriu. O campo nao entra em campos_feitos: na proxima
    busca ele e refeito do inicio, e as decisoes da revisao nao sao tocadas."""
    for pid in _processos():
        try:
            # iniciada pelo app: sessao propria, o grupo leva junto os downloads paralelos
            if os.getpgid(pid) == pid:
                os.killpg(pid, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
    with open(LOG, "a", encoding="utf-8") as saida:
        saida.write(f"\n{CANCELADA}\n")


def ler_log() -> str:
    try:
        return LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def minutos_desde_inicio() -> float | None:
    try:
        return (time.time() - LOG.stat().st_ctime) / 60
    except OSError:
        return None


def estado(log: str) -> dict:
    """Fase atual, progresso (i de N), campo, erro e fim, tirados do texto do log."""
    linhas = [x.strip() for x in log.splitlines() if x.strip()]
    e = {"fase": None, "progresso": None, "campo": None, "erro": None,
         "terminou": any(FIM in x for x in linhas), "fim_da_grade": False,
         "cancelada": any(x.startswith(CANCELADA) for x in linhas)}
    for x in linhas:
        if x.startswith("Executando:"):
            e["fase"], e["progresso"] = x.split(":", 1)[1].strip(), None
        elif m := re.match(r"(\d+)/(\d+)\b", x):
            e["progresso"] = (int(m.group(1)), int(m.group(2)))
        elif x.startswith("Proximo campo:"):
            e["campo"] = x.split(":", 1)[1].strip()
        elif x.startswith("ERRO em"):
            e["erro"] = x
        elif x.startswith("A grade de campos acabou"):
            e["fim_da_grade"] = True
    return e
