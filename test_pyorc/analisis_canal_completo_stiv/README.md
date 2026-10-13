# `analisis_canal_completo_stiv/` — STIV al maximo, y el resto del canal simulado

Cuarta carpeta sobre el mismo video de movil del canal de riego
(`C:\Users\Sergio\Desktop\videos\WhatsApp Video 2026-08-16 at 8.07.12 PM.mp4`, 81 s, 1024x576 a
661 kb/s, sin GCP, sin ancho medido, sin seccion, sin aforo). Dos piezas:

1. **`stiv_mejorado.py`** — STIV sobre el video original con todo lo aprendido en las tres
   carpetas anteriores: barra de error por estacion, tres estimadores independientes, doble
   resolucion transversal y la prueba que cierra la puerta a medir la mitad izquierda.
2. **`simulacion_canal.py`** + **`video_canal_completo.py`** — como se veria el flujo en **todo**
   el canal, con un modelo hidraulico anclado a lo medido. **Simulacion, no medida**, y etiquetada
   asi en cada figura y en cada fotograma del video.

Nada se duplica: geometria, realce, tensor y umbrales se importan de
`analisis_canal_riego_stiv/stiv_canal.py`, y el filtro adaptado de
`analisis_canal_filtro_adaptado/filtro_adaptado.py`.

## 1. STIV, lo mejor que da este video

29 estaciones (el doble que el caso), los 2429 fotogramas, ventanas deslizantes de 360.
**12 estaciones aceptadas, todas entre X = +0.12 y +0.93**, y mediana de seccion **+0.0590
alt.cam/s** — identica a la del caso original con 15 estaciones. Que doblar la resolucion
transversal no mueva la mediana es la primera comprobacion de que el muestreo no la estaba
sesgando.

Lo que se anade sobre el caso:

### Barra de error por estacion

El caso da un numero por estacion y ninguna incertidumbre. Aqui cada estacion se mide en 138
ventanas de 12 s y se reporta mediana, q05-q95 y en cuantas ventanas se acepta. Sale
**sigma ~ 0.010 alt.cam/s de repetibilidad**, y la tasa de aceptacion va de 65/138 en las
estaciones proximas al eje a 136/138 en el centro del chorro de trazador. Esa barra es lo que
despues pondera el ajuste del modelo, y sin ella el ajuste no tendria sentido.

### Tres estimadores, y uno de ellos no sirve de portero

Tensor de estructura con seleccion por senal (el del caso), cresta espectral FFT y filtro
adaptado. Ven la misma STI y no comparten mas que eso.

| | acuerdo con el tensor |
|---|---|
| cresta FFT | mediana **0.0042**, maximo 0.0111 |
| filtro adaptado | mediana **0.0100**, detecta en **12 de 12** aceptadas |

Que tres metodos distintos coincidan a 0.004-0.010 sobre 0.059 es lo que permite decir que la
velocidad esta en el dato y no en el estimador. **Pero el filtro adaptado tambien "detecta" en
7 de las 15 estaciones sin trazador**, donde por construccion no hay nada que detectar. Con
12 barajados su techo nulo se queda corto para STI tan pobres. Conclusion, y es la util:
**corrobora donde ya hay senal, no sirve como criterio de aceptacion.**

### La mitad izquierda no se puede medir, y esta cerrado midiendo

Densidades de trazador de 1e-5 a 4e-4 en la izquierda frente a 6e-3 a 3e-2 en la derecha: el
detrito cae de la vegetacion que cuelga de la orilla derecha y baja por ese lado. La tentacion es
ensanchar la banda de lineas, que es el truco que rescato el caso Bradano. **Se probo con 61
lineas sobre una banda de 0.30, el triple:**

| X | densidad con la banda del caso | con la banda ancha | factor | veredicto |
|---|---|---|---|---|
| -0.90 | 0.000389 | 0.002937 | x7.5 | sigue por debajo del umbral (0.004) |
| -0.60 | 0.000027 | 0.000059 | x2.2 | sigue sin trazador |
| -0.30 | 0.000018 | 0.000054 | x3.0 | sigue sin trazador |
| **0.00** | 0.000181 | **0.007702** | x42.5 | **pasa el umbral, y es un artefacto** |

La ultima fila es la interesante y hay que no leerla mal: una banda de 0.30 centrada en X = 0
**llega hasta X = +0.15**, o sea que se mete en el agua con trazador y mide la densidad de sus
vecinas, no la suya. Y la velocidad que devuelve es **+0.0044 con coherencia 0.85**: un cero
confiado, porque la STI la dominan las posiciones vacias. Es la trampa de Boneyard otra vez, con
disfraz nuevo. **Ensanchar la banda aqui no es inutil, es peligroso.**

## 2. El canal completo, simulado

Solo el **36 % del ancho** esta medido, y todo a un lado del eje. Para el 64 % restante se ajusta
un modelo de distribucion transversal y se extrapola. Eso es hidraulica normal cuando falta parte
del aforo, y es una **simulacion**.

### El modelo

**Shiono-Knight** (SKM, 1991), el metodo estandar para la distribucion lateral de velocidad
promediada en vertical en canal prismatico. Promediando en profundidad la ecuacion de momento y
quedandose con peso, friccion de fondo y tension turbulenta lateral, con profundidad constante y
paredes verticales se integra a mano:

```
U(y) = Umax * sqrt( [1 - cosh(g*y)/cosh(Gamma)] / [1 - 1/cosh(Gamma)] ),   Gamma = g*W
```

Lo que lo hace usable aqui es que **la forma depende de un solo numero adimensional**: no hace
falta conocer g, H, S0 ni f por separado — que en unidades afines no se pueden conocer — porque
todos entran por `Gamma`, y `Gamma` se traduce a relacion de aspecto:

```
Gamma = (B/2H) * sqrt(2) * (f/8)^(1/4) / sqrt(lambda)      ->   B/H ~ 1.51 * Gamma
```

con lambda = 0.07 (Knight, canal recto) y f = 0.03 (hormigon liso).

### La sigma del ajuste no puede ser la de las ventanas

Ajustando solo con la dispersion entre ventanas el chi2 reducido se dispara. Eso no dice que el
modelo este mal: dice que la barra de error lo esta. Las ventanas miden **repetibilidad**
(0.0104); falta la parte **sistematica**, y hay una forma de medirla sin inventar nada — la
dispersion entre los tres estimadores en esa misma estacion, **0.0056**. Sumadas en cuadratura dan
0.0130, y con esa el ajuste se comporta.

### Dos parametros de forma, y el segundo es un hallazgo

Con la pared donde la camara ve la orilla, el ajuste va mal: rms 0.0133, chi2red 1.95, y `Gamma`
se pega al tope. Liberando el **semiancho efectivo** — donde se para el agua, que no tiene por que
coincidir con la linea de orilla — el ajuste cambia de categoria:

| | Gamma | Umax | W | rms | chi2red |
|---|---|---|---|---|---|
| pared en la orilla vista | tope | 0.0551 | 1.125 | 0.0133 | 1.95 |
| **semiancho efectivo libre** | tope | 0.0692 | **0.987** | **0.0064** | **0.52** |

El borde hidraulico sale **0.139 alturas de camara por dentro de la orilla visible**, un 6 % del
ancho por lado. En un canal de riego revestido, que suele ser **trapecial**, eso es exactamente el
talud: lamina fina, velocidad ya practicamente nula. No es un mando para forzar el ajuste, es una
afirmacion fisica, y ademas acotada — W no podia bajar de 0.972, donde esta la estacion medida mas
externa.

### Gamma no se determina por abajo; lo que se puede dar es una cota

`Gamma` se va al limite inferior: **el perfil medido es tan ancho como SKM puede dar**,
practicamente la elipse. Citar el valor ajustado seria citar el tope escrito en el codigo, no lo
que dice la medida. Lo que si sale del perfil de chi2 es una cota por arriba:

> **Gamma <= 4.10 (2 sigma) → B/H <= 6.2** con lambda 0.07, o **B/H <= 12.8** con lambda 0.30.

O sea: **un canal ancho y somero queda descartado**; uno de proporciones normales, no. Es poco,
pero es una restriccion fisica real sacada de un video de WhatsApp sin una sola medida de campo.

### Lo que NO se puede determinar, y cuanto duele

Con datos en un solo lado del eje, **la posicion del eje no esta determinada**. En vez de dejar
que un ajuste con el eje libre se encalle en un tope, se barre el eje supuesto:

| eje supuesto en X | chi2red | v media de la seccion |
|---|---|---|
| **-0.024** (el geometrico) | 0.47 | 0.0476 |
| +0.126 | 0.50 | 0.0450 |
| +0.276 | 0.61 | 0.0422 |
| +0.426 | 0.91 | 0.0393 |

**El chi2 apenas se mueve y la respuesta un 21 %.** Esa es la incertidumbre de verdad de esta
carpeta, y es mayor que la del parametro del modelo.

### El resultado

| | alt.cam/s |
|---|---|
| v superficial media sobre el tramo **medido** | 0.0534 |
| v superficial media sobre el **ancho completo** | **0.0476** |
| sobre el tramo que nadie ha medido — modelo SKM | 0.0438 |
| sobre el tramo que nadie ha medido — espejo de lo medido | 0.0441 |
| envolvente de **todas** las hipotesis, media total | 0.0382 a 0.0520 (**+36 %**) |

Dos cosas que sacar de ahi:

- **Quedarse con el tercio medido sobrestima la seccion en un +12 %**, porque el tramo medido cae
  justo en la parte rapida. Ese es el numero practico que justifica la simulacion.
- **El modelo fisico y el espejo — que no tiene fisica ninguna — dan 0.0438 y 0.0441 sobre el
  tramo sin medir**, o sea que coinciden en un 0.7 %. Que dos hipotesis tan distintas converjan
  ahi es lo mejor que se puede decir a favor de la extrapolacion.
- **De las dos incognitas, la que manda es la posicion del eje**: mover el eje supuesto abre la
  media de seccion un **21 %** y barrer `Gamma` solo un **9 %**. La envolvente llega al 36 %
  porque se toma punto a punto y ademas incluye el espejo. Dicho de otra forma: **afinar el
  modelo hidraulico no sirve de nada mientras no se sepa donde esta el eje del canal**, y eso lo
  arreglaria una foto desde el otro lado, no un algoritmo.

### Contraste con el PTV, que no se uso para ajustar nada

`analisis_canal_riego_stiv/ptv_arbitro.py` sigue particulas una a una y es **inmune a la textura
estatica**, que es la sospecha obvia sobre la caida junto a la orilla. El modelo queda **+18.8 %
por encima del PTV de media**, mismo signo y orden que el desfase STIV-PTV que el caso original ya
tenia documentado, o sea que no es nuevo. Pero hay un detalle que si lo es:

| X | PTV | modelo |
|---|---|---|
| +0.796 | 0.0271 | 0.0384 (**+42 %**) |
| +0.933 | 0.0223 | 0.0169 (**-24 %**) |

El PTV mide **0.0223 en X = +0.933**, y el semiancho efectivo ajustado pone el borde del agua en
X = +0.963. O sea que el PTV ve agua moviendose a 0.03 del punto donde el modelo la da por parada.
**La caida junto a la orilla es real** — el PTV la reproduce — pero **el modelo la hace mas brusca
de lo que es**. El semiancho efectivo esta absorbiendo, ademas del talud, algo de sesgo de las
estaciones pegadas a la pared.

## 3. El video

`video_canal_completo.py` (~7 min) escribe `salidas/canal_completo.mp4`. **Siembra particulas
virtuales por todo el ancho** y las deja correr a la velocidad que el modelo predice en su X, con
una estela que es el recorrido de 1.2 s — asi que **el largo de la estela ES la velocidad** y el
perfil transversal se lee de un vistazo, sin grafica.

La comprobacion esta metida en el diseno, no anadida: **las particulas virtuales se dibujan
tambien sobre el tercio derecho**, donde hay detrito real en amarillo. Ahi las dos poblaciones
comparten pantalla y tienen que ir al mismo paso. Si el modelo se despegara de la realidad donde
si hay datos, se veria sin leer un numero.

Y lo que nunca se puede confundir: **detrito real en amarillo, simulacion en azul**, el tramo sin
medir sombreado en los dos paneles, y el rotulo repitiendolo todo el rato.

## Ficheros

| fichero | que es |
|---|---|
| `stiv_mejorado.py` | STIV con barra de error, tres estimadores y la prueba de la banda ancha |
| `simulacion_canal.py` | el ajuste SKM, la cota de Gamma y el barrido del eje |
| `video_canal_completo.py` | el video de particulas virtuales sobre el video real |
| `figuras.py` | las cuatro figuras |
| `salidas/perfil_mejorado.csv` | una fila por estacion: densidad, los tres estimadores, ventanas |
| `salidas/banda_ancha_izquierda.csv` | la prueba de la banda ancha |
| `salidas/perfil_simulado.csv` | el perfil simulado en malla fina, con la envolvente |
| `salidas/fig1_perfil_completo.png` | lo medido, lo simulado y la envolvente de hipotesis |
| `salidas/fig2_barrido_gamma.png` | todas las Gamma ajustan lo medido; discrepan donde no hay datos |
| `salidas/fig3_estimadores.png` | los tres estimadores y la densidad de trazador, con sus umbrales |
| `salidas/fig4_banda_ancha.png` | por que ensanchar la banda no rescata la izquierda |
| `salidas/canal_completo.mp4` | el video: 30 MB, 1796x888, 2429 fotogramas a tiempo real |
| `salidas/config_*.json` | las configuraciones congeladas |

## Lo que hay que llevarse

- **Doblar la resolucion transversal no movio la mediana** (+0.0590 con 15 y con 29 estaciones):
  el muestreo del caso no la sesgaba.
- **Tres estimadores coincidiendo a 0.004-0.010 sobre 0.059** es lo que convierte una medida en un
  dato. Pero el filtro adaptado da 7 falsos positivos donde no hay trazador: **corrobora, no filtra.**
- **Ensanchar la banda de lineas para llegar a agua sin trazador es peligroso, no solo inutil**:
  arrastra la densidad de las vecinas y devuelve un cero con coherencia 0.85.
- **La sigma para ajustar un modelo no es la repetibilidad**. Aqui la parte sistematica sale de la
  dispersion entre estimadores, y es la que manda.
- **Un parametro que se pega a un tope no es un resultado, es una cota.** Gamma no se determina por
  abajo; lo que se puede publicar es B/H <= 6.2.
- **La incertidumbre dominante de la extrapolacion no es el parametro del modelo sino la posicion
  del eje**, que los datos no fijan: 21 % de la media de seccion frente a menos de la mitad de eso
  por Gamma.
- Y lo que sigue sin poder saberse: con `FOCAL` supuesta, sin ancho medido y sin calado, todo esto
  vive en unidades afines. **Una sola cinta metrica en la orilla convertiria toda esta carpeta en
  m/s**, y una sonda de calado la convertiria en caudal.
