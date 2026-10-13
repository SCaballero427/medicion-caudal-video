<#
Trae al PC lo que ha medido la Raspberry Pi: CSV, imagen anotada y configs de cada camara.
Se ejecuta en el PC (PowerShell):

    .\raspberry\traer_resultados.ps1
    .\raspberry\traer_resultados.ps1 -Abrir               # ademas abre la carpeta y las imagenes
    .\raspberry\traer_resultados.ps1 -Equipo 192.168.1.57

Lo deja en salidas_raspberry\ junto a esta carpeta, separado de las salidas del propio PC para que
nunca se mezclen ni se pisen.
#>
param(
    [string]$Equipo = "stiv-rio.local",
    [string]$Usuario = "stiv",
    [int]$Puerto = 22,
    [switch]$Abrir,
    [string[]]$OpcionesSsh = @()
)
# Los cmdlets paran ante cualquier error; los programas externos (docker, ssh, scp, tar) NO: en
# PowerShell 5.1 con "Stop", todo lo que escriben en stderr (progreso, avisos como "Permanently
# added...") se vuelve un error fatal en cuanto la salida esta redirigida. A ellos se los juzga por
# su codigo de salida ($LASTEXITCODE), que se comprueba despues de cada llamada.
$ErrorActionPreference = "Continue"
$PSDefaultParameterValues = @{ "*:ErrorAction" = "Stop" }
$caso = Split-Path $PSScriptRoot -Parent
$local = Join-Path $caso "salidas_raspberry"
New-Item -ItemType Directory -Force $local | Out-Null

$a = @('-P', $Puerto, '-r') + $OpcionesSsh
& scp.exe @a "$Usuario@${Equipo}:stiv/salidas/*" $local
if ($LASTEXITCODE -ne 0) { throw "no se pudo copiar desde la Pi (codigo $LASTEXITCODE)" }

Get-ChildItem $local -Recurse -File | Sort-Object FullName |
    Format-Table @{n = "archivo"; e = { $_.FullName.Substring($local.Length + 1) } },
                 @{n = "KB"; e = { [math]::Round($_.Length / 1KB) } }, LastWriteTime -AutoSize
if ($Abrir) {
    Invoke-Item $local
    Get-ChildItem $local -Recurse -Filter ultima_vista.png | ForEach-Object { Invoke-Item $_.FullName }
}
