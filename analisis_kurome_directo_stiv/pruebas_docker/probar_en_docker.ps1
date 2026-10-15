<#
Prueba el paquete raspberry/ en una Raspberry Pi falsa (Docker), de punta a punta y con los mismos
scripts que se usaran con la Pi real. Necesita Docker Desktop abierto.

    .\pruebas_docker\probar_en_docker.ps1                 # levanta todo, instala y ejecuta stiv.sh prueba
    .\pruebas_docker\probar_en_docker.ps1 -SinInstalar    # ya instalado: solo sube el codigo y prueba
    .\pruebas_docker\probar_en_docker.ps1 -SoloLevantar   # levanta los contenedores y no toca nada mas
    .\pruebas_docker\probar_en_docker.ps1 -Parar          # DESACTIVA los contenedores, sin borrar nada
    .\pruebas_docker\probar_en_docker.ps1 -Arrancar       # los vuelve a activar tal como quedaron
    .\pruebas_docker\probar_en_docker.ps1 -Bajar          # los BORRA (las dos Pi pierden lo instalado)
    .\pruebas_docker\probar_en_docker.ps1 -Bajar -BorrarImagenes   # ademas borra las imagenes (~2 GB)

Con -PiOS, lo mismo pero sobre Raspberry Pi OS oficial arrancado en QEMU (stiv-pi-os, puerto 2223)
en vez del Debian con systemd (stiv-pi-falsa, puerto 2222). Mas fiel y mas lento:
    .\pruebas_docker\probar_en_docker.ps1 -PiOS
    .\pruebas_docker\probar_en_docker.ps1 -PiOS -SinInstalar

Usa una llave SSH propia en pruebas_docker\.llave\ : no toca la carpeta .ssh del usuario.
#>
param(
    [switch]$PiOS,
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
# -Parar/-Arrancar/-Bajar actuan sobre todo, tambien la Pi OS (que va en un perfil aparte)
$todo = @('-f', $compose, '--profile', 'pi-os')
if ($PiOS) {
    $pi = "stiv-pi-os"; $puerto = 2223; $servicios = @('pi-os', 'rtsp-srv', 'rtsp-pub')
} else {
    $pi = "stiv-pi-falsa"; $puerto = 2222; $servicios = @('pi-falsa', 'rtsp-srv', 'rtsp-pub')
}

function Paso($texto) { Write-Host "`n== $texto" -ForegroundColor Cyan }
function Comprobar($que) { if ($LASTEXITCODE -ne 0) { throw "fallo: $que (codigo $LASTEXITCODE)" } }

& docker.exe info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker no responde: abre Docker Desktop, espera a que diga 'running' y repite." }

if ($Parar) {
    Paso "Desactivando los contenedores (no se borra nada; volver con -Arrancar)"
    & docker.exe compose @todo stop
    Comprobar "docker compose stop"
    return
}
if ($Arrancar) {
    Paso "Reactivando los contenedores tal como quedaron"
    & docker.exe compose @todo start
    Comprobar "docker compose start"
    Write-Host "Las Pi conservan lo instalado; si el servicio estaba activado, arranca solo."
    return
}
if ($Bajar) {
    Paso "Parando y borrando los contenedores de prueba (y la 'tarjeta SD' de la Pi OS)"
    if ($BorrarImagenes) { & docker.exe compose @todo down -v --rmi all } else { & docker.exe compose @todo down -v }
    Comprobar "docker compose down"
    return
}

# -- 1. llave SSH de prueba ------------------------------------------------------------------------
# Antes de levantar nada: la Pi OS la recibe por cloud-init en su primer arranque, como cuando se le
# pone una llave en Raspberry Pi Imager.
$dirLlave = Join-Path $aqui ".llave"
$llave = Join-Path $dirLlave "llave_prueba"
$conocidos = Join-Path $dirLlave "known_hosts"
New-Item -ItemType Directory -Force $dirLlave | Out-Null
if (-not (Test-Path $llave)) {
    & ssh-keygen.exe -t ed25519 -N '""' -f $llave -q -C "stiv-pruebas-docker"
    Comprobar "ssh-keygen"
}
# si se reconstruyo el contenedor, su identidad SSH cambio: se olvida la anterior
Remove-Item $conocidos -ErrorAction SilentlyContinue
$op = @('-i', $llave, '-o', "UserKnownHostsFile=$conocidos", '-o', 'StrictHostKeyChecking=no', '-o', 'LogLevel=ERROR')

# -- 2. contenedores -------------------------------------------------------------------------------
if ($PiOS) {
    Paso "Levantando Raspberry Pi OS en QEMU y la camara RTSP simulada (la primera vez construye la imagen y compila el kernel: ~30 min)"
} else {
    Paso "Levantando la Pi falsa y la camara RTSP simulada (la primera vez construye la imagen: minutos)"
}
& docker.exe compose @todo up -d --build @servicios
Comprobar "docker compose up"

if ($PiOS) {
    # No hay "docker exec" dentro de una maquina virtual: se espera a poder entrar por SSH, que es
    # lo mismo que se hace con la Pi real. El primer arranque emulado expande la tarjeta, corre
    # cloud-init y genera las llaves del servidor SSH: varios minutos.
    Paso "Esperando a que Raspberry Pi OS arranque y acepte SSH (primer arranque: 5-15 min; consola: docker logs -f $pi)"
    $listo = $false
    for ($i = 0; $i -lt 180; $i++) {
        & ssh.exe -p $puerto @op -o BatchMode=yes -o ConnectTimeout=10 stiv@localhost "cloud-init status --wait > /dev/null; true" 2>$null
        if ($LASTEXITCODE -eq 0) { $listo = $true; break }
        if (-not (& docker.exe ps -q --filter "name=^$pi$")) { throw "el contenedor $pi se paro: docker logs $pi" }
        Start-Sleep 5
    }
    if (-not $listo) { throw "Raspberry Pi OS no acepto SSH a tiempo: docker logs $pi" }
    & ssh.exe -p $puerto @op stiv@localhost "echo; cat /etc/rpi-issue 2>/dev/null | head -1; uname -r; systemctl is-system-running; systemctl --failed --no-legend"
} else {
    Paso "Esperando a que arranque systemd en la Pi falsa"
    $estado = ""
    for ($i = 0; $i -lt 60; $i++) {
        $estado = (& docker.exe exec $pi systemctl is-system-running 2>$null) -join ""
        if ($estado -in @("running", "degraded")) { break }
        Start-Sleep 3
    }
    Write-Host "systemd: $estado   (degraded es normal en un contenedor)"
    if ($estado -notin @("running", "degraded")) { throw "la Pi falsa no termino de arrancar" }

    & docker.exe cp "$llave.pub" "${pi}:/home/stiv/.ssh/authorized_keys"
    Comprobar "copiar la llave a la Pi falsa"
    & docker.exe exec $pi sh -c "chown stiv:stiv /home/stiv/.ssh/authorized_keys && chmod 600 /home/stiv/.ssh/authorized_keys"
}

if (-not $SoloLevantar) {
    # -- 3. instalar con el mismo script que se usara con la Pi real ------------------------------
    $subir = Join-Path $caso "raspberry\subir_a_raspberry.ps1"
    if ($SinInstalar) {
        & $subir -Equipo localhost -Puerto $puerto -OpcionesSsh $op -SinInstalar
    } else {
        Paso "Instalando el paquete en $pi (emulado: ~8 min la primera vez en la Pi falsa, mas en la Pi OS)"
        & $subir -Equipo localhost -Puerto $puerto -OpcionesSsh $op
    }

    # -- 4. prueba ---------------------------------------------------------------------------------
    Paso "Ejecutando ./raspberry/stiv.sh prueba en $pi"
    & ssh.exe -p $puerto @op stiv@localhost "cd ~/stiv && ./raspberry/stiv.sh prueba"
    Comprobar "stiv.sh prueba"
}

Paso "Listo"
Write-Host @"
Entrar en $pi (como si fuera la real):
  ssh -p $puerto -i "$llave" -o UserKnownHostsFile="$conocidos" -o StrictHostKeyChecking=no stiv@localhost
  y alli:  cd ~/stiv  y  ./raspberry/stiv.sh ayuda

Camara RTSP simulada (el video de prueba en bucle):
  desde el PC:          rtsp://localhost:8554/camara
  desde la Pi:          rtsp://stiv-rtsp-srv:8554/camara
  simular un corte:     docker stop stiv-rtsp-pub    (reanudar: docker start stiv-rtsp-pub)

Recuerda: las dos Pi son emuladas; sus tiempos NO dicen nada de una Raspberry real.
Al terminar:  probar_en_docker.bat -Parar     (desactiva sin borrar; -Arrancar para volver)
"@
