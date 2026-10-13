@echo off
rem Doble clic (o desde cmd con opciones, p. ej. probar_en_docker.bat -Bajar).
rem Lanza el .ps1 saltando la politica de Windows que bloquea scripts descargados o nuevos.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0probar_en_docker.ps1" %*
if errorlevel 1 echo. & echo HUBO UN ERROR: lee el mensaje de arriba.
pause
