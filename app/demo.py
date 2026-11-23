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


def _descartar_modulos_se_o_codigo_mudou() -> None:
    """O Community Cloud baixa o push, mas so reage a mudanca neste arquivo: os modulos
    importados ficariam na versao antiga ate um reboot manual. Se algum .py mudou desde a
    ultima carga, descarta os modulos do projeto e esta visita ja importa o codigo novo."""
    marca = str(max(p.stat().st_mtime for p in RAIZ.rglob("*.py") if "venv" not in p.parts))
    anterior = os.environ.get("RASTRO_DEMO_CODIGO")
    # na primeira carga do processo tambem: um push que so mudou este arquivo deixa os
    # modulos antigos na memoria
    if anterior != marca:
        for nome in list(sys.modules):
            if nome in ("config", "app", "src") or nome.startswith(("app.", "src.")):
                del sys.modules[nome]
    os.environ["RASTRO_DEMO_CODIGO"] = marca


_descartar_modulos_se_o_codigo_mudou()

import streamlit as st

from app.estilo import css

st.set_page_config(page_title="Rastro: treino", page_icon="🔭", layout="wide")
st.markdown(css(), unsafe_allow_html=True)

if "src.util" not in sys.modules:
    # importar src.util testa o CDS e o espelho do VizieR (ate ~30 s com o CDS fora):
    # sem isto a pagina fica em branco nesse tempo
    with st.spinner("Conferindo se os catálogos do CDS estão no ar (até 30 s na primeira abertura)..."):
        import src.util  # noqa: F401
st.navigation([st.Page("paginas/treino.py", title="Treino", icon=":material/school:", default=True)]).run()
