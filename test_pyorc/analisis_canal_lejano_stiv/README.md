# `analisis_canal_lejano_stiv/` — hasta donde alcanza STIV canal arriba

**No es un caso nuevo.** Es un experimento controlado sobre `analisis_canal_riego_stiv/`, que mide
solo entre Y = 1.40 y Y = 3.20 alturas de camara y deja sin tocar todo el canal que se ve mas
alla. Ese limite se puso **heredando el criterio de Boneyard** -- *cerca del horizonte un pixel
cubre tanto suelo que la textura no sobrevive al remuestreo* -- sin medirlo en este video. Aqui se
mide, y la respuesta resulta ser mas interesante que un simple si o no.

Nada de la carpeta original se modifica. `experimento_alcance.py` **importa** de
`analisis_canal_riego_stiv/stiv_canal.py` la geometria, el realce, el tensor y los umbrales de
calidad; no redefine ni un parametro del metodo. Lo unico que cambia entre casos es **que trozo
del canal se mira y con que paso temporal**.

```powershell
cd analisis_canal_lejano_stiv
..\pyorc_env\Scripts\python.exe experimento_alcance.py    # partes 1 a 3  (~6 min)
..\pyorc_env\Scripts\python.exe correlacion_arbitro.py    # parte 4       (~3 min)
```

## La pregunta, y por que no hace falta ningun dato de campo

Es la misma agua a 2 y a 6 alturas de camara. **Tiene que dar la misma velocidad.** Esa es toda la
prueba.

## 1. Tres bandas de distancia: el campo lejano miente, y miente con seguridad

Con la configuracion del caso, sin cambiar nada:

| banda | filas | DS en px | v en las 6 estaciones | coherencia | aceptadas |
|---|---|---|---|---|---|
| **cerca** (la del caso) | 202-453 | 0.23 | +0.059 +0.064 +0.065 +0.059 +0.043 +0.028 | 0.66 - 0.82 | **6 de 6** |
| media | 118-202 | 0.08 | -0.69 -0.54 -0.80 +0.88 +0.19 +0.46 | 0.76 - 0.97 | 0 de 6 |
| **lejos** | 57-118 | 0.04 | +1.86 +1.22 -0.65 +0.94 +0.88 +1.19 | **0.97 - 0.99** | 0 de 6 |

El campo lejano devuelve velocidades **20 veces** las de cerca, con signos que no concuerdan entre
estaciones vecinas, y lo hace con **la coherencia mas alta de todo el caso: 0.98**. La agudeza del
espectro llega a 9543, cuando en las estaciones buenas vale 8 a 47.

Esto es la trampa de Boneyard llevada al extremo. Boneyard encontro muros que daban coherencia
0.74 con velocidad exactamente cero; aqui el campo lejano da coherencia 0.98 con velocidad 20
veces la real. **La coherencia no mide validez, y este es el ejemplo mas claro que tiene el
workspace.** De los cuatro criterios de calidad del caso, el unico que lo ataja siempre es la cota
fisica `V_MAX_FISICA`.

## 2. Diezmado temporal: aliasing, no celeridad de onda

Ese factor 20 obligaba a descartar una hipotesis fisica antes de llamarlo error. Lo que se ve en
el agua lejana **no son detritos** -- ampliada, esa zona solo tiene el reflejo especular de las
nubes y el rizado de la superficie. Y los reflejos y las ondas no viajan con el agua: viajan a
**celeridad de onda**, que para un calado de 1 m vale `sqrt(g*h)` = 3.1 m/s frente a unos 0.15 m/s
de corriente. **Un factor 21**, casi exactamente el observado.

La forma de separar las dos hipotesis no necesita saber el calado. El conflicto de fondo es este:
DS se elige para que las estelas caigan a 45 grados, o sea `DS = desplazamiento por fotograma`, y
en el campo lejano eso vale **0.04 px de imagen** -- se muestrea 25 veces por debajo de un pixel.
Si en cambio se toma 1 de cada N fotogramas, el desplazamiento por paso es N veces mayor y se
pueden cumplir las dos condiciones a la vez.

Si fuera una senal fisica, el resultado **no** dependeria del muestreo:

| campo lejano | DS en px | v est9 | v est11 | v est13 | coherencia |
|---|---|---|---|---|---|
| N = 1 | 0.04 | +1.2233 | +0.9387 | +1.1887 | 0.97 - 0.99 |
| **N = 20** | **0.73** | **-0.0555** | **-0.1454** | **-0.1712** | **0.23 - 0.33** |

Cambia de signo y cae 20 veces. **Es aliasing.** Bien muestreado, el campo lejano da coherencia
0.23 a 0.33, muy por debajo del umbral de 0.60: alli no hay ninguna senal que medir. La hipotesis
de la celeridad de onda queda descartada sin necesidad de medir el calado.

El mecanismo se ve a simple vista comparando las dos STI (`salidas/`): la de cerca tiene estelas
diagonales limpias y separadas; la de lejos es una **estera de trazos casi horizontales**. Con 25
muestras por pixel de imagen, cualquier fluctuacion temporal de un solo pixel se estira en un trazo
larguisimo, y un trazo horizontal es perfectisimamente coherente.

## 3. Partir la banda actual: el resultado del caso NO esta contaminado

Si el aliasing empieza por debajo de ~0.2 px, el extremo lejano de la AOI que ya se usa (DS = 0.13
px en Y = 3.20) esta en zona dudosa. Partiendo la banda del caso en dos mitades:

| mitad | Y | DS en px (centro) | coherencia | v mediana | aceptadas |
|---|---|---|---|---|---|
| **cercana** | 1.40 - 2.30 | 0.33 | 0.75 - 0.89 | **+0.0580** | **6 de 6** |
| **lejana** | 2.30 - 3.20 | 0.17 | 0.51 - 0.59 | (+0.064 a +0.092) | **0 de 6** |
| entera (el caso) | 1.40 - 3.20 | 0.23 | 0.66 - 0.82 | **+0.0590** | 6 de 6 |

Dos cosas, las dos tranquilizadoras:

1. **La mitad cercana sola da +0.0580 contra los +0.0590 de la banda entera: 1.7 % de
   diferencia.** La senal la lleva la mitad cercana; la lejana aporta poco.
2. **La mitad lejana, medida sola, la rechaza el control de calidad del propio caso**, por
   coherencia (0.51 - 0.59 contra el umbral de 0.60). No hizo falta anadir nada para atraparla.

Y ya asoma el sesgo: la mitad lejana da +0.064 a +0.092 frente a +0.058 de la cercana, siempre
**alta**, que es la direccion en la que empuja el aliasing.

## 4. Un algoritmo distinto dice lo mismo

Todo lo anterior es STIV discutiendo consigo mismo. La ultima comprobacion usa **correlacion de
conjunto**, que no comparte con STIV ni la STI, ni el tensor, ni la banda de lineas: se muestrea
el parche rectificado **a la resolucion nativa de la imagen** en cada banda (para no
sobremuestrear) y se correlacionan pares de fotogramas a desfases crecientes. Si hay agua
detectable, el pico se desplaza en proporcion al desfase.

| desfase | cerca (control) | media | lejos |
|---|---|---|---|
| 1.0 s | **+3 px** | +1 px | +1 px |
| 2.0 s | **+6 px** | 0 | **0** |
| 4.0 s | **+13 px** | -1 px | **0** |
| 8.0 s | **+25 px** | -4 px | **0** |
| 13.3 s | **+34 px** | -3 px | **0** |

El control cercano da un pico que **se desplaza linealmente**, con `dX = 0` en todos los desfases.
En el campo lejano el pico queda **clavado en cero**, y ademas el valor del pico coincide
exactamente con el de desplazamiento nulo (0.2440 = 0.2440): es la firma de «aqui no hay nada»,
la misma que dio el video entero antes de aplicar el top-hat.

Conviene decir que este contraste es una prueba de **presencia o ausencia**, no una medida: la
velocidad que deduce en el control (+0.023) no coincide con los +0.059 de STIV porque el parche
abarca de X = 0.10 a 0.90 y la correlacion de conjunto la domina la zona con mas trazador, que es
la mitad derecha lenta. Lo que vale es que en el control el pico se mueve y en el campo lejano no,
con el mismo codigo y el mismo parche.

## La coherencia no es monotona, y por eso engana

Vale la pena juntar los tres experimentos, porque el patron no es el que uno esperaria:

| DS en px de imagen | 0.73 | 0.33 | 0.23 | 0.17 | 0.08 | 0.04 |
|---|---|---|---|---|---|---|
| coherencia | 0.19 - 0.33 | **0.75 - 0.89** | **0.66 - 0.82** | 0.51 - 0.59 | 0.76 - 0.97 | 0.97 - 0.99 |
| velocidad | ruido | **correcta** | **correcta** | +40 % alta | caos | caos x20 |

La coherencia **baja** en la zona de transicion (0.17 px) y **vuelve a subir** cuando el aliasing
toma el control por completo (0.04 px). Asi que una coherencia alta no significa que el muestreo
sea bueno: puede significar que es tan malo que el artefacto domina limpiamente. El unico
indicador monotono y fiable es `DS / pixel de imagen`, que es puramente geometrico y se puede
calcular **antes** de medir nada.

Una salvedad sobre el extremo de arriba: los casos `lejos N=40` (1.45 px) y `media N=8` (0.68 px)
devuelven coherencia 0.00 y `nan`, pero **no porque no haya senal, sino porque no queda suficiente
STI**: con 40 muestras y 60 pasos temporales el tensor no reune ni 5 bloques y la guarda salta.
El unico ensayo con muestreo grueso que si tiene datos suficientes es `lejos N=20` (0.73 px, 80
muestras x 121 pasos), y ese da coherencia 0.19 - 0.33: ahi si se puede afirmar que no hay senal.

## Lo que hay que llevarse

- **`Y_MAX = 3.20` en el caso principal era correcto**, y ahora esta medido en vez de heredado.
  Podria bajarse a 2.30 sin perder casi nada (1.7 %), pero no hace falta: la mitad lejana se
  rechaza sola.
- **Regla transferible, y es lo mas util de este experimento: exigir `DS >= 0.2 px de imagen`.**
  Es geometrica, se evalua antes de procesar y no depende del video. Por debajo de 0.1 px el
  tensor devuelve basura con coherencia proxima a 1.
- **El campo lejano de este video no se puede medir por ningun camino**, y no es un problema del
  algoritmo: alli no hay trazador, solo reflejo de nubes, y el agua se desplaza 0.04 px por
  fotograma en un video de 661 kb/s. No es informacion que este mal extraida, es informacion que
  no esta grabada.
- Lo unico que lo cambiaria es **acercar la camara o usar mas resolucion**. Es una limitacion de
  la toma, no del procesado.

## El video: lo mismo, pero ventana a ventana

`video_alcance.py` (~7 min) rehace la parte 1 en **ventanas deslizantes de 360 fotogramas** sobre
los 81 s y lo dibuja: `salidas/video_alcance.mp4` (36 MB, 1876x996, 2429 fotogramas, tiempo real)
mas `salidas/alcance_ventanas.csv`. No redefine nada -- importa las bandas, las estaciones y el
mapa de muestreo de `experimento_alcance.py`, y la geometria, el realce y el tensor del caso.

Anade una comprobacion que la tabla de la parte 1 no puede dar, porque alli cada banda se mide
**una sola vez**: si el campo lejano fallara por una peculiaridad de esos 81 s concretos, se veria
igual de mal en la tabla. Midiendo 138 veces se distingue un sesgo de un caos.

| banda | estacion-ventana aceptadas | mediana de las medianas por ventana | \|v\| maximo |
|---|---|---|---|
| **cerca** | **589 de 828** | **+0.0598** | 1.25 |
| media | 20 de 828 | +0.1248 | 2.98 |
| **lejos** | **0 de 828** | -- | **4.73** |

(La mediana es la de las medianas de seccion por ventana, que es el mismo estadistico que da el
caso sobre el video entero. Agrupando las 589 aceptadas sin pasar por ventanas sale +0.0575; la
diferencia entre las dos formas de promediar, 4 %, es menor que la dispersion entre ventanas.)

- **El campo cercano repite.** +0.0598 contra el +0.0590 de la medida unica sobre el video entero:
  **1.4 %**. Que baje de 6/6 a 71 % de aceptacion no es una contradiccion, es lo esperado -- en
  12 s pasan menos particulas por estacion que en 81, asi que la densidad cae por debajo del
  umbral en algunas ventanas. Se rechaza por falta de trazador, no por medir mal.
- **El campo lejano se rechaza en las 828**, sin una sola excepcion, y llega a devolver 4.73
  alturas de camara/s: 80 veces la velocidad real.
- **La banda media cuela 20 de 828 (2.4 %)**, y eso es lo unico nuevo que aporta el video. Son las
  ventanas en las que el artefacto cae por casualidad dentro de la cota fisica y con signo
  positivo, o sea que **pasa las cuatro redes a la vez**. Con una sola medida no se ve: la parte 1
  da 0 de 6. Es un argumento de peso para no acercarse a `DS = 0.08 px` ni con control de calidad.

Lo que se ve en pantalla:

- **La vista de camara con las tres bandas sombreadas.** Antes de leer un solo numero ya se ve el
  problema: la banda lejana son **61 filas de pixeles** contra las 250 de la cercana.
- **Las flechas se colorean por coherencia, no por velocidad**, que es lo unico que hace visible
  la trampa: el rojo -- la mejor nota de calidad -- cae justo donde la medida es absurda.
  Cada flecha se recorta a su propia banda y se marca cuando se sale, porque cuanto recorta es la
  medida del disparate.
- **La serie temporal**, abajo a la izquierda, en escala simlog porque conviven +0.059 y +3. Es el
  resumen del experimento en una imagen: la curva verde es una recta pegada a la referencia y las
  otras dos saltan entre +1 y -1 cambiando de signo.
- **Las tres STI de la misma estacion**, con la recta que el tensor afirma dibujada encima. Arriba
  se ven las estelas y la recta las sigue; abajo no hay ninguna estela y la recta esta puesta
  sobre ruido. Esa es la prueba, y no necesita ningun numero.

## Ficheros

| fichero | que es |
|---|---|
| `experimento_alcance.py` | las partes 1 a 3; importa el metodo del caso principal |
| `correlacion_arbitro.py` | la parte 4: la comprobacion con un algoritmo que no es STIV |
| `video_alcance.py` | el video; importa las bandas y el muestreo de `experimento_alcance.py` |
| `salidas/alcance.csv` | una fila por (caso, estacion) con densidad, coherencia, v y DS/px |
| `salidas/alcance_ventanas.csv` | una fila por (ventana, banda, estacion) de las 138 ventanas |
| `salidas/video_alcance.mp4` | 36 MB, 1876x996, 2429 fotogramas a tiempo real |
| `salidas/config_alcance.json` | la configuracion congelada, con el puntero al caso del que hereda |
| `salidas/config_video_alcance.json` | idem para el video |
