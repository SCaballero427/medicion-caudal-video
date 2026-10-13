# Pruebas en Docker: una Raspberry Pi falsa y una camara RTSP simulada

Sirve para probar el paquete `../raspberry/` **sin tener la placa ni la camara**, con los mismos
scripts que se usaran de verdad. Es como se probo el paquete antes de entregarlo (2026-10-12).

Hace falta **Docker Desktop** abierto (en este PC esta instalado).

## Usarlo

Doble clic en `probar_en_docker.bat`, o desde PowerShell en la carpeta del caso:

```powershell
.\pruebas_docker\probar_en_docker.ps1                 # levanta todo, instala y ejecuta stiv.sh prueba
.\pruebas_docker\probar_en_docker.ps1 -SinInstalar    # ya instalado: solo sube el codigo y prueba
.\pruebas_docker\probar_en_docker.ps1 -SoloLevantar   # levanta los contenedores y nada mas
.\pruebas_docker\probar_en_docker.ps1 -Parar          # DESACTIVA los contenedores, sin borrar nada
.\pruebas_docker\probar_en_docker.ps1 -Arrancar       # los vuelve a activar tal como quedaron
.\pruebas_docker\probar_en_docker.ps1 -Bajar          # los BORRA (la Pi falsa pierde lo instalado)
.\pruebas_docker\probar_en_docker.ps1 -Bajar -BorrarImagenes   # y tambien las imagenes (~1 GB)
```

Con `.bat` igual: `probar_en_docker.bat -Parar`, `probar_en_docker.bat -Arrancar`.

**Para terminar una sesion de pruebas usa `-Parar`, no `-Bajar`.** Los contenedores parados
conservan todo: la Pi falsa sigue con el paquete instalado, sus CSV y su `stiv.conf`, y `-Arrancar`
la devuelve tal cual (si el servicio estaba activado, arranca solo, como una Pi al encenderla).
Tambien se pueden parar y arrancar desde Docker Desktop, en *Containers*, grupo `stiv-pruebas`.
Si se cierra Docker Desktop, los contenedores quedan parados y no se pierde nada.

**Lo que SI recrea la Pi falsa desde cero** (y le borra lo instalado): `-Bajar`, y cualquier cambio
en `docker-compose.yml` o en `pi_falsa/Dockerfile` seguido de la orden normal (o de
`docker compose up`), porque Docker reconstruye un contenedor cuya configuracion cambio. La orden
normal vuelve a instalarlo todo sola (~8 min); `-SinInstalar` fallaria sobre una Pi recreada.

Al pararla, la Pi falsa sale con codigo 137 (Docker la corta): emulada, systemd no atiende la senal
de apagado. No se pierde nada. En una Pi real no se hace asi: `sudo shutdown now`.

La primera vez tarda: construir la imagen y la instalacion emulada son ~10-15 minutos.

## Que levanta (`docker-compose.yml`)

| Contenedor | Que es | Direccion |
|---|---|---|
| `stiv-pi-falsa` | Debian 13 para ARM de 64 bits con systemd y SSH, usuario `stiv` (contrasena `clave`) | SSH en `localhost:2222` |
| `stiv-rtsp-srv` | servidor RTSP (mediamtx) | `rtsp://localhost:8554/camara` desde el PC, `rtsp://stiv-rtsp-srv:8554/camara` desde la Pi falsa |
| `stiv-rtsp-pub` | emite `raspberry/prueba/myoshoji_20s.mp4` en bucle al servidor, como una camara IP (H.264 por RTSP) | - |

Todos llevan el prefijo `stiv-` para no chocar con otros contenedores. La llave SSH de prueba se
crea en `.llave\` dentro de esta carpeta: la carpeta `.ssh` del usuario no se toca.

## Archivos

| Archivo | Que es |
|---|---|
| `pi_falsa/Dockerfile` | la imagen de la Raspberry Pi falsa |
| `docker-compose.yml` | los tres contenedores y como se conectan |
| `probar_en_docker.ps1` / `.bat` | lo levanta, instala el paquete, prueba, para y arranca |
| `.llave/` | la llave SSH de prueba y su `known_hosts` (los crea el script) |

## Pruebas que se pueden hacer

- **Instalar y arrancar como en la Pi**: el script hace la instalacion completa con
  `subir_a_raspberry.ps1`. Despues, dentro de la Pi falsa: `./raspberry/stiv.sh activar`, y
  `docker restart stiv-pi-falsa` simula apagar y encender; `./raspberry/stiv.sh estado` debe decir
  `active (running)`.
- **Camara RTSP desde el PC**:
  ```
  .venv\Scripts\python.exe stiv_directo.py --camara prueba_rtsp --fuente rtsp://localhost:8554/camara
  ```
  El video de prueba tiene fotogramas duplicados (viene de YouTube): para medirlo bien, en
  `salidas\prueba_rtsp\config_stiv_directo.json` pon el cuadrilatero del Myoshoji y
  `"FPS_CAMARA": 15.0` (una camara IP real lleva `null`).
- **Camara RTSP desde la Pi falsa**: en `stiv.conf`, `--fuente rtsp://stiv-rtsp-srv:8554/camara`.
- **Corte de la camara**: `docker stop stiv-rtsp-pub`, unos segundos, `docker start stiv-rtsp-pub`.
  El programa tiene que decir `flujo cortado, reconectando...` y volver a medir unos 10 s despues
  de que vuelva la imagen (lo que tarda en llenarse el STI).

## Lo que esta Pi falsa NO es

- **No es una Raspberry en velocidad.** Corre emulada (QEMU): sus tiempos no dicen nada de una
  Pi 4B. Eso solo lo mide `stiv.sh prueba` en la Pi de verdad.
- `sudo` no pide contrasena (en la Pi real si), para que la prueba no necesite a nadie delante.
- **journald no funciona** dentro del contenedor emulado, asi que `stiv.sh registro` no muestra
  nada aqui; en Raspberry Pi OS funciona. `vcgencmd` (temperatura) tampoco existe.
- No hay `stiv-rio.local` (mDNS): se entra por `localhost:2222`.
