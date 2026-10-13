# `analisis_canal_stiv_puro/` — STIV tal cual, sin nada modelado

Quinta carpeta sobre el mismo video de movil del canal de riego
(`C:\Users\Sergio\Desktop\videos\WhatsApp Video 2026-08-16 at 8.07.12 PM.mp4`). Un solo fichero,
`video_stiv_puro.py`, y un solo producto: `salidas/stiv_puro.mp4`.

## Por que existe

`analisis_canal_completo_stiv/` termina en una **simulacion**: un modelo de Shiono-Knight que
rellena el 64 % del ancho donde no hay trazador, con particulas virtuales corriendo por todo el
canal. Esta bien etiquetado — azul contra amarillo, zona sombreada, rotulo en cada fotograma — pero
tiene un riesgo que ninguna etiqueta arregla del todo: **la imagen que queda en la cabeza es la de
un canal entero en movimiento**, y dos tercios de ese movimiento los pone un modelo.

Este video es el contrapeso, y por eso vive en su propia carpeta en vez de ser una opcion del otro:
**todo lo que se ve aqui esta medido.** Sin particulas virtuales, sin perfil ajustado, sin rellenar
estaciones rechazadas, sin extrapolar. Donde STIV no mide, no se dibuja nada.

La imagen que sale es mas pobre — el canal aparece medido solo en su tercio derecho, con nueve
huecos — y **esa pobreza es el resultado honesto** de un video de WhatsApp sin datos de campo. Las
dos versiones son utiles; hacen falta las dos, y hace falta que se vea cual es cual.

## Que se ve

- **Las lineas de busqueda de las 15 estaciones**: en color las que miden, tenues y con una x las
  que no. Se dibujan todas, tambien las que fallan, porque **donde no se mide es parte del
  resultado**.
- **Una flecha por estacion aceptada**, cuyo largo es el recorrido en 10 s: la longitud de la
  flecha *es* la velocidad, sin necesidad de leer el numero. Sobre la vista de camara la punta se
  proyecta con la misma homografia que todo lo demas, asi que la perspectiva la escorza sola — no
  es una copia girada de la del panel rectificado.
- **La STI de la estacion resaltada, abajo a la izquierda, con la recta que el tensor le ha
  encontrado dibujada encima.** Es lo que convierte esto en STIV y no en "flechas sobre agua": se
  ven las estelas que deja el detrito al bajar, se ve la pendiente que se les ajusta, y arriba se
  ve la flecha que esa pendiente produce. **El foco va rotando cada 4 s** entre las estaciones que
  miden, y la estacion enfocada se resalta en los dos paneles de arriba, para que el ojo pueda ir
  de la STI a su sitio en el canal.
- **El perfil transversal de la ventana actual**, solo con los puntos que existen. Los puntos
  aceptados se unen entre si, pero **nunca a traves de un hueco**: unir dos estaciones separadas
  por una que no mide seria dibujar una interpolacion, que es justo lo que esta carpeta no hace.
  Al fondo, en gris, el recorrido de cada estacion a lo largo de los 81 s — tambien medido.
- **El detrito detectado, en amarillo**, sobre los dos paneles. Es el dato en bruto del que sale
  todo lo demas, asi que se ve.

## Donde estan los huecos

Sobre las 138 ventanas del video entero, estacion por estacion:

| estacion | X | ventanas con medida | |
|---|---|---|---|
| 0 a 7 | -1.05 a -0.02 | **0 / 138** | sin trazador: el detrito baja por la orilla derecha |
| 8 | +0.12 | 65 / 138 | borde del chorro de detrito |
| 9 | +0.27 | 81 / 138 | |
| 10 | +0.42 | 106 / 138 | |
| **11** | **+0.56** | **136 / 138** | el centro del chorro |
| 12 | +0.71 | 109 / 138 | |
| 13 | +0.85 | 92 / 138 | |
| 14 | +1.00 | **0 / 138** | orilla: densidad 0.078, por encima del umbral superior |

**6 de 15 estaciones miden, todas en el tercio derecho.** Ocho fallan por falta de trazador y una
por ser orilla, no agua. Que las estaciones 8 y 13 midan en la mitad de las ventanas y la 11 en
casi todas no es ruido del algoritmo: es que el detrito viaja en una banda estrecha y las ventanas
de 12 s a veces no pillan ninguna particula. En el video eso se ve como flechas que aparecen y
desaparecen en los extremos mientras la del centro no se mueve.

## No mide nada nuevo

La medida es literalmente la del caso original: `pasada_sti` y `medir_ventanas` se **importan** de
`analisis_canal_riego_stiv/video_velocidad.py`, y geometria, realce, tensor y control de calidad de
`stiv_canal.py`. Este fichero solo dibuja. Asi que si el caso cambia, este video cambia con el, y
no hay dos versiones de la verdad — que es la disciplina que esta rama del workspace mantiene desde
`analisis_canal_riego_stiv/`.

Configuracion **la original**: 15 estaciones, banda de 0.10 con 11 lineas, ventanas de 360
fotogramas (12 s) cada 15. No se usan las 29 estaciones de `analisis_canal_completo_stiv/`; la
peticion era ver el algoritmo original, y ademas con 15 las flechas se leen y con 29 se apelmazan.

La comprobacion de que importar en vez de copiar funciona es que **la mediana de seccion sale
0.0598 alt.cam/s, digito a digito la del caso** (q05-q95 0.0432 - 0.0805 sobre las 138 ventanas).
Si alguna vez no coincidiera, seria que alguien ha duplicado codigo por el camino.

## Ficheros

| fichero | que es |
|---|---|
| `video_stiv_puro.py` | el video; importa la medida entera del caso original |
| `salidas/stiv_puro.mp4` | el video, a tiempo real |
| `salidas/perfil_ventanas.csv` | una fila por (ventana, estacion): v, coherencia, densidad, si mide |
| `salidas/config_stiv_puro.json` | la configuracion congelada |

## Lo que hay que llevarse

- **Un video de una simulacion y un video de la medida no son intercambiables**, por muy bien
  etiquetada que este la simulacion. Conviene tener los dos y que se distingan de un vistazo.
- **Los huecos son informacion.** Rellenar el perfil entre dos estaciones separadas por una que no
  mide es una decision, no un detalle de dibujo, y aqui se toma la contraria.
- **La STI al lado de la flecha es lo que hace auditable un video de velocimetria.** Con solo las
  flechas hay que creerse el numero; con la STI se ve la estela, se ve la recta y se puede juzgar
  si el ajuste es razonable sin abrir un CSV.
