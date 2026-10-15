# Evolucion del codigo STIV, caso a caso

Como cambia la implementacion de STIV desde la primera prueba (julio de 2026) hasta el programa en
directo (octubre de 2026), leido **en el propio codigo**, no en los resultados. Para que se midio
en cada caso y con que numeros, ver el README de cada carpeta y `CLAUDE.md`.

Los enlaces a lineas corresponden al estado del 2026-10-15; `stiv_directo.py` sigue cambiando y
sus numeros de linea se moveran.

## Que historial existe

- **No hay versiones formales** (v1, v2...) ni registro de cambios.
- **Git empezo el 2026-10-12.** Todos los casos anteriores entraron en el primer commit y tienen
  un solo commit cada uno: sus versiones intermedias no se conservaron.
- **Solo `analisis_kurome_directo_stiv/stiv_directo.py` tiene historial real** (5 commits, del 12
  al 14 de octubre).
- Las fechas de abajo son las de **modificacion de archivo**, que es lo unico que ordena los casos
  antiguos.
- Casi todos los casos STIV viven en la carpeta anidada `test_pyorc/test_pyorc/`, no en la raiz.

## Cronologia

| Fecha | Caso | Que aporta al metodo |
|---|---|---|
| 25 jul | `STIV_desde_cero.ipynb` | Tutorial: una linea de busqueda y un tensor de estructura. Aun usa pyorc para proyectar. |
| 28-31 jul | `analisis_USGS_SMC_stiv/` | Sin pyorc. DS derivado de la velocidad esperada (estrias a 45 grados). Tensor por bloques de 64x64 con mediana ponderada por coherencia. QC por coherencia >= 0.70. |
| 6-7 ago | `analisis_boneyard_stiv/` | Camara oblicua sin geometria (punto de fuga). Normalizacion temporal por posicion. QC por contraste temporal. Cuadrilatero manual (`stiv_interactivo.py`). |
| 10 ago | `analisis_hommerich_stiv/` | Geometria completa (`solvePnP` + distorsion), `remap` pixel a pixel, lineas recortadas a su tramo visible. |
| 12 ago | `analisis_bradano_stiv/` | Banda de lineas paralelas en vez de una sola. QC por brillo. |
| 12 ago | `analisis_arrow_stiv/` | Direccion de flujo por seccion, bloques pequenos (24 px), PIV independiente como arbitro. |
| 18 ago | `analisis_canal_riego_stiv/` | Top-hat contra la compresion, seleccion de bloques por senal, QC de densidad de trazador, segundo estimador (FFT), PTV como arbitro. Primer caso que importa codigo en vez de copiarlo. |
| 18-19 ago | experimentos del canal (`lejano`, `filtro_adaptado`, `completo`) | Regla DS >= 0.2 px de imagen, filtro adaptado, barras de error, tres estimadores. |
| 21 ago | `canal_stiv_puro`, `canal_seccion_completa` | Presentacion; ningun cambio de metodo. |
| 12-15 oct | `analisis_kurome_directo_stiv/stiv_directo.py` | Tiempo real. Mascara de actividad, cascada de 3 escalas temporales, modo noche, filtro direccional, presets por camara, Raspberry Pi. |

## El nucleo que no cambia

Desde el SMC hasta el directo la medida es la misma:

1. Se calcula el **tensor de estructura** sobre bloques de la STI con un 50 % de solape.
2. Cada bloque da una pendiente y una coherencia.
3. La pendiente de la estacion es la **mediana de las pendientes ponderada por coherencia**. Un
   tensor global dejaria que un parche brillante dictara la respuesta.

Aparece por primera vez como script en
[SMC video_velocidad.py:123-174](test_pyorc/analisis_USGS_SMC_stiv/video_velocidad.py#L123-L174) y
sigue siendo la misma idea en
[stiv_directo.py:525-571](analisis_kurome_directo_stiv/stiv_directo.py#L525-L571).

Todo lo demas son capas alrededor de ese nucleo, y cada capa nace de un caso concreto.

## Seis piezas que evolucionan

### 1. Preparacion de la STI antes de medir

| Caso | Que hace | Codigo |
|---|---|---|
| SMC | Resta la media de cada columna (fondo fijo) y de cada fila (parpadeo). Nada mas. | [preparar_sti](test_pyorc/analisis_USGS_SMC_stiv/video_velocidad.py#L177) |
| Boneyard | Ademas divide por la desviacion temporal de cada posicion: quita el reflejo del cielo, que es estatico. | [video_velocidad.py:252](test_pyorc/analisis_boneyard_stiv/video_velocidad.py#L252) |
| Bradano | Banda de lineas paralelas (24 px). Cada linea se normaliza antes de promediar, para que pesen igual. | [mapa_banda](test_pyorc/analisis_bradano_stiv/video_velocidad.py#L120) |
| Arrow | La misma banda, reducida a 6 px porque las verticales estan mas juntas. | [ANCHO_BANDA](test_pyorc/analisis_arrow_stiv/video_velocidad.py#L69) |
| Canal | Top-hat morfologico de 5 px: aisla los restos vegetales y borra los macrobloques de WhatsApp. Banda de 11 lineas. | [realzar](test_pyorc/analisis_canal_riego_stiv/stiv_canal.py#L290) |
| Directo | Junta todo: banda de 7 lineas y normalizacion por posicion de dia; de noche top-hat y resta de la mediana temporal; suavizado de 1 fila; filtro direccional opcional. | [construir_stis](analisis_kurome_directo_stiv/stiv_directo.py#L574), [top-hat](analisis_kurome_directo_stiv/stiv_directo.py#L477) |

### 2. Que bloques tienen derecho a votar

Es la evolucion mas clara del conjunto.

| Caso | Regla | Codigo |
|---|---|---|
| SMC, Hommerich, Bradano, Arrow | Votan todos los bloques con coherencia por encima de un umbral. | [medir_sti](test_pyorc/analisis_USGS_SMC_stiv/video_velocidad.py#L148) |
| Canal | Solo vota el 15 % de bloques mas brillantes (`CUANTIL_SENAL = 0.85`), los que contienen particula. Sin esa seleccion el fondo estatico gana por mayoria con pendiente 0. | [tensor_seleccion](test_pyorc/analisis_canal_riego_stiv/stiv_canal.py#L411) |
| Directo | Mascara de actividad pixel a pixel (`ACTIVIDAD_MIN = 0.5`) y bloques con al menos una fraccion activa (0.5 de dia, 0.1 de noche). Sin ella, el agua congelada por el codec de YouTube es una estela vertical de coherencia ~0.9 y la mediana devuelve 0.00. | [pendiente_tensor](analisis_kurome_directo_stiv/stiv_directo.py#L525) |

### 3. El estimador

| Caso | Implementacion | Codigo |
|---|---|---|
| SMC | Bucle Python por bloque, Sobel + `np.linalg.eigh`. Se copia casi literal a Hommerich, Bradano y Arrow. | [tensor_estructura](test_pyorc/analisis_USGS_SMC_stiv/video_velocidad.py#L123) |
| Boneyard | Vectorizado con `cv2.boxFilter`, angulo con `arctan2`, sin bucle. | [velocidad](test_pyorc/analisis_boneyard_stiv/video_velocidad.py#L134) |
| Canal | Vectorizado igual, mas un **segundo estimador** espectral (cresta de la FFT 2D) solo para diagnostico: si los dos coinciden, la pendiente esta en el dato y no en el estimador. | [cresta_fft](test_pyorc/analisis_canal_riego_stiv/stiv_canal.py#L456) |
| Directo | Scharr y sumas por celdas de medio bloque, mas rapido, pensado para la Raspberry Pi. La idea espectral del canal reaparece como filtro que anula lo que avanza aguas arriba. | [pendiente_tensor](analisis_kurome_directo_stiv/stiv_directo.py#L525), [filtro_direccional](analisis_kurome_directo_stiv/stiv_directo.py#L604) |

### 4. Control de calidad

Cada caso trajo un tipo de falso positivo nuevo, y el QC crecio para atraparlo.

| Caso | Criterio que se anade | Por que |
|---|---|---|
| SMC (notebook) | Coherencia >= 0.70 | Criterio inicial. |
| SMC (video) | `V_MAX_FISICA = 3 x V_ESPERADA` ([linea 89](test_pyorc/analisis_USGS_SMC_stiv/video_velocidad.py#L89)) | Una onda estacionaria daba ~7 m/s con coherencia > 0.70. |
| Boneyard | Contraste temporal >= 1.5 | Los muros dan coherencia 0.74-0.76 con v = 0 exacto. |
| Hommerich | Contraste temporal >= 3.0 + coherencia 0.60 | Hereda la leccion de Boneyard. |
| Bradano | Brillo <= 5.0 | La orilla de grava tiene **mas** contraste que el agua; el discriminador de Boneyard no sirve. |
| Canal | Densidad de trazador con dos umbrales (0.004-0.05). Los criterios se evaluan **por separado** y se devuelve la lista de motivos. | Agua con y sin trazador tienen el mismo brillo y contraste. Encadenar los criterios ocultaba cuantos atrapaban cada estacion. [motivos_rechazo](test_pyorc/analisis_canal_riego_stiv/stiv_canal.py#L496) |
| Directo | Motivos `lento`, `sin_textura`, `ambiguo`, `coherencia`, `fuera_de_campo`, `v_max`, `noche_no_valida` | Hereda el formato de lista de motivos del canal y lo amplia para el directo. [medir](analisis_kurome_directo_stiv/stiv_directo.py#L617) |

### 5. El tiempo

| Caso | Ventana |
|---|---|
| Notebooks | Una sola ventana sobre todo el video. |
| Scripts `video_velocidad.py` | Ventanas deslizantes; cada fotograma toma la medida de la ventana mas cercana. |
| Directo | Cascada de 3 escalas (10 s fotograma a fotograma, 30 s y 60 s promediadas, [ESCALAS](analisis_kurome_directo_stiv/stiv_directo.py#L234)). Cada estacion usa la primera escala en que la estela no es casi vertical, para no perder el agua lenta. |

### 6. Muestreo de la linea

| Caso | Como se obtienen las muestras |
|---|---|
| SMC | Linea inclinada sobre la imagen nadir; escala por dos filas leidas a mano. |
| Boneyard | Homografia por punto de fuga; despues cuadrilatero arrastrado a mano en `stiv_interactivo.py`. |
| Hommerich | `remap` pixel a pixel con distorsion de lente, raster alineado con la seccion, lineas recortadas a su tramo visible ([tramo_visible](test_pyorc/analisis_hommerich_stiv/video_velocidad.py#L328)). |
| Bradano / Arrow | Mapa de banda: un solo `cv2.remap` por fotograma resuelve todas las lineas de todas las estaciones. |
| Canal | Clase `Geometria` con horizonte por punto de fuga ([Geometria](test_pyorc/analisis_canal_riego_stiv/stiv_canal.py#L208)). |
| Directo | Clase `Geometria` con el cuadrilatero de Boneyard, editable en vivo ([Geometria](analisis_kurome_directo_stiv/stiv_directo.py#L412)). |

## Constantes del metodo por caso

| Caso | Bloque | Coherencia minima por estacion | QC principal | Banda |
|---|---|---|---|---|
| SMC | 64 | 0.70 | coherencia + v maxima | 1 linea |
| Boneyard | 48 | 0.40 | contraste >= 1.5 | 1 linea |
| Hommerich | 32 | 0.60 | contraste >= 3.0 | 1 linea |
| Bradano | 64 | 0.70 | brillo <= 5.0 | 24 px |
| Arrow | 24 | 0.70 | contraste >= 2.0 | 6 px |
| Canal | 64 | 0.60 | densidad 0.004-0.05 | 11 lineas |
| Directo | 48 | 0.40 | actividad >= 0.5 | 7 lineas |

## El fallo que aparece tres veces

La misma trampa reaparece con disfraz distinto, y cada vez el codigo responde con una pieza nueva.
Algo que no se mueve forma una estela vertical perfecta en la STI: **coherencia alta y velocidad
cero**. Un umbral de coherencia la deja pasar.

| Caso | Que era el "cero estatico" | Respuesta en el codigo |
|---|---|---|
| Boneyard | El muro del canal | QC por contraste temporal |
| Canal | El residuo del fondo tras el top-hat | Solo votan los bloques con particula |
| Directo | El agua que congela el codec de YouTube | Mascara de actividad por pixel |

El canal lejano muestra la version opuesta del mismo problema: coherencia 0.97-0.99 a 20 veces la
velocidad real por aliasing. De ahi la regla DS >= 0.2 px y la cascada de escalas del directo.

## No es una linea, es un arbol

En agosto hubo varias copias del metodo que evolucionaron por separado:

```
STIV_desde_cero.ipynb (25 jul)
 └─ SMC STIV (28-31 jul)  ── tensor en bucle, mediana ponderada
     ├─ Hommerich (10 ago) ─┐
     ├─ Bradano  (12 ago)  ─┼─ copian el tensor del SMC casi literal
     ├─ Arrow    (12 ago)  ─┘   ("Copia literal de la Parte 4 del notebook")
     ├─ Boneyard (6-7 ago) ──── tensor vectorizado propio, normalizacion por posicion
     │                          └─ cuadrilatero manual (stiv_interactivo.py)
     └─ Canal    (18 ago)  ──── tensor vectorizado + seleccion por senal + FFT
         └─ lejano / filtro_adaptado / completo / puro / seccion_completa
                                (importan el codigo del canal, no lo copian)

stiv_directo.py (12-15 oct) ── recoge piezas de todas las ramas
```

## Que hereda `stiv_directo.py` de cada caso

| Pieza en el directo | Viene de |
|---|---|
| Tensor por bloques con mediana ponderada por coherencia | SMC |
| DS ligado a la velocidad esperada | SMC |
| `V_MAX_FISICA` | Video del SMC |
| Normalizacion temporal por posicion | Boneyard |
| Cuadrilatero rectificado a mano | Boneyard (`stiv_interactivo.py`) |
| Cobertura minima de la linea (`fuera_de_campo`) | Boneyard (cobertura), Hommerich (tramo visible) |
| Banda de lineas normalizadas y promediadas | Bradano |
| Top-hat (modo noche) | Canal |
| Seleccion de bloques por senal, ahora como mascara de actividad | Canal |
| Lista de motivos de rechazo evaluados por separado | Canal |
| Filtro espectral (el directo lo usa para filtrar, el canal para diagnosticar) | Canal (`cresta_fft`) |
| Limite de muestreo y escalas lentas | Canal lejano (regla DS >= 0.2 px) |

## Organizacion del codigo

1. **Constantes duplicadas** entre notebook y script (SMC, Boneyard, Hommerich, Bradano, Arrow):
   cambiar una obliga a cambiar la otra.
2. **Imports en vez de copias** (canal y sus experimentos): `video_velocidad.py` y los
   experimentos importan geometria, realce, tensor y QC de `stiv_canal.py`.
3. **Un programa con presets** (`stiv_directo.py`): todo lo que depende de la camara esta en el
   diccionario `CAMARAS` o en `fuentes.json`, y el metodo es uno solo.

## Para versionar a partir de ahora

- Etiquetas de git en los hitos de `stiv_directo.py`.
- `validacion/regresion.py` ya reproduce grabaciones con el codigo actual; guardar su salida por
  version deja cada cambio medido y no solo descrito.
