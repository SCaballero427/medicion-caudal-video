# `analisis_canal_filtro_adaptado/` — el ultimo intento sobre el campo lejano

**No es un caso.** Es el tercer y ultimo experimento sobre `analisis_canal_riego_stiv/`, y cierra
la pregunta de si se puede medir velocidad a lo largo de **todo** el canal y no solo en el tercio
cercano.

Lo anterior ya habia descartado dos familias de metodos:

- `analisis_canal_riego_stiv/` mide bien de Y = 1.40 a 3.20, con el tensor de estructura.
- `analisis_canal_lejano_stiv/` demostro que mas alla el tensor devuelve basura **con coherencia
  0.98**, que es aliasing y no celeridad de onda, y que la correlacion de conjunto tampoco ve nada.

Quedaba una familia sin probar: **integrar coherentemente sobre toda la ventana de residencia**
en vez de sobre bloques de 64 fotogramas. Es lo que se hace aqui.

```powershell
cd analisis_canal_filtro_adaptado
..\pyorc_env\Scripts\python.exe filtro_adaptado.py                 # sintetico + bandas + escalera
..\pyorc_env\Scripts\python.exe filtro_adaptado.py --solo-sintetico
..\pyorc_env\Scripts\python.exe escalera_honesta.py                # la escalera pasando por el codec
..\pyorc_env\Scripts\python.exe figuras_filtro.py
```

Video de entrada: el mismo de siempre, md5 `7b8576e5f9f37d789041a2b1a0f0eb57`, 1024x576 a
**661 kb/s**. Se busco una version de mayor calidad y no existe: la que hay es la que se descargo.

## El metodo

Para cada velocidad candidata `v` se recorre la trayectoria `s(t) = s0 + v*t` que seguiria una
particula, y se suma la imagen realzada a lo largo de ella. Si `v` es la real, cada particula se
apila consigo misma en fase y sobresale; si no, se difumina. Es *track-before-detect* clasico, o
la transformada de Radon de la STI.

Tres cosas lo separan de lo ya probado:

- **Se integra sobre la ventana de residencia entera** (8.6 s en la banda cercana, 23.3 s en la
  lejana), no sobre bloques de 64 fotogramas. Para senal por debajo del ruido en cada fotograma,
  eso es lo unico que importa.
- **Se muestrea a la resolucion nativa de la imagen**, no al `DS` de 45 grados, que es
  precisamente el submuestreo que aliaseaba la STI en el campo lejano.
- **Se puntua con el maximo normalizado por MAD**, no con la energia. La energia de una proyeccion
  esta determinada por el espectro de potencia 2D (teorema de proyeccion-corte), asi que puntuar
  asi seria repetir el `cresta_fft` del caso principal.

## Cuatro errores, y como aparecieron

Esto merece contarse porque **los cuatro los destapo el control positivo**, no una revision del
codigo. La primera version daba, en el campo cercano donde la respuesta se conoce, un pico en
+0.0150 en vez de +0.0590. De ahi salieron:

1. **El desplazamiento por Fourier es circular.** Una particula cruza la banda en 22 s, no en los
   81 del video, asi que la trayectoria se salia por un lado y **reaparecia por el otro**,
   penalizando sistematicamente las velocidades altas. Se sustituyo por desplazamiento con relleno
   de ceros y **recuento de muestras validas** por posicion.
2. **El tiempo de integracion tiene que ser igual para todas las candidatas.** Integrando el video
   entero, una hipotesis lenta permanece mas dentro de la banda, acumula mas promediado y sale
   favorecida. Se integra en ventanas de residencia iguales.
3. **Hay que promediar las PUNTUACIONES, no las proyecciones.** Promediar proyecciones de ventanas
   distintas supone que la misma particula esta en la misma posicion en todas, que es justo lo que
   no pasa: solo promedia ruido.
4. **El pico se busca sobre el z respecto a la nula en cada velocidad, no sobre el score bruto.**
   El score bruto tiene una linea base que depende de `v`, porque a mayor velocidad la mascara de
   cobertura deja menos posiciones y el maximo sobre menos puntos es menor por estadistica de
   extremos.

Y un quinto que no es un error del filtro sino de mi lectura: la apuesta inicial fue que la
**curtosis** seria el discriminador. La validacion sintetica la desmintio -- resulto el mas flojo
de los tres. El bueno es el maximo. Se calculan y reportan los tres igualmente.

## Validacion: sin esto el veredicto no valdria nada

**Sintetica**, inyectando una estela de velocidad conocida en ruido:

| caso | pico | score / techo nulo | z |
|---|---|---|---|
| senal clara (v = +0.059) | **+0.0600** | 35.33 / 3.50 | +186 |
| senal debil | **+0.0600** | 14.44 / 3.13 | +75 |
| solo ruido | -- | 2.99 / 3.07 | rechaza |

**Control positivo sobre el video real**, en bandas estrechas de X donde el caso da velocidades
distintas:

| banda | filtro adaptado | STIV (el caso) | z |
|---|---|---|---|
| X ~ 0.27 | +0.0600 | 0.064 | +40 |
| X ~ 0.42 | +0.0475 | 0.065 | +138 |
| X ~ 0.71 | +0.0525 | 0.043 | +136 |
| X ~ 0.86 | +0.0200 | 0.028 | +27 |

Recupera el perfil y ordena bien los extremos. Cuando este filtro diga que no hay nada, la
afirmacion tiene respaldo.

### El filtro mide la moda de la poblacion, no la mediana de la seccion

Sobre la banda **ancha** (X de 0.10 a 0.90) el filtro da **+0.0250**, no los +0.0590 del caso, y
estuve a punto de leerlo como un fallo. No lo es: el estadistico de maximo lo domina la zona con
**mas particulas**, que es la orilla derecha, donde el agua va a 0.028. El X ~ 0.86 estrecho da
+0.0200, practicamente lo mismo. La correlacion de conjunto de `analisis_canal_lejano_stiv/` ya
habia dado +0.023 por su cuenta.

Es una diferencia real entre metodos y hay que declararla: **el filtro adaptado y la correlacion
de conjunto miden la moda de la poblacion de trazadores; STIV por estaciones mide cada vertical por
separado y por eso puede dar un perfil.** No son el mismo numero.

`fig1_curvas_filtro.png` lo ensena de forma directa: en el panel de cerca, ademas del pico
dominante en +0.025, hay un **hombro claro justo sobre +0.059**, que es donde cae la linea del
caso. Las dos poblaciones estan ahi -- la orilla derecha lenta y densa, y el nucleo rapido -- y lo
que decide cual gana el maximo es cuantas particulas tiene cada una, no cual es mas representativa
de la seccion.

## Resultado sobre las tres bandas de distancia

| banda | filas | pico | score / techo | tiempo invertido | veredicto |
|---|---|---|---|---|---|
| **cerca** (1.40-3.20) | 202-453 | +0.0250 | 16.48 / 4.82 (z +33) | **-0.0250**, espejo exacto | **DETECTA** |
| media (3.20-5.00) | 118-202 | -0.1500 | 3.49 / 3.81 | +0.1350, no espeja | no |
| lejos (5.00-8.50) | 57-118 | -0.1325 | 2.97 / 5.19 | -0.0725, no espeja | no |

La prueba de **inversion temporal** es la que remata: una senal que avanza tiene que dar el pico
espejado al reproducir el tiempo al reves, y en el campo cercano lo hace exactamente. En media y
lejos los picos de ida y de vuelta no guardan ninguna relacion: es ruido.

### El estadistico de varianza dice "DETECTA" en todas partes, y es falso

Vale la pena dejarlo escrito porque es una trampa: la **varianza** marca deteccion en las tres
bandas, siempre con el pico pegado al borde de la zona muerta (-0.0125, +0.0150) y con z absurdos
(240 a 1025). La razon es que su distribucion nula tiene dispersion practicamente nula, asi que
cualquier valor no nulo da un z enorme. Es un detector roto en esta implementacion **y ademas es
el estadistico de segundo orden, o sea el equivalente al `cresta_fft` del caso principal**. Se
reporta solo para dejar constancia de por que no se usa.

## El trazador no sobrevive a la degradacion, y esta medido sin usar ningun estimador

`supervivencia_trazador.py` es la medida mas directa del experimento y no depende del filtro ni de
STIV: se recodifica el video a resoluciones y bitrates decrecientes (manteniendo los bits por
pixel) y se **cuenta cuantos detritos quedan** en la region del campo CERCANO, donde se sabe que
hay trazador de sobra. Cualquier perdida es del codec, no falta de particulas.

| factor | tamano | kb/s | px con particula (>4) | energia top-hat | maximo |
|---|---|---|---|---|---|
| 1.0 | 1024x576 | 661 | 0.03776 | 39445 | 64 |
| 1.5 | 682x384 | 294 | 0.02376 | 22353 | 44 |
| 2.0 | 512x288 | 165 | 0.01833 | 17102 | 35 |
| 3.0 | 342x192 | 73 | 0.00897 | 9700 | 36 |
| 4.5 | 228x128 | 33 | 0.00216 | 4359 | 19 |
| 6.5 | 158x88 | 16 | **0.00020** | 2027 | **10** |

De un extremo al otro la fraccion de pixeles con particula cae **190 veces** y el realce maximo de
64 a 10 niveles de gris. El campo lejano equivale a f = 6.5.

**Cuidado con leer de mas en esta tabla, que es lo que yo hice al principio.** Aqui bajan a la vez
la resolucion y el bitrate (se mantienen constantes los bits por pixel), asi que la tabla dice que
*en esas condiciones* el trazador desaparece, pero **no separa cual de las dos causas manda**. Y
esa separacion es justo la que decide la recomendacion practica: otra camara, o la misma grabando
a mas calidad. `separar_causas.py` cruza las dos variables por separado -- solo bitrate, solo
resolucion, y las dos -- para responderlo.

### La escalera honesta, ya corregida

Reduciendo **y recodificando** a bits por pixel constantes, sobre el campo cercano:

| factor | tamano | kb/s | v del pico | score / techo | veredicto |
|---|---|---|---|---|---|
| 1.0 | 1024x576 | 661 | +0.0250 | 15.78 / 4.49 | DETECTA (z +86) |
| 1.5 | 682x384 | 294 | +0.0225 | 11.74 / 4.00 | DETECTA |
| 2.0 | 512x288 | 165 | +0.0225 | 8.84 / 3.90 | DETECTA |
| 3.0 | 342x192 | 73 | +0.0225 | 4.13 / 3.49 | DETECTA, justo |
| 4.5 | 228x128 | 33 | +0.0900 | 3.46 / 3.79 | no |
| 6.5 | 158x88 | 16 | -0.0350 | 3.70 / 3.72 | no |

La deteccion muere entre f = 3 y f = 4.5, y hasta f = 3 la **velocidad estimada sigue siendo
correcta** (+0.0225 frente al +0.0250 del original). El campo lejano equivale a f = 6.5, o sea que
queda fuera del limite -- lo cual es coherente con que no se vea nada alli, sin necesidad de
invocar nada mas.

### Las dos escaleras, con el mismo codigo

| factor | optimista (solo reducir el fotograma) | honesta (reducir + recodificar) |
|---|---|---|
| 1.0 | DETECTA 7.13 / 4.82 | DETECTA 15.78 / 4.49 |
| 1.5 | DETECTA 6.97 / 4.27 | DETECTA 11.74 / 4.00 |
| 2.0 | DETECTA 9.71 / 3.88 | DETECTA 8.84 / 3.90 |
| 3.0 | DETECTA 6.40 / 3.43 | DETECTA justo 4.13 / 3.49 |
| 4.5 | DETECTA 4.42 / 3.59 | **no** 3.46 / 3.79 |
| 6.5 | DETECTA justo 4.11 / 3.84 | **no** 3.70 / 3.72 |

**El codificador cuesta entre f = 4.5 y f = 6.5 de alcance**, o sea un factor 1.5 a 2 en resolucion
lineal. Es un efecto real y medible, pero **no** el factor 3 que sugeria la version con el error.

Dos avisos sobre como leer esta tabla:

- **Lo fiable es el veredicto detecta/no detecta, no la velocidad del pico.** A f = 1.0 las dos
  columnas son practicamente el mismo video y sin embargo una da el pico en +0.0525 y la otra en
  +0.0250. Es la bimodalidad ya descrita: sobre banda ancha conviven la poblacion densa y lenta de
  la orilla y el nucleo rapido, y la normalizacion por la nula puede coronar a cualquiera de las
  dos. Para leer velocidades hay que usar bandas estrechas en X.
- **La escalera no separa resolucion de bitrate**, porque los baja a la vez. Para eso esta
  `separar_causas.py`.

### Y la version anterior de esta escalera tenia un error que casi me lleva a una conclusion
### correcta por el motivo equivocado

La primera version de `escalera_honesta.py` daba score **exactamente 0.00** desde f = 2, lo que
parecia una confirmacion redonda. No lo era: recodificaba a 512x288 pero **nunca reampliaba al
tamano original**, pese a que su propio docstring decia que si. La geometria del caso muestrea en
coordenadas de hasta 1024 px, sobre un fotograma de 512 eso cae fuera y `remap` devuelve ceros.

Lo que lo destapo fue precisamente la tabla de arriba: mostraba 0.018 de pixeles con particula a
f = 2, o sea trazador de sobra, justo donde el filtro afirmaba no ver absolutamente nada. Un cero
exacto es sospechoso; un cero exacto donde hay senal medible es un error. Corregido con una segunda
pasada de ffmpeg a CRF 12 que reamplia sin perdida apreciable.

## Resolucion o bitrate: la resolucion, y por mucho

`separar_causas.py` cruza las dos variables por separado sobre el campo cercano, donde se sabe que
hay trazador de sobra:

| caso | tamano | kb/s | px con particula | perdida |
|---|---|---|---|---|
| original | 1024x576 | 661 | 0.03783 | -- |
| **solo menos resolucion** | 158x88 | **661** | 0.00034 | **x111** |
| solo menos bitrate | 1024x576 | 16 | 0.00003 | x1260 |
| las dos (= campo lejano) | 158x88 | 16 | 0.00019 | x199 |

La fila que responde la pregunta es la segunda. A 158x88 con 661 kb/s el video esta codificado con
**48 bits por pixel**, o sea practicamente sin perdida, y aun asi **se pierde el 99.1 % del
trazador solo por el cambio de tamano**. Pasar de ahi a las condiciones reales del campo lejano
anade nada mas un factor 1.8.

**Domina la resolucion.** Un codec mejor no rescataria el campo lejano; una camara con mas
resolucion, o mas cerca, si. Esto contradice una conclusion intermedia que llegue a escribir --
"el culpable es el codificador" -- que salio de la escalera cuando todavia tenia el error del
reescalado, y que este ensayo controlado desmiente.

### Aviso: en esta tabla solo vale la columna de supervivencia

Las cuatro filas salen marcadas como DETECTA, y las tres degradadas son **falsos positivos**: los
picos caen en +0.0150, -0.0150 y -0.0125, todos a menos de 0.003 del borde de la zona muerta
(0.012), dos de ellos con signo negativo -- o sea agua corriendo hacia atras -- y con margenes de
nada (3.37 contra un techo de 3.24). Es residuo de continua colandose por el borde de la zona
muerta, que para estos casos degradados se queda corta. **El contraste util aqui es el conteo de
particulas, que no depende de ningun estimador**; la deteccion en condiciones tan degradadas
habria que rehacerla con una zona muerta mas ancha si alguna vez importara.

## El video: el barrido, no el agua

`video_filtro.py` (~4 min) escribe `salidas/video_filtro.mp4` (2.5 MB, 1388x1040, 483 fotogramas,
16 s). **No es un video del rio**, y esa es la decision de diseno: los otros videos del workspace
ensenan agua con flechas encima, pero aqui el resultado es que en el campo lejano *no hay nada que
ensenar*, y un panel de agua quieta sin flechas no distingue "no hay senal" de "el programa no
dibuja". Lo que si se puede ver es el detector trabajando.

Un fotograma por velocidad candidata, tres columnas por banda: la **STI con la familia de
trayectorias** de la candidata actual encima, la **proyeccion** que sale de integrar sobre ellas, y
la **puntuacion** rellenandose contra el techo de la nula. Cuando la inclinacion de las rectas se
acerca a la de las estelas, el pico aparece en la proyeccion y la curva se dispara. Es el metodo
explicado sin texto.

**Cuatro filas, y la de arriba es la que da derecho a creerse las otras tres.** El control positivo
sintetico va en el mismo fotograma que las bandas reales, con el mismo codigo, asi que el negativo
de abajo se lee al lado de un positivo conocido y no de una promesa:

| fila | pico | score / techo | espejo temporal | veredicto |
|---|---|---|---|---|
| **sintetico** (+0.059 conocido) | **+0.0600** | 34.30 / 3.37 | **-0.0600**, exacto | **DETECTA** |
| **cerca** | **+0.0250** | 16.48 / 4.37 | **-0.0225**, coincide | **DETECTA** |
| media | -0.1475 | 3.18 / 3.82 | +0.1200, no coincide | no |
| lejos | -0.1300 | 2.66 / 5.44 | -0.0675, no coincide | no |

Dos detalles del dibujo que son decisiones, no adorno:

- **La pausa final para cada fila en SU pico**, no en la ultima candidata. Con la candidata
  +0.15 la mascara de cobertura deja la proyeccion casi sin puntos, y ese era justo el fotograma
  que quedaba congelado al acabar el barrido.
- **La escala vertical del panel de proyeccion es fija durante todo el barrido.** Reescalando cada
  cuadro, el pico de la candidata buena se veria igual de alto que el ruido de las malas, que es
  precisamente lo que hay que distinguir.

Y una advertencia que salio de comparar este video con la ejecucion suelta de `filtro_adaptado.py`:
el **score es reproducible** (16.48 en los dos) pero el **techo y la z no** (4.37 / z +71 aqui,
4.82 / z +33 alli), porque la fila sintetica consume tiradas del generador antes y con solo 12
barajados `nulo_std` es ruidosa. **El estadistico que hay que citar es score contra techo**, no la
z; la z sirve para ordenar candidatas dentro de una misma ejecucion, que es para lo que la usa
`veredicto`.

## Ficheros

| fichero | que es |
|---|---|
| `filtro_adaptado.py` | el filtro, la validacion sintetica, las tres bandas y la escalera optimista |
| `video_filtro.py` | el barrido en video; importa el filtro entero, no lo reimplementa |
| `escalera_honesta.py` | la escalera pasando de verdad por el codificador |
| `supervivencia_trazador.py` | cuenta detritos supervivientes; **necesita los `.mp4` que deja `escalera_honesta.py` en `tmp_codificados/`** |
| `separar_causas.py` | cruza resolucion y bitrate por separado; es el que responde que manda |
| `figuras_filtro.py` | las dos figuras |
| `salidas/filtro_adaptado.csv` | una fila por (experimento, banda, estadistico) |
| `salidas/escalera_honesta.csv` | la escalera recodificada |
| `salidas/separar_causas.csv` | el cruce resolucion x bitrate |
| `salidas/curva_*.npy` | `(vs, real, invertido, techo_nulo)` de cada banda, para redibujar |
| `salidas/video_filtro.mp4` | 2.5 MB, 1388x1040, 483 fotogramas: el barrido con su control positivo |
| `salidas/config_video_filtro.json` | la configuracion del video y los cuatro veredictos |

Los `.mp4` intermedios (`tmp_codificados/`, `tmp_causas/`) se borran al terminar: son 40 MB y se
regeneran solos. Por eso `supervivencia_trazador.py` avisa y no hace nada si se lanza en frio.

## Y la conclusion, en una linea

El campo lejano de este video **no es medible por ningun camino**, y no porque la senal este mal
extraida: a esa distancia el detrito ocupa menos de un pixel y **el 99.1 % del trazador se pierde
solo por el tamano, incluso con codificacion sin perdida**. Es una limitacion de la toma, no del
procesado. Lo que la levantaria es acercar la camara, usar mas resolucion, o mirar el canal desde
un punto que no lo comprima en perspectiva -- no un algoritmo mejor.
