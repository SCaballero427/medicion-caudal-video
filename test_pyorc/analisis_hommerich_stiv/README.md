# `analisis_hommerich_stiv/` — STIV metrico sobre el video original de Hommerich

STIV desde cero (OpenCV puro, pyorc no se importa) sobre el video **original** de la camara del
Geul en Hommerich (NL), el que el dataset publica junto a su ortomosaico ya procesado. Produce
velocidad superficial en **m/s**, perfil transversal y **caudal**, y lo dibuja sobre las dos
vistas a la vez.

```powershell
cd analisis_hommerich_stiv
..\pyorc_env\Scripts\python.exe video_velocidad.py                    # ~15 s
..\pyorc_env\Scripts\python.exe video_velocidad.py --desplazamiento 0 # seccion sin mover
```

Salidas en `salidas/`: `velocidad_tiempo_real.mp4` (3.7 MB, 122 fotogramas, 2181x698, reproduccion
a tiempo real), `velocidad_ventanas.csv` con la serie por ventana y `config_stiv_hommerich.json`
con la configuracion entera congelada.

## Datos de entrada

Fuera del workspace, en `C:\Users\Sergio\Desktop\datasets vision velocimetria\Hommerich`. Del
paquete se usan tres ficheros y **no** se usa el ortomosaico:

| Fichero | Para que |
|---|---|
| `20241010_081717.mp4` | el video original, 1920x1080, 122 fotogramas, 29.853 fps |
| `cam_config_gcp1.json` | intrinsecos, distorsion, 6 GCPs (pixel <-> EPSG:28992), `h_ref`, `z_0` |
| `cs1_ordered.geojson` | seccion transversal, 24 puntos WGS84 con cota |

`20241010_081717_ortho.mp4` y `hommerich_frames_*/` son la salida ya ortorectificada de pyorc:
sirven para contrastar la rectificacion a ojo, nunca como entrada.

## Que hace distinto a los otros dos casos STIV

- Frente a **`analisis_boneyard_stiv/`**: alli la rectificacion salia del horizonte y una focal
  supuesta, o sea una afinidad del plano, y todo quedaba en alturas de camara por segundo. Aqui
  el dataset trae intrinsecos, distorsion y 6 GCPs RTK, asi que la pose se resuelve entera con
  `solvePnP` y hay **metros**, y por tanto **m3/s**.
- Frente a **`analisis_USGS_SMC_stiv/`**: alli la camara es cenital y el fotograma *es* el plano
  de agua. Aqui es oblicua y con barril fuerte (k1 = -0.485), asi que se mide en la rectificada y
  la original esta para juzgar que lo medido cae donde uno cree. De ahi los dos paneles.

## La cadena de geometria

1. `solvePnP` (SQPNP + refinado LM) con los 6 GCPs, en coordenadas locales: en RD New absolutas
   (~3e5) la condicion numerica es mala. **Reproyeccion: 0.56 px de mediana, 2.50 px la peor.**
2. Lamina de agua en `z = z_0 + (h_a - h_ref) = 150.49 + 0.895 = 151.385 m`. `h_a = 93.345` es el
   `--h_a` del propio script del dataset; el otro script, sin el, deja el agua bajo el talweg.
3. La seccion se reproyecta a EPSG:28992 y se le ajusta una recta por PCA sobre los puntos
   mojados. Su direccion es el eje transversal `u`; la perpendicular es la linea de flujo.
4. El raster rectificado se construye en ese sistema a 0.01 m/px. Cada punto se lleva a pixel con
   `projectPoints`, que **si** incluye la distorsion — por eso se calcula el mapa una vez y se
   aplica con `remap`, en vez de una homografia, que no podria.

Con eso cada vertical es una **columna** del raster y su STI sale de leer esa columna cada DS px.

## Decisiones deliberadas

- **La seccion se mide 2.5 m rio abajo de donde se levanto.** En su posicion original las cuatro
  verticales de la orilla lejana veian entre el 42 % y el 75 % de su linea; a 2.5 m aguas abajo
  **todas** tienen cobertura 1.00. 2.5 m es el minimo que lo consigue y por eso es el valor: mas
  lejos solo mejora el punto de orilla, que no se mide. El precio hay que decirlo — los calados
  siguen siendo los de la seccion levantada, asi que el caudal supone cauce prismatico en esos
  2.5 m. La velocidad no sufre: se mide donde se dibuja.
- **`DS` se deriva, no se teclea**: `DS = V_ESPERADA * dt / resolucion` = 4 px, para que las
  estelas caigan cerca de 45 grados, donde el error angular pesa menos. Salen a **43.5 grados**
  medidos, asi que la estimacion a ojo de 1.2 m/s era buena.
- **El SENTIDO del flujo no se impone.** La *linea* si es configuracion (la normal a la seccion),
  como en todo STIV; el sentido sale del signo mayoritario de la pendiente que mide el tensor.
- **Las lineas se recortan, no se descartan.** Aunque con la seccion desplazada ya no haga falta,
  el recorte al tramo contiguo visible se queda: es lo que hace que mover la seccion sea una
  eleccion y no una obligacion, y sin el se perdian 4 verticales con textura de sobra
  (contraste 11 y 12) mientras el relleno se comia 3.2 m de los 12.13 m de ancho.
- **El filtro de calidad es contraste temporal, no solo coherencia**, la leccion de Boneyard: una
  estructura estatica da coherencia altisima con velocidad cero y el umbral de coherencia la
  aprueba. Los valores medidos van 1.06, 1.14, 2.28, 2.63 | 3.14, 3.81, ... y las dos del lado
  malo del hueco devolvian 0.06 y 0.03 m/s pegadas a una que da 0.65. El umbral no es critico:
  bajarlo a 2.0 y admitirlas mueve Q un +1.4 %.
- **`ALFA = 0.85`**, el estandar del USGS y ademas el `v_corr` que el propio `hommerich.yml` del
  dataset usa. Fijado antes de mirar nada.
- **Relleno lineal, sin modelo de pared**, igual que el caso SMC, con su coste conocido.
- La flecha mide **lo que el agua recorre en 1 s**, o sea una longitud del mundo real: en el panel
  original la perspectiva la acorta sola porque se proyecta su punta, no se rota a mano.

## Resultado

13 de 16 verticales medibles se aceptan. Las 3 rechazadas ya **no** lo son por campo de vision
sino por contraste (0.50, 1.04 y 1.95): estan sobre la orilla, con 21 a 43 cm de calado y sin
trazador que seguir. Esa es la debilidad de siempre junto a la pared, y mover la seccion no la
arregla porque no es geometrica.

| | |
|---|---|
| Ancho mojado / area | 12.13 m / 11.636 m2 (calado maximo 1.29 m) |
| v superficial mediana de la seccion | **0.943 m/s** (maximo por vertical 2.13 m/s) |
| **Q mediana** | **13.68 m3/s** (q05–q95 13.33 – 13.99, rango 13.27 – 14.04) |

Con la seccion sin desplazar salia 12.94 m3/s y 0.827 m/s: el +5.7 % es que tres verticales de la
orilla lejana pasan de rellenarse a medirse. Es mas medida y menos relleno, pero conviene saber
que el numero se movio por esa decision.

## Limitaciones

- **La seccion no se mide donde se levanto**, sino 2.5 m aguas abajo, lo que supone cauce
  prismatico en ese tramo. Es la unica forma de que las verticales de la orilla lejana entren en
  cuadro. `--desplazamiento 0` reproduce la posicion original.
- **No hay aforo independiente.** El paquete no incluye la Q que produjo pyorc, solo su log. El
  13.68 m3/s no esta contrastado contra nada: para cerrarlo hay que ejecutar pyorc con el
  `cam_config` + `hommerich.yml` + `cs1_ordered.geojson` que vienen, y entonces si seria la
  comparacion controlada LSPIV vs STIV sobre el mismo video.
- **Solo 4.1 s de video** (122 fotogramas): 26 ventanas de 2.4 s. La dispersion entre ventanas
  (±2.5 %) mide repetibilidad a corto plazo, no estabilidad del caudal.
- **La incertidumbre de fps es del 0.5 %** (`r_frame_rate` 30 vs `avg_frame_rate` 29.853) y entra
  directa en la velocidad. Se usa el que declara OpenCV, 29.853.
- Las verticales pegadas a las orillas se rellenan por interpolacion lineal, que no puede
  reproducir un perfil que se mantiene alto hasta muy cerca de la orilla.
- No se corrige movimiento de camara: es fija y son 4 s. No se ha medido.
