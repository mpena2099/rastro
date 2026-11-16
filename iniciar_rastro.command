#!/bin/bash
# Rastro no macOS (e Linux): clique duas vezes neste arquivo (no Linux: ./iniciar_rastro.command).
# Na primeira vez cria o ambiente (venv) e instala as dependencias; depois so abre o app.
cd "$(dirname "$0")" || exit 1

erro() {
    echo
    echo "$1"
    read -r -p "Aperte Enter para fechar."
    exit 1
}

if [ ! -f venv/.instalado ]; then
    echo "Primeira vez: preparando o Rastro (alguns minutos)..."
    PY=""
    for c in python3 python; do
        if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
            PY="$c"; break
        fi
    done
    [ -n "$PY" ] || erro "Python 3.10 ou mais novo não encontrado. Instale em https://www.python.org/downloads/ e rode este arquivo de novo."
    if [ ! -x venv/bin/python ]; then
        "$PY" -m venv venv || erro "Não consegui criar o ambiente (venv)."
    fi
    venv/bin/python -m pip install --upgrade pip
    venv/bin/python -m pip install -r requirements.txt || erro "A instalação falhou. Veja a mensagem acima, confira a internet e rode de novo."
    echo ok > venv/.instalado
fi

echo "Abrindo o Rastro no navegador. Para fechar, feche esta janela."
venv/bin/python iniciar.py
