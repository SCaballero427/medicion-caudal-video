# Guia de `Boneyard_STIV_pipeline.ipynb`

Que hace cada parte, que mirar en cada figura y que se puede tocar sin romper nada. En castellano
llano; el notebook mismo va sin acentos, como el resto de casos del workspace.

## De que va este caso

Mide la velocidad del agua en la superficie de un arroyo urbano encajonado, a partir del video de
una camara IP colgada bajo una pasarela. La estacion es la USGS 03337000, *Boneyard Creek at
Urbana, IL*, y los datos son el release doi:10.5066/P9VZ6VYM.

Lo que lo distingue de los otros tres casos del workspace es lo que **no** hay: ni puntos de
control, ni ancho de canal, ni seccion transversal, ni configuracion de camara. Solo 61 videos y,
para cada uno, el calado y el caudal del limnigrafo.

Por eso **este notebook no calcula caudal**. Llega a velocidad superficial y ahi se para. No es que
se haya quedado a medias: es hasta donde la geometria disponible permite llegar honestamente.

## La idea central, en una frase

La camara mira en oblicuo, asi que un pixel del fondo del encuadre vale muchos mas centimetros que
uno del primer plano. Hay que rectificar. Y para rectificar sin puntos de control se usa el punto
donde convergen las hiladas de piedra de los dos muros: el **punto de fuga**.

Lo interesante es que con eso basta, aunque no se sepa la focal de la camara:

> Cualquier homografia que mande el horizonte correcto al infinito es, respecto del plano de agua,
> una **afinidad**. Y una afinidad estira todas las longitudes de una misma direccion por el mismo
> factor. Como el agua va siempre en la direccion del canal, la velocidad sale bien **salvo una
> constante que multiplica a todo por igual**.

De ahi que la focal sea decorativa, y que el resultado se de en *alturas de camara por segundo*. El
dia que alguien mida el ancho del canal, se multiplica y quedan m/s. Mientras tanto, las
comparaciones entre estaciones y entre instantes son validas tal cual.

## Parte por parte

### Parte 0 — Rutas
Comprueba que estan los ficheros. Si sale `FALTA`, el kernel no arranco en esta carpeta.

Hay **dos** videos y no es un error: uno de aguas bajas para calibrar la geometria (con los muros al
descubierto) y otro de aguas altas para medir. Vale porque el horizonte de un plano horizontal no
cambia si el plano sube; lo unico que cambia es la constante global, que ya era desconocida.

### Parte 1 — El dataset y por que este video
Pasa por los 61 videos midiendo brillo, saturacion y nitidez.

**fig1**: a la izquierda, saturacion contra caudal. Los rojos son nocturnos — la camara pasa a
infrarrojo y sale en gris, desenfocada y con gotas en la lente. Son ilegibles, no hay nada que
rescatar. A la derecha, la curva de gasto del dataset con el video elegido marcado con una estrella.

Lo que hay que ver: **los dos caudales mas altos del release son nocturnos y se pierden**. El rango
utilizable queda en 94–368 cfs.

Al final de la parte se mide si la camara se mueve, en dos escalas: entre fechas (18 meses) y entre
fotogramas consecutivos. Sale ~1.3 px y ~0.05 px respectivamente. Conclusion: **este caso no
necesita estabilizacion**, a diferencia del SMC.

### Parte 2 — Geometria
Detecta segmentos rectos en los dos muros y busca por RANSAC el punto donde concurren.

**fig2**: verde son las hiladas aceptadas, gris las descartadas, y de cada aceptada sale una linea
hacia el punto de fuga. Lo que hay que mirar: **que los segmentos de los dos muros, uno a cada
lado, apunten al mismo sitio**. Eso es lo que demuestra que el punto es real y no un artefacto de
un muro solo. La linea roja discontinua es el horizonte del plano de agua.

**fig3**: el resultado, con los dos videos lado a lado. Aqui esta la verificacion de todo el
montaje: **el canal tiene que salir como una banda recta de anchura constante**. Si el horizonte
estuviera mal, o si la distorsion de lente importara, saldria en abanico o combado. Los muros se
ven estirados hacia fuera y eso es correcto: son paredes verticales, no pertenecen al plano de
agua, y solo la superficie del agua se rectifica bien.

La parte alta se ve borrosa. No es un fallo: cerca del horizonte un pixel de camara cubre tanto
terreno que el remuestreo no tiene informacion que poner. Por eso solo se mide la mitad cercana.

### Parte 3 — La imagen espacio-temporal
Para cada estacion transversal se muestrea una linea a lo largo del flujo, fotograma a fotograma, y
se apilan. Las manchas de espuma dejan trazas diagonales cuya pendiente **es** la velocidad.

`DS` (cada cuantos pixeles se muestrea) no se teclea: se mide el desplazamiento real por correlacion
de fase y se elige `DS` para que las trazas caigan cerca de 45 grados, que es donde un error de
angulo pesa lo menos posible. El notebook imprime cuanto pesaria con `DS = 1` para que se vea la
diferencia.

**fig4**: el STI antes y despues de normalizar. En el crudo hay una franja vertical quemada en el
centro — el reflejo del cielo, que no tiene textura. Como ese reflejo es fijo en el espacio y el
agua no, restar a cada posicion su media temporal lo borra sin necesidad de ningun parametro. En el
normalizado quedan solo las trazas.

### Parte 4 — Tensor de estructura
Saca la orientacion dominante de las trazas. Se calcula por bloques con solape y se combinan con
mediana ponderada, porque un tensor global dejaria que una sola mancha brillante decidiera por toda
la estacion.

### Parte 4b — Control de calidad
**Esta es la parte que hay que leer con atencion, porque contiene la trampa del caso.**

En el caso SMC el filtro era coherencia > 0.70. Aqui eso no solo no sirve: hace lo contrario de lo
que uno espera. Las estaciones que caen sobre los muros dan **coherencia 0.75 con velocidad
exactamente cero**, de las mejores notas de toda la seccion. Y esta bien calculado: un muro quieto
es una traza perfectamente coherente de pendiente nula. Un umbral de coherencia **las aprueba**.

Lo que las distingue es que un muro no cambia con el tiempo. Por eso el filtro es la varianza
temporal, y el umbral no esta elegido a ojo: hay un hueco limpio de factor 5 entre lo estatico
(≤0.94) y lo que fluye (≥4.56).

**fig5**: a la izquierda el contraste temporal por estacion en escala logaritmica, donde se ve el
hueco. A la derecha, coherencia contra velocidad: los puntos etiquetados arriba a la derecha, con
coherencia alta y velocidad cero, son los muros.

### Parte 5 — Perfil transversal
**fig6**: la velocidad estacion a estacion. Las rechazadas se marcan con una cruz y **no se
rellenan**. En el caso SMC se interpolaban y ese relleno costaba la mayor parte del error final;
aqui no hay seccion que integrar, asi que rellenar solo seria inventar.

Lo que hay que mirar con desconfianza: el maximo cae junto a la margen izquierda. Fisicamente el
agua deberia frenar contra el muro, no acelerar. Probablemente sea contaminacion de muro en las
estaciones de cobertura parcial. Esta declarado como limitacion, no arreglado.

### Parte 6 — Recursos
Cuanto cuesta cada bloque. El resultado util antes de optimizar nada: **el tensor de estructura es
el 0.1% del tiempo**. Todo lo caro es leer y rectificar el video. Dentro de ese bloque, el
`warpPerspective` es el 42% — es el coste nuevo que este caso introduce y que el caso SMC no tenia,
por ser cenital.

### Parte 7 — Contraste con el aforo
El limnigrafo da Q = 368 cfs y GH = 14.88 ft para este video. **No se usa para ajustar nada.**

La tabla que se imprime dice que altura de camara haria falta para cerrar el caudal bajo una
seccion rectangular supuesta. Es una comprobacion de orden de magnitud, **no una calibracion**, y
esta etiquetada como tal. Si se usara al reves —elegir la altura que da el caudal correcto— no
quedaria ninguna validacion.

Lo que de verdad cerraria el caso son las mediciones de campo de la estacion 03337000 en NWIS, que
publican ancho, area y velocidad media por aforo.

### Parte 8 — El video
Lanza `video_velocidad.py`, que repite el STIV en ventanas deslizantes sobre el video completo y
dibuja el resultado sobre las dos vistas a la vez.

**fig7** es un fotograma de muestra. La vista rectificada es donde se mide, porque ahi la escala es
uniforme. La original esta para poder juzgar si lo medido cae donde uno cree: los puntos de colores
deben verse alineados sobre una transversal del canal.

**fig8** es la serie temporal de la mediana de la seccion. Ahi se ve que la velocidad no es
constante: fluctua unos pocos por ciento a lo largo de los 38 s.

## Que se puede tocar

Todo lo marcado `>>> AJUSTABLE <<<` esta al principio de la parte que lo usa.

| Constante | Parte | Efecto de cambiarla |
|---|---|---|
| `V1`, `FOCAL` | 2 | `V1` es critico, cambia el horizonte y con el toda la medida. `FOCAL` solo cambia el aspecto. |
| `XMIN`…`YMAX`, `ESC` | 2 | Recorte y resolucion de la rectificada. Subir `YMAX` mete zona sin textura. |
| `DS` | 3 | El angulo de las trazas. Alejarse de 45 grados amplifica el error. |
| `N_EST`, `N_FRAMES` | 3 | Resolucion transversal y longitud de las trazas. |
| `BLOQUE`, `SOLAPE` | 4 | Escala a la que se mide la orientacion. `BLOQUE` debe caber en la ventana de la Parte 8. |
| `COH_MIN`, `CONTRASTE_MIN`, `COBERTURA_MIN` | 4b | El filtro. `CONTRASTE_MIN` es el que rechaza los muros. |

**Lo que no conviene tocar**: `V1` sin volver a mirar fig2, y `CONTRASTE_MIN` sin volver a mirar
fig5. Y por encima de todo, nada de la Parte 7 debe realimentar a las anteriores.

## Ojo con esto

- Los videos **no estan en el workspace**: son 4.7 GB en `C:\Users\Sergio\Desktop\Boneyardcreek`.
- Varios ficheros tienen fotogramas corruptos, asi que una ejecucion completa escupe un chorro de
  `[h264] error while decoding MB ...`. Es ruido del decodificador, no un fallo.
- `video_velocidad.py` **repite las constantes de geometria del notebook**. Si se cambia una, hay
  que cambiarla en los dos sitios. La tabla de constantes compartidas esta en la introduccion del
  notebook.
- El notebook completo tarda ~3 minutos, de los cuales la mitad es el triaje de los 61 videos y
  otro tanto el render del video.
