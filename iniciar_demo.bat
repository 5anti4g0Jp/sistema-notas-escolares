@echo off
rem Abre o sistema com dados de exemplo (sem banco e sem chave). Duplo clique neste arquivo.
rem Na primeira vez cria a pasta .venv e instala as dependencias (precisa de internet).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv 2>nul || python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
    echo Nao encontrei o Python. Instale em python.org e marque "Add python.exe to PATH".
    pause
    exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m pip install -q -r requirements.txt
python demo.py
if errorlevel 1 pause
