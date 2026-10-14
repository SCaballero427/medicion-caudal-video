# Verificacion con el nivel del agua (Myoshoji)

Graba el directo y cruza la velocidad que mide el programa con el **nivel del agua** que publica el
Gobierno de Tokio en la estacion de la propia camara, **上高田上** (pagina
`kasen-suibo.metro.tokyo.lg.jp/im/uryosuii/tsim0105g_222013.html`).

```powershell
..\.venv\Scripts\python.exe grabar_directo.py --minutos 60          # graba (grabaciones/, fuera de git)
..\.venv\Scripts\python.exe analizar.py grabaciones\<a>.ts [<b>.ts ...]   # mide y cruza con el nivel (salidas/)
..\.venv\Scripts\python.exe analizar.py ... --reusar                 # sin volver a medir: solo baja el nivel
..\.venv\Scripts\python.exe analizar.py ... --modo noche             # fuerza el proceso (salidas con sufijo)
```

| Archivo | Que hace |
|---|---|
| `grabar_directo.py` | Graba el directo sin recomprimir, con la hora de cada segmento |
| `analizar.py` | Mide una o varias grabaciones con el codigo del programa y las cruza con el nivel (CSV diario; si aun no esta, la tabla de 10 min de la pagina y, si no cubre, la horaria interpolada) |
| `diagnostico_dia_noche.py` | Arbitro independiente: correlacion cruzada 2D de conjunto en la planta, a desfases de 0.07 a 8 s |
| `trazas_flotantes.py` | Trazas del realce de motas acumulado 10 s (imagen) y seguimiento de motas >= 3 s |
| `espectro_kw.py` | Espectro numero de onda-frecuencia del STI largo: advencion (recta) frente a ondas (curva de dispersion) |
| `prueba_escalas.py` | Un tramo de dia solo con escalas lentas o con el proceso de motas |
| `referencia/` | Aforos oficiales del puente Ochiai (caudal y calado, 2005-2009) y `velocidad_ochiai.py` |

## Resultado del 2026-10-14: tres horas, dia y noche con el mismo nivel

Tres grabaciones de 60 min sin huecos (15:32, 17:12 y 18:17 hora de Japon). Nivel 1.21-1.23 m todo
el rato (2 cm, la resolucion del sensor): **la comparacion con el nivel no dice nada en seco**.

Antes del cambio del programa (la noche se tomaba por dia), y forzando el proceso de noche:

| Tramo | Proceso de dia | Proceso de noche (motas) |
|---|---|---|
| 15:40-16:40, dia | **0.46-0.50 m/s**, todas las medidas validas | - |
| 17:20-17:30, atardecer | 0.46-0.48 | 0.23-0.26 |
| 17:50-19:00, noche en color con farolas | 1-20 de 120 validas, 0.47-0.77 (basura) | **0.063-0.072**, 60-100 % validas |

Con el programa final (`myoshoji_20261014_1532JST_a_1817JST_10min.csv`, nivel del CSV diario oficial):

| Hora (Japon) | Nivel (m) | Velocidad (m/s) | Validas | Modo |
|---|---|---|---|---|
| 15:40 | 1.23 | 0.502 | 88/88 | dia |
| 15:50 | 1.23 | 0.501 | 119/119 | dia |
| 16:00 | 1.22 | 0.488 | 119/119 | dia |
| 16:10 | 1.22 | 0.484 | 120/120 | dia |
| 16:20 | 1.22 | 0.473 | 119/119 | dia |
| 16:30 | 1.22 | 0.464 | 119/119 | dia |
| 16:40 | 1.22 | 0.475 | 31/31 | dia |
| 16:50-17:10 | 1.21-1.22 | - | - | sin grabacion |
| 17:20 | 1.21 | 0.464 | 89/89 | dia |
| 17:30 | 1.21 | 0.482 | 118/118 | dia |
| 17:40 | 1.21 | **0.540** | 61/118 | mixto (cambia a noche a las 17:35) |
| 17:50-19:20 | 1.21-1.22 | - | 0 de ~1100 | noche: `noche_no_valida` |

Mediana de dia: **0.483 m/s** (983 medidas). El descenso de 0.50 a 0.46 entre las 15:40 y las 16:30
acompana una bajada de 1 cm del nivel; con esa resolucion no se puede decir si es real.

**El atardecer sesga antes de que salte el umbral.** Entre las 17:32 y las 17:35, con brillo de las
lineas entre 54 y 60 (por encima de `BRILLO_NOCHE` = 50), el proceso de dia sube a 0.53-0.59 m/s con
solo 4-6 estaciones; a las 17:28-17:31 daba 0.45-0.52 con 6-8. Eso es el 0.540 "mixto" de las 17:40.
Subir el umbral a ~60 lo cortaria, pero la grabacion de dia mas oscura (`myoshoji_largo`) tiene 66.5:
el margen seria pequeno. Queda como pendiente, con estas cifras.

**Cual es la buena: la de dia.** Los aforos oficiales del puente Ochiai (`referencia/`) dan en tiempo
seco Q 0.38 m3/s con 0.13 m de calado, es decir ~0.4-0.6 m/s en superficie; la de noche queda 5-8
veces por debajo. Lo que se ve de noche son **destellos de las farolas sobre ondulaciones casi fijas de
la superficie** (las piedras del fondo en 13 cm de agua), que apenas se mueven en 2 s: el proceso de
motas, el seguimiento de motas (0.04-0.05, 125-174 pistas) y la correlacion de conjunto (0.04-0.05
constante hasta 8 s) los miden igual de bien, y por eso coincidian sin medir el agua. El espectro de
la noche no tiene nada a 0.4 m/s: de noche esta camara no ve el agua que fluye. El de dia pone la
energia en una recta f = 0.42 k que pasa por el origen, a todas las longitudes de onda: advencion (unas
ondas no dispersivas a 0.42 m/s exigirian ~2 cm de calado; con 13 cm irian a ~1.1 m/s).

**Lo que se dio por bueno primero y era falso**, para que no se repita: con los objetos flotantes junto
al muro (0.05-0.07 de dia y de noche) se concluyo que el agua iba a ~0.05 y que de dia el STIV seguia
ondas. Lo desmonto el aforo oficial. Las burbujas del muro estan en una zona lenta en sombra; que
coincidieran con la noche fue casualidad.

**Que se cambio en el programa:** la noche se detecta tambien por brillo (`BRILLO_NOCHE` = 50; la
camara no pasa a infrarrojo y la saturacion sola no la detectaba) y el Myoshoji lleva
`"medir_noche": False`: de noche mide y dibuja, pero ninguna estacion se acepta (`noche_no_valida`).

**Salidas:** `salidas/myoshoji_20261014_1532JST_a_1817JST_*` son las tres horas con el programa final
(nivel del CSV diario oficial); `..._1712JST_a_1817JST_noche_*` las horas 2-3 forzando el modo noche;
`salidas/diagnostico/` las figuras de los diagnosticos y `salidas/registros/` sus salidas de texto
(`diag_*.log` del atardecer y la noche son las versiones con realce de motas: las de brillo crudo se
sobrescribieron al lanzarlas en paralelo).

**Pendiente:**
- De dia esta camara emite a ~12 fps (duplicados alternos de 2 y 3), no a 15. La hora de cada fila es
  correcta, pero el escalon irregular puede sesgar unos pocos por ciento; sin revisar.
- El atardecer (brillo 50-60) sesga +10-20 % durante unos minutos antes del cambio de modo (arriba).
- El programa en directo no usa deno: en este PC puede no abrir YouTube (`grabar_directo.py` si).
- Una comprobacion con el nivel que diga algo necesita una grabacion con lluvia.

## Notas de uso

- **Que publica la pagina:** solo nivel (cm, cada 10 min; CSV diario `Tokyo_Suii_AAAAMMDD.csv` desde
  2025-11, publicado al dia siguiente; la pagina muestra las ultimas 4 h) y lluvia. **No** caudal, ni
  velocidad, ni cota del fondo, ni seccion. El sensor no mide por debajo de 1.12 m.
- **Que se puede comprobar:** que la velocidad sube y baja con el nivel. **No** los m/s (sin caudal ni
  calado, y el largo de la escala del Myoshoji es supuesto).
- **Hace falta lluvia:** en seco el nivel se mueve 1-2 cm (13 oct: 1.19-1.28 m); el 20 sep, con lluvia,
  fue de 1.26 a 3.10 m. En crecida usar `--v-esperada` mas alta en `analizar.py` (la camara esta
  configurada para ~0.3 m/s y rechaza > 0.9 m/s).
- **Grabacion:** segmentos HLS tal como llegan (sin recomprimir; Myoshoji 720p: ~0.8 GB/h). Los segmentos
  de YouTube no traen hora de programa, asi que la hora de cada uno es la de descarga (lleva el retraso
  del directo, segundos, nada frente a tramos de 10 min). Si YouTube pide "confirma que no eres un bot":
  `--cookies cookies.txt` (exportado de un navegador con sesion; `cookies*.txt` esta en `.gitignore`).
- **Desde oct 2026 YouTube exige resolver un desafio en JavaScript** para dar los formatos ("No video
  formats found" / "The page needs to be reloaded", incluso con cookies). Hace falta `deno.exe` junto al
  python del `.venv` (`.venv\Scripts\deno.exe`, descargado de github.com/denoland/deno/releases) y el
  paquete `yt-dlp-ejs` (`pip install yt-dlp-ejs`); `grabar_directo.py` usa ese deno. **El programa en
  directo (`stiv_directo.py`) todavia no lo usa.**
- **El nivel se publica con ~15 min de retraso:** correr `analizar.py` al menos 20 min despues de acabar
  la grabacion (o al dia siguiente, con el CSV diario).
