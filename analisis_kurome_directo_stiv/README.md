# STIV en directo - camaras de vigilancia de rios de Tokio

STIV desde cero sobre OpenCV aplicado **en tiempo real** a directos de YouTube de las camaras de
vigilancia del Gobierno Metropolitano de Tokio (Tokyo Suibou Channel). Al arrancar, el script
resuelve el flujo con yt-dlp, lo abre y empieza a medir; no hay paso previo. pyorc no se importa en
ningun momento.

| `--camara` | Rio y lugar | Directo |
|---|---|---|
| `myoshoji` (**por defecto**) | rio Myoshoji en Kamitakada (Nakano) | `https://www.youtube.com/watch?v=huAp4q7lxiQ` |
| `kurome` | rio Kurome en el puente Koma (Higashikurume) | `https://www.youtube.com/watch?v=loW9744B-Co` |
| `shimoda` | rio Kurome en el puente Shimoda (Higashikurume) | `https://www.youtube.com/watch?v=bpL7MAbdoI8` |
| `akigawa` | rio Aki en Todohara (Akiruno) | `https://www.youtube.com/watch?v=ZRUh9gNk8-g` |

El metodo es el mismo para las dos; lo que cambia por camara (URL, cuadrilatero, dimensiones
supuestas, `v_esperada`, longitud de linea, ancho de banda) esta en el diccionario `CAMARAS` al
principio de `stiv_directo.py`. Anadir una camara del mismo canal es anadir una entrada ahi. La
carpeta conserva el nombre del primer caso (`kurome`).

## Arrancar

Doble clic en `arrancar.bat`: muestra un **menu con las fuentes de `fuentes.json`** (los dos
directos y los dos videos de prueba) y arranca la elegida. O desde esta carpeta:

```powershell
.\.venv\Scripts\python.exe stiv_directo.py                         # Myoshoji, con ventana
.\.venv\Scripts\python.exe stiv_directo.py --camara kurome         # Kurome
.\.venv\Scripts\python.exe stiv_directo.py --sin-ventana --duracion 120   # solo CSV, 2 min
.\.venv\Scripts\python.exe stiv_directo.py --archivo clip.mp4      # mismo metodo sobre un video
.\.venv\Scripts\python.exe stiv_directo.py --camara sitio1 --fuente rtsp://usuario:clave@IP:554/Streaming/Channels/101
```

`arrancar.bat` con argumentos se los pasa al script sin menu (`arrancar.bat --camara kurome`);
`--elegir` es el menu.

### Cambiar de directo o de video: `fuentes.json`

`fuentes.json` es la lista de fuentes. Con la ventana abierta, **`c` pasa a la siguiente** y
**`1`-`9` van directamente a esa** (la cabecera dice "fuente n/N"): se cierra la fuente actual (CSV
incluido) y se abre la nueva en la misma ventana. Si la nueva no abre (YouTube bloqueado, camara
apagada) vuelve a la anterior. Cada fuente escribe en su `salidas/<camara>/`.

Anadir una es anadir una entrada:

```json
{"titulo": "Mi camara", "camara": "sitio1", "url": "rtsp://usuario:clave@IP:554/Streaming/Channels/101"}
```

- `camara` fija la geometria y la carpeta de salida: `myoshoji`, `kurome` o un **nombre nuevo**
  (parte de un cuadrilatero generico: arrastrarlo con `e` y guardarlo con `g`).
- `url` (directo: YouTube, RTSP, HLS) o `archivo` (video grabado, relativo a esta carpeta).
- `modo` opcional: `auto` si falta. El video de prueba de dia necesita `"dia"` (esta guardado en gris).
- `ajustes` opcional, valores por camara: p. ej. `{"fps_camara": 15.0}` para **otro directo de
  YouTube** de Tokyo Suibou (emiten a 15 fps duplicados a 30; sin esto la mascara de actividad
  compara duplicados, ve 0 y no acepta nada), o `{"v_esperada": 0.5}`.

Sin `fuentes.json` (p. ej. en la Raspberry, adonde no viaja) la lista son las camaras de `CAMARAS`.

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

Teclas: `q` salir | `c` siguiente fuente | `1`-`9` fuente n de `fuentes.json` | `e` editar el
cuadrilatero arrastrando sus esquinas (el video sigue corriendo) | `g` guardar la config | `r` vaciar el buffer | espacio congelar la imagen (la medida sigue) |
`f` pantalla completa | `+` / `-` agrandar / achicar | `p` ocultar/mostrar el panel de STI.

La ventana abre al ~90 % de la pantalla, centrada, y se redimensiona arrastrando el borde sin
deformar la imagen. En una pantalla 1920x1080 el limite es la altura (el panel de STI ocupa 210 px):
abre a 1335x964 con panel y a 1728x972 sin el (`p`). Editar el cuadrilatero funciona igual a
cualquier tamano: comprobado con clics simulados, OpenCV devuelve el raton en coordenadas de la
imagen.

El STI necesita 10 s de video antes de la primera medida; despues se recalcula cada segundo.

## Que se ve

- **Dos vistas lado a lado.** A la izquierda el directo con el cuadrilatero, las 9 lineas de
  busqueda (verde = aceptada, rojo = rechazada) y una flecha por estacion aceptada, con la punta
  proyectada, asi que la perspectiva la acorta sola. A la derecha la **vista rectificada**: el agua
  en planta, como desde arriba, con el flujo de izquierda a derecha, las mismas lineas y flechas a
  escala real y una barra de 1 m. Si al arrastrar el cuadrilatero el cauce no queda recto en la
  vista rectificada, la rectificacion esta mal.
- Cada flecha representa los segundos de recorrido que hagan falta para que la mediana mida ~1 m
  (entre 2 y 60 s); la cabecera dice cuantos. Con 2 s fijos, el agua de la noche (0.05 m/s) daba
  flechas de 10 cm, invisibles.
- Abajo, **el STI de cada estacion con la pendiente ajustada dibujada encima**, en la escala en la
  que se midio. Es lo que hace auditable cada flecha: si la linea no sigue las estelas, el numero no
  vale. Etiqueta: velocidad, `c` = coherencia, `b` = bloques activos, y la escala (10s/30s/60s); en
  las rechazadas, el motivo.

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

**Myoshoji, 2026-10-13: el ancho ya esta medido, el largo no.** La camara es la estacion 上高田上
(Kamitakada 5-6, Nakano; 35.717608, 139.678653 segun la ficha del sistema de Tokio). En ortofoto
(Google/Airbus, escala comprobada con una pista de tenis al 0.4 %) el cauce mide **8.8 m +-0.7 de
coronacion a coronacion**, constante de -20 a +40 m; `ancho_m` pasa de 8.0 a 8.8 (el JSON lo anota
en `nota_escala`). Al nivel del agua puede ser hasta ~1.4 m menos si el muro derecho de mamposteria
esta en talud o hay berma. Cambiar el ancho no cambia las velocidades (van a lo largo del flujo):
con la grabacion de 200 s la mediana sigue en 0.46-0.50 m/s. El "salto" del fondo no es un salto:
de dia es una zona de piedras con agua blanca estacionaria, de noche el reflejo de una farola.

Para el largo se probo un modelo de camara (punto de fuga de los muros + 8.8 m + coronacion del muro
derecho + fin de las gradas a +7 m segun la ortofoto): da camara a 8.4 m sobre el agua, muro de
6.0 m y **cuadrilatero de 9.6 m de largo** (7.9-13.4 segun los supuestos; el mas influyente es la
altura del paseo de las gradas respecto a la coronacion derecha). Pero **no pasa una comprobacion
independiente**: una persona en el paseo del fondo mide 76 px y el modelo la predice de 102-177 px.
Por eso `largo_m` se queda en 10 m (supuesto) y `escala_verificada` en false. Ojo tambien: por la
imagen (muro izquierdo de canto, derecho de frente, gradas junto a la camara) la camara parece estar
en la orilla izquierda (este), no en la derecha como situa la ficha; las distancias medidas desde
las coordenadas de la ficha pueden llevar ese desfase.

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

## Noche y agua lenta (2026-10-13)

> **CORREGIDO el 2026-10-14 (ver `verificacion_nivel/README.md`).** Lo que sigue concluia que de noche
> el agua del Myoshoji iba ~10 veces mas despacio. Es falso: con el mismo nivel de dia se miden
> 0.46-0.50 m/s, y el caudal oficial del puente Ochiai da ~0.4-0.6 m/s en superficie. Las "motas" que
> avanzan a ~0.05 m/s son destellos de farola sobre ondulaciones casi fijas de la superficie, no la
> corriente; por eso el Myoshoji lleva ahora `"medir_noche": False`. Las escalas lentas y el modo
> noche siguen en el programa (sirven para agua lenta de verdad y para otras camaras); lo que fallaba
> era el trazador.

De noche el programa no media nada en el Myoshoji, aunque se veia basura moverse. Medido sobre
79 s grabados del directo:

- **El agua iba ~10 veces mas despacio que el dia de la calibracion**: ~0.05 m/s (escala supuesta)
  frente a 0.45 m/s, es decir **0.1 px por fotograma real**. Lo confirmo un juez independiente sin
  STIV (correlacion de conjunto de las motas a desfases de 0.5 a 8 s: el pico se desplaza en
  proporcion al tiempo, hacia arriba en la imagen). A desfases de un fotograma no hay pico: el
  movimiento es demasiado pequeno.
- Con eso fallaban tres cosas: el STI de 10 s fotograma a fotograma veia estelas casi verticales;
  el filtro de actividad (comparar fotogramas consecutivos) daba 0 en todo -> "sin textura"; y los
  reflejos de las farolas, cuyos destellos viajan con las ondas, daban 5-11 m/s.

Lo que se cambio:

- **Tres escalas de tiempo en cascada** (`ESCALAS`): 10 s fotograma a fotograma, 30 s con filas
  cada 0.133 s y 60 s con filas cada 0.5 s (las lentas son promedios: antialias temporal). Cada
  estacion se mide en la **primera** escala que resuelve su movimiento (|pendiente| >= 0.3 muestras
  por fila); solo baja a una mas lenta si la rapida dice "demasiado lento" o "sin textura", y en las
  lentas una estela casi horizontal (|pendiente| > 2.5) se rechaza como `ambiguo` en vez de aceptar
  un posible aliasing de agua rapida. De dia todo sigue midiendose en la rapida, con los mismos
  numeros que antes (clip de prueba: 0.526/0.519/0.515, identico).
- **Modo noche automatico** (`--modo auto`, por defecto; `dia`/`noche` lo fuerzan): cuando la
  camara pasa a infrarrojo la saturacion de color del agua es exactamente 0. En modo noche: top-hat
  de 9 px (deja las motas de 2-6 px, borra los reflejos grandes y los bloques congelados), resta de
  la mediana temporal de cada posicion sin dividir por la desviacion, y **exclusion del
  deslumbramiento**: las posiciones con brillo mediano > 60 (agua 4-41, farolas 59-255) no
  cuentan. Sin esa exclusion la estacion 5 daba 0.91 y 0.33 m/s en las escalas rapidas; con ella
  las tres escalas coinciden (0.059/0.053/0.055).
- Los cambios de modo tienen histeresis (tres lecturas iguales, una cada 5 s) y vacian el STI.
- El CSV gana dos columnas (`s_por_fila`, `modo`); un CSV con las columnas antiguas se aparta con
  la fecha en el nombre en vez de mezclarse.

Resultado en directo, de noche (2026-10-13, 80 s): **5-6 de 9 estaciones desde t = 30 s, mediana
de la seccion 0.056-0.067 m/s**, estable entre medidas, casi todas en la escala de 30 s. Las 0-2 (orilla
izquierda, mas oscura, pocas motas) salen sin textura. La medida cuesta ~0.3 s en el PC (antes
0.14): hay que calcular hasta tres escalas.

`raspberry/prueba/myoshoji_noche_90s.mp4` es esa noche grabada (recodificada), para probar el
modo noche sin directo: `stiv.sh prueba-noche` en la Pi o `--archivo` en el PC.

## Fotogramas duplicados, burbujas junto al muro y el Shimoda (2026-10-13, tarde)

**El STI rapido se construye ahora con una fila por fotograma REAL de la camara** (el promedio de
cada par de duplicados de YouTube), no con una por fotograma del flujo. Con los duplicados el STI es
una escalera, y en cuanto el agua avanza mas de ~1.5 muestras por fila el tensor la sobreestima. STI
sintetico de pendiente conocida: 2.0 -> 2.14 (+7 %), 2.5 -> 3.15 (+26 %, coherencia 0.54), 3.0 ->
5.6; sin duplicados es exacto hasta 3. Consecuencias medidas: el Kurome de dia bajo de ~0.94 a ~0.85
m/s (estaba un 10-20 % inflado), el clip de dia del Myoshoji de 0.52 a 0.49-0.50, y la noche no
cambia (va por las escalas lentas). DS se duplica (0.32 -> 0.65 px en el Myoshoji, mas lejos del
limite de aliasing). Una correlacion de conjunto independiente en el Kurome da 0.72-1.0 m/s en las
estaciones 5-8 frente a 0.75-1.10 del STIV; en las 1-2 el STIV queda un 25 % por encima. Nada lo
valida en campo.

**Burbujas sobre agua oscura (Myoshoji, estaciones 6-8, junto al muro derecho).** El agua en sombra
no tiene textura y solo lleva burbujas sueltas: el proceso de dia las diluye (actividad de la banda
~0, coherencia 0.14-0.33) y esas estaciones nunca median. Ahora, de dia, una estacion que falla se
**reintenta con el realce de motas del modo noche** (top-hat + resta de la mediana temporal). Las
burbujas derivan despacio, ~0.02-0.05 m/s con coherencia 0.7-0.9, igual en dos escalas, y se miden
en la de 60 s: con 200 s grabados, **9 de 9 estaciones desde t = 70 s** (antes 6). En la consola,
la letra de la escala sale en MAYUSCULAS (R/M/L) cuando se midio asi, y el CSV pone `dia+motas` en
la columna `modo`. "ambiguo" no se reintenta (es agua rapida, no falta de textura). Ademas las lineas
del Myoshoji pasan de 6 a 9 m para llegar a la parte cercana a la camara. Coste: la medida pasa de
~0.35 a ~0.7 s en este PC.

**`shimoda` (puente Shimoda, Kurome, `bpL7MAbdoI8`).** El agua va de derecha a izquierda, *hacia*
el puente (el agua blanca bajo el puente es un rapido aguas abajo): el STI y una correlacion 2D lo
confirman. Escala supuesta 12 x 5 m. El dia que se configuro (lluvia) el agua iba a 4-5 px por
fotograma real junto a la orilla cercana (~1.3 m/s) y a 10-30 px en el centro, donde a 15 fps la
textura no sobrevive de un fotograma al siguiente. En directo mide las estaciones 4-8 (la mitad
cercana), mediana ~1.35 m/s; las 0-3 salen "coherencia"/"ambiguo". `v_esperada` 0.6: con 0.4 el
tensor medía bien pero todo caía por encima del tope fisico de 1.2 m/s.

**Filtro direccional (`filtro_direccional`, por camara; activo solo en `shimoda`).** A las 18 h el
Shimoda daba signos opuestos en estaciones vecinas (+3.1 / -2.5 / -3.8 m/s), "ambiguo" y "v_max":
con el agua a 1-1.5 m/s las ondas de la superficie, casi regulares, avanzan entre dos fotogramas
reales mas de media longitud de onda, y el STI muestra una trama cruzada (las estelas reales "\" y
su imagen estroboscopica "/", el efecto de las ruedas que giran al reves en el cine). El filtro
anula en el espectro 2D del STI los cuadrantes de lo que avanza aguas arriba y deja solo lo que
avanza aguas abajo (+x del cuadrilatero). Resultado en 90 s grabados: de 0-6 estaciones-medida
aceptadas a 156-162 (9/9 casi siempre), mediana 0.94-1.00 m/s **con DS de 2, 3 y 4 px**: no sigue
al muestreo, que es lo que haria un artefacto del filtro (el ruido filtrado tiende a 45 grados). En
la grabacion de la tarde, 9/9 tambien (antes 1-2). Impone el sentido del flujo, asi que exige el
cuadrilatero bien orientado y oculta un contraflujo real (sale como coherencia baja). Por eso no es
global. Probado en las demas: Kurome bajaria de 0.86 a 0.66 m/s (estable con el muestreo, y mas
cerca de una correlacion independiente: 0.72), Myoshoji un 7-10 % con mas estaciones; en `akigawa`
"mediria" ~0.7 m/s pero el valor sube un 20 % con el muestreo y nada lo confirma. Se activa en
otra camara con `"ajustes": {"filtro_direccional": true}` en `fuentes.json`.

**`akigawa` (rio Aki, Todohara, `ZRUh9gNk8-g`): anadida, pero hoy no mide.** Rio ancho visto de
lado; el agua va de izquierda a derecha, hacia el puente. A las 17:40 (atardeciendo) la imagen
cambia solo 0.3-0.6 niveles de gris entre fotogramas reales: el codec aplana el agua y la congela a
trozos, y lo que se mueve con contraste son olas fijas del rapido. En el STI se ven estelas
diagonales, pero dominan las rayas verticales del codec y la coherencia se queda en 0.1-0.36
(umbral 0.40) en todo el tramo, en dos subzonas, con tres muestreos y con el proceso de motas. Un
paso alto temporal en el STI rapido la sube a 0.37 como mucho; no se adopto. No se bajo el umbral:
aceptaria medidas falsas. Queda como fuente por si mide con otra luz o mas caudal. Escala supuesta
30 x 12 m.

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

## Validacion con datos de referencia (2026-10-13/14): `validacion/`

El metodo de este programa si se valido, con videos que tienen referencia, pasandolos por **este mismo
codigo** (`validacion/correr.py` importa `stiv_directo.py`). Detalle en `validacion/README.md`.

- **Canal USGS (Sile)**, video original sin estabilizar: **11 de 11 verticales, Q +1.2 % del aforo ADV**.
- **Bradano** (agua casi negra, particulas sueltas): el programa medía **1 de 7**; con
  `FRACCION_ACTIVA_NOCHE` = 0.1, **5 de 7, sesgo -4.5 %**. Solo de noche: de dia, 0.1 aceptaba destellos del
  sol (ver la validacion).
- **Heiskanen** (Finlandia, camara IP Reolink con ADCP): -14 a -18 % en el tercio cercano con el sol
  detras; con el sol de cara se abstiene; **con destellos del sol (13 h) acepta +33 %**. La zona lejana
  (20-40 m) se rechaza siempre.
- `validacion/regresion.py` pasa las grabaciones de los directos por el programa: es la forma de
  comprobar que un cambio del metodo no estropea las camaras que ya miden.

## Verificacion con el nivel y el caudal oficial (2026-10-14): `verificacion_nivel/`

Tres horas grabadas del Myoshoji (15:32-19:17 hora de Japon) cruzadas con el nivel de la estacion de
la propia camara (上高田上) y con los aforos oficiales del puente Ochiai. El nivel no se movio (2 cm),
asi que la comparacion con el nivel no dice nada en seco; lo que si salio:

- **De dia el programa acierta, de noche no.** Dia 0.46-0.50 m/s; noche 0.04-0.07. Los aforos (Q 0.38
  m3/s, 0.13 m de calado) dan ~0.4-0.6 m/s en superficie. De noche la camara sigue en color con las
  farolas y lo unico visible son destellos sobre ondulaciones casi fijas.
- **Cambios:** noche detectada tambien por brillo (`BRILLO_NOCHE` = 50) y `"medir_noche": False` para
  el Myoshoji (`noche_no_valida`).
- `verificacion_nivel/grabar_directo.py` necesita `deno.exe` y `yt-dlp-ejs` en el `.venv`: desde octubre
  YouTube no da los formatos sin resolver un desafio en JavaScript. **El programa en directo todavia no
  usa deno**, asi que en un PC sin el formato antiguo puede no abrir los directos de YouTube.

## Limites conocidos

- **De noche, el Myoshoji no se mide** (`medir_noche` = False): con farolas no hay trazador visible de
  la corriente. Para ALIAR, comprobar con la camara real que de noche se ve el agua fluir (iluminacion
  infrarroja propia, sin destellos fijos) antes de fiarse de las medidas nocturnas.
- De dia el Myoshoji emite a ~12 fps (duplicados alternos de 2 y 3), no a los 15 de `fps_camara`. Sin
  revisar si sesga.

- **De dia no hay defensa contra los destellos del sol**: medidas con buena coherencia y +33 %
  (Heiskanen, `validacion/`). La exclusion de reflejos (`BRILLO_REFLEJO`) es solo de noche, y la
  saturacion no los separa del agua buena. Orientar la camara para que no los vea.
- Una fuente en blanco y negro entra siempre en modo noche (el automatico mira la saturacion).

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
