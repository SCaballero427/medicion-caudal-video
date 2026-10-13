# `analisis_canal_riego_stiv/` — STIV sobre un video de WhatsApp, sin un solo dato de campo

STIV desde cero (OpenCV puro, pyorc no se importa) sobre un video de movil de un canal de riego
revestido de hormigon. Es el caso con **menos informacion de todo el workspace**: no hay GCPs, ni
ancho medido, ni seccion, ni batimetria, ni aforo, ni EXIF. Solo 81 s de video reencodeado por
WhatsApp. Produce velocidad superficial en unidades afines y un perfil transversal, y lo dibuja
sobre las dos vistas a la vez.

```powershell
cd analisis_canal_riego_stiv
..\pyorc_env\Scripts\python.exe stiv_canal.py                  # medida + 6 figuras + CSV  (~95 s: 83 s la STI)
..\pyorc_env\Scripts\python.exe ptv_arbitro.py                 # arbitro independiente      (~2 min)
..\pyorc_env\Scripts\python.exe video_velocidad.py             # video a tiempo real
..\pyorc_env\Scripts\python.exe stiv_canal.py --barrer-focal    # sensibilidad al unico parametro no medible
```

El video de entrada esta **fuera del workspace**, en
`C:\Users\Sergio\Desktop\videos\WhatsApp Video 2026-08-16 at 8.07.12 PM.mp4` (7.4 MB), y la ruta
es absoluta a proposito, como en Boneyard y en los casos HARMONIOUS.

| | |
|---|---|
| Video | 1024x576, 29.975 fps, 2429 fotogramas, 81.0 s, **661 kb/s** (H.264 Baseline) |
| Camara | movil a pulso, oblicua, mirando practicamente por el eje del canal |
| Geometria disponible | ninguna. Solo el punto de fuga que se deduce de las propias orillas |
| Deriva de camara | mediana **6.70 px**, maxima 10.08 px sobre los 81 s |
| Resultado | **v mediana 0.0590 alturas de camara/s** = 0.0262 anchos de canal/s |
| Estaciones | **6 de 15** aceptadas |
| Arbitro | PTV independiente: **r = +0.984**, sesgo +13.1 %, RMSE 0.0070 |
| Sobre 138 ventanas de 12 s | mediana **0.0598** (q05-q95 0.0432 - 0.0805) -- coincide al 1.4 % |

## Por que este video parecia imposible

La primera medida que se hizo sobre el agua fue una correlacion de conjunto entre fotogramas, y
dio el resultado que en el caso Arrow significa «aqui no hay nada»:

| desfase | 0.033 s | 0.067 s | 0.13 s | 0.27 s | 0.53 s |
|---|---|---|---|---|---|
| pico | 0.953 | 0.878 | 0.847 | 0.682 | 0.372 |
| desplazamiento del pico | (0,0) | (0,0) | (0,0) | (0,0) | (0,0) |

Correlacion altisima con el pico **clavado en desplazamiento cero**: un patron que decae pero no
se mueve. Y la desviacion temporal del agua era de **0.54 a 1.06 niveles de gris**, mientras que
el hormigon estatico en sombra daba **1.2 a 2.3**: el agua variaba MENOS que una superficie
inmovil, exactamente la firma del video sin sembrar del caso Arrow. Estabilizar y filtrar en
espacio con un paso alto no cambio nada: el pico seguia en cero con razon 1.00.

La explicacion esta en los 661 kb/s. A ese bitrate el codificador aplana una superficie de agua
turbia y de bajo contraste hasta dejarla casi uniforme, y lo que sobrevive son **artefactos de
bloque anclados a la rejilla de pixeles**. La STI en crudo (fig2, panel central) no es agua: es
un mosaico de macrobloques de H.264.

## Las tres cosas que lo hacen medible

### 1. Realce morfologico top-hat — la leccion del caso

La senal si existe, pero no es una textura continua: son **detritos vegetales sueltos, pequenos y
brillantes**. Un top-hat morfologico con elemento de 5 px los aisla y, de paso, **borra los
bloques**, porque un macrobloque es una region plana y el top-hat solo deja lo que es mas
brillante que su entorno inmediato. 5 px es algo mayor que un detrito (2-4 px) y bastante menor
que un macrobloque (16 px), que es justo la separacion que hace falta.

El efecto es la diferencia entre los dos paneles de la derecha de `fig2_realce.png`: de mosaico
de bloques a estelas rectas y limpias. **Es la tecnica nueva que aporta este caso al workspace**
y la que habria que probar primero en cualquier otro video comprimido.

### 2. Seleccion de bloques por senal en el tensor

Con trazador escaso, la mayoria de los bloques de la STI no contienen ninguna estela, solo el
residuo estatico -- que es una estela de pendiente cero perfectamente coherente, **la trampa de
Boneyard**. La mediana ponderada por coherencia sobre todos los bloques da esto:

```
  frac 0.15  ang -0.23 deg  coh 0.703  v = -0.0012      <- estacion con estelas evidentes a ojo
  frac 0.50  ang +0.00 deg  coh 0.739  v = +0.0000
  frac 0.75  ang -3.63 deg  coh 0.632  v = -0.0190
```

Cero en las 15 estaciones, con coherencia 0.7, incluidas las que tienen estelas visibles. La
correccion es tomar la mediana **solo sobre los bloques cuyo maximo supera el cuantil
`CUANTIL_SENAL`**. El valor no se elige por su resultado: se mide cuantos bloques contienen de
verdad una particula (**entre el 11 y el 21 %** en las estaciones con trazador), asi que quedarse
con el 15 % mas brillante -- q = 0.85 -- es quedarse con esos.

### 3. Banda de lineas paralelas

El truco de Bradano, por la misma razon (trazador escaso), pero mas ancho. Medido:

| banda | lineas | coherencia | sesgo contra PTV |
|---|---|---|---|
| 0.035 | 3 | 0.48 - 0.75 | erratico, +5 % a +29 % |
| **0.10** | **11** | **0.65 - 0.86** | **estable, +11 % a +16 %** |
| 0.20 | 21 | 0.70 - 0.75 | +11 % a +17 % |

0.10 es el 68 % del paso entre estaciones, muy por encima del 22-24 % de Bradano y Arrow, y a
proposito: el perfil transversal aqui es suave, asi que promediar a traves cuesta poca resolucion
y compra mucha senal. A partir de 11 lineas deja de pagar.

## Dos estimadores de pendiente, y una validacion sintetica

Sobre la misma STI se calculan **dos** pendientes por caminos que no comparten nada mas que la
propia STI:

- **Tensor de estructura por bloques con seleccion por senal** (el que manda). Medida local,
  mediana ponderada por coherencia sobre los bloques con particula.
- **Cresta del espectro 2D** (`cresta_fft`, solo diagnostico). Un patron que se traslada,
  `f(s,t) = g(s - m*t)`, tiene transformada `G(k_s)·delta(k_s·m + omega)`: **toda su energia vive
  sobre una recta por el origen** del plano `(k_s, omega)`. Asi que la pendiente se lee agrupando
  la potencia por angulo y buscando el maximo, sin tensor ninguno. Es la variante espectral
  clasica de STIV. Se excluyen la cruz de continua -- donde vive precisamente el residuo
  estatico -- y los radios extremos.

Uno es local y promediado, el otro global y en frecuencia. Que coincidan es lo que dice que la
pendiente esta en el dato y no en el estimador.

Los dos se validaron primero contra una **STI sintetica de pendiente conocida** (m = 1.300):
FFT 1.297 (-0.2 %), tensor 1.275 (-1.9 %). Eso importa porque separa dos preguntas que es facil
confundir: el sesgo del +13 % contra el arbitro **no** viene de un estimador roto, y el tensor no
esta sesgado al alza por construccion -- sobre el sintetico lee ligeramente bajo.

Sobre el video real, y este es el resultado que hay que leer con cuidado:

| estacion | 8 | 9 | 10 | 11 | 12 | 13 |
|---|---|---|---|---|---|---|
| tensor | 0.0585 | 0.0635 | 0.0646 | 0.0594 | 0.0431 | 0.0279 |
| cresta FFT | 0.0572 | 0.0529 | 0.0714 | 0.0636 | 0.0529 | 0.0208 |
| diferencia | +2 % | +20 % | -10 % | -7 % | -18 % | +34 % |

**Coinciden en la mediana de la seccion (-2.1 %) pero discrepan hasta un tercio estacion por
estacion.** Asi que la mediana de la seccion es un numero mucho mas solido que cualquier valor
individual del perfil, y el sesgo del +13 % contra el arbitro cae dentro de la dispersion entre
estimadores. El perfil transversal de este caso sirve para ver la *forma*, no para leer valores
puntuales.

La **agudeza** del espectro resulta ser, sin haberla buscado, un cuarto discriminador de calidad
que corrobora el de densidad sin usarse para nada: **2.9 a 4.2 en las estaciones rechazadas y 10.3
a 30.3 en las aceptadas**, un hueco de factor 2.5. Y en la estacion 0 -- la de la orilla izquierda,
que devuelve 0.7551 -- el FFT devuelve 0.8268 y agudeza 3.6: los dos estimadores coinciden en que
ahi no hay una estela.

Tambien se probo y se descarto la **correlacion de conjunto con refinamiento subpixel** como
estimador principal: funciona (fue la que dio la primera prueba de que habia movimiento y de que
`dX = 0`) pero se agota con el desfase -- el pico cae a 0.37 a 0.53 s -- mientras que la STI
integra los 81 s enteros. Sirve de sonda, no de medida.

## Como se comprueba la rectificacion, y como NO

Las dos orillas son paralelas en el mundo y convergen en la imagen en el punto de fuga
longitudinal, ajustado por RANSAC sobre el maximo gradiente fila a fila:

```
orilla izq   x = -1.0745*y + 461.90   (35/50 inliers)
orilla der   x = +0.9874*y + 571.39   (18/50 inliers)
punto de fuga  (519.0, -53.1)
```

Con roll nulo -- **una hipotesis, no una medida**, igual que en Boneyard -- la horizontal que pasa
por ese punto es el horizonte, y la homografia que lo manda al infinito deja el plano del agua en
afinidad.

**Que el ancho del canal salga constante NO valida nada.** Conviene decirlo porque es tentador
presentarlo como autocomprobacion y no lo es: el punto de fuga se calcula como la interseccion de
las dos rectas de orilla, asi que la homografia las manda a paralelas **por construccion**. La
variacion medida es **1.97e-16**, epsilon de maquina, y sale igual de nula para cualquier `FOCAL`.
Es una identidad algebraica: solo delata un error de programacion en la homografia, no juzga la
geometria.

Lo que si la valida es que **las estelas de la STI salen rectas**. Si el horizonte estuviera mal,
una particula a velocidad constante trazaria una estela **curva**, porque recorreria cada vez mas
pixeles al acercarse y la correccion aplicada no lo compensaria. Salen rectas -- se ve en
`fig2_realce.png` y en `fig3_sti.png`. Es una comprobacion visual, no una cota, igual que la de la
distorsion de lente en Boneyard. La segunda, mas debil, es la calidad del ajuste RANSAC de las dos
orillas (35/50 y 18/50 inliers), que dice que las orillas son de verdad rectas en la imagen.

Y una tercera, independiente: el PTV mide la componente **transversal** del movimiento y da
**-0.0012** alturas de camara/s, o sea cero. El flujo sale puramente longitudinal sin que se le
haya impuesto: la direccion es la normal a la seccion, pero el sentido y la componente
transversal salen de la medida.

El **sentido** se comprobo ademas sin usar la rectificacion en absoluto, para que no dependiera de
su convenio de signos: emparejando manchas en coordenadas de imagen crudas con desfase de 30
fotogramas (1 s), la mediana de `dy` es **-0.57 px** y el **59.3 % de 60.702 parejas suben** hacia
el punto de fuga. El agua se aleja de la camara. Ese contraste solo sirve para el signo, no para la
magnitud: en un campo con miles de detecciones el vecino mas proximo a 1 s suele ser *otra*
particula mas cercana que el desplazamiento real, asi que la magnitud sale sesgada a cero por un
factor 17. Es precisamente la razon por la que `ptv_arbitro.py` enlaza fotograma a fotograma
exigiendo continuidad de la pista en vez de emparejar a saltos largos.

### FOCAL es la mayor incertidumbre del caso, por encima del algoritmo

`FOCAL = 780` px no se puede medir: WhatsApp reencodea y no queda EXIF. 780 equivale a unos 26 mm
en 35 mm sobre un fotograma de 1024 px, que es la camara principal tipica de un movil. Fija la
inclinacion deducida y con ella la escala longitudinal, que es la direccion en la que se mide.
`--barrer-focal` lo cuantifica (600 fotogramas):

| FOCAL | inclinacion | ancho del canal | v (alt.cam/s) | v (anchos/s) |
|---|---|---|---|---|
| 600 | 29.62 deg | 2.3719 | 0.0426 | 0.0179 |
| 700 | 25.98 deg | 2.2938 | 0.0494 | 0.0216 |
| **780** | **23.62 deg** | **2.2505** | **0.0548** | **0.0243** |
| 900 | 20.76 deg | 2.2051 | 0.0596 | 0.0270 |
| 1000 | 18.83 deg | 2.1786 | 0.0647 | 0.0297 |

**La velocidad se mueve un +52 % de un extremo al otro** (+66 % en anchos de canal). Es facil
enganarse aqui: el *ancho* del canal apenas cambia (8.6 %) y la variacion del ancho con la
distancia sale nula para cualquier F, asi que da la impresion de que la geometria esta atada. No lo
esta. Lo que esas dos cosas comprueban es la coherencia interna de la homografia; la escala
**longitudinal** -- la unica que importa para la velocidad -- depende de la inclinacion, y la
inclinacion depende enteramente de FOCAL.

Acotado a un rango realista de objetivo de movil (F = 700 a 900, o sea 24 a 31 mm equivalentes), la
banda es de **0.0494 a 0.0596**, es decir **+-9 %** alrededor del valor adoptado. Esa es la
incertidumbre dominante del caso: mayor que el +13 % contra el arbitro solo en el rango ancho, y
del mismo orden en el estrecho, pero a diferencia de aquella **es un sesgo sistematico, no una
dispersion**, y no se puede reducir con mas video ni con mejor algoritmo. Solo con una medida real.

El resultado se reporta en **alturas de camara por segundo** y en **anchos de canal por segundo**.
El dia que alguien mida el ancho real del canal, la conversion a m/s es una multiplicacion y no hay
que reprocesar nada -- **y ademas deja de importar FOCAL**, porque un ancho medido fija la escala
directamente en vez de deducirla de la inclinacion. Como referencia: si el canal midiera 6 m de
ancho en la lamina, la velocidad seria de unos 0.16 m/s, coherente con lo lisa que se ve la
superficie y con que el reflejo de las nubes salga nitido.

## Control de calidad: el discriminador de este caso es la densidad de trazador

Boneyard descubrio que la coherencia sola aprueba el hormigon; su discriminador fue el contraste
temporal. Bradano descubrio que en su video el contraste no separaba y uso el brillo. **Aqui no
sirve ninguno de los dos**: el agua con trazador y el agua sin trazador tienen exactamente el
mismo brillo y el mismo contraste temporal, porque la diferencia no esta en el fondo sino en si
pasa o no una particula por encima. Lo que separa es **cuantas particulas hay**:

| poblacion | densidad | estaciones |
|---|---|---|
| agua sin trazador | 0.00001 - 0.00039 | 1 a 7 (mitad izquierda) |
| agua con trazador | 0.00575 - 0.01969 | 8 a 13 (banda de detritos) |
| orilla derecha | 0.07779 | 14 |

Hueco de factor 15 abajo y de factor 4 arriba; `DENSIDAD_MIN = 0.004` y `DENSIDAD_MAX = 0.05` van
dentro. **El umbral de arriba no es decorativo**: sin el, la estacion 14 entra con coherencia 0.67
-- por encima del umbral -- y una velocidad de 0.0185 que no es agua, sino hormigon mojado.

Lo que la densidad **no** separa, y hay que decirlo: la estacion 0, pegada a la orilla izquierda,
da densidad 0.01023, o sea plena banda de agua con trazador. La paran la coherencia (0.580 contra
0.60, por poco) y la cota fisica `V_MAX_FISICA = 3 x V_ESPERADA`, que la caza por un factor 13
(devuelve 0.7551). Por eso los criterios se evaluan de forma **independiente y no en cadena**: el
informe dice cuantas redes atrapan cada estacion, no solo la primera.

## Resultado

**v superficial mediana 0.0590 alturas de camara/s** (q05-q95 0.0317 - 0.0643), 6 de 15
estaciones, y esto es el perfil:

| estacion | X | densidad | coherencia | v (alt.cam/s) | estado |
|---|---|---|---|---|---|
| 0 | -1.049 | 0.01023 | 0.580 | +0.7551 | coherencia; v_no_fisica |
| 1-7 | -0.903 a -0.024 | < 0.0004 | 0.32-0.53 | ~0 | sin_trazador; coherencia |
| **8** | **+0.122** | 0.00633 | 0.707 | **+0.0585** | OK |
| **9** | **+0.269** | 0.00575 | 0.656 | **+0.0635** | OK |
| **10** | **+0.415** | 0.01042 | 0.820 | **+0.0646** | OK |
| **11** | **+0.562** | 0.01356 | 0.797 | **+0.0594** | OK |
| **12** | **+0.708** | 0.01496 | 0.729 | **+0.0431** | OK |
| **13** | **+0.855** | 0.01969 | 0.698 | **+0.0279** | OK |
| 14 | +1.001 | 0.07779 | 0.674 | +0.0185 | orilla |

### La mitad izquierda no se puede medir, y eso es parte del resultado

No hay **ni un trazador** en la mitad izquierda del canal: de 4 a 31 detecciones frente a 1.500 -
16.000 en la derecha, y el PTV cierra 0 pistas alli sobre los 81 s enteros. Los detritos caen de
la vegetacion que cuelga de la orilla derecha -- visible en el encuadre -- y viajan en una banda
por ese lado. Las estaciones rechazadas **no se rellenan**: no hay seccion que integrar, asi que
rellenar solo inventaria datos. Misma regla que Boneyard y Bradano, la contraria que SMC.

Asi que el perfil que se mide no es el del canal, es el de su tercio derecho, y su maximo
(0.0646 en X = +0.42) no tiene por que ser el maximo de la seccion. Con el eje del canal en
X = 0 y el maximo medido en X = +0.42, lo mas probable es que el verdadero maximo quede en la
mitad ciega.

## El arbitro: PTV, porque no hay nada de campo con lo que contrastar

Sin ningun dato de campo, la unica manera de saber si el numero significa algo es medir lo mismo
por un camino que no comparta con STIV mas que el video y la geometria. Es la disciplina de la
Parte 7 del caso Arrow, donde un PIV de conjunto arbitra el STIV: **el arbitro no usa datos de
validacion, usa otro algoritmo.**

Y aqui cae de forma natural, porque el trazador son particulas discretas: eso es lo que un
rastreador quiere y lo que un metodo de correlacion sufre. `ptv_arbitro.py` detecta manchas por
componentes conexas sobre la imagen realzada, las enlaza entre fotogramas y ajusta una recta a
cada trayectoria; exige que la pista dure 6 fotogramas y que el residuo del ajuste recto sea
menor de 0.004, que es lo que separa una particula arrastrada de una deteccion espuria. De
4.524.347 detecciones salen 660 pistas y 562 rectas y con movimiento.

**r = +0.984, sesgo +13.1 %, RMSE 0.0070 alturas de camara/s sobre las 6 estaciones.**

| X | STIV | PTV | dif |
|---|---|---|---|
| +0.12 | 0.0585 | 0.0489 | +19.6 % |
| +0.27 | 0.0635 | 0.0572 | +11.0 % |
| +0.42 | 0.0646 | 0.0545 | +18.5 % |
| +0.56 | 0.0594 | 0.0515 | +15.3 % |
| +0.71 | 0.0431 | 0.0419 | +2.9 % |
| +0.85 | 0.0279 | 0.0271 | +3.0 % |

La forma del perfil se reproduce casi exactamente, y el sesgo **no es constante: crece con la
velocidad** (+19 % en el nucleo rapido, +3 % en las estaciones lentas). Eso apunta a que las dos
medidas no promedian la misma poblacion de particulas: STIV se queda con los bloques mas
brillantes, o sea con los detritos mas grandes, que flotan mas altos y van con la superficie,
mientras que el PTV mediana sobre todas las pistas que consigue cerrar, y las lentas son mas
faciles de enlazar. **No se ha ajustado nada para cerrar ese 13 %.** Cual de los dos esta mas
cerca de la velocidad superficial real no se puede decidir con este video.

## El video

`video_velocidad.py` repite el mismo STIV en ventanas deslizantes de 360 fotogramas (12 s) con paso
de 15 (0.5 s) y escribe `salidas/velocidad_tiempo_real.mp4` -- 21 MB, 1798x702, 2429 fotogramas,
**reproduccion a tiempo real** (un fotograma de salida por cada fotograma de entrada). Dos paneles,
como en Boneyard y Hommerich: la camara es oblicua, asi que la medida ocurre en el panel
rectificado y el original es lo que permite juzgar que las estaciones caen donde uno cree. La
flecha es el **recorrido en 10 s**, una longitud real, asi que la perspectiva la acorta sola en el
panel de la camara; 1 s -- la convencion de Hommerich -- seria invisible a esta velocidad.

Sobre 138 ventanas, **589 de 2.070 parejas estacion-ventana** se aceptan y la mediana de la seccion
es **0.0598** (q05-q95 0.0432 - 0.0805, rango 0.0413 - 0.0844) contra el **0.0590** de la medida
unica sobre los 81 s enteros. Coinciden al 1.4 %, que es lo util: el numero no es un artefacto de
una ventana afortunada. Las ventanas cortas son mas ruidosas y ocasionalmente devuelven valores
absurdos -- por eso existe `V_MAX_FISICA`, igual que en el `video_velocidad.py` del caso SMC.

**Los detritos detectados se pintan en amarillo en los dos paneles**, recortados al tramo de agua
que se mide. Eso es lo que hace el video autoexplicativo: se ve la particula y se ve la flecha que
produce. Sustituye a un estirado de contraste referido al agua, que se probo y se descarto: quema
las dos orillas (30 % de pixeles saturados) y aun asi deja el agua plana, porque el problema no es
el rango sino que el codec ha borrado el contraste local.

El recorte al agua **no es cosmetico**. Sin el, las dos orillas salen en amarillo macizo: el
top-hat responde muchisimo mas a la grava y a la vegetacion que al agua, porque tienen mucha mas
estructura fina, y los pocos detritos reales quedan invisibles al lado. Es el mismo hecho que hace
que un mapa de densidad de top-hat sobre el fotograma entero solo dibuje las orillas, y deja claro
que el top-hat no funciona dentro del canal porque responda poco a lo demas, sino porque **ahi no
hay nada mas a lo que responder**.

## Limites conocidos, en orden de importancia

1. **`FOCAL` es la incertidumbre dominante**: +-9 % sobre un rango realista de objetivo, +52 %
   sobre el rango ancho. Es un sesgo sistematico, no dispersion, y **no se reduce con mas video ni
   con mejor algoritmo**. Ver la tabla de arriba.
2. **Nada valida la magnitud, y con estos datos nada puede.** El arbitro PTV es una comprobacion de
   coherencia *interna*: comparte con STIV la rectificacion, la estabilizacion y las mismas
   particulas. Si los detritos no viajaran con el agua superficial -- arrastrados por viento, por
   ejemplo -- los dos metodos estarian igual de equivocados y seguirian dando r = +0.984. Ese
   coeficiente dice que los dos algoritmos leen bien la misma senal, no que la senal sea la
   velocidad del agua.
3. **No hay caudal y no puede haberlo**: sin ancho ni batimetria no hay area. Ni siquiera hay m/s.
4. **Solo se mide el tercio derecho** de la seccion, por falta de trazador en el resto. El maximo
   medido cae en X = +0.42 con el eje en X = 0, asi que el maximo real probablemente esta en la
   mitad ciega y **el perfil no es el del canal**.
5. **Los valores estacion por estacion son blandos**: los dos estimadores discrepan entre -18 % y
   +34 % en estaciones individuales aunque coincidan al -2.1 % en la mediana de la seccion. El
   perfil sirve para la forma, no para leer puntos.
6. **Solo se mide de Y = 1.40 a 3.20**, un tercio del canal visible. El limite de arriba ya no es
   heredado de Boneyard: esta medido en `analisis_canal_lejano_stiv/`, que muestra que por encima
   el muestreo cae por debajo de 0.2 px de imagen y el tensor devuelve velocidades 20 veces
   mayores **con coherencia 0.98**. No es recuperable con este video.
7. **Roll nulo es una hipotesis.** El punto de fuga vertical no se intento: en este encuadre no hay
   ninguna vertical fiable. Un roll real de 1 grado inclinaria el horizonte y sesgaria la escala.
8. **La distorsion de lente no se corrige.** No hay EXIF ni patron con el que estimarla. Si
   importara, el canal saldria curvado en el panel rectificado; no lo hace, pero eso es una
   comprobacion visual, no una cota.
9. **La orilla izquierda contamina** la estacion 0 pese al retranqueo de 0.10; la paran dos
   criterios pero por poco margen en uno de ellos.
10. **Solo hay 81 s** y un solo video, sin ninguna repeticion con la que juzgar la estabilidad del
   numero mas alla de las ventanas de `video_velocidad.py`.
11. El sesgo del **+13 %** contra el arbitro queda abierto.

**Lo unico que hace falta para desbloquear casi todo esto es una cinta metrica.** Un ancho de agua
medido convierte el resultado a m/s, elimina la dependencia de FOCAL (porque fija la escala
directamente en vez de deducirla de la inclinacion) y deja como unicos limites de fondo la falta de
trazador en la mitad izquierda y la ausencia de batimetria.

## Donde encaja en el workspace

| caso | camara | geometria disponible | trazador | llega a |
|---|---|---|---|---|
| `analisis_USGS_SMC_stiv/` | nadir, 4K | metrica (ancho conocido) | bueno | caudal m3/s |
| `analisis_hommerich_stiv/` | oblicua | completa (intrinsecos + 6 GCP RTK) | bueno | caudal m3/s |
| `analisis_bradano_stiv/` | nadir, ya ortorectificado | escala declarada | escaso | v en m/s |
| `analisis_boneyard_stiv/` | oblicua | **ninguna** | espuma fina | v en unidades afines |
| `analisis_arrow_stiv/` | fija | escala declarada | **ninguno** (el resultado es el negativo) | nada, a proposito |
| **este caso** | **oblicua a pulso, muy comprimida** | **ninguna** | **escaso y solo en un tercio** | **v en unidades afines** |

Es el hermano pobre de Boneyard: la misma geometria por punto de fuga y las mismas unidades
afines, pero con un bitrate 10 veces peor, deriva de camara real (6.70 px frente a 0.02-0.06 de
Boneyard) y trazador solo en un tercio de la seccion. Lo que aporta de nuevo es el **realce
top-hat**, la **seleccion de bloques por senal** y un **discriminador de calidad por densidad de
trazador**, las tres cosas transferibles a cualquier video comprimido de movil.

## Ficheros

| fichero | que es |
|---|---|
| `stiv_canal.py` | el caso entero: geometria, realce, STI, tensor, control de calidad, figuras |
| `ptv_arbitro.py` | el arbitro independiente por rastreo de particulas |
| `video_velocidad.py` | el video a tiempo real, dos paneles |
| `figuras.py` | las 6 figuras; se llama desde `stiv_canal.py` |
| `escritor_video.py` | copia del escritor H.264 compartido del workspace |
| `salidas/perfil_velocidades.csv` | una fila por estacion, con densidad, coherencia y motivo de rechazo |
| `salidas/ptv_perfil.csv` | el perfil del arbitro, por bandas |
| `salidas/config_stiv_canal.json` | la configuracion entera congelada |
| `salidas/velocidad_ventanas.csv` | la serie por ventana del video |

**Este caso no duplica constantes.** `video_velocidad.py` importa de `stiv_canal.py` la
geometria, el realce, el tensor y `motivos_rechazo`, en vez de copiarlos como hacen los
`video_velocidad.py` de los otros cinco casos. Lo unico propio del video es el tamano de ventana,
el paso y el lenguaje visual.
