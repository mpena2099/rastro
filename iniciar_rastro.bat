@echo off
rem Rastro no Windows: clique duas vezes neste arquivo.
rem Na primeira vez cria o ambiente (venv) e instala as dependencias; depois so abre o app.
cd /d "%~dp0"

if exist "venv\.instalado" goto abrir

echo Primeira vez: preparando o Rastro (alguns minutos)...
set PY=
for %%V in (3.13 3.12 3.11) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>nul && set PY=py -%%V
    )
)
if not defined PY (
    where python >nul 2>nul && python -c "import sys; sys.exit(not ((3, 11) <= sys.version_info[:2] <= (3, 13)))" >nul 2>nul && set PY=python
)
if not defined PY (
    echo.
    echo Python de 3.11 a 3.13 nao encontrado ^(o 3.14 ainda nao e aceito^).
    echo Instale um em https://www.python.org/downloads/ e marque a opcao "Add python.exe to PATH" no instalador.
    echo Depois rode este arquivo de novo.
    pause
    exit /b 1
)

if not exist "venv\Scripts\python.exe" (
    %PY% -m venv venv
    if errorlevel 1 goto erro
)
"venv\Scripts\python.exe" -m pip install --upgrade pip
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto erro
echo ok> "venv\.instalado"

:abrir
echo Abrindo o Rastro no navegador. Para fechar, feche esta janela.
"venv\Scripts\python.exe" iniciar.py
pause
exit /b 0

:erro
echo.
echo A instalacao falhou. Veja a mensagem acima, confira a internet e rode este arquivo de novo.
pause
exit /b 1
