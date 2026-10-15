# Resultados de las pruebas del paquete raspberry/ (2026-10-15)

Tres sitios donde se probo el mismo paquete, con los mismos scripts (`subir_a_raspberry.ps1`,
`instalar.sh`, `stiv.sh prueba`). Las dos simulaciones prueban que **funciona**; solo la Pi real
dice **a que velocidad**.

| | Pi falsa (Docker) | Pi OS simulada (Docker + QEMU) | **Pi 4 real (alquilada)** |
|---|---|---|---|
| Hardware | CPU ARM emulada | Cortex-A72 emulado, 4 nucleos, 4 GB | **Raspberry Pi 4 Model B Rev 1.2, 4 GB** |
| Sistema | Debian 13 arm64 (contenedor) | Raspberry Pi OS Lite trixie 2026-10-06, arm64 | Raspberry Pi OS bookworm (Debian 12), arm64 |
| Kernel | el de Docker Desktop | 6.18.50+rpt-rpi-v8 (recompilado con virtio) | 6.1.21-v8+ |
| Python / numpy / OpenCV | - | 3.13 / 2.5.4 / 5.0.0.93 | 3.11.2 / 2.4.6 / 5.0.0.93 |
| Disco | contenedor | imagen de 32 GB | NFS de red, 10 GB |
| Instalacion completa | ~8 min | ok | **236 s, a la primera** |
| `stiv.sh prueba` (20 s de video) | - | 56.8 s de reloj | **10.8-11.4 s de reloj** |
| Lectura+muestreo por fotograma | - | 88.6 ms | **16.0-17.2 ms** (limite 33 ms) |
| Cada medida | - | 2738 ms | **714-922 ms** (limite: `--paso-medida`, 5 s en stiv.conf) |
| Velocidad medida (clip de prueba) | 0.49 m/s, 6/9 | 0.49 m/s, 6/9 | 0.49 m/s, 6/9 |
| Temperatura | - | no hay sensor | 42.8 -> **53.0 C** maximo, 1500 MHz, `throttled=0x0` |
| `vcgencmd` | no existe | existe y falla | funciona (usuario en el grupo `video`) |

Los tiempos de las dos simulaciones **no valen como rendimiento**: son CPU ARM emulada sobre x86.

## Pi 4 real: detalle

- Raspberry Pi 4B de 4 GB alquilada en Mythic Beasts (centro de datos, refrigerado). El sistema se
  reinstalo a "Raspberry Pi OS Bookworm (12) (64 bit)": no ofrecen trixie. Usuario `stiv` con sudo
  sin contrasena creado a mano (la imagen solo trae `root`).
- **Diez vueltas seguidas** de `stiv.sh prueba` (~2 min a plena carga): 20 s de video en 10.8-11.4 s,
  es decir **~1.8x mas rapido que el tiempo real**, estable de una vuelta a otra.
- **Directo de YouTube del Myoshoji, 60 s**: YouTube no bloqueo la IP del centro de datos. 60 s de
  flujo procesados en tiempo real, 18.6 ms/fotograma, **1084 ms por medida** con una medida por
  segundo (justo por encima del presupuesto; con `--paso-medida 5`, como en stiv.conf, sobra).
  Estaciones 3-6 a 0.47-0.52 m/s, en linea con la mediana diurna verificada de 0.483 m/s.

## Lo que esta prueba NO cubre

- trixie (la placa llevara trixie; aqui bookworm, Python 3.11 en vez de 3.13);
- microSD (aqui disco de red);
- temperatura en una caja a la intemperie (aqui centro de datos refrigerado);
- funcionamiento continuo durante horas con el servicio activado.
