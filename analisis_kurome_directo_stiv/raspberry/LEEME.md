# STIV en una Raspberry Pi 4B (4 GB)

Todo lo necesario para pasar `stiv_directo.py` a una Raspberry Pi y que mida sola desde que se
enciende. Pensado para alguien que nunca ha usado una Raspberry: sigue los pasos en orden.

## Que hay en esta carpeta

| Archivo | Donde se usa | Para que |
|---|---|---|
| `subir_a_raspberry.bat` / `.ps1` | **PC** | copia el codigo a la Pi y la instala (o la actualiza) |
| `traer_resultados.bat` / `.ps1` | **PC** | trae a `salidas_raspberry\` el CSV, la imagen y las configs |
| `instalar.sh` | Pi | lo ejecuta `subir_a_raspberry` solo: programas, Python, librerias, servicio |
| `stiv.sh` | Pi | todas las ordenes del dia a dia (`./raspberry/stiv.sh ayuda`) |
| `stiv.conf.ejemplo` | Pi | que camara mide el servicio y con que opciones (se copia a `stiv.conf`) |
| `stiv.service` | Pi | el servicio que lo arranca solo al encender |
| `requirements-raspberry.txt` | Pi | librerias de Python (OpenCV **sin pantalla**) |
| `prueba/myoshoji_20s.mp4` | Pi | 20 s de video de dia para probar sin camara y sin internet (va con `--modo dia`: esta en gris) |
| `prueba/myoshoji_noche_90s.mp4` | Pi | 90 s de noche (motas sobre agua negra, ~0.05 m/s) para probar el modo noche |

Los `.bat` se abren con doble clic. Existen porque Windows bloquea por defecto los scripts `.ps1`.

## Paso 1 - Grabar el sistema en la microSD (en el PC)

1. Instala **Raspberry Pi Imager** (raspberrypi.com/software) y mete la microSD (32 GB o mas).
2. Dispositivo: **Raspberry Pi 4**. Sistema: *Raspberry Pi OS (other)* -> **Raspberry Pi OS Lite
   (64-bit)**. Tiene que ser de **64 bits**: en 32 bits OpenCV no tiene paquete listo.
3. En **Editar ajustes**:
   - nombre del equipo: `stiv-rio`
   - usuario: `stiv` y una contrasena que recuerdes
   - Wi-Fi: no (ira por cable); zona horaria: la tuya
   - pestana Servicios: **activar SSH** con contrasena

   `stiv-rio` y `stiv` son los nombres que usan los scripts por defecto. Si eliges otros, anade
   `-Equipo` y `-Usuario` a cada orden de los `.bat` (ver mas abajo).
4. Graba.

## Paso 2 - Encender y comprobar que el PC la ve

1. microSD en la Pi, **cable de red al mismo router que el PC**, y la fuente oficial (USB-C 3 A).
2. Espera 2-3 minutos.
3. En PowerShell del PC: `ssh stiv@stiv-rio.local`. La primera vez escribe `yes`. La contrasena
   no se ve al escribirla. Si ves `stiv@stiv-rio:~ $`, estas dentro; sal con `exit`.

Si no encuentra `stiv-rio.local`: en la pagina del router busca la lista de dispositivos y usa la
IP de `stiv-rio`, por ejemplo `ssh stiv@192.168.1.57`.

## Paso 3 - Subir e instalar (en el PC, una sola orden)

Doble clic en **`subir_a_raspberry.bat`**. La primera vez tarda unos 10 minutos y pide la
contrasena de la Pi varias veces (al conectar, al copiar y para `sudo`).

Para no tener que escribir la contrasena cada vez, haz la primera subida asi, desde una ventana de
`cmd` abierta en esta carpeta:

```
subir_a_raspberry.bat -ConfigurarLlave
```

Otras opciones (se pueden combinar):

```
subir_a_raspberry.bat -Equipo 192.168.1.57      si stiv-rio.local no funciona
subir_a_raspberry.bat -SinInstalar              actualizar solo el codigo (unos segundos)
subir_a_raspberry.bat -SobrescribirConfig       pisar las configs de camara de la Pi con las del PC
```

Que copia: `stiv_directo.py`, esta carpeta (sin los `.bat`/`.ps1`) y los JSON de configuracion de
camara de `salidas\`. **Nunca** copia `.venv` (el de Windows no sirve en la Pi) ni los CSV.

## Paso 4 - Primera prueba (en la Pi)

```bash
ssh stiv@stiv-rio.local
cd ~/stiv
./raspberry/stiv.sh prueba
```

Mide el video de prueba (no hace falta camara ni internet). Mira las dos ultimas lineas:

- **`20.0 s de flujo en Y s de reloj`**: si Y es **menor que 20**, la Pi procesa mas rapido que el
  tiempo real y dara abasto con una camara.
- **`medida: Z ms`**: lo que tarda cada calculo de velocidad. Tiene que ser bastante menor que
  `--paso-medida` (5 s en `stiv.conf`).
- `./raspberry/stiv.sh prueba 5` repite 5 veces seguidas; despues mira la temperatura con
  `./raspberry/stiv.sh salud` (si `get_throttled` no es `0x0`, la Pi se esta frenando: calor o
  fuente).

**Las velocidades del video de prueba no valen como medida.** Esta recodificado y la
recodificacion anade ruido que el filtro de actividad confunde con textura (deja pasar a veces la
estacion 7, que esta en sombra). Solo sirve para comprobar que todo funciona y cuanto tarda.

## Paso 5 - Que arranque solo

```bash
./raspberry/stiv.sh activar
sudo reboot
```

Espera un minuto, vuelve a entrar y comprueba: `./raspberry/stiv.sh estado` tiene que decir
**`active (running)`**. Desde ahi arranca en cada encendido y, si el programa se cae (camara caida,
sin red, video de prueba terminado), systemd lo vuelve a lanzar a los 15 s.

Con el `stiv.conf` de ejemplo el servicio procesa el video de prueba una y otra vez. Para medir de
verdad, cambia la linea `STIV_ARGS` (paso siguiente o seccion "Usar tu camara").

## Paso 6 - Ver lo que mide

- En la Pi: `./raspberry/stiv.sh medidas` (ultimas filas del CSV) o `./raspberry/stiv.sh registro`
  (lo que imprime, en vivo; `Ctrl+C` sale y el programa sigue).
- En el PC: doble clic en **`traer_resultados.bat`**. Deja en `salidas_raspberry\` el CSV, la
  imagen anotada (`ultima_vista.png`, renovada cada `--vista-cada` segundos) y las configs.

## El dia a dia: `./raspberry/stiv.sh <orden>`

| Orden | Para |
|---|---|
| `estado` | ver si esta corriendo |
| `registro` | ver lo que imprime, en vivo |
| `medidas` | ultimas filas de cada CSV |
| `salud` | temperatura, frenado, disco, memoria |
| `editar` | cambiar `stiv.conf` (camara, opciones) |
| `reiniciar` | aplicar cambios de codigo o de `stiv.conf` |
| `parar` / `arrancar` | parar o arrancar el programa |
| `activar` / `desactivar` | poner o quitar el arranque automatico |
| `prueba [n]` | prueba de rendimiento con el video incluido (de dia) |
| `prueba-noche` | lo mismo con el video de noche (modo noche, escalas lentas) |
| `prueba-conf [s]` | ejecutar s segundos (60) con lo que diga `stiv.conf` |

Para **cambiar el codigo**: editalo en el PC, y `subir_a_raspberry.bat -SinInstalar` (copia y
reinicia el servicio en segundos).

**Apagar**: `sudo shutdown now`, esperar a que la luz verde deje de parpadear y desenchufar.
Quitar la corriente sin apagar puede estropear la microSD.

## Usar tu camara (Hikvision por RTSP)

La direccion de una Hikvision es
`rtsp://usuario:clave@IP_CAMARA:554/Streaming/Channels/101` (`101` = flujo principal, `102` =
secundario). Ajustes de la camara en su web, *Configuracion -> Video*: **H.264** (no H.265),
**H.264+ / Smart Codec desactivado**, bitrate constante (~4 Mbps), 1280x720, 15 fps, intervalo de
fotograma I = 15.

1. **En el PC, con ventana** (el PC tiene que ver la camara en su red), crea la camara y dibuja su
   cuadrilatero. Desde una ventana de `cmd` en la carpeta `analisis_kurome_directo_stiv`:
   ```
   .venv\Scripts\python.exe stiv_directo.py --camara sitio1 --fuente rtsp://usuario:clave@192.168.1.64:554/Streaming/Channels/101
   ```
   `sitio1` es un nombre nuevo cualquiera. Pulsa `e`, arrastra las 4 esquinas sobre un rectangulo
   real del agua (orden: aguas arriba-orilla A, aguas abajo-orilla A, aguas abajo-orilla B, aguas
   arriba-orilla B), `e` otra vez y `g` para guardar.
2. Abre `salidas\sitio1\config_stiv_directo.json` y pon las medidas reales del rectangulo en
   `largo_m` / `ancho_m`; si son reales, `escala_verificada: true`. En `parametros` puedes ajustar
   `V_ESPERADA` (velocidad aproximada del rio). Deja `FPS_CAMARA` en `null`: una camara IP entrega
   fotogramas reales, sin los duplicados de YouTube.
3. `subir_a_raspberry.bat -SinInstalar` (la config de `sitio1` viaja con el codigo; si la Pi ya
   tuviera una, anade `-SobrescribirConfig`).
4. En la Pi: `./raspberry/stiv.sh editar`, comenta la linea de prueba, descomenta la 3) con tu URL
   y `--camara sitio1`, guarda, y `./raspberry/stiv.sh reiniciar`.

**Antes de fiarte de los numeros**, dos constantes de `stiv_directo.py` se midieron sobre el codec
de YouTube y hay que volver a medirlas con tu camara: `ACTIVIDAD_MIN` (umbral que separa agua
congelada por el codificador de agua con textura) y, si la camara duplicara fotogramas,
`FPS_CAMARA`. Y la escala, mientras no sea medida, es un supuesto (la pantalla lo dice).

Si la camara se reinicia o se corta la red, el programa reconecta solo: espera hasta 15 s a que
lleguen fotogramas, reintenta 5 veces y, si sigue sin camara, termina y systemd lo relanza.

## Si algo falla

| Sintoma | Solucion |
|---|---|
| `ssh: Could not resolve hostname stiv-rio.local` | usa la IP del router: `-Equipo 192.168.1.57` |
| `WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED` | regrabaste la microSD: `ssh-keygen -R stiv-rio.local` en el PC |
| `\r: command not found` al ejecutar un `.sh` | se guardo con finales de linea de Windows. `subir_a_raspberry` lo corrige solo; si editaste en la Pi: `sed -i 's/\r$//' raspberry/*.sh` |
| la instalacion de librerias falla o tarda horas | el sistema es de 32 bits: regraba con **64-bit** |
| `Sign in to confirm you're not a bot` | YouTube bloquea esa conexion. Usa el video de prueba o tu camara; o exporta `cookies.txt` de un navegador con sesion iniciada y activa `STIV_COOKIES` en `stiv.conf` |
| `cola` sube sin parar en `registro` | la Pi no da abasto: baja resolucion/fps en la camara o usa el canal `102` |
| `get_throttled` distinto de `0x0` | calor (disipador/ventilador) o fuente insuficiente (usa la oficial) |
| no hay imagen nueva en `ultima_vista.png` | `--vista-cada` solo escribe cuando ya hay una medida (10 s tras arrancar) |

## Que se probo y que no (2026-10-12)

Probado, sin Raspberry real, con el banco de pruebas de `../pruebas_docker/` (se puede repetir:
`probar_en_docker.bat`):

- **El paquete entero en un Linux ARM de 64 bits emulado** (Debian 13 aarch64 en Docker, con
  systemd y SSH; Raspberry Pi OS es Debian): `subir_a_raspberry.ps1` instala desde cero (apt, venv,
  OpenCV 5.0 sin pantalla, numpy 2.5, servicio) en ~8 min emulado; `stiv.sh prueba` da los mismos
  numeros que en el PC; `activar` + reinicio del sistema -> el servicio arranca solo; `-SinInstalar`
  actualiza en 6 s sin pisar `stiv.conf`; `traer_resultados.ps1` trae CSV, imagen y configs.
- **RTSP**: un servidor RTSP (mediamtx) emitiendo el video de prueba en H.264, conectado como camara
  nueva (`--camara ... --fuente rtsp://...`), configurada despues solo con el JSON. Cortando la
  emision 8 s: reconecta solo y vuelve a medir 10 s despues (lo que tarda en llenarse el STI).
- Fallos encontrados y corregidos en esas pruebas: `cv2.destroyAllWindows()` revienta en OpenCV sin
  pantalla; al reconectar, el tiempo del flujo volvia a 0 y no se media hasta superar el tiempo de
  antes del corte; la cola de 600 fotogramas llevaba la memoria a 1.3 GB (ahora 150, ~626 MB).

**No probado** (necesita la Pi de verdad):

- **Cuanto tarda una Pi 4B**: la emulacion no dice nada de la velocidad real. Es lo primero que
  mide `stiv.sh prueba`. En el PC: 1-2 ms por fotograma y ~0.5 s por medida.
- `stiv.sh registro` (journald no funciona en el contenedor), la temperatura (`vcgencmd`), el
  nombre `stiv-rio.local`, la contrasena de `sudo` pedida a traves de `ssh -t`, y `-ConfigurarLlave`
  (no se probo para no tocar la carpeta `.ssh` de este PC).
- Una camara Hikvision real.
