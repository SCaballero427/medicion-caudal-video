# Validacion de `stiv_directo.py` con datos de referencia

Pruebas hechas el 2026-10-13/14, antes de tener la Raspberry y la camara: pasar videos con referencia
independiente por **el mismo codigo de medida del programa en directo** (`Geometria`, `Buffers` con el
canal de motas, `medir` con la cascada de escalas, modo automatico, una medida por segundo). Solo se
ponen la geometria y los parametros **por camara** (`N_ESTACIONES`, `LARGO_LINEA_M`, `ANCHO_BANDA_M`,
`V_ESPERADA`...); los del metodo (bloques de 48 px, `COH_MIN`, actividad, escalas) son los del programa.
La referencia de cada caso solo se abre al final de su script, como en el resto del workspace.

`correr.py` importa `../stiv_directo.py`, no una copia: lo que se valida es lo que corre en directo.

## Como se ejecuta

Desde esta carpeta, con el `.venv` del programa:

```powershell
..\.venv\Scripts\python.exe caso_sile.py            # ~1.5 min
..\.venv\Scripts\python.exe caso_bradano.py         # ~15 s
..\.venv\Scripts\python.exe caso_heiskanen.py 1.0   # ~3.5 min, los 6 videos de la Reolink
..\.venv\Scripts\python.exe regresion.py kurome     # un caso de la regresion (ver abajo)
```

Los datos estan fuera de git (`datasets vision velocimetria/` en la raiz del workspace) salvo el video
del Sile (`test_pyorc/USGS/Video/`, la copia anidada). Los JSON de resultados van a `salidas/`.

| Archivo | Que hace |
|---|---|
| `correr.py` | El bucle del programa sobre un video grabado: `correr()` con geometria propia, `correr_camara()` con la de una camara de `CAMARAS` + su `config_stiv_directo.json` |
| `caso_sile.py` | USGS Sile Main Canal contra el aforo ADV (caudal y velocidad por vertical) |
| `caso_bradano.py` | HARMONIOUS Rio Bradano contra sus 7 verticales de referencia |
| `caso_heiskanen.py` | Heiskanen et al., Oulankajoki, camara IP Reolink, contra ADCP y contra el STIV de los autores |
| `proyeccion.py` | Modelo de camara de Heiskanen (formato `GeoCorrectionParameter` de Hydro-STIV) a pixeles |
| `angulo_flujo.py` | Como se eligio la convencion de ese modelo (ver abajo) |
| `sigma_por_estacion.py` | Variante probada (antialias por estacion): sin efecto, no esta en el programa |
| `regresion.py`, `regresion_casos.py`, `grabar.py` | Regresion de cambios del metodo sobre grabaciones de los directos |
| `destellos.py` | Diagnostico: fraccion de muestras saturadas por estacion (por que de dia no se excluyen los destellos por saturacion) |
| `xlsx.py` | Lector minimo de `.xlsx` (el `.venv` no tiene pandas) |

## Resultados

| Caso | Estaciones | Contra la referencia |
|---|---|---|
| **Sile** (video original **sin estabilizar**) | **11/11**, tambien las dos junto a los muros | Q **1.4537** m3/s vs aforo 1.4362 (**+1.2 %**); 0.92 x v superficial vs ADV: sesgo +1.6 %, RMSE 0.042 m/s |
| **Bradano** (programa de antes) | 1/7 | no mide: 7 de 9 estaciones "sin textura" |
| **Bradano** (programa ahora, `FRACCION_ACTIVA_NOCHE` 0.1) | 5/7 | sesgo -4.5 %, RMSE 0.070 m/s, r +0.992 (el notebook del caso: 5/7, -3.1 %, 0.068) |
| **Heiskanen** 08:03 y 09:03 | 7-8 de 20 (el tercio cercano) | **-14 a -18 %** vs ADCP, igual con `V_ESPERADA` 0.7-1.4 |
| **Heiskanen** 10-12 h (sol de cara) | 1-3 de 20 | el resto "sin textura" (agua saturada): se abstiene |
| **Heiskanen** 13:03 (destellos del sol) | 16 de 20 | **+33 %**, aceptado con coherencia alta |

**Sile.** Sin estabilizar porque el programa no estabiliza: con 1.78 mm/px y ~0.95 m/s cada fila del STI
avanza ~18 px y la deriva del dron (46 px en 22 s, ~0.07 px por fotograma) es un 0.4 %. La deriva no se
nota. Las verticales 1 y 11, que el caso `analisis_USGS_SMC_stiv` rechaza (coherencia < 0.70), aqui
pasan con 0.59-0.64 (`COH_MIN` 0.40) y coinciden con el ADV (0.641 vs 0.630 y 0.774 vs 0.737).

**Bradano.** La mascara de actividad (contra el agua que congela el codec de YouTube) exigia que la
mitad de los pixeles de cada bloque cambiase 0.5 niveles de gris entre fotogramas. El Bradano es agua
casi negra (brillo medio 0.01-0.36/255) con particulas sueltas: la actividad mediana es **0 exacto** y
ningun bloque llegaba a la mitad. Ver "Cambio en el programa". Ademas el video es gris (saturacion 0.0)
y el modo automatico lo trata como noche: **cualquier fuente en blanco y negro entra en modo noche**.
Aqui da igual (dia y noche miden lo mismo), pero con una Hikvision configurada en B/N de dia habria que
fijar `--modo dia`.

**Heiskanen.** Camara IP de 4K montada de lado (los metadatos dicen girar 90 grados; el modelo de camara
es de la imagen nativa, asi que se lee con `CAP_PROP_ORIENTATION_AUTO` = 0). Las 20 lineas de busqueda
del dataset se proyectan sobre el plano del agua (nivel diario 160.75 m) con su modelo de camara. Ese
modelo admite dos convenciones que son espejo una de otra y ambas caen sobre agua; se eligio **sin mirar
el ADCP**: la que no es espejo, y la unica que alinea las lineas con el flujo optico medido (0-7 grados
en las estaciones 3-8, frente a 12-18 de la otra; `angulo_flujo.py`). Si fuese la otra, los numeros
cambiarian. La linea 1 del dataset mide 3.15 m y las otras 4.00: el rectangulo usa el largo de las demas.

- Las estaciones 9-20 (20-40 m de la camara, agua lisa que refleja los arboles) se rechazan **siempre**,
  por coherencia. El STIV publicado por los autores da ahi 0.24-0.46 m/s donde el ADCP mide ~1.0: el
  programa se abstiene donde ellos se equivocan.
- El -15 % del tercio cercano no esta explicado. No es el antialias (`sigma_por_estacion.py`: un sigma
  por estacion en vez del de la mediana, -17.9 % vs -18.4 %) ni `V_ESPERADA`. El STIV de los autores (media
  de 6 h) queda ~10 % por encima del programa en esas estaciones. El ADCP mide bajo la superficie, asi que
  la superficie deberia ir, si acaso, mas rapida.
- **13:03 no es una crecida**: el caudal bajaba (141 -> 120 m3/s en el dia). Son los destellos del sol en
  las ondas, que el programa mide con confianza. De dia no hay defensa contra eso (la exclusion de
  deslumbramiento es solo de noche), y es el caso peligroso: un error que parece una buena medida.
- Lecciones para el sitio de ALIAR: que la camara no mire al sol (3 de 6 horas sin datos), cerca del
  agua (a 20-40 m el agua lisa no se mide ni en 4K) y probablemente con polarizador.

## Cambio en el programa: `FRACCION_ACTIVA_NOCHE` = 0.1

En `pendiente_tensor`, un bloque cuenta si una fraccion de sus pixeles es activa. Era 0.5 siempre.
Ahora es **0.1 en modo noche** (`FRACCION_ACTIVA_NOCHE`) y sigue en **0.5 de dia**, tambien en el
reintento de motas (`FRACCION_ACTIVA`). Lo que protege del agua congelada sigue siendo la mascara **por
pixel**, que no cambia: los pixeles quietos no aportan gradiente al tensor. En agua negra con motas los
pixeles inactivos tampoco tienen textura, asi que no estorban; lo que fallaba era el umbral por bloque.

**Por que solo de noche.** La primera version bajaba la fraccion a 0.1 siempre. La regresion de los
directos salio limpia, pero al repasar Heiskanen con el programa cambiado, el video de las 10:03 (agua
saturada por el sol de cara) paso de rechazarse ("sin textura", 3 de 20) a **14 de 20 estaciones a +36 %**:
los bordes del reflejo y los destellos llenan el 10 % de un bloque. El 50 % protegia de eso sin que nadie
lo hubiera pensado. De noche si hay exclusion de reflejos (`BRILLO_REFLEJO`); de dia no, y no se puede
hacer por saturacion: `destellos.py` muestra que las estaciones buenas del Myoshoji de dia tienen el
71-82 % de sus posiciones saturadas (y el Kurome y el Shimoda nada). El Bradano entra por la noche
porque es gris (saturacion 0.0) y el modo automatico lo toma por infrarrojo. Un video **en color** de
agua oscura con trazador disperso seguiria sin medir de dia: queda como limitacion.

Comprobado con el programa final sobre las grabaciones de los directos (`regresion.py`), comparado con
el programa anterior:

| Grabacion | Modo | Antes (0.5 siempre): aceptadas, mediana | Ahora | |
|---|---|---|---|---|
| Kurome (`kurome`) | dia | 294 de 450, 0.856 m/s | 294 de 450, 0.856 | identico |
| Myoshoji (`myoshoji`) | dia | 268 de 450, 0.505 | 268 de 450, 0.505 | identico |
| Myoshoji 200 s (`myoshoji_largo`) | dia | 1643 de 1872, 0.482 | 1643 de 1872, 0.482 | identico |
| Myoshoji clip 20 s (`myoshoji_dia20`) | dia | 60 de 90, 0.492 | 60 de 90, 0.492 | identico |
| **Myoshoji de noche** (`myoshoji_noche`) | noche | **220** de 720, 0.054 | **318** de 720, 0.057 | estaciones 1, 2 y 8 nuevas, a 0.02-0.07 como sus vecinas |
| Myoshoji de noche, desde el 2026-10-14 | noche | | **0** de 720 | `medir_noche` = False: esos 0.05 m/s eran destellos de farola, no la corriente (`../verificacion_nivel/`) |
| Shimoda (`shimoda`, `shimoda2`) | dia | 581 de 585, 1.055; 789 de 792, 1.002 | igual | identico |
| Shimoda (`shimoda3`) | dia | - | 709 de 720, 1.070 | (sin corrida previa; de dia el codigo es el de antes) |
| Akigawa (`akigawa`) | dia | 0 de 540 | 0 de 540 | sigue sin medir, como debe |
| Bradano (`caso_bradano.py`) | noche (gris) | 1 de 7 verticales | **5 de 7**, -4.5 % | |
| Sile (`caso_sile.py`) | dia | Q +1.2 % | Q +1.2 % | identico |
| Heiskanen (`caso_heiskanen.py`) | dia | 08 h -18 %, 09 h -14 %, 10 h 3 de 20, 13 h +35 % | igual | identico (con 0.1 de dia, 10 h daba 14 de 20 a +36 %) |

De dia el programa hace exactamente lo mismo que antes; los cambios estan todos en modo noche.

## Regresion

`regresion.py <caso>` pasa una grabacion por el programa, tal como esta, con los ajustes de su camara, y
guarda `salidas/reg_<caso>.json`. Para comprobar un cambio del metodo: correrlo antes y despues y
comparar. Los casos estan en `regresion_casos.py`. Las grabaciones (FFV1, 1-4 GB) estan en
`grabaciones/`, **fuera de git**; se rehacen con `grabar.py <camara> <segundos> [nombre]`. Los dos clips
de `raspberry/prueba/` si estan en el repositorio. Una grabacion nueva no reproduce los numeros de
arriba (es otro momento del rio): sirve para comparar antes/despues, no contra esta tabla.
