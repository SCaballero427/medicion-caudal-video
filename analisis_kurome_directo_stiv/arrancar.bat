@echo off
rem Doble clic: menu con los directos y videos de fuentes.json y arranca el STIV con el entorno propio
rem de la carpeta. Con argumentos (arrancar.bat --camara kurome ...) los pasa tal cual, sin menu.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creando el entorno e instalando librerias...
    python -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || goto :error
)
if "%~1"=="" (
    ".venv\Scripts\python.exe" stiv_directo.py --elegir
) else (
    ".venv\Scripts\python.exe" stiv_directo.py %*
)
goto :eof
:error
echo No se pudo preparar el entorno. Hace falta Python 3.10+ en el PATH.
pause
