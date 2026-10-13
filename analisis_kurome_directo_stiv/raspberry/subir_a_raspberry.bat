@echo off
rem Doble clic (o desde cmd con opciones, p. ej. subir_a_raspberry.bat -Equipo 192.168.1.57).
rem Lanza el .ps1 saltando la politica de Windows que bloquea scripts descargados o nuevos.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0subir_a_raspberry.ps1" %*
if errorlevel 1 echo. & echo HUBO UN ERROR: lee el mensaje de arriba.
pause
