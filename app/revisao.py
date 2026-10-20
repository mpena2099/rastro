"""Rastro: app de revisao visual dos candidatos.

    streamlit run app/revisao.py

Router das paginas: a revisao visual (Fase 6) e o modo treino. Rodar a partir da
raiz do repositorio.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from app.estilo import css

st.set_page_config(page_title="Rastro", page_icon="🔭", layout="wide")
st.markdown(css(), unsafe_allow_html=True)

st.navigation([
    st.Page("paginas/fila.py", title="Revisão", icon=":material/fact_check:", default=True),
    st.Page("paginas/treino.py", title="Treino", icon=":material/school:"),
]).run()
