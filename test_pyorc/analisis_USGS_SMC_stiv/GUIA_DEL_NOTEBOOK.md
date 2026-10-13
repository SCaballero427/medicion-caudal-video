# Guia del notebook `SMC_STIV_pipeline.ipynb`

Explicacion paso a paso de que hace cada parte, por que lo hace asi, y que hay que mirar en la
salida de cada una. Esta escrita para leerse **antes** o **junto** al notebook, no despues.

Igual que el notebook, esta en espanol sin acentos, que es la convencion de esta carpeta.

---

## 1. El problema, en una frase

Tenemos un video de dron mirando hacia abajo un canal de hormigon, y queremos saber **cuantos metros
cubicos por segundo** pasan por el. Nadie ha metido un sensor en el agua: toda la informacion esta en
como se mueven las manchas de espuma en la imagen.

Para llegar del video al caudal hacen falta tres cosas, y el notebook las va consiguiendo en orden:

```
   video   ---->  velocidad     ---->  velocidad media  ---->  caudal
            (1)   en superficie   (2)   en la vertical    (3)
                  [m/s]                  [m/s]                 [m3/s]
```

1. **Del video a la velocidad en superficie**: esto es STIV, y es el 80 % del notebook.
2. **De superficie a media en la vertical**: un coeficiente, `ALFA = 0.85`. El agua va mas despacio
   cerca del fondo que en la superficie.
3. **De velocidad a caudal**: multiplicar por la profundidad de cada vertical e integrar a lo ancho.

Los pasos 2 y 3 son convenios de hidrometria, no algoritmo. El unico dificil es el 1.

---

## 2. La idea de STIV, sin formulas

STIV significa *Space-Time Image Velocimetry*, velocimetria por imagen espacio-temporal.

Imagina que pintas una **raya recta** sobre el agua, en el sentido en que corre el rio. En cada
fotograma del video, lees los pixeles que caen justo debajo de esa raya. Eso te da una **fila** de
valores de gris. Como el video tiene 250 fotogramas, obtienes 250 filas. Las apilas una encima de
otra y te queda una imagen nueva:

```
                    espacio (a lo largo de la raya, aguas abajo -->)
                  +--------------------------------------------------+
   fotograma 0    |  ....##....#####.......##.....                    |
   fotograma 1    |  .....##....#####.......##....                    |
   fotograma 2    |  ......##....#####.......##...                    |
   fotograma 3    |  .......##....#####.......##..                    |
        ...       |                                                  |
   fotograma 249  |                                                  |
                  +--------------------------------------------------+
                       ^
                       una mancha de espuma va corriendose a la derecha
                       en cada fila -> dibuja una raya diagonal
```

Esa imagen apilada se llama **STI** (imagen espacio-temporal). Y en ella pasa algo util: una mancha
de espuma que baja con la corriente aparece un poco mas a la derecha en cada fila, asi que en la STI
**dibuja una linea diagonal**.

Y ahora lo importante: **la inclinacion de esa diagonal es la velocidad.**

- Si el agua va rapida, la mancha se corre mucho de una fila a la siguiente, y la raya sale muy
  tumbada.
- Si va lenta, se corre poco, y la raya sale casi vertical.
- Si el agua estuviera parada, la mancha no se moveria y la raya seria completamente vertical.

Todo el metodo se reduce a **medir bien el angulo de esas rayas**. Eso es lo que hace el *tensor de
estructura* de la Parte 4.

### En que se diferencia del PIV (lo que hace pyorc)

El PIV coge un cuadradito de la imagen en el fotograma 1, lo busca en el fotograma 2, y mide cuanto
se ha movido. Repite eso en una malla y saca un campo de flechas.

STIV renuncia a la segunda dimension: no busca en 2D, solo pregunta a que velocidad viaja el patron
*a lo largo de una raya que tu le das*. A cambio:

- **Usa los 250 fotogramas de golpe** en un unico ajuste, en vez de par a par. Con poca espuma en el
  agua, eso es mucho mas robusto.
- **Gasta muy poca memoria**: 870 MB frente a los ~14 GB del notebook de pyorc con el mismo video.
- **Necesita que le digas la direccion del flujo.** Aqui no es problema: el canal es recto.

---

## 3. El mapa completo del notebook

```
  PARTE 0   rutas
  PARTE 1   abrir el video, leer un fotograma
     |
  PARTE 2   [FILA_AGUA_SUP/INF, ANCHO_CANAL, COLUMNA_INI/FIN, ANGULO_FLUJO]
            escala (m/px) y geometria: donde va cada raya
     |
  PARTE 3   [V_ESPERADA, N_FRAMES]
            construir las 13 STI            <-- unica pasada sobre el video
     |
  PARTE 4   [LADO_BLOQUE, COH_MIN_BLOQUE, SIGMA_DERIVADA]
            medir el angulo: TENSOR DE ESTRUCTURA  ->  velocidad de cada vertical
  PARTE 4b  [COH_MIN_ESTACION]
            tirar las medidas malas y rellenarlas
  PARTE 5   [ALFA]
            seccion + caudal  ->  Q
     |
  PARTE 6   cuanto ha costado (tiempo y memoria)
  PARTE 7   [Q_AFORO, V_ADV, ...]  comparar con el aforo real  ->  Y AQUI SE ACABA
```

Entre corchetes, las constantes ajustables de cada parte. Estan **al principio de la primera celda
de codigo de su parte**, dentro de un recuadro de comentarios marcado `>>> AJUSTABLE <<<`, con la
explicacion de que es cada una y para que se usa. Las que salen del data release del USGS llevan la
marca *(obtenido del dataset)*.

Las tres decisiones que lo condicionan todo son **ESCALA** (Parte 2), **DS** (Parte 3) y **ALFA**
(Parte 5). El resto son detalles de implementacion.

Una propiedad del notebook que conviene entender: **no hay ningun detector automatico**. Ni la linea
de agua, ni la direccion del flujo, ni el paso de muestreo se "descubren" solos. Los tres son
constantes que tu escribes, igual que los GCPs del notebook de Ngwerere, y el notebook solo dibuja lo
necesario para que puedas comprobarlas de un vistazo. Es mas simple, mas rapido y mucho mas facil de
llevar a otro video.

Fijate ademas en donde estan los datos de validacion: **en la Parte 7, no en la 0**. Hasta la ultima
celda del notebook, el caudal del aforo no existe siquiera como variable en memoria. Esa es la regla
de oro del notebook, y esta puesta de forma que sea dificil saltarsela por accidente.

---

## 4. Parte por parte

### Parte 0 - Rutas de trabajo

**Que hace.** Solo define donde estan los archivos: el video estabilizado que entra, el CSV de la
seccion, y la carpeta `salidas/` donde va todo lo que se genera. Nada mas.

Las constantes ajustables **no estan aqui**: cada una vive al principio de la parte donde se usa, en
un recuadro marcado `>>> AJUSTABLE <<<`. Asi, cuando estas leyendo una parte, tienes delante los
numeros que la gobiernan y su explicacion, sin tener que subir al principio del notebook.

**Que mirar.** Que salga `OK` en los tres archivos. Si sale `FALTA`, casi seguro es que has lanzado
el notebook desde otra carpeta: tiene que arrancar desde `analisis_USGS_SMC_stiv/`.

---

### Parte 1 - Lectura del video

**Que hace.** Abre el video con `cv2.VideoCapture`, lee los metadatos (resolucion, fps, numero de
fotogramas) y saca el primer fotograma para verlo.

**Lo importante de esta parte esta en el texto, no en el codigo:** explica **por que el video que
entra ya viene estabilizado**. El dron no esta quieto. Y STIV es especialmente sensible a eso, porque
supone que la raya apunta siempre al mismo trozo de canal durante los 250 fotogramas. Si el dron se
mueve, ese movimiento se suma directamente a la inclinacion de las rayas de la STI, y por tanto a la
velocidad medida.

La correccion se hace **fuera del notebook**, una sola vez, con `estabilizar_stiv.py`. Ese script:

1. Busca 600 puntos con esquina marcada en el terreno **fuera del agua** (el hormigon, la hierba),
   sobre el primer fotograma.
2. Sigue esos mismos puntos hasta cada fotograma con flujo optico.
3. Calcula la rotacion + traslacion que devuelve cada fotograma a la posicion del primero, y se la
   aplica.

Resultado medido: el temblor entre fotogramas baja de 0.50 px a **0.02 px**, 27 veces menos.

**Que mirar.** `DT = 33.317 ms` (el intervalo entre fotogramas) aparecera en la formula final de la
velocidad. Y la figura 1, que es simplemente el canal visto desde arriba.

---

### Parte 2 - Escala y geometria de la seccion

Esta es la parte de la que depende **todo el resultado**, asi que merece leerse con calma.

**Las constantes de esta parte** (arriba del todo de la celda de codigo): `FILA_AGUA_SUP`,
`FILA_AGUA_INF`, `ANCHO_CANAL` *(obtenido del dataset)*, `COLUMNA_INI`, `COLUMNA_FIN` y
`ANGULO_FLUJO`. Las dos filas de la lamina de agua hacen aqui el mismo papel que los GCPs en un caso
de camara oblicua: **son lo unico que liga pixeles con metros**.

**El objetivo.** Saber cuantos metros mide un pixel. Como el dataset da el ancho real de la lamina de
agua (1.8288 m = 6 pies exactos) y las constantes dicen en que filas de la imagen toca cada muro, es
una regla de tres:

```
                    1.8288 m
    ESCALA  =  --------------------- = 1.7790 mm/px
                 (1466 - 438) px
```

**Por que esto se configura a mano.** Podria detectarse automaticamente, pero no compensa. El borde
del agua es facil de ver para una persona y sorprendentemente traicionero para un algoritmo: debajo
de la linea de agua inferior hay una banda oscura de unos 50 px que parece agua en sombra y no lo es,
es la **cara interna del muro** (el dron no esta exactamente encima de ese muro, asi que lo ve un
poco de lado). Un detector por contraste se la traga y ensancha el canal. Poner dos numeros a mano y
dibujarlos para comprobarlos es mas fiable, mas rapido y se entiende mejor.

**Las lineas de busqueda.** Se coloca **una raya por vertical del aforo**, leyendo las progresivas
del propio CSV `Station_Stage_SileCanal.csv`. Asi cada velocidad tiene su pareja exacta en el aforo y
la integracion del caudal reproduce el mismo convenio *mid-section*, sin remuestrear nada. La fila de
cada raya sale de la escala: `fila = FILA_AGUA_SUP + progresiva / ESCALA`.

Las verticales con **profundidad cero** en el CSV (la 0 y la 12) caen sobre la propia linea de agua.
No se miden: se les **impone v = 0**, porque no aportan caudal y porque en el muro el agua no desliza.
Esto se decide aqui, antes de ver ningun resultado.

**Que mirar.** La figura 2 (`fig2_geometria.png`) es la comprobacion visual de toda la geometria:

- Arriba, las 13 rayas sobre el fotograma, **dibujadas con su inclinacion real** (`ANGULO_FLUJO`), o
  sea exactamente como se van a muestrear. Las amarillas (0 y 12) deben caer justo sobre el borde del
  agua, y las rojas repartirse por dentro. Si estan corridas, `FILA_AGUA_*` esta mal; si estan
  torcidas respecto al cauce, lo que esta mal es `ANGULO_FLUJO`.
- Abajo, dos ampliaciones de los dos bordes, en gris y con el contraste estirado. La linea roja debe
  caer sobre la transicion hormigon-agua. El muro de abajo esta en sombra y sin estirar el contraste
  no se ve nada, por eso el zoom no es en color.

**La incertidumbre.** La transicion agua-muro no es un escalon perfecto, ocupa unos 5 px. Eso es un
0.49 % de error en la escala, y **el mismo 0.49 % en el caudal**, porque el caudal es directamente
proporcional a la escala.

> **Nota.** El notebook de pyorc de este workspace usa 436 y 1480. Son 16 px mas ancho, o sea un
> 1.5 % de diferencia en la escala. Los dos notebooks discrepan aqui, y no hay forma de saber cual
> tiene razon sin ir al canal con una cinta metrica.

---

### Parte 3 - Construccion de las STI

Aqui se construyen las 13 imagenes espacio-temporales. Es la unica parte cara del notebook.

**Las constantes de esta parte:** `V_ESPERADA` (la velocidad a ojo, de la que sale todo lo demas) y
`N_FRAMES` (cuanto video procesar).

**La decision importante: cada cuanto se lee la raya.**

Podrias leer la raya pixel a pixel. Seria lo natural, y seria un error. La razon es esta:

A 1.78 mm/px y 30 fotogramas por segundo, con el agua a ~0.95 m/s, **el agua avanza unos 18 pixeles
entre un fotograma y el siguiente**. Si lees un pixel por muestra, cada fila de la STI sale corrida
18 columnas respecto a la anterior, y las rayas quedan casi **horizontales** (87 grados). Y ahi medir
el angulo es pesimo: un error minimo en el angulo se convierte en un error enorme en la velocidad.

La solucion es que **no estas obligado a leer pixel a pixel**. Puedes leer una muestra cada `DS`
pixeles. Y como el angulo de la raya depende de `DS`, eligiendo `DS` **eliges el angulo**:

```
   DS = 1  px  ->  rayas a 87 grados  ->  malisimo
   DS = 6  px  ->  rayas a 72 grados  ->  regular
   DS = 18 px  ->  rayas a 45 grados  ->  OPTIMO
   DS = 30 px  ->  rayas a 31 grados  ->  regular otra vez
```

El optimo esta en 45 grados, que es donde `DS` iguala al desplazamiento por fotograma. Por eso la
configuracion pide `V_ESPERADA` en vez de `DS`: es mucho mas facil estimar a ojo una velocidad que un
paso de muestreo. El notebook hace la cuenta:

```
   DS = V_ESPERADA * DT / ESCALA = 0.95 * 0.0333 / 0.00178 = 17.8  ->  18 px
```

No hace falta afinar: cerca de 45 grados la curva de error es muy plana, y equivocarte un 30 % en
`V_ESPERADA` apenas mueve el resultado.

**El filtro obligatorio.** Si lees una muestra cada 18 px de una textura cuyos detalles miden 10-20
px, estas submuestreando, y aparece **aliasing**: estructuras falsas con orientaciones inventadas.
Como en cualquier remuestreo, antes hay que emborronar: `SIGMA = DS/2 = 9 px`.

Ese filtro tiene un segundo efecto **buscado**: como es isotropo (redondo, no alargado), tambien
promedia *a traves* de la raya, unos 3.5 cm. Eso le da a la raya una **anchura efectiva**, que borra
la turbulencia de pequena escala. Esa turbulencia no viaja con la corriente, solo ensucia la STI. Es
el equivalente del "ancho de linea" que usan las implementaciones habituales de STIV. **No lo
cambies por un filtro solo a lo largo de la linea:** se probo y la coherencia baja de 0.97 a 0.87.

**Como se muestrea.** `cv2.remap` interpola bilinealmente en las coordenadas de la raya, que no caen
en pixeles enteros. Las 13 rayas se muestrean en **la misma pasada** sobre el video: lo caro es
decodificar y filtrar el fotograma 4K, y remapear 13 rayas mas es casi gratis.

**La limpieza de la STI.** La STI recien construida tiene dos cosas que no son senal:

1. **Rayas verticales**: cada punto de la raya tiene su brillo propio (un reflejo fijo, una mancha).
   El tensor las leeria como "velocidad cero" con muchisima energia. Se quitan restando, a cada
   columna, su media a lo largo del tiempo.
2. **Rayas horizontales**: si un fotograma entero sale mas claro (una nube, la autoexposicion), el
   tensor lo leeria como velocidad infinita. Se quitan restando, a cada fila, su media espacial.

**Que mirar.**

- La figura 3 (`fig3_preparacion_sti.png`): a la izquierda la STI cruda, donde casi no se ve nada; a
  la derecha la limpia, donde **las rayas diagonales aparecen de golpe**. Es la figura que mejor
  explica el metodo entero.
- La figura 4 (`fig4_todas_las_sti.png`): las 13 STI juntas. En el centro las rayas son limpias y
  paralelas; en los extremos (verticales 0, 1, 11, 12) casi desaparecen. **Esa figura ya predice
  cuales van a fallar en la Parte 4b.**

---

### Parte 4 - Velocidad con el tensor de estructura

**Que hace.** Mide el angulo de las rayas de cada STI y lo convierte en m/s. Solo mide: el criterio
de aceptacion se aplica en la Parte 4b.

**Las constantes de esta parte:** `LADO_BLOQUE`, `COH_MIN_BLOQUE` y `SIGMA_DERIVADA`. Son los tres
parametros del estimador, y sirven tal cual para casi cualquier caso.

**Como funciona el tensor de estructura, en cristiano.** En cada punto de la imagen calculas el
gradiente: hacia donde cambia el brillo. En una raya diagonal, el gradiente apunta **perpendicular** a
la raya (cruzandola es donde el brillo cambia; a lo largo, no cambia).

Si juntas todos los gradientes de un trozo de imagen en una matriz 2x2 y la diagonalizas, sacas dos
direcciones:

- la del autovalor **grande** = por donde mas cambia el brillo = **perpendicular** a las rayas;
- la del autovalor **pequeno** = por donde menos cambia = **a lo largo** de las rayas. **Esa es la
  que buscamos.**

Como el resultado sale con signo, el metodo tambien te dice **hacia donde va el agua**: no hay que
decirselo.

**La coherencia: la calidad, gratis.** Los dos autovalores dan de regalo un numero entre 0 y 1:

```
   C = (grande - pequeno) / (grande + pequeno)
```

- `C = 1`: toda la textura apunta en la misma direccion. Rayas perfectas.
- `C = 0`: no hay direccion dominante. Ruido.
- `C = 0.70`: la direccion dominante es unas 6 veces mas fuerte que la perpendicular.

Esa es la nota de confianza de cada medida, y es lo que usa el control de calidad de la Parte 4b.

**Por bloques, no de golpe.** Aplicar el tensor a la STI entera es fragil: un reflejo del sol muy
brillante mete tanta energia que puede imponer su orientacion sobre todo lo demas. Por eso la STI se
parte en **bloques de 64x64 con 50 % de solape**, se mide cada bloque, y los resultados se combinan
con una **mediana ponderada por coherencia**. Asi los bloques nitidos pesan mas y ninguno manda solo.

**La formula final**, encadenando conversiones:

```
   u [m/s] = m [muestras/fotograma] * DS [px/muestra] * ESCALA [m/px] / DT [s/fotograma]
```

**Que mirar.**

- La figura 5 (`fig5_tensor.png`): la STI de una vertical central con **la recta roja dibujada
  encima**, que es lo que el tensor ha medido. Debe seguir las rayas. Si no las sigue, algo va mal.
- La tabla de las 13 verticales. Dos columnas dicen si fiarse:
  - `coherencia`: en el centro sale ~0.97; en las verticales 1 y 11 baja a ~0.54 y ~0.61.
  - `bloques`: cuantos bloques de la STI eran utilizables, sobre 18.

Fijate en la vertical 11: sale **1.398 m/s**, mas rapida que el centro del canal, lo cual es
fisicamente imposible. El tensor no ha medido agua, ha medido reflejos. Y su coherencia (0.61) lo
delata sin que nadie tenga que mirar el numero.

---

### Parte 4b - Control de calidad y relleno

**Que hace.** Tira las verticales con coherencia por debajo de 0.70 y rellena el hueco.

**La constante de esta parte:** `COH_MIN_ESTACION`, el umbral de aceptacion. El relleno no tiene
ninguna: es una interpolacion, y no hace falta configurarla.

Es el equivalente exacto del filtrado por mascaras de un flujo LSPIV, y es **imprescindible**: sin
el, la vertical 11 entraria en el caudal con 1.40 m/s.

**Por que fallan siempre las mismas.** Son las pegadas al hormigon, y por una razon fisica clara que
ya se veia en la figura 4: alli el agua va lenta, apenas arrastra espuma, y la franja esta medio en
sombra del muro. A la STI le quedan pocas rayas y muy tenues, asi que el tensor acaba midiendo ondas
superficiales y reflejos, que **no viajan a la velocidad de la corriente**.

**Con que se rellenan: interpolacion lineal.** Los puntos de apoyo son las verticales aceptadas mas
los ceros impuestos en los muros:

```
   v_final[hueco] = np.interp(s[hueco], s[aceptadas o contorno], v[aceptadas o contorno])
```

Una sola linea y ningun parametro. No pretende reproducir la fisica de la capa limite del muro: solo
dice que entre dos verticales conocidas la velocidad varia de forma monotona. Es la hipotesis mas
neutra que se puede hacer con un hueco de una vertical, y por eso mismo es **conservadora** — el
perfil transversal real se mantiene alto hasta muy cerca del hormigon y luego cae de golpe, asi que
la recta pasa por debajo. Es la principal razon de que el caudal salga por debajo del aforo, y esta
anotada como tal en las limitaciones.

**Que mirar.** La figura 6 (`fig6_perfil_superficial.png`), que lo cuenta todo de un vistazo:

- puntos azules: verticales medidas y aceptadas;
- **x rojas**: lo que STIV midio en las rechazadas (la vertical 11 se sale del grafico por arriba);
- cuadrados naranjas: el valor con el que se sustituyen;
- cuadrados negros en los extremos: los ceros impuestos.

El perfil final debe ser una campana suave: maximo en el centro, caida hacia los dos muros.

---

### Parte 5 - Caudal sobre la seccion

**Que hace.** Convierte velocidades superficiales en caudal. Dos pasos, y los dos son convenios de
hidrometria, no algoritmo.

**La constante de esta parte:** `ALFA`, y es la mas importante del notebook entero.

**Paso 1: de superficie a media en la vertical.** STIV solo ve la superficie, pero el caudal necesita
la velocidad media de toda la columna de agua, que es menor porque el agua roza el fondo:

```
   v_media = ALFA * v_superficie      con ALFA = 0.85
```

**0.85 es el estandar de la practica del USGS.** Se fija al principio de esta parte, **antes** de
mirar la referencia, y no se toca. Es el unico parametro del notebook que no se puede medir en la
imagen, y es el que mas pesa en el error final: hablaremos de el en la Parte 7.

**Paso 2: integrar.** Caudal especifico de cada vertical `q = v_media * profundidad` [m2/s], y luego
trapecios a lo ancho de la seccion.

**Por que la seccion tiene profundidad cero en los extremos.** El hidrografo no midio un area: midio
13 verticales y sumo caudales parciales por el metodo **mid-section**, en el que las dos verticales
de los extremos se anotan con profundidad 0. Asi viene el CSV y asi se usa. Eso da 1.803 m2 en vez de
los 1.962 m2 que fisicamente tiene la caja de hormigon (1.8288 x 1.073 m). La diferencia, un 9 %, son
las dos franjas de 7.6 cm junto a cada muro que el convenio descarta.

Es deliberado: **se replica la geometria del aforo** para que el caudal sea comparable. Usar la caja
entera seria mas correcto fisicamente pero daria un 9 % mas, y esa diferencia no seria un error del
metodo sino un cambio de convenio.

**Que mirar.** La figura 7 (`fig7_caudal.png`): arriba la seccion con las dos curvas de velocidad
superpuestas, abajo la distribucion del caudal. Y el numero: **Q = 1.2221 m3/s**.

Esta celda tambien escribe `salidas/config_stiv.json`, que congela **toda** la configuracion usada.
Es lo que hace el resultado reproducible: con ese archivo sabes exactamente que se hizo.

---

### Parte 6 - Recursos consumidos

**Que hace.** Recoge lo que ha medido `benchmark.py` en cada bloque caro: tiempo de reloj, tiempo de
CPU, nucleos usados en paralelo y pico de memoria.

**El resultado es lo interesante, porque va al reves de la intuicion.** Uno diria que lo caro es "el
algoritmo": el tensor, los autovalores, la mediana ponderada. Medido:

| Etapa | Tiempo | % del total |
|---|---|---|
| Construir las STI (unica pasada sobre el video) | ~38-80 s | **~100 %** |
| Preparar las STI | 0.00 s | 0 % |
| **Tensor en las 13 verticales** | **0.03 s** | **0 %** |
| Integracion del caudal | 0.00 s | 0 % |

El tensor de estructura, el corazon del metodo, tarda **treinta milisegundos**. Trabaja sobre 13
imagenes de 250x155 px, medio megabyte en total. Lo caro es **llegar hasta ahi**: decodificar 250
fotogramas de 3840x2160, pasarlos a gris y filtrarlos. Entre 150 y 320 ms por fotograma, segun lo
caliente que este la cache de disco.

De ahi sale la unica conclusion util para optimizar: **si quieres que vaya mas rapido, toca la
lectura del video** (leer a media resolucion, recortar la region decodificada), no el algoritmo.

El rango 38-80 s no es ruido de medida: es la cache de disco. El video son 1.1 GB, y la primera
lectura despues de arrancar el ordenador va a disco en vez de a memoria. El notebook entero tarda
entre **1 y 2 minutos**, y casi todo es esa unica pasada.

**El contraste con LSPIV.** Esta es la comparacion que merece la pena, porque el notebook de pyorc
procesa **el mismo video** y tambien se mide a si mismo:

|  | STIV (este) | LSPIV (pyorc) |
|---|---|---|
| Pico de memoria | **870 MB** | **~14 GB** |
| Que guarda | un fotograma cada vez | el video entero proyectado |

STIV lee un fotograma, lo filtra, se queda con 155 valores por raya y **lo tira**. Todo lo que
sobrevive son las STI. Por eso su memoria es plana y casi no depende de cuantos fotogramas proceses.
LSPIV cambia memoria por informacion 2D; STIV renuncia a la segunda dimension y a cambio cabe en
cualquier maquina.

---

### Parte 7 - Comparacion con la referencia, y fin

**Que hace.** Solo aqui se abren los datos de validacion. Hasta este punto el notebook no ha visto ni
un solo numero del aforo: `Q_AFORO`, `AREA_AFORO`, `V_MEDIA_AFORO` y `V_ADV` *(todos obtenidos del
dataset)* se declaran al principio de esta celda y no existen antes.

Se comparan contra dos referencias:

1. **El aforo con FlowTracker** (un ADV, sensor acustico metido en el agua por vadeo) del mismo dia.
   Caudal total y velocidad media de cada vertical. Incertidumbre declarada: 4.2 %.
2. **El LSPIV del propio USGS** (`SMC_PIV_results.mat`, hecho con PIVlab). Ojo: es del vuelo **020**,
   no del **022** que procesamos. Sirve para comparar **la forma** del perfil, no punto por punto.

**El resultado.**

```
   STIV (este notebook) :  1.2221 m3/s
   Aforo FlowTracker    :  1.4362 m3/s
   Diferencia           :  -14.9 %
```

**Como leerlo.** El error **no esta en el algoritmo**, y hay tres indicios que lo respaldan:

1. La **forma** del perfil transversal sale bien sin haberla impuesto: maximo en el centro, caida
   hacia los muros, y la asimetria del canal. Y sigue de cerca al LSPIV del USGS, calculado con otro
   software y sobre otro vuelo.
2. Las verticales que fallan son **exactamente** las que la coherencia rechaza por su cuenta.
3. Sobre las **9 verticales que STIV si mide**, el desacuerdo es un **sesgo uniforme**, no ruido:
   todas salen bajas en una proporcion parecida. Eso apunta a un factor de escala, no a un error de
   medida. (Las estadisticas de la celda se calculan solo sobre esas 9: incluir las rellenadas
   mediria el relleno, no el metodo.)

El −14.9 % se reparte entre dos causas de naturaleza distinta:

**El relleno de las dos verticales del muro, que es lo que mas resta.** La interpolacion lineal hasta
el cero del muro les asigna 0.36 y 0.41 m/s, mientras que el ADV midio 0.63 y 0.74 ahi mismo. El
perfil real se mantiene alto hasta muy cerca del hormigon y luego cae de golpe; una recta no puede
hacer eso. Es el precio de rellenar sin parametros, y se ve de un vistazo en el panel derecho de la
figura 9: los dos cuadrados naranjas se alejan de la diagonal mucho mas que cualquier punto azul.

**Y ALFA.** El notebook uso 0.85. El propio ADV permite calcular a posteriori cual tendria que haber
sido, comparando solo contra las verticales medidas: sale **0.93**. Tiene sentido fisico: en un canal
de hormigon liso el perfil vertical es mas uniforme que en un cauce natural, asi que la media se
parece mas a la superficie.

**Y aqui esta el punto entero del notebook: ese numero NO se usa para corregir el resultado.** Si
ajustaramos ALFA hasta acertar, lo que demostrariamos es que existe un ALFA que acierta, no que el
metodo funcione. La comparacion se hace una vez, al final, y no se vuelve atras. Por eso el notebook
termina aqui.

---

## 5. Glosario de las variables clave

| Variable | Que es | Valor en este caso | Donde se decide |
|---|---|---|---|
| `FILA_AGUA_SUP/INF` | filas de la lamina de agua | 438 y 1466 | Parte 2, a mano |
| `ANCHO_CANAL` | ancho real de la lamina | 1.8288 m | Parte 2, del dataset |
| `ANGULO_FLUJO` | direccion del flujo en la imagen | -1.0 grados | Parte 2, a mano |
| `ESCALA` | metros por pixel | 0.0017790 m/px | Parte 2, calculado |
| `V_ESPERADA` | velocidad superficial a ojo | 0.95 m/s | Parte 3, a mano |
| `DS` | paso de muestreo de la STI | 18 px | Parte 3, calculado |
| `SIGMA_ANTIALIAS` | emborronado antes de muestrear | 9 px (= DS/2) | Parte 3, calculado |
| `m` | pendiente de las rayas de la STI | ~1 (45 grados) | Parte 4, medido |
| `C` (coherencia) | calidad de la medida | 0.97 centro, 0.54 muro | Parte 4, medido |
| `COH_MIN_ESTACION` | umbral de aceptacion | 0.70 | Parte 4b, a mano |
| `ALFA` | superficie -> media vertical | 0.85 | Parte 5, convenio |
| `Q_AFORO` | caudal de referencia | 1.4362 m3/s | Parte 7, del dataset |

---

## 6. Como llevar el notebook a otro caso

Todo lo que hay que cambiar son los recuadros `>>> AJUSTABLE <<<` que abren cada parte. En orden de
importancia:

**1. Las dos filas de la lamina de agua y el ancho real** (Parte 2). Sin esto no hay escala y no hay
nada. Abre el primer fotograma (o usa `pixel_locator.py`) y anota las dos filas. Necesitas ademas
**una distancia real conocida** entre ellas: el ancho del canal, una cinta metrica en el suelo, dos
estacas medidas con GPS.

**2. `COLUMNA_INI` y `COLUMNA_FIN`** (Parte 2). El tramo util de la imagen. Mas largo da mejor
estadistica, pero acercarse a los bordes mete la distorsion de la lente, que aqui no se corrige.

**3. `ANGULO_FLUJO`** (Parte 2). Si el cauce corre paralelo a las filas de la imagen, 0. Si no, el
angulo que forma. La figura 2 dibuja las rayas con ese angulo encima del fotograma, asi que se
comprueba a ojo.

**4. `V_ESPERADA`** (Parte 3). Un orden de magnitud. No hace falta acertar: equivocarse un 30 %
apenas cambia nada.

**5. El CSV de la seccion** (`ARCHIVO_SECCION`, Parte 0). Dos columnas, `Progresiva` y `Prof`. Las
verticales con `Prof = 0` se toman automaticamente como contorno.

**6. `ALFA`** (Parte 5). 0.85 si no tienes nada mejor. Si tienes un aforo previo en ese punto, usa el
que salga de el.

**7. Los datos de validacion** (Parte 7). Si el caso nuevo no tiene aforo con el que comparar, esta
parte se borra entera y el notebook termina en la Parte 6.

Los tres parametros del tensor (`LADO_BLOQUE`, `COH_MIN_BLOQUE`, `SIGMA_DERIVADA`, Parte 4) y el
umbral de aceptacion (`COH_MIN_ESTACION`, Parte 4b) casi nunca hay que tocarlos.

**Lo que NO deberias cambiar sin motivo:**

- **La regla `DS = desplazamiento`.** Es lo que pone las rayas a 45 grados. Fijar `DS` a mano rompe
  el compromiso.
- **Que el antialias sea isotropo.** Filtrar solo a lo largo de la raya baja la coherencia de 0.97 a
  0.87.
- **Que el tensor vaya por bloques.** De golpe, un reflejo brillante puede dictar el resultado.
- **Que las verticales de profundidad cero valgan 0.** Si las mides, el tensor devuelve decenas de
  m/s: en el borde no hay agua que seguir.
- **ALFA, despues de ver el resultado.** Ahi se acaba la validacion.

---

## 7. Problemas frecuentes

**"No se pudo abrir el video."** Falta `entradas/SMC_estabilizado_stiv.mkv` (1.1 GB, no esta en
ninguna carpeta de salidas). Regeneralo desde la raiz del workspace:

```powershell
python estabilizar_stiv.py USGS/Video/SMC_D_RC_022_08172020_AC.mp4 `
    analisis_USGS_SMC_stiv/entradas/SMC_estabilizado_stiv.mkv `
    --poligono "0,420 3840,420 3840,1500 0,1500" --fin 249
```

Ese archivo es **distinto** del `SMC_estabilizado.mkv` del caso de pyorc y no son intercambiables:
distinto script, distinto temblor residual.

**Sale `FALTA` en los archivos de la Parte 0.** Has lanzado el notebook desde otra carpeta. Tiene que
arrancar desde `analisis_USGS_SMC_stiv/`.

**Las rayas de la figura 2 no caen sobre el agua.** `FILA_AGUA_SUP` o `FILA_AGUA_INF` estan mal.
Corrigelas en el recuadro ajustable de la Parte 2, mirando los zooms de abajo de esa misma figura.

**Las STI de la figura 4 no tienen rayas diagonales, solo ruido.** Dos causas posibles: el video no
esta estabilizado, o `DS` esta muy lejos del desplazamiento real (revisa `V_ESPERADA`).

**Muchas verticales salen `RECHAZADA`.** Poca espuma en el agua, o el video es demasiado corto. Baja
`COH_MIN_ESTACION` con cuidado y mira si las velocidades siguen teniendo sentido fisico. Rechazar 2
de 11 es normal; rechazar 7 significa que el video no da para esto.

**La primera ejecucion tras encender el ordenador tarda mucho mas.** Normal: el video son 1.1 GB y la
cache de disco esta fria. La segunda vez baja a la mitad.
