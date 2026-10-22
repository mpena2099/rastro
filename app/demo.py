"""Rastro: demo online so com o treino (Streamlit Community Cloud).

    streamlit run app/demo.py

Usa o banco pequeno demo/treino_demo.db (gerado por tools/gerar_demo.py). As respostas de cada
visitante ficam num arquivo temporario da sessao; nada e gravado no banco do repositorio.
"""

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
# antes de importar config: ele le essas variaveis ao carregar
os.environ["RASTRO_DEMO"] = "1"
os.environ["RASTRO_DB"] = str(RAIZ / "demo" / "treino_demo.db")
sys.path.insert(0, str(RAIZ))

import streamlit as st

from app.estilo import css

st.set_page_config(page_title="Rastro: treino", page_icon="🔭", layout="wide")
st.markdown(css(), unsafe_allow_html=True)
st.navigation([st.Page("paginas/treino.py", title="Treino", icon=":material/school:", default=True)]).run()
