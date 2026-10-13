# Guion del vídeo ISATECK

Pieza de **38 s**, lo mínimo para entender qué hace el sistema. Se monta con `montar_demo.py`.
Salida: `C:\Users\Sergio\Desktop\videos\ISATECK_medicion_de_caudal.mp4`, 1920×1080 a 30 fps.

## Tres bloques y nada más

| # | Bloque | s | Qué se ve |
|---|---|---|---|
| 1 | Portada | 5 | Hueco del logo + «Medición de caudal con cámaras, sin contacto». |
| 2 | Canal | 17 | El vídeo del canal con tres números encima explicando las partes. |
| 3 | Arroyo | 16 | El vídeo del arroyo con tres números: cámara, vista rectificada y nivel. |

Sin resultados, sin comparación con el aforo, sin explicar el algoritmo, sin cierre. Solo dos
fundidos: la entrada desde blanco y la salida.

## Los números

**Canal** — coordenadas en píxeles del fotograma ya recortado:

| # | Dónde apunta | Texto |
|---|---|---|
| 1 | `(425, 215)` | Puntos de medición, repartidos de orilla a orilla |
| 2 | `(748, 357)` | Velocidad del agua en cada punto, en metros por segundo |
| 3 | `(950, 715)` | Velocidad media y caudal, actualizados en vivo |

**Arroyo**:

| # | Dónde apunta | Texto |
|---|---|---|
| 1 | `(400, 400)` | La imagen de la cámara |
| 2 | `(830, 250)` | Los cuatro puntos de referencia (GCP) con los que se rectifica |
| 3 | `(1150, 274)` | Vista de la cámara rectificada, se simula una visión desde arriba del agua |
| 4 | `(90, 292)` | El nivel del agua, leído a partir del pluviómetro |

Los círculos van en una **capa aparte** que se aplica *después* de pegar cada fotograma. Si se
dibujan en el fondo, el clip los borra al pegarse encima — pasó en la primera versión.

## Los puntos de apoyo (GCP)

Se dibujan en ámbar sobre el arroyo: el cuadrilátero con sus cuatro vértices en la vista de la
cámara, y el rectángulo en que se convierten en la vista rectificada. Enseñar los dos a la vez
es lo que hace entender qué es rectificar, sin una sola palabra técnica.

**No están escritos a mano**: salen de `analisis_boneyard_stiv/salidas/config_stiv_manual.json`,
que los guarda en píxeles del vídeo original de la cámara. El script les aplica la misma
composición con la que se montó ese vídeo (panel escalado a 500 px de alto, hueco de 18,
cabecera de 34; cámara de 1280×720) y después el recorte de esta pieza. Si la geometría se
reajusta, el dibujo la sigue solo.

## El aviso sobre la franja negra

«Vídeo preprocesado, no en directo», en gris claro, sobre la banda negra que ya traen los dos
clips. Es corto a propósito: en el arroyo solo hay ~450 px libres entre las cifras del pie y la
barra de color, y un texto más largo se monta encima de una de las dos.

## El logo

Se espera en `video_ejecutivo/logo_isateck.png` (fondo blanco o transparente, da igual: el
script recorta el margen solo). Va centrado en la portada y arriba a la izquierda en los dos
bloques de vídeo. **Si el archivo no está, el hueco queda en blanco a propósito** — no se
dibuja ningún texto de relleno que luego haya que tapar.

Colores: verde `#177A1F`, verde oscuro `#0B4F13`, blanco.

## Los clips se recortan

Los vídeos de origen llevan grabada información técnica que aquí sobra. Se recorta por
coordenadas de píxel, **sin tocar los archivos originales**:

| | Recorte | Qué se quita |
|---|---|---|
| Canal | `(0, 46, 1920, 798)` de 1920×844 | Cabecera «STIV en ventana movil…» y las dos líneas de leyenda del pie. Se conserva la línea del reloj, la velocidad y el caudal. |
| Arroyo | `(18, 60, 1424, 573)` de 1442×586 | Bordes negros, la fila de parámetros y la etiqueta «mira_rectificada». **Se conservan los dos paneles**, porque la vista rectificada es una de las cosas que se enseña. |

## Revisar antes de montar

`python video_ejecutivo\montar_demo.py --previo` escribe un PNG por bloque en `previo/` sin
codificar nada. Es la forma barata de mover los números y corregir textos.
