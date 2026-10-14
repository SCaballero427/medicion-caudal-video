# Resumen cronológico del trabajo — medición de caudal a partir de video

Este documento recorre, en orden, todo lo hecho en esta carpeta: cómo empezó, qué algoritmos se
probaron, con qué variantes, qué se descartó y por qué, y cuánto tarda cada cosa.

**De dónde salen las fechas.** De la fecha de modificación de los archivos que siguen en la carpeta,
de las fechas que citan los propios documentos (`CLAUDE.md`, la *Comparativa* y la *Guía STIV*) y del
README de cada caso. Varias carpetas de análisis (Boneyard, Hommerich, Bradano, Arrow y los
experimentos del canal) **ya no están en este equipo**. Sus fechas se deducen de lo que las rodea y
van marcadas como *aprox.*

---

## 1. Línea de tiempo resumida

| Fecha | Hito |
|---|---|
| 12 jul | Instalación de pyorc y descarga del ejemplo oficial del río Ngwerere |
| 12–17 jul | Primer notebook exploratorio de Ngwerere con pyorc (LSPIV) y GIF animado de velocidades |
| 20 jul | Plantilla para Castor River (sin datos todavía); descarga del conjunto USGS del canal Sile Main Canal |
| 25 jul | **STIV implementado desde cero** como tutorial sobre Ngwerere |
| 26 jul | Primer intento con la aplicación RIVeR-STIV sobre un video GoPro (abandonado) |
| 27 jul | Herramientas de estabilización y conversión de video; medidor de recursos |
| 28–29 jul | RIVeR-STIV aplicado al canal USGS; reescritura de los notebooks SMC con la regla «la referencia se abre una sola vez» |
| 29 jul | Configuración compartida entre los notebooks LSPIV y STIV del canal USGS |
| 31 jul | Ejecución final del notebook pyorc del canal USGS; **documento comparativo de los tres métodos** |
| 1–6 ago *(aprox.)* | Caso Boneyard Creek: triaje de 61 videos, rectificación por punto de fuga, control de calidad por contraste |
| 6 ago | Herramienta interactiva de geometría para Boneyard; video de velocidad reescrito |
| 6–9 ago *(aprox.)* | Detección de nivel sobre la regla graduada (tres versiones) |
| 9 ago | **Guía «STIV y detección de nivel»** (documento Word) |
| 10 ago | Video de presentación de 38 s (canal + arroyo) |
| 10–16 ago *(aprox.)* | Casos Hommerich, Bradano y Arrow (experimento de sembrado) |
| 16 ago | Llega el video de WhatsApp del canal de riego |
| 16–21 ago | Canal de riego: caso base, árbitro PTV, experimento de alcance, filtro adaptado, modelo de sección completa |
| 21 ago | Videos «STIV puro» y «sección completa» del canal |
| 9 oct | Traslado del workspace a este equipo; informe de avances en Word; **STIV en tiempo real sobre cámaras en directo de Tokio** |
| 12 oct | Paquete de instalación para **Raspberry Pi 4B**; soporte de cámaras propias por RTSP; YouTube bloquea este PC |
| 12 oct | **Prueba en Docker**: Raspberry emulada (Debian 13 ARM64 con systemd y SSH) y cámara RTSP simulada; 4 fallos encontrados y corregidos |
| 12 oct | Repositorio privado en GitHub con todo el workspace |
| 13 oct | Prueba en Docker convertida en **banco de pruebas reutilizable** (`pruebas_docker/`): Pi falsa + servidor RTSP + cámara simulada, con un solo script |
| 13 oct | Directo de noche: **escalas de tiempo en cascada y modo noche**; ventana con **dos vistas** (directo y rectificada) |
| 13 oct | **`fuentes.json`**: menú y teclas para cambiar entre directos y videos; corregido el **sesgo por fotogramas duplicados** (hasta +26 %) |
| 13 oct | Burbujas junto al muro del Myoshoji medidas con el **reintento de motas** (9 de 9); ancho del Myoshoji medido en ortofoto (8.8 m) |
| 13 oct | Cámaras nuevas: **Shimoda** (con **filtro direccional** contra el aliasing estroboscópico) y **Akigawa** (añadida, no mide) |
| 13–14 oct | **Validación del programa en directo** con referencia: canal USGS (+1.2 % del aforo, sin estabilizar), Bradano y **Heiskanen** (cámara IP con ADCP, Finlandia) |
| 14 oct | Máscara de actividad al 10 % por bloque **de noche**: el programa mide trazador disperso (Bradano 1 → 5 de 7); de día se mantiene, porque aceptaba destellos del sol. Comprobado con una regresión sobre las grabaciones de los directos |

---

## 2. Fase 0 — Punto de partida: pyorc y el ejemplo de Ngwerere (12–20 jul)

**Objetivo inicial:** aprender a usar **pyorc** (pyOpenRiverCam), una librería de código abierto que
mide la velocidad del agua con **LSPIV** (velocimetría por imagen de partículas a gran escala) y
calcula el caudal sobre una sección transversal.

- Se creó un entorno Python 3.11 (`pyorc_env`) con pyorc 0.9.8. Se clonó también el repositorio
  oficial (`pyorc_repo/`) como referencia de solo lectura.
- Se descargó el **ejemplo oficial del río Ngwerere** (Zambia): un video de cámara fija oblicua, 4
  puntos de control medidos con GPS RTK y una sección transversal levantada en campo.
- `Notebook_Analisis_Ngwerere.ipynb` (24 celdas) reproduce el flujo de los tutoriales 02, 03 y 04 de
  pyorc. Pasos: lectura de video → puntos de control → reproyección → PIV con enmascarado de
  velocidades espurias → caudal sobre el transecto.
- Se generó `ngwerere/velocidad_animada.gif`, con el campo de velocidades animado sobre la imagen.
- Más tarde se ordenó en un notebook de pipeline formal en 6 partes, que sirvió de plantilla a todos
  los demás.

**Resultado:** **0.1672 m³/s frente a los 0.164 m³/s publicados (+1.9 %).**

**Decisión que se mantuvo:** la máscara de ángulo se calcula pero *no* se aplica. Así se reproduce el
valor publicado; aplicarla llevaría la mediana a ~0.174.

**Lo que se aprendió:**

- La reproducción exacta no es posible: pyorc estima la focal por optimización y la versión actual
  de `ffpiv` redondea la ventana de 25 a 26 px.
- En la versión 0.9.8, `get_piv` no es perezoso, al contrario de lo que dice su documentación: ahí se
  concentran el tiempo y la memoria.

**En paralelo (20 jul):**

- `Prueba_Castor_River.ipynb`: copia de la plantilla de Ngwerere preparada para el río Castor. Nunca
  llegó a ejecutarse: los datos estaban fuera de la carpeta.
- Descarga del conjunto USGS del **canal Sile Main Canal** (video 4K desde dron, sección del aforo,
  resultado PIVlab del propio USGS y aforo con ADV FlowTracker).

---

## 3. Fase 1 — STIV desde cero (25 jul)

`STIV_desde_cero.ipynb` (22 celdas) implementa **STIV** (*Space-Time Image Velocimetry*, Fujita
et al. 2007) sin librería de velocimetría, sobre el mismo video de Ngwerere, para contrastarlo con
el LSPIV de pyorc.

- **Idea:** se traza una línea en la dirección del flujo y se apilan los píxeles de esa línea en cada
  fotograma. Se forma así una imagen espacio-temporal (STI) en la que cada partícula deja una raya
  inclinada. La pendiente de la raya es la velocidad.
- **Estimador:** **tensor de estructura**. Es una matriz 2×2 de productos de gradientes; su
  autovector menor apunta a lo largo de las rayas. Además da gratis la **coherencia** (0–1), que
  indica si hay una dirección dominante o solo ruido.
- pyorc se usa aquí **solo** para la geometría (configuración de cámara, proyectar y desproyectar
  puntos), nunca para la velocidad.
- Tiene una celda final de validación cruzada contra el PIV de pyorc (`ngwerere_piv.nc`).

Este notebook es el origen de todo el STIV posterior.

---

## 4. Fase 2 — Canal Sile Main Canal con pyorc (26–31 jul)

Es el primer caso **con validación independiente**: un canal de hormigón de 1.83 m de ancho grabado
desde un dron, con un aforo ADV de **1.4362 m³/s** (incertidumbre declarada del 4.2 %).

### 4.1 Intento con RIVeR-STIV y video GoPro (26 jul) — abandonado

Se probó la aplicación de escritorio **RIVeR-STIV** con su ejemplo GoPro y se empezó un notebook que
adaptaba Ngwerere a ese caso. Se abandonó: de él solo quedan los puntos marcados con
`pixel_locator.py`. Los datos del ejemplo siguen dentro de `RIVeR-STIV_1.0/`.

### 4.2 Estabilización (27 jul)

El dron deriva **25.6 px** en 250 fotogramas, y ese movimiento se suma a la velocidad del agua. Hubo
que estabilizar.

| Variante | Temblor entre fotogramas | Notas |
|---|---|---|
| Video original | 0.50 px | — |
| `estabilizar_video.py` (funciones de pyorc, encadenado fotograma a fotograma) | 0.10 px (×4.9) | ~110 s |
| `estabilizar_stiv.py` (solo OpenCV, cada fotograma contra el fotograma 0) | **0.02 px (×27)** | ~135 s; el error no se acumula |

**Códec del video intermedio:**

- **mp4v se descartó:** mete 2.1 niveles de gris de error, un 10 % del contraste del trazador.
- **Se eligió FFV1 sin pérdida:** 1.1 GB, relectura idéntica bit a bit.
- `convertir_a_mp4.py` genera copias ligeras **solo para mirar**.

**Detalle técnico:** en este entorno OpenCV no puede escribir H.264, así que se usa mp4v como
alternativa para las copias de visualización.

### 4.3 Notebook pyorc del canal y su evolución

- **Primera versión:**
  - Escala tomada de las filas 436/1480 de la imagen.
  - Sección regenerada cada 0.1524 m.
  - Un **barrido de `v_corr`** (0.85 / 0.90 / 0.95 / 1.00) que imprimía la distancia de cada valor
    al aforo.
- **Reescritura (29 jul):**
  - El barrido se **eliminó**, por ser ajuste contra la referencia.
  - Todos los valores se fijan a priori y el aforo solo aparece en la Parte 7, una vez, al final.
  - Las constantes ajustables se agrupan en un recuadro `>>> AJUSTABLE <<<` en cada parte.
- **Configuración compartida con STIV (29 jul):** misma escala (filas 438/1466 → 1.7790 mm/px), misma
  sección leída del CSV (1.8026 m²), mismas columnas, mismos 250 fotogramas y mismo coeficiente
  α = 0.92. Así la comparación mide el algoritmo y no la configuración.
- **Problema detectado:** la fila de agua inferior figuraba como **1520**, que es el borde inferior de
  la sombra del muro y cuesta un 5–8 % de escala. Se corrigió a 1466. Dos comprobaciones
  independientes sitúan el borde real cerca de la fila 1430; queda como cuestión abierta.

**Evolución del resultado:**

| Versión | Caudal | Error |
|---|---|---|
| Con error de escala (documento comparativo) | 1.5352 m³/s | +6.9 % |
| Con la configuración compartida | 1.4507–1.4565 m³/s | **+1.0 a +1.4 %** |

### 4.4 RIVeR-STIV sobre el mismo canal (28–29 jul)

Se procesó el video del canal con RIVeR como tercer método.

- **Resultado:** 1.4293 m³/s (−0.5 %).
- **Problema:** el perfil oscila entre 0.72 y 1.66 m/s, algo que no es físico en un canal recto. El
  total acierta por compensación de errores.

### 4.5 Medición de recursos

`benchmark.py` registra tiempo, CPU y memoria por etapa en cada ejecución (ver la sección 14).

---

## 5. Fase 3 — STIV propio sobre el canal USGS (28–31 jul)

El mismo video y la misma referencia, pero con STIV escrito sobre OpenCV y **sin pyorc**.

### Variantes probadas

| Aspecto | Probado | Resultado / decisión |
|---|---|---|
| Paso de muestreo `DS` | 1 px por muestra | Rayas a 87°: el error angular pesa 19× más |
| | Derivado de la velocidad esperada (`DS = v·Δt/escala`) ≈ 18 px | **Elegido**: rayas a ~45°, donde el error es mínimo; poco sensible a fallar la estimación un 30 % |
| Filtro antialias | Solo a lo largo de la línea | Coherencia 0.97 → 0.87: peor |
| | Isotrópico, σ = DS/2 | **Elegido**: además suaviza la turbulencia pequeña |
| Preparación de la STI | Cruda | Pendiente 49.9 (verdad 1.0) |
| | Restar media temporal | 159: mide el parpadeo |
| | Restar media temporal y espacial | **1.03: correcto** |
| Estimador | Tensor global sobre toda la STI | Con un reflejo fijo devuelve −89 % de error **con coherencia 0.74** |
| | Bloques de 64×64 con 50 % de solape y mediana ponderada por coherencia | **Elegido**: −0.06 % |
| Detectores automáticos | Línea de agua por movimiento, ángulo de flujo por máxima coherencia, validación sintética de `DS` | **Eliminados** por sobreajustados a un solo video. Sus valores (438/1466, −1.0°, DS 18) quedaron como constantes |
| Relleno de verticales rechazadas | Ley logarítmica de pared (`K_S = 1 mm`) | 1.3168 m³/s (−8.3 %). Eliminada como maquinaria innecesaria |
| | Interpolación lineal | **Elegida** (un solo `np.interp`, sin parámetros) |
| Umbral de calidad | Coherencia ≥ 0.70 | Rechaza siempre las verticales 1 y 11, pegadas a los muros. La 11 medía 1.34–1.40 m/s, más que el centro |

### Evolución del resultado

| Versión | Caudal | Error |
|---|---|---|
| Primera | 1.2009 m³/s | −16.4 % |
| α = 0.85 y relleno lineal apoyado en los ceros de los muros | 1.2221 m³/s | −14.9 % |
| Fila de agua inferior corregida (1520 → 1463/1466), α = 0.92 y relleno sin apoyarse en los ceros | **1.4475 m³/s** | **+0.8 %** |

### Comparativa final de los tres métodos (`Comparativa_metodos_USGS_SMC.docx`, 31 jul)

| Método | Caudal | Error | Sesgo por vertical | RMSE por vertical | Tiempo / memoria |
|---|---|---|---|---|---|
| STIV propio | 1.4475 | +0.8 % | −0.5 % | **0.054 m/s** | 38 s / 0.87 GB |
| pyorc LSPIV | 1.5352* | +6.9 %* | +5.4 % | 0.056 m/s | 158 s / 15.3 GB |
| RIVeR-STIV | 1.4293 | −0.5 % | +0.7 % | 0.278 m/s | no medido |

\* Valor de ese documento. Tras corregir la escala, pyorc queda en +1.0 a +1.4 %.

**Conclusión de esa etapa:** el STIV propio es el más equilibrado. RIVeR acierta el total sin
acertar el perfil, y pyorc es igual de estable pero arrastraba un error de escala.

### Extensión a todo el video: `video_velocidad.py`

Repite el STIV en ventanas deslizantes de 150 fotogramas sobre los **672 fotogramas (22 s)**. Dibuja
el video original con flechas y el caudal en vivo, sin video intermedio: la estabilización se aplica
como cambio de coordenadas.

- **Problema nuevo:** con ventanas cortas, la vertical 11 dio dos veces ~7 m/s *con coherencia alta*
  (una onda estacionaria). Se añadió una cota física `V_MAX = 3 × velocidad esperada`, que actuó en
  2 de 1155 medidas.
- **Resultado:** **1.4493 m³/s de mediana** (1.403–1.489), a un 0.1 % de la medida sobre los primeros
  8 s.

---

## 6. Fase 4 — Boneyard Creek: cámara oblicua sin geometría, y nivel (1–9 ago, aprox.)

Una cámara IP fija del USGS. Se publican 61 videos con su caudal y su nivel, **pero ni una distancia,
ni sección, ni calibración.**

### 6.1 Triaje

Se clasificaron los 61 videos por brillo, saturación y nitidez. **11 son nocturnos** (infrarrojo,
desenfocados, gotas en la lente) y no se pueden usar. Entre ellos están los dos caudales más altos
(446 y 470 cfs).

### 6.2 Geometría: variantes probadas

| Variante | Resultado |
|---|---|
| Punto de fuga de las hiladas de los muros + horizonte (RANSAC con los dos muros) | **Usado**: velocidad correcta salvo una constante → unidades de «alturas de cámara/s» |
| Punto de fuga vertical para medir el giro de la cámara | Falló (los bordes «verticales» eran piedras irregulares) → se supone giro nulo |
| Corrección de distorsión barriendo k1 | Falló: la métrica premiaba una sobrecorrección absurda (k1 = −0.38) → descartada |
| Estabilización | No hacía falta: medido 0.02–0.06 px de temblor |
| **Editor interactivo** `stiv_interactivo.py` (6 ago): se arrastran 4 esquinas de un rectángulo real sobre el agua con el video corriendo | Sustituye al punto de fuga, que se juzgó erróneo; da m/s con un ancho supuesto de ~6 m. La ventana interactiva no se ha probado con una persona |

### 6.3 Control de calidad: la lección del caso

Las estaciones que caen sobre los muros daban **coherencia 0.74–0.76 con velocidad exactamente 0**:
una estructura quieta es una raya perfecta. **Un filtro de coherencia las aprueba.**

Se añadió un filtro de **contraste temporal**: muro ≤ 0.94 frente a agua ≥ 4.56, un hueco de factor 5.
Las estaciones rechazadas **no se rellenan**, porque no hay sección.

### 6.4 Resultados

- **Velocidad:** **0.2427 alturas de cámara/s** con 15 de 21 estaciones. Sobre el video entero,
  0.2428.
- **Video de velocidad:** rehecho el 6 ago para reproducirse a tiempo real, con dos paneles (original
  y rectificado).

### 6.5 Detección de nivel (6–9 ago, aprox.)

Es un segundo algoritmo, independiente del de velocidad. Lee el nivel sobre la **regla graduada**
del muro.

| Versión | Qué hace | Resultado |
|---|---|---|
| `velocidad_nivel.py` | Línea recta sobre la regla; busca el cruce al 50 % entre «seca» y «agua» con interpolación subpíxel | 10 lecturas rechazadas por salpicaduras |
| `velocidad_nivel_chapa.py` | Regla rectificada con un cuadrilátero | 0 rechazos |
| `velocidad_nivel_curva.py` | Bandas de lados curvos (Bézier), porque la lente de ojo de pez curva la regla | Las graduaciones salen horizontales |
| Contar marcas visibles (probado) | — | **Descartado**: fluctúa 6× más que la señal |

**Resultado:** nivel detectado en **929 de 929 fotogramas**, con una desviación de 0.60 px, que es la
oscilación real del agua. El periodo de las graduaciones se mide por autocorrelación (5.37 px por
marca).

### 6.6 Documentación (9 ago)

`Guia_STIV_y_deteccion_de_nivel.docx` explica desde cero el método, el código y la configuración.

---

## 7. Fase 5 — Video de presentación (10 ago)

`video_ejecutivo/montar_demo.py` monta una pieza de **38 s** en tres bloques: portada, canal y arroyo.

- Rotulado numerado y recorte de la información técnica de los clips.
- Los puntos de referencia se leen de la configuración real, no se escriben a mano.
- `--previo` genera los PNG de revisión sin codificar el video.

---

## 8. Fase 6 — Tres conjuntos de datos más: Hommerich, Bradano y Arrow (10–16 ago, aprox.)

### 8.1 Hommerich (río Geul, Países Bajos) — cámara oblicua con calibración completa

- **Datos:** cámara calibrada con distorsión fuerte (k1 = −0.485) y 6 puntos de control RTK.
- **Geometría:** pose por `solvePnP`, con un error de 0.56 px. Rectificación **píxel a píxel con
  `remap`** (no con homografía), para poder corregir la lente.
- **Variante probada:** sección en su posición original frente a sección desplazada 2.5 m aguas
  abajo. En la posición original, cuatro verticales veían solo el 42–75 % de su línea. Desplazada, el
  caudal pasa de 12.94 a 13.68 m³/s.
- **Resultado:** 13 de 16 verticales, **v = 0.943 m/s, Q = 13.68 m³/s** (13.33–13.99). **No hay
  referencia publicada** para validarlo.

### 8.2 Bradano (Italia) — video ya rectificado, agua casi negra

- **Variante probada:** una sola línea frente a una **banda de 7 líneas** (24 px). La coherencia pasa
  de 0.47–0.80 a 0.76–0.94.
- **Control de calidad:** el contraste temporal de Boneyard **no funciona aquí**, porque la grava de
  la orilla tiene más contraste que el agua. Se usa el brillo (factor 30 entre orilla y agua).
- **Resultado:** **5 de 7 verticales de referencia, sesgo −3.1 %, correlación 0.996**.

### 8.3 Arrow (Reino Unido) — experimento de sembrado

Dos videos idénticos, uno con trazadores y otro sin ellos, procesados con la **misma configuración**.

- **Sin trazadores:** 0 de 49 estaciones medidas.
- **Nueve variantes probadas sobre el video sin trazadores:**
  - DS = 1;
  - bandas de 30 y 60 px;
  - filtro paso alto;
  - una STI por sección entera;
  - todas combinadas.

  **Todas dan 0 de 49.**
- **Explicación física (curva de decorrelación):** el patrón sembrado dura ~1 s; el no sembrado no
  existe ni entre dos fotogramas consecutivos.
- **Con trazadores:** media 0.389 frente a 0.417 m/s (−6.7 %).
- **Árbitro:** un PIV independiente coincide con el STIV a 3 cm/s (r = 0.974). La discrepancia de
  perfil con la referencia apunta a la referencia, no al método.

---

## 9. Fase 7 — Canal de riego grabado con WhatsApp (16–21 ago)

Es el caso con menos información: 81 s a mano desde una alcantarilla, 1024×576 a 661 kb/s, sin
ninguna medida de campo.

### 9.1 Caso base: `stiv_canal.py`

| Problema | Variante probada | Resultado |
|---|---|---|
| La compresión borra la textura y deja bloques fijos | Filtro **top-hat** de 5 px (aísla restos de 2–4 px) | **Hace medible el video** |
| La mayoría de bloques de la STI no tiene partículas | Mediana ponderada clásica | 0.000 en las 15 estaciones |
| | Mediana sobre el 15 % de bloques con más señal | **Elegida** (medido: un 11–21 % de bloques tiene partícula) |
| Ancho de la banda | 3, 11 y 21 líneas | **11 líneas** (con 3, sesgo errático; con 21, nada mejora) |
| Control de calidad | Brillo o contraste (Bradano, Boneyard) | No discriminan |
| | **Densidad de trazador con dos umbrales** | Elegida. El umbral superior impide medir el hormigón mojado |
| Estimador | Tensor y cresta FFT, validados en sintético (1.300 → 1.275 y 1.297) | Tensor como principal, FFT como diagnóstico |
| Focal supuesta (WhatsApp borra el EXIF) | Barrido entre 600 y 1000 px | La velocidad varía +52 %; **±9 % con lentes realistas**: es la mayor incertidumbre |

**Resultado:** **6 de 15 estaciones** (tercio derecho del canal), mediana **0.0590 alturas de
cámara/s**.

**Árbitro:** `ptv_arbitro.py` (seguimiento de partículas) construye 562 trayectorias.
**Correlación 0.984**, sesgo +13 %.

**Video:** 138 ventanas; la mediana coincide al 1.4 %.

### 9.2 Experimento de alcance: `analisis_canal_lejano_stiv/`

¿Hasta dónde mide el método? Se probaron tres bandas de distancia:

| Banda | Paso de muestreo | Resultado |
|---|---|---|
| Cerca | 0.23–0.33 px | **Correcto**, 6 de 6 |
| Media | 0.08 px | Valores erráticos; en video, 20 de 828 ventanas pasan todos los filtros con un valor falso |
| Lejos | 0.04 px | **20× la velocidad real con coherencia 0.97–0.99** |

**Pruebas:**

- **Decimación temporal:** con 1 de cada 20 fotogramas, la «velocidad» lejana se desploma y cambia
  de signo. Era aliasing, no celeridad de ondas.
- **Correlación de conjunto:** un segundo algoritmo confirma que lejos no hay señal.

**Regla obtenida:** el paso de muestreo tiene que ser **≥ 0.2 px de imagen**.

### 9.3 Filtro adaptado: `analisis_canal_filtro_adaptado/`

Último intento sobre la zona lejana: integración coherente sobre toda la ventana (*track-before-
detect*).

- **Veredicto:** lejos no hay nada. Ahora el resultado negativo está respaldado por controles
  sintéticos y reales.
- **Hallazgo:** lo que borra el trazador es la **resolución, no la compresión**. Reducir sin
  comprimir ya pierde ×111; la compresión añade solo ×1.8.
- **Errores encontrados por los controles:**
  - desplazamiento circular de Fourier;
  - tiempos de integración desiguales;
  - promediar proyecciones en vez de puntuaciones;
  - pico buscado sobre la puntuación cruda;
  - un reescalado olvidado que daba ceros «perfectos».
- **Hipótesis descartada:** la curtosis como discriminador. La validación sintética la contradijo.

### 9.4 Sección completa con modelo: `analisis_canal_completo_stiv/`

- **STIV mejorado** (29 estaciones):
  - barras de error por estación;
  - tres estimadores;
  - prueba de banda ancha: ensancharla hacia el agua sin trazador **es peligroso**, porque mide a las
    vecinas.
- **Modelo Shiono-Knight** ajustado al tercio medido:
  - Con la pared rígida, χ²red = 1.95. Con borde hidráulico libre, **0.52**: el agua deja de moverse
    un 6 % antes de la orilla visible.
  - **Quedarse solo con lo medido sobrestima la velocidad media un 12 %.**
- **Video:** partículas virtuales en azul y restos reales en amarillo.

### 9.5 Dos presentaciones del canal (21 ago)

| Video | Qué muestra |
|---|---|
| `analisis_canal_stiv_puro/` → `stiv_puro.mp4` | **Solo lo medido**: flechas donde hay medida, huecos donde no, y la STI de cada estación con su pendiente |
| `analisis_canal_seccion_completa/` → `seccion_completa.mp4` | **Flechas en las 15 estaciones**: 6 medidas y 9 deducidas del modelo, dibujadas igual (sin aviso en pantalla, a petición). El CSV y el README indican cuáles son cuáles |

---

## 10. Fase 8 — Traslado y documentación (9 oct)

- El workspace se copió a este equipo. **Faltan aquí** las carpetas de Ngwerere (pipeline), SMC
  STIV, Boneyard, Hommerich, Bradano, Arrow y los experimentos del canal, así como los datos
  externos. `pyorc_env` llegó incompleto (sin `Scripts\`).
- Se redactó `Informe_avances_medicion_caudal.docx`: 12 páginas, sin fechas, para presentar.

---

## 11. Fase 9 — STIV en tiempo real sobre cámaras en directo (9 oct)

`analisis_kurome_directo_stiv/stiv_directo.py` aplica el mismo STIV **en directo** a cámaras de
vigilancia de ríos de Tokio en YouTube. Tiene su propio entorno `.venv`, porque `pyorc_env` no
funciona en este equipo.

- **Cómo funciona:** resuelve el flujo con yt-dlp; 9 líneas de búsqueda; STI deslizante de 10 s;
  medida cada segundo en un hilo aparte (~140 ms).
- **Interfaz:** ventana con el directo, las flechas y la STI de cada estación. El cuadrilátero se
  puede editar en vivo.
- **Problemas resueltos:**
  - Las cámaras emiten a 15 fps y YouTube duplica cada fotograma. Deduplicar por contenido perdía
    fotogramas reales, así que se usa la rejilla de tiempos sin deduplicar (validado en sintético).
  - **El códec congela el agua lisa:** da rayas verticales perfectas a 0.00 m/s, y la primera
    versión las aceptaba. Se resolvió con un **filtro de actividad entre fotogramas reales**: agua
    congelada 0.00, agua con textura 0.7–5.6, umbral 0.5.
  - Coherencia mínima de 0.40, elegida con datos nocturnos en infrarrojo.

**Resultados, con escala supuesta (no validados):**

| Cámara | Condición | Estaciones aceptadas | Velocidad mediana |
|---|---|---|---|
| Myoshoji (por defecto) | Día | 6 de 9 | **0.45 m/s** |
| Kurome | Noche, infrarrojo | 3 de 9 (las del rápido central) | 0.55–0.74 m/s |

---

## 12. Fase 10 — Raspberry Pi, prueba en Docker y repositorio (12–13 oct)

### 12.1 Paquete para Raspberry Pi 4B

El objetivo es que el STIV en directo mida solo, sin pantalla, desde que la Raspberry se enciende,
con una cámara propia. Todo está en `analisis_kurome_directo_stiv/raspberry/`, con una guía paso a
paso en `LEEME.md` pensada para quien no ha usado nunca una Raspberry.

| Pieza | Dónde se ejecuta | Qué hace |
|---|---|---|
| `subir_a_raspberry.bat` / `.ps1` | PC | Empaqueta el código y las configuraciones de cámara, los copia a la Pi por SSH y la instala o actualiza (`-SinInstalar`, `-ConfigurarLlave`, `-SobrescribirConfig`) |
| `traer_resultados.bat` / `.ps1` | PC | Trae a `salidas_raspberry\` el CSV, la imagen anotada y las configuraciones |
| `instalar.sh` | Pi | Instalación repetible: paquetes del sistema, entorno Python con OpenCV sin pantalla, servicio |
| `stiv.sh` | Pi | Órdenes del día a día: `prueba`, `activar`, `estado`, `registro`, `medidas`, `salud`… |
| `stiv.service` + `stiv.conf` | Pi | Servicio systemd que lo arranca al encender y lo relanza si se cae |
| `prueba/myoshoji_20s.mp4` | Pi | 20 s de video para probar sin cámara ni internet (sirve para funcionamiento y velocidad, no para medir) |

**Cambios en `stiv_directo.py`:**

- `--fuente` admite cualquier URL, incluidas cámaras **Hikvision por RTSP** (sobre TCP, con 15 s de
  espera y reconexión automática).
- `--camara` acepta nombres nuevos; su configuración (URL incluida) vive en su JSON.
- `--paso-medida` y `--vista-cada`, pensados para funcionar sin pantalla.
- `STIV_COOKIES`, para cuando YouTube responde «confirma que no eres un bot» (le pasó a este PC
  el 12 oct).
- Gris y suavizado calculados solo sobre el recuadro que tocan las líneas: **6–8× más barato** y
  resultado idéntico bit a bit (de 4–9 ms a 1–2 ms por fotograma).
- Cola de fotogramas reducida de 600 a 150.

### 12.2 Prueba en Docker: una Raspberry emulada

Como todavía no hay Raspberry física ni cámara, el paquete se probó en una **Raspberry Pi falsa
montada con Docker**. Primero se hizo a mano (12 oct). Después se dejó como un **banco de pruebas
reutilizable** en `analisis_kurome_directo_stiv/pruebas_docker/` (13 oct), que cualquiera puede volver
a levantar con un doble clic, con Docker Desktop abierto.

**Archivos del banco de pruebas:**

| Archivo | Qué es |
|---|---|
| `pi_falsa/Dockerfile` | La imagen de la Pi falsa: **Debian 13 (trixie) para ARM de 64 bits** con systemd como proceso principal, SSH, `sudo` y Python 3, y un usuario `stiv`, como en Raspberry Pi OS |
| `docker-compose.yml` | Los tres contenedores del banco (grupo `stiv-pruebas`) y cómo se conectan |
| `probar_en_docker.ps1` / `.bat` | Lo levanta todo, instala el paquete con el **mismo script que se usará con la Pi real** y ejecuta la prueba |
| `.llave/` | Llave SSH solo para las pruebas, creada por el script, para no tocar la carpeta `.ssh` del usuario |
| `LEEME.md` | Guía de uso y lista de lo que la Pi falsa no reproduce |

**Contenedores que levanta:**

| Contenedor | Qué simula | Acceso |
|---|---|---|
| `stiv-pi-falsa` | La Raspberry: Debian ARM64 emulado con QEMU, nombre de equipo `stiv-rio` | SSH en `localhost:2222` |
| `stiv-rtsp-srv` | Servidor RTSP (mediamtx), el «enchufe» de una cámara IP | `rtsp://localhost:8554/camara` desde el PC; `rtsp://stiv-rtsp-srv:8554/camara` desde la Pi falsa |
| `stiv-rtsp-pub` | La **cámara simulada**: ffmpeg emite en bucle el video de prueba de 20 s en H.264 por RTSP | `docker stop` / `docker start` simulan un corte de cámara |

**Cómo se usa** (`probar_en_docker.bat` con opciones):

| Opción | Efecto |
|---|---|
| sin opciones | Levanta los contenedores, espera a systemd, copia la llave, instala el paquete (~8 min emulado) y ejecuta `stiv.sh prueba` |
| `-SinInstalar` | Solo sube el código nuevo y repite la prueba |
| `-SoloLevantar` | Levanta los contenedores sin tocar nada más |
| `-Parar` / `-Arrancar` | Desactiva o reactiva los contenedores **sin perder lo instalado** (lo recomendado al terminar) |
| `-Bajar` (`-BorrarImagenes`) | Los borra; la Pi falsa pierde lo instalado (y además se liberan ~1 GB de imágenes) |

**Decisiones de diseño:**

- **Se usan los scripts reales.** `subir_a_raspberry.ps1` recibe `-Equipo localhost -Puerto 2222` y
  sus opciones SSH, así que lo que se prueba es exactamente lo que se usará con la placa.
- **systemd de verdad dentro del contenedor** (`privileged`, cgroups del anfitrión, `/run` en tmpfs).
  Así se puede probar el servicio y el arranque automático: `docker restart stiv-pi-falsa` hace de
  «apagar y encender».
- **`sudo` no pide contraseña en la Pi falsa**, para que la prueba corra sin nadie delante. En la Pi
  real sí la pide, y por eso el script de subida usa `ssh -t`.
- **Al pararla, Docker la corta a la fuerza** (código 137): emulado, systemd no atiende la señal de
  apagado. No se pierde nada. En la Pi real se apaga con `sudo shutdown now`.
- **El video de prueba viene de YouTube** y lleva fotogramas duplicados. Para medirlo como cámara
  RTSP hay que poner `FPS_CAMARA: 15.0`; una cámara IP real lleva `null`.

**Resultados de la prueba:**

| Prueba | Resultado |
|---|---|
| Instalación desde cero (paquetes del sistema, entorno Python, OpenCV 5.0 sin pantalla, numpy 2.5, servicio) | Correcta, **~8 min** emulada |
| `stiv.sh prueba` con el video incluido | **Mismos números que en el PC** |
| Activar el servicio y reiniciar el contenedor | El servicio **arranca solo** |
| Actualizar solo el código (`-SinInstalar`) | **6 s**, sin pisar la configuración de la Pi |
| `traer_resultados.ps1` | Trae CSV, imagen y configuraciones |
| **Cámara RTSP simulada**: servidor mediamtx emitiendo el video en H.264, conectado como cámara nueva | Mide; configurada después solo con su JSON |
| Corte de la emisión RTSP durante 8 s | **Reconecta solo** y vuelve a medir a los 10 s (lo que tarda en llenarse la STI) |

**Fallos reales que encontró la prueba (todos corregidos):**

1. Una función de PowerShell llamada `Ssh` se llamaba a sí misma en bucle (PowerShell no distingue
   mayúsculas de minúsculas en los nombres).
2. `cv2.destroyAllWindows()` falla en OpenCV sin pantalla.
3. Tras una reconexión el tiempo del flujo volvía a 0 y no se medía nada hasta superar el tiempo de
   antes del corte. Ahora cualquier discontinuidad (reconexión, tiempo que retrocede, salto de más de
   1 s) vacía la STI y **re-ancla el reloj**.
4. La cola de 600 fotogramas llevaba la memoria a **1.3 GB**. Con 150 queda en **~626 MB**, que cabe
   con holgura en una Pi de 4 GB.

**Lo que la emulación no puede decir** (pendiente de la Raspberry real):

- La velocidad real de una Pi 4B: la emulación no informa de eso. En el PC son 1–2 ms por fotograma
  y ~0.5 s por medida; es lo primero que mide `stiv.sh prueba` en la Pi.
- El registro con `journalctl` (no funciona en el contenedor, así que `stiv.sh registro` no muestra
  nada), la temperatura (`vcgencmd` no existe), el nombre `stiv-rio.local` (no hay mDNS, se entra por
  `localhost:2222`), la contraseña de `sudo` a través de SSH y `-ConfigurarLlave`.
- Una cámara Hikvision real. Además, `ACTIVIDAD_MIN` se midió sobre el códec de YouTube y habrá que
  volver a medirlo con esa cámara.

### 12.3 Repositorio en GitHub

Todo el workspace se guardó en un repositorio privado
(`github.com/SCaballero427/medicion-caudal-video`), incluidos los entornos, los binarios y los datos.
El video estabilizado de 1.1 GB va por Git LFS, porque supera el límite de 100 MB de GitHub.

---

## 13. Fase 11 — Cámaras en directo: noche, dos vistas, varias fuentes y cámaras nuevas (13 oct)

Todo en `analisis_kurome_directo_stiv/stiv_directo.py`. Cada cambio se probó sobre **grabaciones sin
pérdida de los propios directos** (FFV1, 60–200 s), no solo en directo, para poder repetir la misma
prueba con y sin el cambio. Las pruebas se hicieron en una copia aparte, para no mezclar sus
medidas con las del usuario.

### 13.1 De noche no detectaba movimiento

**Síntoma:** de noche el Myoshoji no medía ninguna estación, aunque a simple vista se veían basura
y burbujas avanzando.

**Diagnóstico:** de noche el agua iba unas **10 veces más despacio** que de día: ~0.05 m/s, es decir
**0.1 px por fotograma real**. Se confirmó con una correlación de conjunto a desfases largos, sin
STIV. Con el STI de 10 s fotograma a fotograma:

- las estelas salían casi verticales;
- la actividad entre fotogramas era 0, y todo quedaba como «sin textura»;
- los destellos de las farolas sobre las ondas daban falsos 5–11 m/s.

**Ajustes:**

- **Tres escalas de tiempo en cascada:** 10 s fotograma a fotograma, 30 s con filas cada 0.133 s y
  60 s con filas cada 0.5 s. Las filas lentas son promedios, que hacen de antialias temporal.
  - Cada estación usa la **primera** escala cuya pendiente sea de al menos 0.3 muestras por fila.
  - En las escalas lentas, una pendiente mayor de 2.5 se rechaza como «ambiguo»: es agua rápida
    que esa escala no puede resolver.
  - La elección es por el ángulo de la estela, nunca por la coherencia.
- **Modo noche automático:** se activa cuando la cámara pasa a infrarrojo, con saturación exactamente
  0. Aplica tres pasos:
  - un top-hat de 9 px, que deja solo las motas brillantes;
  - resta la mediana temporal de cada posición, para quitar lo que no se mueve;
  - **excluye los reflejos de farola**: posiciones con brillo mediano mayor de 60 (el agua da 4–41
    y las farolas 59–255).

**Resultado:**

- **De día no cambia nada:** el clip de prueba da los mismos números y todas las estaciones se miden
  en la escala rápida.
- **De noche, en directo:** 5–6 de 9 estaciones desde t = 30 s, mediana **0.056–0.067 m/s**, casi
  todas en la escala de 30 s.
- Se añadió el clip nocturno `raspberry/prueba/myoshoji_noche_90s.mp4` (orden `stiv.sh
  prueba-noche`).
- El clip de día está guardado en gris, así que hay que forzar `--modo dia` con él.

### 13.2 Dos vistas en la ventana

**Ajustes:**

- La ventana muestra el directo y la **vista rectificada en planta**, una junto a la otra. En la
  vista rectificada el flujo va de izquierda a derecha y hay una barra de 1 m.
- Las dos vistas llevan las líneas, las flechas y los valores.
- La duración de las flechas se adapta (entre 2 y 60 s de recorrido) para que la flecha mediana
  mida ~1 m. Con agua a 0.05 m/s, una flecha de 2 s medía 10 cm y no se veía.

### 13.3 Cambiar entre directos y videos

**Ajustes:**

- **`fuentes.json`** guarda la lista de fuentes. Cada entrada lleva:
  - título y cámara;
  - `url` (directo) o `archivo` (video grabado);
  - `modo`, opcional, `auto` por defecto;
  - `ajustes`, opcional, para cambiar valores por cámara.
- **Menú en la consola:** `arrancar.bat` sin argumentos lo muestra (`--elegir`).
- **Teclas en la ventana:** `c` pasa a la siguiente fuente y `1`–`9` van a una concreta. Cada fuente
  escribe en su carpeta; si la nueva no abre, se vuelve a la anterior.
- Sin `fuentes.json`, por ejemplo en la Raspberry, la lista son las cámaras definidas en el código.

**Prueba:** se simularon las pulsaciones de teclas, pasando por cuatro fuentes con la ventana
abierta. Al cambiar, los hilos de lectura y de medida se cierran y no se acumulan.

**Fallos encontrados:**

- El clip nocturno heredaba el `--modo dia` de la línea de comandos. Ahora una entrada sin `modo`
  usa siempre `auto`.
- Con el CSV abierto en Excel, el programa abortaba al arrancar (`PermissionError` al apartar el CSV
  de columnas antiguas). Ahora escribe en un CSV con fecha y avisa.

### 13.4 Fotogramas duplicados: un sesgo de hasta el 26 %

**Diagnóstico:** YouTube repite cada fotograma de la cámara (15 fps convertidos en 30), y el STI rápido
se construía con todos. Con duplicados el STI es una escalera, y el tensor sobreestima en cuanto la
estela avanza más de ~1.5 muestras por fila. Se probó con un STI sintético de pendiente conocida:

| Pendiente real | Sin duplicados | Con duplicados |
|---|---|---|
| 1.0 | 1.000 | 1.000 |
| 2.0 | 2.015 | **2.136 (+7 %)** |
| 2.5 | 2.524 | **3.154 (+26 %, coherencia 0.54)** |
| 3.0 | 3.030 | **5.555** |

**Ajuste:** el STI rápido usa **una fila por fotograma real**, el promedio de cada par de duplicados.
DS se duplica y queda más lejos del límite de aliasing (Myoshoji: de 0.32 a 0.65 px).

**Resultado:**

- **Kurome de día:** pasa de ~0.94 a ~0.85 m/s; antes salía inflado un 10–20 %. Una correlación
  independiente da 0.72–1.0 m/s en las estaciones 5–8. En las 1–2 el STIV queda todavía un 25 % por
  encima.
- **Clip de día del Myoshoji:** de 0.52 a 0.49–0.50 m/s.
- **Noche:** no cambia, porque se mide en las escalas lentas.
- Subir `v_esperada` del Kurome a 0.9 no sirvió: el muestreo pasaba a 4 px y la textura desaparecía.
  Se dejó en 0.4.

### 13.5 Burbujas junto al muro del Myoshoji

**Síntoma:** a la derecha de la imagen se veían burbujas moviéndose, pero las estaciones 6–8 nunca
medían.

**Diagnóstico:**

- Un mapa de las motas que pasan por cada píxel mostró trayectorias de burbujas justo sobre las
  líneas 6–8.
- Es agua en sombra, casi quieta, junto al muro derecho, con burbujas que derivan despacio.
- El proceso de día las diluye: la actividad de la banda sale ~0 y la coherencia 0.14–0.33.

**Ajustes:**

- **De día, una estación que falla se reintenta con el realce de motas del modo noche.** Las burbujas
  dan 0.02–0.05 m/s con coherencia 0.7–0.9, igual en dos escalas, y se miden en la de 60 s.
- «Ambiguo» no se reintenta: es agua rápida, no falta de textura.
- La consola marca esas medidas con R/M/L en mayúsculas y el CSV con `dia+motas`.
- Las líneas del Myoshoji pasan de 6 a 9 m, para llegar a la parte cercana a la cámara. Por sí solo
  aportó poco: de 236 a 251 estaciones-medida en 200 s.

**Resultado en 200 s grabados:** **9 de 9 estaciones desde t ≈ 70 s** (antes 6). La estación 6, en el
borde entre el agua rápida y la quieta, da a veces valores sueltos. La medida pasa de ~0.35 a ~0.7 s
en el PC.

### 13.6 Escala del Myoshoji: el ancho sí, el largo no

Otro agente localizó la cámara: estación **上高田上** (Kamitakada 5-6, Nakano; 35.717608,
139.678653). En ortofoto midió:

- un **ancho de 8.8 m ± 0.7** de coronación a coronación, comprobado con una pista de tenis (error
  del 0.4 %);
- el fin de las gradas de la orilla izquierda a +7 m de la cámara.

**Ajustes y resultados:**

- **`ancho_m` pasa de 8.0 a 8.8.** Las velocidades no cambian (mediana 0.46–0.50 m/s), porque se
  miden a lo largo del flujo.
- **El «salto» del fondo no es un salto:** de día es una zona de piedras con agua blanca quieta, y de
  noche el reflejo de una farola.
- **El largo se intentó con un modelo de cámara.** Datos: punto de fuga de los muros, los 8.8 m,
  coronación del muro derecho y gradas a +7 m.
  - Resultado: cámara a 8.4 m sobre el agua, muro de 6.0 m y **cuadrilátero de 9.6 m** (7.9–13.4
    según los supuestos).
  - **No pasó una comprobación independiente:** una persona en el paseo mide 76 px y el modelo la
    predecía de 102–177 px. El largo se dejó en 10 m supuestos.
- **Discrepancia con el informe:** por la imagen, la cámara parece estar en la orilla izquierda
  (este), no en la derecha. El muro izquierdo se ve de canto, el derecho de frente y las gradas junto
  a la cámara.

### 13.7 Cámara nueva: Shimoda (río Kurome)

**Configuración inicial** (`shimoda`, `youtube.com/watch?v=bpL7MAbdoI8`):

- **El agua va hacia el puente.** El agua blanca bajo el puente es un rápido aguas abajo; lo
  confirmaron el STI y una correlación 2D. La primera versión del cuadrilátero lo tenía al revés y
  daba velocidades negativas.
- Escala supuesta de 12 × 5 m.
- Con `v_esperada` 0.4, todo caía por encima del tope de 1.2 m/s; se subió a 0.6.
- **Resultado:** en directo, con lluvia, medía las estaciones 4–8, a ~1.35 m/s.

**Problema a las 18 h: signos opuestos en estaciones vecinas** (+3.1 / −2.5 / −3.8 m/s), con casi todo
«ambiguo» o «v_max».

- **Diagnóstico:** el agua iba a 1–1.5 m/s con ondas casi regulares. A 15 fps, cada onda avanza entre
  dos fotogramas más de media longitud de onda. El STI muestra una **trama cruzada**: las estelas
  reales («\») y su imagen estroboscópica («/»), como las ruedas que en el cine giran al revés.
- **Ajuste: filtro direccional.** En el espectro 2D del STI se anulan los cuadrantes de lo que avanza
  aguas arriba. El sentido aguas abajo lo fija el cuadrilátero.
- **Resultado:** en 90 s grabados, de 0–6 a **156–162 estaciones-medida aceptadas** (9 de 9 casi
  siempre), con mediana 0.94–1.00 m/s.
- **Control de que el filtro no fabrica la medida:** con DS de 2, 3 y 4 px el resultado apenas
  cambia. Un artefacto seguiría al muestreo, porque el ruido filtrado tiende a 45°.
- **Por qué es opcional por cámara** (`filtro_direccional`, solo en el Shimoda): impone el sentido
  del flujo y cambia los números de cámaras que ya funcionaban.
  - Kurome: de 0.86 a 0.66 m/s, más cerca de una correlación independiente (0.72).
  - Myoshoji: −7–10 %.
  - Akigawa: «mediría» ~0.7 m/s, pero el valor sube un 20 % con el muestreo.

**Incidencia posterior:** el usuario vio otra vez trama cruzada y velocidades negativas.

- Su CSV (21:15–22:34) tenía 1955 velocidades negativas y coherencia 0.12–0.40. Con el filtro eso es
  imposible.
- En el mismo minuto, con el código actual, el directo daba **9 de 9 a ~1.1 m/s**, con coherencia
  0.42–0.64.
- **Causa probable:** un proceso abierto antes del cambio. **Cambiar de fuente con las teclas no
  recarga el código.**
- **Ajuste:** la consola muestra la versión (fecha del archivo) al arrancar, y la cabecera indica
  «filtro direccional» cuando está activo.

### 13.8 Cámara nueva: Akigawa (río Aki), que no mide

Cámara `akigawa` (`youtube.com/watch?v=ZRUh9gNk8-g`, estación 留原 en Akiruno): un río ancho visto de
lado, con el agua de izquierda a derecha, hacia el puente. **Se añadió como fuente, pero no mide:**

- El video está muy comprimido: entre fotogramas reales cambia solo 0.3–0.6 niveles de gris.
- El códec congela trozos de agua, y lo que se mueve con contraste son olas fijas del rápido.
- La coherencia se queda en 0.1–0.36, con un umbral de 0.40. Se probó:
  - dos subzonas;
  - muestreos de 0.9 a 2.5 px;
  - el proceso de motas;
  - un paso alto temporal, que llegó como mucho a 0.37.
- **No se bajó el umbral:** aceptaría medidas falsas.
- El filtro direccional la haría «medir», pero el valor sigue al muestreo; no se activó.

### 13.9 Ajustes por cámara, en resumen

| Cámara | Ajustes propios | Ajustes generales que le afectan | Estado |
|---|---|---|---|
| **Myoshoji** | Líneas de 6 a 9 m; ancho 8.8 m (ortofoto) | Modo noche y escalas lentas; una fila por fotograma real; reintento con motas (estaciones 6–8) | Día: 9 de 9 tras ~70 s, ~0.48 m/s. Noche: 5–6 de 9, ~0.06 m/s |
| **Kurome** (puente Koma) | Ninguno (`v_esperada` 0.9 probado y descartado) | Una fila por fotograma real (−10–20 %) | Día: 5–6 de 9, ~0.85 m/s |
| **Shimoda** | Cuadrilátero invertido (agua hacia el puente); `v_esperada` 0.6; banda 0.35 m; **filtro direccional** | Una fila por fotograma real | 9 de 9, ~1.0–1.1 m/s con el río crecido |
| **Akigawa** | Cuadrilátero sobre todo el tramo; `v_esperada` 1.0 | — | No mide (códec y olas fijas) |

Todas las escalas son **supuestas** salvo el ancho del Myoshoji. Ninguna velocidad está validada en
campo.

---

## 14. Fase 12 — Validación del programa en directo con datos de referencia (13–14 oct)

Antes de tener la Raspberry y la cámara, se pasaron videos con referencia independiente por **el mismo
código de medida** de `stiv_directo.py`: la misma geometría, los mismos buffers con el canal de motas, la
cascada de escalas, el modo automático y una medida por segundo. De cada caso solo se pusieron la
geometría y los parámetros propios de la cámara. Los del método (bloques de 48 px, umbral de coherencia
0.40, máscara de actividad, escalas) son los del programa. La referencia se abrió al final de cada caso.
Todo está en `analisis_kurome_directo_stiv/validacion/`, con su README.

### 14.1 Canal USGS (Sile Main Canal): el mejor resultado

- **Video original, sin estabilizar**, como llegaría de una cámara. Con 1.78 mm/px y ~0.95 m/s cada
  fila del STI avanza ~18 px; la deriva del dron (46 px en 22 s) es un 0.4 %, y no se nota.
- **11 de 11 verticales**, incluidas las dos junto a los muros, que el caso original rechazaba por
  coherencia (< 0.70). Aquí pasan con 0.59–0.64 y coinciden con el ADV.
- **Q = 1.4537 m³/s frente al aforo de 1.4362 (+1.2 %)**. Velocidad media en la vertical (0.92 × la
  superficial) frente al ADV: sesgo +1.6 %, RMSE 0.042 m/s.

### 14.2 Bradano: el programa no medía un trazador disperso

- Con el programa tal cual, **1 de 7 verticales**: 7 de 9 estaciones salían «sin textura».
- **Causa:** la máscara contra el agua que congela el códec de YouTube exigía que **la mitad** de los
  píxeles de cada bloque cambiara entre fotogramas. El Bradano es agua casi negra (brillo medio
  0.01–0.36 de 255) con partículas sueltas: la actividad mediana es **0 exacto**.
- Sin la máscara, el código del programa reproduce el caso original: 5 de 7, sesgo −2.4 %, RMSE 0.083,
  r 0.993 (el notebook: 5 de 7, −3.1 %, 0.068, 0.996). El núcleo del método funciona.
- **Arreglo (`FRACCION_ACTIVA_NOCHE` = 0.1):** en modo noche basta con que el 10 % de los píxeles del
  bloque cambie; de día sigue el 50 %. Lo que protege del agua congelada es la máscara **por píxel**, que
  no cambió: los píxeles quietos no aportan al tensor, y en agua negra los quietos tampoco tienen
  textura. Con el arreglo: **5 de 7, sesgo −4.5 %, RMSE 0.070, r 0.992**. Con 0.05 se llegaba a 6 de 7,
  pero en el Myoshoji entraban medidas falsas junto al muro en sombra; por eso 0.1.
- **Por qué solo de noche.** La primera versión bajaba la fracción siempre. Al repasar Heiskanen con el
  programa cambiado, el video de las 10:03 (agua saturada por el sol) pasó de rechazarse a **14 de 20
  estaciones a +36 %**: los bordes del reflejo y los destellos llenan el 10 % de un bloque. El 50 %
  protegía de eso sin que nadie lo hubiera buscado. De noche sí hay exclusión de reflejos; de día no, y
  no se puede hacer por saturación (las estaciones buenas del Myoshoji de día están saturadas en un
  71–82 %). Se encontró porque se volvieron a pasar **todos** los casos con el programa final.
- El video es gris (saturación 0.0) y el modo automático lo trata como **noche**, que es por lo que el
  arreglo le llega. Cualquier fuente en blanco y negro entra en modo noche; con una cámara configurada en
  B/N de día hay que fijar `--modo dia`. Un video **en color** de agua oscura con trazador disperso
  seguiría sin medir de día.

### 14.3 Regresión del arreglo sobre las grabaciones de los directos

Todos los casos se volvieron a pasar con el programa final (`validacion/regresion.py` sobre las
grabaciones de los directos, más los tres casos con referencia):

| Grabación | Modo | Antes (0.5 siempre): aceptadas, mediana | Ahora | |
|---|---|---|---|---|
| Kurome (`kurome`) | dia | 294 de 450, 0.856 m/s | 294 de 450, 0.856 | idéntico |
| Myoshoji (`myoshoji`) | dia | 268 de 450, 0.505 | 268 de 450, 0.505 | idéntico |
| Myoshoji 200 s (`myoshoji_largo`) | dia | 1643 de 1872, 0.482 | 1643 de 1872, 0.482 | idéntico |
| Myoshoji clip 20 s (`myoshoji_dia20`) | dia | 60 de 90, 0.492 | 60 de 90, 0.492 | idéntico |
| **Myoshoji de noche** (`myoshoji_noche`) | noche | **220** de 720, 0.054 | **318** de 720, 0.057 | estaciones 1, 2 y 8 nuevas, a 0.02-0.07 como sus vecinas |
| Shimoda (`shimoda`, `shimoda2`) | dia | 581 de 585, 1.055; 789 de 792, 1.002 | igual | idéntico |
| Shimoda (`shimoda3`) | dia | - | 709 de 720, 1.070 | (sin corrida previa; de día el código es el de antes) |
| Akigawa (`akigawa`) | dia | 0 de 540 | 0 de 540 | sigue sin medir, como debe |
| Bradano (`caso_bradano.py`) | noche (gris) | 1 de 7 verticales | **5 de 7**, -4.5 % | |
| Sile (`caso_sile.py`) | dia | Q +1.2 % | Q +1.2 % | idéntico |
| Heiskanen (`caso_heiskanen.py`) | dia | 08 h -18 %, 09 h -14 %, 10 h 3 de 20, 13 h +35 % | igual | idéntico (con 0.1 de dia, 10 h daba 14 de 20 a +36 %) |

De día el programa hace exactamente lo mismo que antes; los cambios están todos en modo noche.

### 14.4 Heiskanen (río Oulankajoki, Finlandia): una cámara IP fija con ADCP

El conjunto más parecido a ALIAR: cámaras fijas en dos ríos (una **cámara IP Reolink** 4K, una térmica
FLIR y una OAK-D), 94 videos de 30 s de 2023–2024, aforos con ADCP, batimetría, modelos de cámara,
líneas de búsqueda STIV y los resultados STIV y LSPIV de los propios autores. Se usó la Reolink del
20-05-2023 (6 videos, de 08 a 13 h; ADCP a las 10:13).

- **Geometría:** la cámara está montada de lado (el video lleva una rotación de 90° en los metadatos y el
  modelo es de la imagen nativa). El modelo (formato de Hydro-STIV: focal, posición y ángulos) admite dos
  convenciones que son espejo una de otra y ambas caen sobre agua. Se eligió **sin mirar el ADCP**: la que
  no es espejo y la única que alinea las líneas con el flujo medido en la imagen (0–7° frente a 12–18°).
- **08:03 y 09:03:** 7–8 de 20 estaciones, solo el tercio cercano, **−14 a −18 %** frente al ADCP, igual
  con `V_ESPERADA` de 0.7 a 1.4. La causa no está identificada; no es el antialias (probado con un σ
  por estación: sin cambio) ni `V_ESPERADA`.
- **10 a 12 h, con el sol de cara:** el agua sale saturada y el programa la rechaza («sin textura») en
  vez de inventar.
- **13:03:** 16 de 20 estaciones, pero **+33 %**, con buena coherencia. No es el río (el caudal bajaba de
  141 a 120 m³/s ese día): son **destellos del sol** en las ondas. Es el caso peligroso, un error que
  parece una buena medida; de día el programa no tiene defensa contra eso.
- **Zona lejana (20–40 m):** rechazada siempre; agua lisa que refleja los árboles. Ahí el STIV de los
  autores da 0.24–0.46 m/s donde el ADCP mide ~1.0: el programa se abstiene donde ellos se equivocan.
- Lecciones para el sitio de ALIAR: que la cámara no mire al sol, que esté cerca del agua y,
  probablemente, con polarizador.

---

## 15. Algoritmos probados, en resumen

| Algoritmo | Dónde | Estado |
|---|---|---|
| **LSPIV** (correlación cruzada de ventanas, pyorc) | Ngwerere, canal USGS | En uso; preciso pero pesado (~14 GB) |
| **STIV con tensor de estructura** por bloques | Todos los casos STIV | **Método principal** |
| STIV con cresta espectral (FFT) | Canal de riego | Diagnóstico secundario |
| RIVeR-STIV (aplicación de terceros) | Canal USGS | Comparación; perfil no fiable |
| PIV por correlación de conjunto | Arrow, canal (alcance) | Árbitro independiente |
| **PTV** (seguimiento de partículas) | Canal de riego | Árbitro independiente |
| Filtro adaptado / *track-before-detect* (Radon de la STI) | Canal (zona lejana) | Control; confirmó la ausencia de señal |
| Detección de nivel por cruce al 50 % con interpolación subpíxel | Boneyard | En uso |
| Estabilización GFTT + Lucas-Kanade contra el fotograma 0 | Canal USGS | En uso |
| Rectificación por punto de fuga | Boneyard, canal de riego | Usada; en Boneyard sustituida por la manual |
| Rectificación con 4 puntos (homografía) | Boneyard, cámaras en directo | En uso |
| Pose completa con distorsión (`solvePnP` + `remap`) | Hommerich | En uso |
| Modelo Shiono-Knight (distribución lateral) | Canal de riego | Extrapolación, etiquetada como simulación |
| STIV en **cascada de escalas de tiempo** (10 / 30 / 60 s) | Cámaras en directo | En uso; agua lenta y de noche |
| Realce de motas (top-hat + resta de la mediana temporal + exclusión de reflejos) | Cámaras en directo | En uso de noche y como reintento de día |
| **Filtro direccional** en el espectro 2D del STI | Shimoda | En uso, solo por cámara; validado por invariancia al muestreo |
| Paso alto temporal en el STI | Akigawa | Probado; insuficiente (coherencia 0.37) |
| Modelo de cámara (punto de fuga + ancho + referencia a lo largo) | Myoshoji | Probado; no pasó la comprobación con una persona |
| Modelo de cámara de Hydro-STIV (colinealidad) → cuadrilátero sobre el plano del agua | Heiskanen | En uso para la validación |
| Antialias con un σ por estación (en vez de uno común) | Heiskanen | Probado; sin efecto, no se adoptó |
| Máscara de actividad por bloque al 10 % solo de noche (de día sigue al 50 %) | Todas las cámaras | **En uso** desde el 14 oct; al 10 % también de día aceptaba destellos |

---

## 16. Tiempos de procesamiento

| Proceso | Tiempo | Memoria |
|---|---|---|
| Estabilizar 250 fotogramas 4K (pyorc / OpenCV) | ~110 s / ~135 s | — |
| Notebook pyorc del canal USGS (250 fotogramas 4K) | ~160 s | **13.7–15.3 GB** |
| → abrir video y `get_frames` | 26.8 s | 1.3 GB |
| → `normalize` + `project` | 53.9 s | 7.5 GB |
| → `get_piv` (cálculo real) | 75.3 s | 13.7 GB |
| → máscaras y caudal | ~3 s | 1.4 GB |
| Notebook STIV del canal USGS (mismo video) | **38 s** (80 s en frío) | **0.87 GB** |
| → tensor de estructura, 13 estaciones | 0.02–0.03 s | — |
| STIV del canal USGS sobre el video entero (22 s) | ~9 min | — |
| Boneyard, video de velocidad | ~2 min | ~0.9 GB |
| Hommerich, herramienta completa | ~15 s | — |
| Bradano, notebook / video | ~65 s / ~3.5 min | 268 MB |
| Arrow, notebook / video | ~50 s / ~45 s | — |
| Canal de riego: caso base / PTV / video | ~95 s / ~110 s / ~9 min | — |
| Canal: alcance / video de alcance / video del filtro | ~6 / ~7 / ~4 min | — |
| Canal: STIV mejorado / video de la sección completa | ~9 / ~7 min | — |
| STIV en directo | 1 medida por segundo (~140 ms); primera medida a los 10 s | — |
| STIV en directo tras la optimización | 1–2 ms por fotograma (antes 4–9 ms) | ~626 MB (antes 1.3 GB) |
| Primera vez del banco Docker (construir la imagen + instalar emulado) | ~10–15 min | ~1 GB de imágenes Docker |
| Instalación en la Raspberry emulada en Docker | ~8 min (emulado) | — |
| Actualizar solo el código en la Pi (`-SinInstalar`) | 6 s | — |
| Reconexión RTSP tras un corte | Vuelve a medir a los 10 s | — |
| Medida en directo con tres escalas (noche) | ~0.3 s por medida en el PC | — |
| Medida de día con reintento de motas (Myoshoji) | ~0.7 s por medida en el PC (antes ~0.35) | — |
| Medida del Shimoda con filtro direccional | 0.15–0.22 s por medida | — |
| Primera medida en estaciones lentas (escala de 60 s) | ~60–70 s tras arrancar | — |
| Programa en directo sobre video 4K de 30 s (Heiskanen, 20 estaciones) | 31–38 s en el PC | — |
| Programa en directo sobre el canal USGS (22 s, 4K, 11 estaciones) | ~81 s en el PC | — |

**Lección de costes:** en STIV, el algoritmo es el 0.1 % del tiempo; leer el video es el 99.9 %.
LSPIV necesita 16 veces más memoria porque guarda todo el video proyectado.

---

## 17. Resultados finales

| Caso | Método | Resultado | Referencia |
|---|---|---|---|
| Ngwerere | pyorc LSPIV | 0.1672 m³/s | +1.9 % del valor publicado |
| Canal USGS | STIV propio | 1.4475 m³/s (video entero: 1.4493) | **+0.8 %** del aforo ADV |
| Canal USGS | pyorc LSPIV | 1.4507–1.4565 m³/s | +1.0 a +1.4 % |
| Canal USGS | RIVeR-STIV | 1.4293 m³/s | −0.5 % (perfil no fiable) |
| Boneyard | STIV + nivel | 0.2427 alturas/s; nivel en 929/929 fotogramas | Sin sección |
| Hommerich | STIV métrico | 13.68 m³/s | Sin referencia |
| Bradano | STIV, banda de 7 líneas | 5 de 7 verticales | Sesgo −3.1 %, r 0.996 |
| Arrow con trazadores | STIV | 0.389 m/s | −6.7 % |
| Arrow sin trazadores | STIV, 9 variantes | 0 de 49 | No medible, explicado |
| Canal de riego | STIV + top-hat | 6 de 15 estaciones, 0.0590 alturas/s | r 0.984 con PTV |
| Cámaras de Tokio en directo | STIV en tiempo real | 0.45 m/s (Myoshoji, de día) | Escala supuesta, sin referencia |
| Myoshoji tras los ajustes del 13 oct | STIV + escalas lentas + motas | Día: 9 de 9, ~0.48 m/s; noche: 5–6 de 9, ~0.06 m/s | Ancho medido (8.8 m), largo supuesto |
| Kurome tras corregir los duplicados | STIV | 5–6 de 9, ~0.85 m/s (antes ~0.94) | Correlación independiente: 0.72–1.0 m/s (estaciones 5–8) |
| Shimoda | STIV + filtro direccional | 9 de 9, ~1.0–1.1 m/s (río crecido) | Escala supuesta; invariante al muestreo |
| Akigawa | STIV, varias variantes | 0 de 9 | No medible con este video, explicado |
| Canal USGS, programa en directo sin estabilizar | STIV en directo | **1.4537 m³/s, 11 de 11 verticales** | **+1.2 %** del aforo ADV |
| Bradano, programa en directo (con el arreglo de la máscara) | STIV en directo | 5 de 7 verticales | Sesgo −4.5 %, r 0.992 |
| Heiskanen, Reolink 08–09 h | STIV en directo | 7–8 de 20 estaciones (tercio cercano) | −14 a −18 % del ADCP |
| Heiskanen, Reolink 13 h | STIV en directo | 16 de 20, **+33 %** | Destellos del sol: error aceptado |
| Raspberry Pi emulada en Docker | Mismo STIV, sin pantalla, como servicio | Mismos números que en el PC; reconecta sola | Velocidad real de la Pi sin medir |

---

## 18. Reglas de trabajo que salieron del proceso

1. **La referencia se abre una sola vez, al final.** Nada se ajusta después (de ahí que se eliminaran
   el barrido de `v_corr` y los detectores automáticos sobreajustados).
2. **La escala lo decide todo:** un 1 % de error en metros por píxel es un 1 % en el caudal.
3. **La coherencia alta no garantiza una medida buena:** muros, códecs que congelan el agua y zonas
   lejanas dan coherencia alta con valores falsos. Hace falta un segundo filtro adaptado a cada caso
   y, si no hay aforo, un segundo algoritmo como árbitro.
4. **Las orillas fallan en todos los casos:** sombra, poca agua y pocas partículas.
5. **Sin trazador no hay medida, y lejos de la cámara tampoco:** paso de muestreo ≥ 0.2 px.
6. **Todo error encontrado lo detectó un control (sintético o real), no la lectura del código.**
7. **Probar el despliegue antes de tener el hardware:** la Raspberry emulada en Docker y la cámara RTSP
   simulada sacaron cuatro fallos que en el campo habrían dejado el equipo sin medir.
8. **Saber cómo llega el video antes de medir:** fps real de la cámara, fotogramas duplicados y
   compresión. Los duplicados de YouTube sesgaban hasta un 26 % sin que nada lo indicara.
9. **El tiempo también tiene aliasing:** con agua rápida y ondas regulares, a 15 fps aparece un
   movimiento falso hacia atrás. Los síntomas son una trama cruzada en el STI y signos opuestos en
   estaciones vecinas.
10. **Un filtro o un realce no debe fabricar la medida:** se comprueba cambiando el muestreo. Si el
    resultado lo sigue, es un artefacto.
11. **Cambiar de fuente no recarga el código:** tras una actualización hay que cerrar y volver a abrir
    el programa. La versión se muestra al arrancar.
12. **Un filtro pensado para un problema puede tapar otro caso:** la máscara contra el agua congelada
    de YouTube dejaba sin medir un trazador disperso sobre agua negra. Cada cambio del método se
    comprueba con una regresión sobre grabaciones (`validacion/regresion.py`).
13. **La luz del sol decide más que el algoritmo:** de cara satura el agua (sin datos) y con destellos
    da errores con buena coherencia. La orientación de la cámara es parte del diseño.
