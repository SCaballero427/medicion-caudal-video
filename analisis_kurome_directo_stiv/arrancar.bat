@echo off
rem Doble clic: arranca el STIV sobre el directo del rio Kurome con el entorno propio de la carpeta.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creando el entorno e instalando librerias...
    python -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || goto :error
)
".venv\Scripts\python.exe" stiv_directo.py %*
goto :eof
:error
echo No se pudo preparar el entorno. Hace falta Python 3.10+ en el PATH.
pause
