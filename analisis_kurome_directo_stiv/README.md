# STIV en directo - camaras de vigilancia de rios de Tokio

STIV desde cero sobre OpenCV aplicado **en tiempo real** a directos de YouTube de las camaras de
vigilancia del Gobierno Metropolitano de Tokio (Tokyo Suibou Channel). Al arrancar, el script
resuelve el flujo con yt-dlp, lo abre y empieza a medir; no hay paso previo. pyorc no se importa en
ningun momento.

| `--camara` | Rio y lugar | Directo |
|---|---|---|
| `myoshoji` (**por defecto**) | rio Myoshoji en Kamitakada (Nakano) | `https://www.youtube.com/watch?v=huAp4q7lxiQ` |
| `kurome` | rio Kurome en el puente Koma (Higashikurume) | `https://www.youtube.com/watch?v=loW9744B-Co` |

El metodo es el mismo para las dos; lo que cambia por camara (URL, cuadrilatero, dimensiones
supuestas, `v_esperada`, longitud de linea, ancho de banda) esta en el diccionario `CAMARAS` al
principio de `stiv_directo.py`. Anadir una camara del mismo canal es anadir una entrada ahi. La
carpeta conserva el nombre del primer caso (`kurome`).

## Arrancar

Doble clic en `arrancar.bat` (Myoshoji), o desde esta carpeta:

```powershell
.\.venv\Scripts\python.exe stiv_directo.py                         # Myoshoji, con ventana
.\.venv\Scripts\python.exe stiv_directo.py --camara kurome         # Kurome
.\.venv\Scripts\python.exe stiv_directo.py --sin-ventana --duracion 120   # solo CSV, 2 min
.\.venv\Scripts\python.exe stiv_directo.py --archivo clip.mp4      # mismo metodo sobre un video
.\.venv\Scripts\python.exe stiv_directo.py --camara sitio1 --fuente rtsp://usuario:clave@IP:554/Streaming/Channels/101
```

`arrancar.bat` pasa sus argumentos al script (`arrancar.bat --camara kurome`).

- **`--camara <nombre nuevo>` + `--fuente <URL>`**: camara propia (p. ej. una Hikvision por RTSP).
  Parte de un cuadrilatero generico que hay que arrastrar con `e`; su config (URL incluida) queda
  en `salidas/<nombre>/config_stiv_directo.json` y desde ahi manda: las siguientes veces basta
  `--camara <nombre>`. RTSP va por TCP, con 15 s de tiempo de espera y reconexion automatica.
- `--paso-medida S` (segundos entre medidas, 1 por defecto) y `--vista-cada S` (sin ventana: guarda
  `ultima_vista.png` cada S s) existen sobre todo para la Raspberry Pi.
- Si YouTube responde "Sign in to confirm you're not a bot" (le paso a este PC el 2026-10-12),
  `STIV_COOKIES=ruta\cookies.txt` le pasa a yt-dlp las cookies de un navegador con sesion.

## Raspberry Pi

`raspberry/` tiene todo para ejecutarlo en una **Raspberry Pi 4B** sin pantalla y que arranque solo
al encenderse: `subir_a_raspberry.bat` (en el PC) lo copia e instala, `stiv.sh` lo maneja en la Pi,
y trae un video de prueba de 20 s para probar sin camara ni internet. Instrucciones paso a paso, y
lo que se probo y lo que no, en [raspberry/LEEME.md](raspberry/LEEME.md).

`pruebas_docker/` es el banco de pruebas con el que se probo ese paquete sin hardware: una
Raspberry Pi falsa (Debian 13 arm64 emulado, con systemd y SSH) y una camara RTSP simulada que emite
el video de prueba. `probar_en_docker.bat` lo levanta, instala el paquete con el mismo
`subir_a_raspberry.ps1` y ejecuta la prueba. Ver [pruebas_docker/LEEME.md](pruebas_docker/LEEME.md).
Esta fuera de `raspberry/` a proposito: todo lo de `raspberry/` viaja a la Pi.

La carpeta tiene su **propio entorno** `.venv` (numpy, opencv-python, yt-dlp; `requirements.txt`),
porque `pyorc_env` de la raiz esta incompleto en este equipo (no tiene `Scripts\`). Si `.venv` no
existe, `arrancar.bat` lo crea e instala las librerias. Si el script se lanza con otro Python al que
le faltan librerias (p. ej. el interprete que elige VS Code al darle a "Run"), **se relanza solo con
`.venv`**. El Python 3.13 por defecto de este equipo tambien las tiene ya instaladas.

Teclas: `q` salir | `e` editar el cuadrilatero arrastrando sus esquinas (el video sigue corriendo) |
`g` guardar la config | `r` vaciar el buffer | espacio congelar la imagen (la medida sigue) |
`f` pantalla completa | `+` / `-` agrandar / achicar | `p` ocultar/mostrar el panel de STI.

La ventana abre al ~90 % de la pantalla, centrada, y se redimensiona arrastrando el borde sin
deformar la imagen. En una pantalla 1920x1080 el limite es la altura (el panel de STI ocupa 210 px):
abre a 1335x964 con panel y a 1728x972 sin el (`p`). Editar el cuadrilatero funciona igual a
cualquier tamano: comprobado con clics simulados, OpenCV devuelve el raton en coordenadas de la
imagen.

El STI necesita 10 s de video antes de la primera medida; despues se recalcula cada segundo.

## Que se ve

- Arriba, el directo con el cuadrilatero, las 9 lineas de busqueda (verde = aceptada, rojo =
  rechazada) y una flecha por estacion aceptada: 2 s de recorrido en el mundo, con la punta
  proyectada, asi que la perspectiva la acorta sola.
- Abajo, **el STI de cada estacion con la pendiente ajustada dibujada encima**. Es lo que hace
  auditable cada flecha: si la linea no sigue las estelas, el numero no vale.
  `c` = coherencia, `b` = bloques activos del tensor.

## Salidas (`salidas/<camara>/`)

| Archivo | Contenido |
|---|---|
| `medidas_directo.csv` | una fila por estacion y medida: hora, v, coherencia, bloques activos, aceptada, motivo. **Se anade**, no se sobrescribe. |
| `config_stiv_directo.json` | camara, URL, cuadrilatero, dimensiones, `escala_verificada` y todos los parametros |
| `ultima_vista.png` | la ultima imagen dibujada, al salir |

## LA ESCALA ES UN SUPUESTO, en las dos camaras

No hay GCPs, ni anchos medidos, ni secciones publicadas para ninguno de los dos puntos (se busco en
los documentos del Gobierno Metropolitano). Los cuadrilateros semilla se trazaron a ojo sobre el
borde del agua y sus dimensiones son suposiciones: **Myoshoji 10 m x 8 m, Kurome 15 m x 6 m**.
Mientras `escala_verificada` sea `false` en la config, la pantalla dice "ESCALA SUPUESTA" y el CSV
lo registra. La coherencia, que estacion pasa y la *forma* del perfil no dependen de esas
dimensiones; los m/s si, linealmente con `largo_m` (la direccion del flujo).

Para hacerlo metrico: medir dos distancias reales sobre el agua (p. ej. en un mapa), arrastrar el
cuadrilatero con `e` para que sea un rectangulo real, guardar con `g`, editar `largo_m`/`ancho_m` en
el JSON y poner `escala_verificada: true`. En el Myoshoji, el muro derecho es de bloques de
mamposteria de tamano regular: contar bloques a lo largo del flujo daria el largo en "bloques", y
con el tamano de un bloque, en metros.

## Lo que se midio de los directos antes de escribir el metodo

- **Las dos camaras emiten a 15 fps y YouTube duplica cada fotograma** para llegar a 30 (patron
  2,2,2... en 150 de 150 cambios en el Kurome, 298 de 298 en el Myoshoji). El PTS es perfectamente
  regular (todos los saltos de 33 ms). Por eso el STI se construye sobre la rejilla de 30 fps del
  PTS **sin deduplicar**: deduplicar por contenido descarto fotogramas reales en una prueba (132
  filas nuevas de 300). Un STI sintetico con cada fotograma duplicado recupera la pendiente exacta
  (1.000 -> 1.000, coherencia 0.99), asi que los duplicados no sesgan el tensor.
- **Kurome: el agua avanza hacia la derecha** de la imagen, ~-7 grados (correlacion de conjunto en
  el rapido: +8 px, -1 px en 4 fotogramas reales). `v_esperada = 0.40 m/s` -> DS 13.3 mm = 0.89 px.
- **Myoshoji: la camara mira a lo largo del cauce y el agua se aleja** (sube en la imagen): -1 px por
  fotograma real en las tres zonas bajas. El agua blanca del salto (y~300-370) da desplazamiento 0:
  es estacionaria, y por eso el cuadrilatero acaba justo debajo. `v_esperada = 0.30 m/s` -> DS 10 mm,
  que son 0.50 px de imagen por muestra cerca y **0.23 px al fondo**, apenas por encima del ~0.2 px
  que `analisis_canal_lejano_stiv/` midio como frontera del aliasing. No alargar el cuadrilatero
  hacia el salto sin mirar ese numero (se imprime al arrancar como mediana).

## Decisiones que no hay que "arreglar"

- **Seleccion de bloques por actividad entre fotogramas reales.** El codificador de YouTube congela
  el agua lisa (bloques "skip"): en el STI son rayas verticales perfectas, coherencia ~0.9 y
  velocidad 0.00. La primera version aceptaba asi estaciones a 0.00 m/s - la trampa de Boneyard,
  ahora causada por el codec. La actividad es la mediana de |I(t + 1/15 s) - I(t)|: el agua
  congelada da **exactamente 0.00**, el agua con textura **0.7-5.6** niveles de gris.
  `ACTIVIDAD_MIN = 0.5` esta en ese hueco, y se aplica **por pixel** dentro del tensor (los parches
  congelados aparecen tambien dentro del agua activa). En el Myoshoji es lo que rechaza las
  estaciones 7-8, sobre la sombra oscura del muro derecho (0 bloques activos).
- **Normalizacion temporal por posicion** antes del tensor (resta la media, divide por la
  desviacion de cada muestra): quita lo estatico sin parametros, incluidos los reflejos fijos.
- **`COH_MIN = 0.40`, no 0.70.** El STI nocturno del rapido del Kurome da 0.3-0.55 con estelas
  claras a simple vista, y el control sintetico da 0.99, asi que lo bajo es la textura, no el
  estimador. 0.40 es el valor de Boneyard (espuma fina). **Elegido viendo datos nocturnos del
  Kurome**: dicho aqui para que no pase por un valor a priori. En el Myoshoji, de dia, las
  estaciones aceptadas dan 0.52-0.76, holgadas.
- **Suavizado del STI de 1 fila, no mas.** Al subirlo a 2-3 la velocidad baja un 10-15 % en el
  Kurome, y en el sintetico no cambia nada: es fisico - en el rapido hay textura fina que viaja con
  el agua y estructura gruesa casi estacionaria (ondas fijas), y suavizar da peso a la segunda.
- `V_MAX_FISICA = 3 x v_esperada`, como en los otros casos STIV.
- **La medida corre en un hilo aparte.** Cuesta ~140 ms; el directo entrega un fotograma cada
  33 ms. Medido: 1-2 ms por fotograma en el hilo principal (lectura + muestreo; eran 4-9 ms hasta
  que el gris y el suavizado pasaron a hacerse solo sobre el recuadro que tocan las lineas, con
  resultado identico bit a bit), ~12 ms mas el dibujo. Si el proceso se retrasa mas de 2 s
  respecto al flujo, se dibuja 1 de cada 3 fotogramas, pero todos entran al STI. La cola de
  fotogramas leidos y sin procesar admite 150 (~415 MB): con 600 la memoria llego a 1.3 GB.
- El directo llega a rafagas (al arrancar entrega varios segundos de golpe): se reproduce a ritmo
  real segun el PTS. Un hueco de PTS se rellena repitiendo la ultima fila. Un salto de mas de 1 s,
  un PTS que retrocede (camara o emisor reiniciado: el tiempo vuelve a 0) o una reconexion vacian
  el STI y **re-anclan el reloj** para que t siga creciendo; sin re-anclar, tras una reconexion no
  se media hasta que el t nuevo superaba al de antes del corte (hallado cortando un RTSP de
  prueba). Si el flujo se corta, se vuelve a resolver la URL (las de HLS caducan) y se reconecta.

## Resultados de las pruebas (2026-10-09)

**Myoshoji, de dia** (40 s en directo + dos ventanas de 10 s de un clip grabado): **6 de 9
estaciones** aceptadas en todo momento (0-5), a 0.42-0.59 m/s, y **mediana de la seccion
0.448-0.456 m/s** - bajo la escala supuesta. La 6 falla por coherencia (0.30-0.34) y la 7-8 no
tienen textura (sombra). El maximo esta en la estacion 2, en el centro de la mancha iluminada.

**Kurome, de noche** (infrarrojo, varias corridas de 15-60 s): las estaciones **3, 4 y 5** (el
rapido central) se aceptan de forma estable a **0.55-0.74 m/s**, mediana 0.61-0.74 m/s - bajo la
escala supuesta. La 0 cae sobre la vegetacion (sin textura), la 1-2 y la 6-7 fallan por coherencia
y la 8 da ~1.4 m/s y la para `V_MAX_FISICA` (esta junto a las plantas de la orilla cercana).
**Ojo:** en una corrida corta de dia la estacion 8 del Kurome paso el control a 1.18 m/s con
coherencia 0.65, justo bajo el limite de 1.2 m/s. Esta sobre la vegetacion de la orilla cercana y
es sospechosa; no se ha revisado de dia.

**Nada valida esos numeros**: no hay aforo ni referencia. Son reproducibles y coherentes entre
ventanas, no exactos.

## Limites conocidos

- **Escala supuesta** (arriba). Es, de lejos, la mayor incertidumbre.
- `ACTIVIDAD_MIN` y `COH_MIN` se fijaron con el Kurome de noche; en el Myoshoji de dia funcionan,
  pero no se han revisado el Myoshoji de noche ni el Kurome de dia con calma.
- Los reflejos del Myoshoji (arboles, cielo, muro) son estaticos y la normalizacion los quita; lo
  que queda en el STI son estelas regulares que siguen el agua. No se ha descartado del todo que
  parte de la textura sea rizado que viaja a otra velocidad que la corriente.
- Las semillas de los cuadrilateros son a ojo. Si al arrastrarlos el canal no queda "recto" (las
  lineas no siguen el agua), la rectificacion esta mal.
- Si una camara gira o hace zoom (el canal avisa de que lo hacen durante emergencias), su geometria
  deja de valer.
- yt-dlp avisa de que, sin un runtime de JavaScript (deno), la extraccion de YouTube esta en
  desuso. Hoy funciona; si un dia deja de resolver el flujo: `pip install -U yt-dlp` en `.venv`,
  o instalar deno.
- No hay caudal: no hay seccion ni batimetria.
