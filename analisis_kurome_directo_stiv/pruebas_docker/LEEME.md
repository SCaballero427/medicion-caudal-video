# Pruebas en Docker: dos Raspberry Pi simuladas y una camara RTSP simulada

Sirve para probar el paquete `../raspberry/` **sin tener la placa ni la camara**, con los mismos
scripts que se usaran de verdad. Es como se probo el paquete antes de entregarlo (2026-10-12).

Hay dos "Raspberry", y se elige con `-PiOS`:

| | `stiv-pi-falsa` (por defecto) | `stiv-pi-os` (`-PiOS`) |
|---|---|---|
| Que es | Debian 13 arm64 con systemd, en un contenedor | **la imagen oficial de Raspberry Pi OS Lite** (trixie, 2026-10-06) arrancada en una maquina virtual QEMU dentro del contenedor |
| Arranque | ninguno: systemd sobre el kernel de Docker | completo: kernel, initramfs de la imagen, expansion de la tarjeta, cloud-init, servicios de Raspberry Pi OS |
| Usuario y SSH | creados en el Dockerfile | los crea cloud-init en el primer arranque, con el formato de Raspberry Pi (lo que hace Imager) |
| journald / `stiv.sh registro` | no funciona | funciona |
| `vcgencmd` | no existe | existe y **falla** (no hay VideoCore): prueba esa rama de `stiv.sh` |
| Apagado (`-Parar`) | Docker la corta (codigo 137) | boton de apagado -> systemd apaga ordenadamente (~8 s, codigo 0) |
| Primera vez | ~10-15 min | ~30 min (descarga la imagen y compila el kernel) + primer arranque ~5 min |
| SSH | `localhost:2222` | `localhost:2223` |

Hace falta **Docker Desktop** abierto (en este PC esta instalado).

## Usarlo

Doble clic en `probar_en_docker.bat`, o desde PowerShell en la carpeta del caso:

```powershell
.\pruebas_docker\probar_en_docker.ps1                 # levanta todo, instala y ejecuta stiv.sh prueba
.\pruebas_docker\probar_en_docker.ps1 -SinInstalar    # ya instalado: solo sube el codigo y prueba
.\pruebas_docker\probar_en_docker.ps1 -SoloLevantar   # levanta los contenedores y nada mas
.\pruebas_docker\probar_en_docker.ps1 -Parar          # DESACTIVA los contenedores, sin borrar nada
.\pruebas_docker\probar_en_docker.ps1 -Arrancar       # los vuelve a activar tal como quedaron
.\pruebas_docker\probar_en_docker.ps1 -Bajar          # los BORRA (las dos Pi pierden lo instalado)
.\pruebas_docker\probar_en_docker.ps1 -Bajar -BorrarImagenes   # y tambien las imagenes (~2 GB)

.\pruebas_docker\probar_en_docker.ps1 -PiOS               # lo mismo sobre Raspberry Pi OS de verdad
.\pruebas_docker\probar_en_docker.ps1 -PiOS -SinInstalar  # ya instalado: solo sube el codigo y prueba
```

`-Parar`, `-Arrancar` y `-Bajar` actuan sobre las dos Pi a la vez. La consola de la Pi OS (lo que se
veria en una pantalla conectada por serie) se sigue con `docker logs -f stiv-pi-os`.

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
| `pi_os/Dockerfile` | Raspberry Pi OS oficial + QEMU + el kernel recompilado (ver abajo) |
| `pi_os/arrancar_vm.sh` | "graba la tarjeta" la primera vez y arranca la maquina virtual |
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

## Como esta hecha la Pi OS (`pi_os/`)

- La imagen es la oficial, **sin modificar**, comprobada con su sha256: `2026-10-06-raspios-trixie-
  arm64-lite.img.xz`. Para otra version, cambiar `FECHA`, `NOMBRE`, `ETIQUETA_KERNEL` y
  `VERSION_KERNEL` al principio del Dockerfile.
- **Lo unico que no es de la imagen es el kernel.** El de serie no trae ningun controlador para el
  hardware virtual de QEMU (virtio, PCI generico), asi que no encuentra ni el disco. Se recompila
  desde `raspberrypi/linux`, etiqueta `stable_20260911` (del mismo dia que el de la imagen), con la
  configuracion que trae la propia imagen, el mismo compilador (gcc 14.2.0-19 de Debian) y el mismo
  nombre (`6.18.50+rpt-rpi-v8`), mas esos controladores. Por eso **los modulos de la imagen cargan**
  sin tocarlos (comprobado). Compilar tarda ~8 min con 16 hilos.
- Maquina `virt` de QEMU con CPU `cortex-a72`, 4 nucleos y 4 GB, como la Pi 4B de 4 GB. La "tarjeta"
  se agranda a 32 GB y **la propia imagen expande la particion** en el primer arranque (31 GB
  utiles), y luego quita `resize` de `cmdline.txt`, como en la placa.
- No se emula reloj: la Pi 4 no tiene, y aqui tambien arranca en 1970 hasta que NTP pone la hora.
- La "tarjeta" vive en el volumen `stiv-pi-os-sd`: sobrevive a `-Parar`/`-Arrancar`; `-Bajar` la
  borra (la siguiente vez se "graba" de nuevo y vuelve a pasar por el primer arranque).
- Usuario `stiv`, contrasena `clave`, la llave de `.llave\` y `sudo` sin contrasena, en el formato
  del ejemplo oficial de cloud-init de Raspberry Pi (`enable_ssh: true`). Si Raspberry Pi Imager
  pone o no `sudo` sin contrasena al grabar la tarjeta real no se ha comprobado.

### Lo que se probo con ella (2026-10-15)

Instalacion completa desde cero con `subir_a_raspberry.ps1`; `stiv.sh prueba` (mediana 0.49 m/s,
6/9 estaciones: los mismos numeros que en el PC y en la Pi falsa); `stiv.sh salud`; servicio
activado -> `docker stop` (apagado ordenado) -> `docker start` -> el servicio arranca solo;
`journalctl -u stiv`; camara RTSP desde dentro (`rtsp://stiv-rtsp-srv:8554/camara`) con un corte de
10 s: dice `flujo cortado, reconectando...` y vuelve a medir.

**Un fallo que solo salio aqui**, ya corregido: `vcgencmd` existia pero no funcionaba, y como escribe
su error por la salida normal, `stiv.sh prueba` imprimia `temperatura antes: Can't open device file:
/dev/vcio_gencmd` en vez de recurrir al sensor del kernel. En la Pi real deberia funcionar (el
usuario esta en el grupo `video`), pero si no, ahora se nota: dice `?` / `no disponible`.

Unico servicio fallido en el arranque: `rpi-eeprom-update` (no hay EEPROM que leer). Normal aqui.

## Lo que estas Pi simuladas NO son

- **No son una Raspberry en velocidad.** Corren emuladas (QEMU): sus tiempos no dicen nada de una
  Pi 4B. Eso solo lo mide `stiv.sh prueba` en la Pi de verdad.
- **La Pi OS tampoco tiene el hardware de la placa**: ni VideoCore (`vcgencmd` falla), ni sensor de
  temperatura, ni recortes por calor o fuente, ni tarjeta SD real, ni Wi-Fi.
- En ninguna de las dos hay `stiv-rio.local` (mDNS en la red de casa): se entra por `localhost`.

Solo la Pi falsa:

- `sudo` no pide contrasena, para que la prueba no necesite a nadie delante.
- **journald no funciona** dentro del contenedor emulado, asi que `stiv.sh registro` no muestra
  nada aqui; en la Pi OS si funciona. `vcgencmd` (temperatura) tampoco existe.
