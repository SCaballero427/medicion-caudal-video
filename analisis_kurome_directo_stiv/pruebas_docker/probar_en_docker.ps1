<#
Prueba el paquete raspberry/ en una Raspberry Pi falsa (Docker), de punta a punta y con los mismos
scripts que se usaran con la Pi real. Necesita Docker Desktop abierto.

    .\pruebas_docker\probar_en_docker.ps1                 # levanta todo, instala y ejecuta stiv.sh prueba
    .\pruebas_docker\probar_en_docker.ps1 -SinInstalar    # ya instalado: solo sube el codigo y prueba
    .\pruebas_docker\probar_en_docker.ps1 -SoloLevantar   # levanta los contenedores y no toca nada mas
    .\pruebas_docker\probar_en_docker.ps1 -Parar          # DESACTIVA los contenedores, sin borrar nada
    .\pruebas_docker\probar_en_docker.ps1 -Arrancar       # los vuelve a activar tal como quedaron
    .\pruebas_docker\probar_en_docker.ps1 -Bajar          # los BORRA (la Pi falsa pierde lo instalado)
    .\pruebas_docker\probar_en_docker.ps1 -Bajar -BorrarImagenes   # ademas borra las imagenes (~1 GB)

Usa una llave SSH propia en pruebas_docker\.llave\ : no toca la carpeta .ssh del usuario.
#>
param(
    [switch]$SinInstalar,
    [switch]$SoloLevantar,
    [switch]$Parar,
    [switch]$Arrancar,
    [switch]$Bajar,
    [switch]$BorrarImagenes
)
# Los cmdlets paran ante cualquier error; los programas externos (docker, ssh, scp, tar) NO: en
# PowerShell 5.1 con "Stop", todo lo que escriben en stderr (progreso, avisos como "Permanently
# added...") se vuelve un error fatal en cuanto la salida esta redirigida. A ellos se los juzga por
# su codigo de salida ($LASTEXITCODE), que se comprueba despues de cada llamada.
$ErrorActionPreference = "Continue"
$PSDefaultParameterValues = @{ "*:ErrorAction" = "Stop" }
$aqui = $PSScriptRoot
$caso = Split-Path $aqui -Parent
$compose = Join-Path $aqui "docker-compose.yml"
$pi = "stiv-pi-falsa"

function Paso($texto) { Write-Host "`n== $texto" -ForegroundColor Cyan }
function Comprobar($que) { if ($LASTEXITCODE -ne 0) { throw "fallo: $que (codigo $LASTEXITCODE)" } }

& docker.exe info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker no responde: abre Docker Desktop, espera a que diga 'running' y repite." }

if ($Parar) {
    Paso "Desactivando los contenedores (no se borra nada; volver con -Arrancar)"
    & docker.exe compose -f $compose stop
    Comprobar "docker compose stop"
    return
}
if ($Arrancar) {
    Paso "Reactivando los contenedores tal como quedaron"
    & docker.exe compose -f $compose start
    Comprobar "docker compose start"
    Write-Host "La Pi falsa conserva lo instalado; si el servicio estaba activado, arranca solo."
    return
}
if ($Bajar) {
    Paso "Parando y borrando los contenedores de prueba"
    if ($BorrarImagenes) { & docker.exe compose -f $compose down --rmi all } else { & docker.exe compose -f $compose down }
    Comprobar "docker compose down"
    return
}

# -- 1. contenedores -------------------------------------------------------------------------------
Paso "Levantando la Pi falsa y la camara RTSP simulada (la primera vez construye la imagen: minutos)"
& docker.exe compose -f $compose up -d --build
Comprobar "docker compose up"

Paso "Esperando a que arranque systemd en la Pi falsa"
$estado = ""
for ($i = 0; $i -lt 60; $i++) {
    $estado = (& docker.exe exec $pi systemctl is-system-running 2>$null) -join ""
    if ($estado -in @("running", "degraded")) { break }
    Start-Sleep 3
}
Write-Host "systemd: $estado   (degraded es normal en un contenedor)"
if ($estado -notin @("running", "degraded")) { throw "la Pi falsa no termino de arrancar" }

# -- 2. llave SSH de prueba ------------------------------------------------------------------------
$dirLlave = Join-Path $aqui ".llave"
$llave = Join-Path $dirLlave "llave_prueba"
$conocidos = Join-Path $dirLlave "known_hosts"
New-Item -ItemType Directory -Force $dirLlave | Out-Null
if (-not (Test-Path $llave)) {
    & ssh-keygen.exe -t ed25519 -N '""' -f $llave -q -C "stiv-pruebas-docker"
    Comprobar "ssh-keygen"
}
& docker.exe cp "$llave.pub" "${pi}:/home/stiv/.ssh/authorized_keys"
Comprobar "copiar la llave a la Pi falsa"
& docker.exe exec $pi sh -c "chown stiv:stiv /home/stiv/.ssh/authorized_keys && chmod 600 /home/stiv/.ssh/authorized_keys"
# si se reconstruyo el contenedor, su identidad SSH cambio: se olvida la anterior
Remove-Item $conocidos -ErrorAction SilentlyContinue
$op = @('-i', $llave, '-o', "UserKnownHostsFile=$conocidos", '-o', 'StrictHostKeyChecking=no', '-o', 'LogLevel=ERROR')

if (-not $SoloLevantar) {
    # -- 3. instalar con el mismo script que se usara con la Pi real ------------------------------
    $subir = Join-Path $caso "raspberry\subir_a_raspberry.ps1"
    if ($SinInstalar) {
        & $subir -Equipo localhost -Puerto 2222 -OpcionesSsh $op -SinInstalar
    } else {
        Paso "Instalando el paquete en la Pi falsa (emulado: ~8 min la primera vez)"
        & $subir -Equipo localhost -Puerto 2222 -OpcionesSsh $op
    }

    # -- 4. prueba ---------------------------------------------------------------------------------
    Paso "Ejecutando ./raspberry/stiv.sh prueba en la Pi falsa"
    & ssh.exe -p 2222 @op stiv@localhost "cd ~/stiv && ./raspberry/stiv.sh prueba"
    Comprobar "stiv.sh prueba"
}

Paso "Listo"
Write-Host @"
Entrar en la Pi falsa (como si fuera la real):
  ssh -p 2222 -i "$llave" -o UserKnownHostsFile="$conocidos" -o StrictHostKeyChecking=no stiv@localhost
  y alli:  cd ~/stiv  y  ./raspberry/stiv.sh ayuda

Camara RTSP simulada (el video de prueba en bucle):
  desde el PC:          rtsp://localhost:8554/camara
  desde la Pi falsa:    rtsp://stiv-rtsp-srv:8554/camara
  simular un corte:     docker stop stiv-rtsp-pub    (reanudar: docker start stiv-rtsp-pub)

Recuerda: la Pi falsa es emulada; sus tiempos NO dicen nada de una Raspberry real.
Al terminar:  probar_en_docker.bat -Parar     (desactiva sin borrar; -Arrancar para volver)
"@
