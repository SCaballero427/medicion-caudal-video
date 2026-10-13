@echo off
rem Doble clic (o desde cmd con opciones, p. ej. traer_resultados.bat -Equipo 192.168.1.57).
rem Lanza el .ps1 saltando la politica de Windows que bloquea scripts descargados o nuevos.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0traer_resultados.ps1" %*
if errorlevel 1 echo. & echo HUBO UN ERROR: lee el mensaje de arriba.
pause
