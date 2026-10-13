<#
Sube el STIV a la Raspberry Pi y lo instala. Se ejecuta en el PC (PowerShell), desde cualquier carpeta:

    .\raspberry\subir_a_raspberry.ps1                         # primera vez y cada actualizacion
    .\raspberry\subir_a_raspberry.ps1 -ConfigurarLlave        # ademas: entrar sin contrasena en adelante
    .\raspberry\subir_a_raspberry.ps1 -SinInstalar            # solo copiar codigo y reiniciar (rapido)
    .\raspberry\subir_a_raspberry.ps1 -SobrescribirConfig     # pisar las configs de camara de la Pi
    .\raspberry\subir_a_raspberry.ps1 -Equipo 192.168.1.57    # si stiv-rio.local no se encuentra

Copia stiv_directo.py, la carpeta raspberry\ (sin los .ps1) y las configs de camara de salidas\ del
PC (solo los JSON; nunca los CSV ni las imagenes) a ~/stiv en la Pi, y ejecuta alli instalar.sh.
No copia .venv: el entorno de Windows no sirve en la Pi, instalar.sh crea el suyo.
#>
param(
    [string]$Equipo = "stiv-rio.local",
    [string]$Usuario = "stiv",
    [int]$Puerto = 22,
    [switch]$SinInstalar,
    [switch]$SobrescribirConfig,
    [switch]$ConfigurarLlave,
    # opciones extra para ssh/scp, p. ej. @('-i', 'C:\ruta\llave')
    [string[]]$OpcionesSsh = @()
)
# Los cmdlets paran ante cualquier error; los programas externos (docker, ssh, scp, tar) NO: en
# PowerShell 5.1 con "Stop", todo lo que escriben en stderr (progreso, avisos como "Permanently
# added...") se vuelve un error fatal en cuanto la salida esta redirigida. A ellos se los juzga por
# su codigo de salida ($LASTEXITCODE), que se comprueba despues de cada llamada.
$ErrorActionPreference = "Continue"
$PSDefaultParameterValues = @{ "*:ErrorAction" = "Stop" }
$caso = Split-Path $PSScriptRoot -Parent
$destino = "$Usuario@$Equipo"

function Paso($texto) { Write-Host "`n== $texto" -ForegroundColor Cyan }
function Comprobar($que) {
    if ($LASTEXITCODE -ne 0) { throw "fallo: $que (codigo $LASTEXITCODE)" }
}
function EnPi([string]$orden, [switch]$Tty) {
    $a = @('-p', $Puerto) + $OpcionesSsh
    if ($Tty) { $a += '-t' }
    & ssh.exe @a $destino $orden
}

# -- 1. paquete ------------------------------------------------------------------------------------
Paso "Preparando el paquete desde $caso"
$tmp = Join-Path $env:TEMP ("stiv_paquete_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$raiz = Join-Path $tmp "contenido"
New-Item -ItemType Directory -Force (Join-Path $raiz "raspberry") | Out-Null
Copy-Item (Join-Path $caso "stiv_directo.py") $raiz
Get-ChildItem (Join-Path $caso "raspberry") -Force |
    Where-Object { $_.Extension -notin @(".ps1", ".bat") -and $_.Name -ne "stiv.conf" -and $_.Name -ne "cookies.txt" } |
    ForEach-Object { Copy-Item $_.FullName (Join-Path $raiz "raspberry") -Recurse }
$configs = Get-ChildItem (Join-Path $caso "salidas") -Filter config_stiv_directo.json -Recurse -ErrorAction SilentlyContinue
foreach ($c in $configs) {
    $d = Join-Path $raiz ("raspberry\config_pc\" + $c.Directory.Name)
    New-Item -ItemType Directory -Force $d | Out-Null
    Copy-Item $c.FullName $d
}
Write-Host ("configs de camara incluidas: " + (($configs | ForEach-Object { $_.Directory.Name }) -join ", "))

# Linux exige finales de linea LF: un .sh guardado con CRLF en Windows falla con "\r: command not found"
$utf8 = New-Object System.Text.UTF8Encoding($false)
Get-ChildItem $raiz -Recurse -File -Include *.sh, *.service, *.ejemplo, *.txt, *.py, *.md, *.json |
    ForEach-Object {
        $texto = [IO.File]::ReadAllText($_.FullName)
        [IO.File]::WriteAllText($_.FullName, $texto.Replace("`r`n", "`n"), $utf8)
    }

$paquete = Join-Path $tmp "paquete.tgz"
& tar -czf $paquete -C $raiz .
Comprobar "crear el paquete con tar"
Write-Host ("paquete: {0:N1} MB" -f ((Get-Item $paquete).Length / 1MB))

try {
    # -- 2. llave SSH (opcional) ------------------------------------------------------------------
    if ($ConfigurarLlave) {
        Paso "Configurando la llave SSH (pedira la contrasena de la Pi una vez)"
        $llave = Join-Path $env:USERPROFILE ".ssh\id_ed25519"
        if (-not (Test-Path "$llave.pub")) {
            New-Item -ItemType Directory -Force (Split-Path $llave) | Out-Null
            & ssh-keygen.exe -t ed25519 -N '""' -f $llave -q
            Comprobar "ssh-keygen"
        }
        Get-Content "$llave.pub" | & ssh.exe -p $Puerto @OpcionesSsh $destino "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
        Comprobar "copiar la llave a la Pi"
        Write-Host "llave copiada: a partir de ahora no pedira contrasena"
    }

    # -- 3. copiar --------------------------------------------------------------------------------
    Paso "Copiando a $destino`:~/stiv"
    EnPi "mkdir -p ~/stiv"
    Comprobar "conectar con la Pi (esta encendida? es correcto -Equipo?)"
    $a = @('-P', $Puerto) + $OpcionesSsh
    & scp.exe @a $paquete "${destino}:stiv/paquete.tgz"
    Comprobar "copiar el paquete"

    # -- 4. instalar ------------------------------------------------------------------------------
    $extraer = "cd ~/stiv && tar -xzf paquete.tgz && rm paquete.tgz"
    if ($SinInstalar) {
        Paso "Codigo actualizado; reiniciando el servicio si estaba en marcha"
        EnPi "$extraer && chmod +x raspberry/*.sh && if systemctl is-enabled --quiet stiv || systemctl is-active --quiet stiv; then sudo systemctl restart stiv && echo 'servicio reiniciado con el codigo nuevo'; else echo 'servicio no activado: nada que reiniciar'; fi" -Tty
    } else {
        Paso "Instalando en la Pi (la primera vez tarda varios minutos; pedira la contrasena para sudo)"
        $opcion = ""
        if ($SobrescribirConfig) { $opcion = " --sobrescribir-config" }
        EnPi "$extraer && bash raspberry/instalar.sh$opcion" -Tty
    }
    Comprobar "instalar en la Pi"
    Paso "Hecho. Para entrar en la Pi:  ssh $destino   y luego   cd ~/stiv"
} finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
