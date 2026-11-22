"""Rodar `pipeline.py --proximo` pelo app, em segundo plano, e ler o progresso no log.

Sem Streamlit (testavel offline). O processo roda em sessao propria: fechar a pagina ou
parar o Streamlit nao o interrompe. O log fica em data/pipeline.log; a pagina rele o
log a cada poucos segundos.
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "pipeline.log"
INICIO = "Inicio:"


def comando_exibido(script_e_args: str, plataforma: str | None = None) -> str:
    """Comando para o terminal, com o python do venv conforme o sistema."""
    win = (plataforma or sys.platform) == "win32"
    py = "venv\\Scripts\\python" if win else "venv/bin/python"
    return f"{py} -u {script_e_args.replace('/', chr(92)) if win else script_e_args}"


COMANDO = comando_exibido("pipeline.py --proximo")


def casa_script(cmd: list[str], script: str) -> bool:
    """Algum argumento e o script (com / ou \\), nao outro arquivo que so termina igual."""
    alvo = script.replace("\\", "/")
    for p in cmd:
        p = p.replace("\\", "/")
        if p == alvo or p.endswith("/" + alvo):
            return True
    return False
FIM = "registrado em campos_feitos"
CANCELADA = "Busca cancelada pelo app."


def _processos() -> list[int]:
    """PIDs de pipeline.py rodando a partir deste projeto (do app ou do terminal).

    psutil em vez de /proc: funciona tambem no macOS e no Windows.
    """
    achados = []
    for proc in psutil.process_iter(["cmdline", "cwd"]):
        try:
            cmd = proc.info["cmdline"] or []
            cwd = proc.info["cwd"]
            if casa_script(cmd, "pipeline.py") and cwd and Path(cwd) == ROOT:
                achados.append(proc.pid)
        except (psutil.Error, OSError, ValueError):
            continue
    return achados


def rodando() -> bool:
    return bool(_processos())


def _sessao_propria() -> dict:
    """Processo desligado do Streamlit: parar o app nao interrompe a busca."""
    if sys.platform == "win32":
        # DETACHED_PROCESS: fechar a janela do .bat nao mata o processo
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
                | getattr(subprocess, "DETACHED_PROCESS", 0)}
    return {"start_new_session": True}


def iniciar() -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as saida:
        saida.write(f"{INICIO} {time.time():.0f}\n")
        saida.flush()
        subprocess.Popen([sys.executable, "-u", "pipeline.py", "--proximo"], cwd=ROOT,
                         stdout=saida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         env={**os.environ, "PYTHONIOENCODING": "utf-8"}, **_sessao_propria())


def cancelar() -> None:
    """Encerra a busca e o que ela abriu. O campo nao entra em campos_feitos: na proxima
    busca ele e refeito do inicio, e as decisoes da revisao nao sao tocadas."""
    for pid in _processos():
        try:
            # leva junto os downloads paralelos que a busca abriu
            proc = psutil.Process(pid)
            for filho in proc.children(recursive=True):
                filho.terminate()
            proc.terminate()
        except psutil.Error:
            continue
    with open(LOG, "a", encoding="utf-8") as saida:
        saida.write(f"\n{CANCELADA}\n")


def ler_log() -> str:
    try:
        return LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def minutos_desde_inicio(agora: float | None = None) -> float | None:
    """Minutos desde a hora gravada na primeira linha do log (st_ctime nao e a criacao)."""
    primeira = ler_log().split("\n", 1)[0].strip()
    if not primeira.startswith(INICIO):
        return None
    try:
        return ((agora or time.time()) - float(primeira[len(INICIO):])) / 60
    except ValueError:
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
