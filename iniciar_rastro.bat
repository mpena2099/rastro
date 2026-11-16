@echo off
rem Rastro no Windows: clique duas vezes neste arquivo.
rem Na primeira vez cria o ambiente (venv) e instala as dependencias; depois so abre o app.
cd /d "%~dp0"

if exist "venv\.instalado" goto abrir

echo Primeira vez: preparando o Rastro (alguns minutos)...
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY (
    where python >nul 2>nul && set PY=python
)
if not defined PY (
    echo.
    echo Python nao encontrado. Instale o Python 3.10 ou mais novo em https://www.python.org/downloads/
    echo e marque a opcao "Add python.exe to PATH" no instalador. Depois rode este arquivo de novo.
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
