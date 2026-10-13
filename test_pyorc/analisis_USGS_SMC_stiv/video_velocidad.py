"""Video de la velocidad superficial por STIV sobre el video ENTERO del Sile Main Canal.

Que hace
--------
Repite el STIV del notebook (`SMC_STIV_pipeline.ipynb`) en ventanas temporales
deslizantes a lo largo de los 22 s completos del video del dron, en vez de sobre
los 250 fotogramas que procesa el notebook, y dibuja el resultado encima del
**video original**: las 13 lineas de busqueda del aforo, una flecha por vertical
con la velocidad instantanea y su valor en m/s.

La vista es cenital, asi que aqui no hay nada que rectificar: la escala ya es
uniforme en toda la imagen y el plano de agua es la imagen. Eso lo separa del
caso Boneyard, donde la mitad del cuadro era la vista rectificada porque sin ella
las velocidades no eran comparables entre si. Aqui sobra: un solo panel.

Estabilizacion, que si hace falta
---------------------------------
El notebook parte de `entradas/SMC_estabilizado_stiv.mkv`, que solo tiene 250
fotogramas. Para el video completo no se genera un `.mkv` de ~3 GB: se estima la
misma transformacion, con la misma funcion de `estabilizar_stiv.py` (seguimiento
directo contra el fotograma 0, sin encadenar), y se aplica de dos maneras
distintas segun para que:

* para MEDIR, la transformacion se compone con las coordenadas de muestreo, de
  modo que se muestrea el sitio correcto sin deformar el fotograma entero. Es
  equivalente a haber estabilizado el video y ademas evita una interpolacion.
* para DIBUJAR, se transforman las lineas y las flechas, no el fotograma. Asi lo
  que se ve es el video original tal cual, sin bordes replicados, y las lineas
  siguen al canal cuando el dron deriva. La deriva se imprime al arrancar.

Constantes compartidas con el notebook
--------------------------------------
Las filas de agua, el ancho del canal, el tramo de columnas, el angulo de flujo,
la velocidad esperada y los parametros del tensor son LOS MISMOS que en la Parte
2, 3, 4 y 4b del notebook. Estan duplicados aqui a proposito para que el script
sea autonomo: si se cambian alli hay que cambiarlos aqui.

Uso
---
    python video_velocidad.py                       # video entero, desde esta carpeta
    python video_velocidad.py --frames 300          # solo los primeros 300 fotogramas
"""

import argparse
import csv
import shutil
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

# `estabilizar_stiv.py` vive en la raiz del workspace. Se reutiliza en vez de copiar el
# seguimiento: es el mismo algoritmo que produjo el video de entrada del notebook, asi
# que las dos cadenas corrigen el movimiento del dron exactamente igual. Sigue siendo
# OpenCV puro, de modo que este script tampoco depende de pyorc.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from estabilizar_stiv import estimar_transformaciones, mascara_zona_fija, parsear_poligono

# ===========================================================================================
#  >>> AJUSTABLE <<<  Geometria. IDENTICA a la Parte 2 del notebook.
# ===========================================================================================
FILA_AGUA_SUP = 438           # fila donde el agua toca el muro superior
FILA_AGUA_INF = 1463          # idem muro inferior; el hormigon en sombra se confunde con
                              # el agua, esta fila sale del criterio de movimiento
ANCHO_CANAL = 1.8288          # m, 6 ft exactos (obtenido del dataset)
COLUMNA_INI, COLUMNA_FIN = 600, 3400
ANGULO_FLUJO = -1.0           # grados respecto a las filas de la imagen

# ===========================================================================================
#  >>> AJUSTABLE <<<  Muestreo y tensor. IDENTICOS a las Partes 3 y 4 del notebook.
# ===========================================================================================
V_ESPERADA = 0.95             # m/s, estimacion a ojo; de aqui sale DS
LADO_BLOQUE = 64
COH_MIN_BLOQUE = 0.50
SIGMA_DERIVADA = 1.5
COH_MIN_ESTACION = 0.70       # criterio de aceptacion de una vertical (Parte 4b)
ALFA = 0.92                   # velocidad media en la vertical / superficial (Parte 5)

# Cota de plausibilidad, que el notebook no necesita y este script si. Al medir en 105
# ventanas cortas en vez de una sola larga, la vertical 11 (pegada al muro en sombra) cuela
# alguna vez una onda estacionaria con coherencia > 0.70 y pendiente absurda: 7 m/s en un
# canal que va a 1. La cota se fija en 3 x V_ESPERADA, o sea a partir de la estimacion a
# ojo previa y no de ninguna referencia; esta tan lejos de los datos que solo puede cazar
# disparates, y las verticales que la superan se rellenan igual que las de coherencia baja.
V_MAX_FISICA = 3.0 * V_ESPERADA

# ===========================================================================================
#  >>> AJUSTABLE <<<  Lo unico propio de este script: la ventana movil
# ===========================================================================================
# Fotogramas por medida. Es el compromiso central: mas corta da mas resolucion temporal
# pero menos bloques del tensor. Con 150 fotogramas (5 s) la STI de una ventana admite
# 3x3 bloques de 64 px con solape, frente a los 6x3 que tiene el notebook con 250. Por
# debajo de ~120 solo caben 2 filas de bloques y la mediana ponderada deja de ser robusta.
VENTANA = 150
# Fotogramas entre medidas consecutivas. No es la cadencia del video de salida: el video
# se escribe fotograma a fotograma a 30 fps (tiempo real) y cada uno toma la medida de la
# ventana cuyo centro le queda mas cerca.
PASO = 5
# ===========================================================================================

# Poligono que encierra el AGUA, para la estabilizacion. El mismo de la linea de comandos
# documentada en CLAUDE.md para estabilizar_stiv.py.
POLIGONO_AGUA = "0,420 3840,420 3840,1500 0,1500"

DIR_CASO = Path(__file__).resolve().parent
RUTA_VIDEO = DIR_CASO / ".." / "USGS" / "Video" / "SMC_D_RC_022_08172020_AC.mp4"
RUTA_SECCION = DIR_CASO / ".." / "USGS" / "Station_Stage_SileCanal.csv"

# --- Presentacion -------------------------------------------------------------------------
ESC_SALIDA = 0.5              # el video es 4K; a la mitad se lee todo y ocupa un tercio
MARGEN_CROP = 190             # filas por encima y por debajo del agua que entran en el cuadro
PX_POR_MS = 300               # pixeles de flecha (ya en el cuadro de salida) por cada m/s
V_COLOR_MAX = 1.2             # m/s a los que satura la paleta; el mismo rango de la fig7
ALTO_CABECERA = 46
ALTO_PIE = 96


# ------------------------------------------------------------------ tensor de estructura
def tensor_estructura(bloque, sigma=SIGMA_DERIVADA):
    """Pendiente m (muestras/fotograma) y coherencia C de un trozo de STI.

    Copia literal de la Parte 4 del notebook: autovector del autovalor menor del tensor
    del gradiente, que es la direccion a lo largo de las estelas.
    """
    g = cv2.GaussianBlur(bloque, (0, 0), sigma)
    It = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)      # eje 0 = tiempo
    Ix = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)      # eje 1 = espacio
    It, Ix = It[2:-2, 2:-2], Ix[2:-2, 2:-2]           # Sobel contamina 2 px de borde

    Jxx = float((Ix * Ix).sum())
    Jtt = float((It * It).sum())
    Jxt = float((Ix * It).sum())
    if Jxx + Jtt <= 0:
        return np.nan, 0.0
    _, vec = np.linalg.eigh(np.array([[Jxx, Jxt], [Jxt, Jtt]]))
    ex, et = vec[:, 0]
    if et < 0:                                        # definido salvo signo
        ex, et = -ex, -et
    m = ex / et if et != 0 else np.nan
    coherencia = np.sqrt((Jxx - Jtt) ** 2 + 4 * Jxt ** 2) / (Jxx + Jtt)
    return m, float(coherencia)


def medir_sti(sti_p, lado=LADO_BLOQUE, coh_min=COH_MIN_BLOQUE):
    """Pendiente robusta de una STI completa, por bloques con 50 % de solape.

    Un tensor global dejaria que un parche brillante dictara la respuesta, asi que se
    combinan los bloques con una mediana ponderada por coherencia.
    """
    nt, nx = sti_p.shape
    paso = lado // 2
    ms, cs = [], []
    for t0 in range(0, nt - lado + 1, paso):
        for x0 in range(0, nx - lado + 1, paso):
            m, c = tensor_estructura(sti_p[t0:t0 + lado, x0:x0 + lado])
            if np.isfinite(m):
                ms.append(m)
                cs.append(c)
    if not ms:
        return np.nan, 0.0
    ms, cs = np.array(ms), np.array(cs)
    coh_mediana = float(np.median(cs))
    usables = cs >= coh_min
    if usables.sum() == 0:
        return np.nan, coh_mediana
    mm, cc = ms[usables], cs[usables]
    orden = np.argsort(mm)
    mm, cc = mm[orden], cc[orden]
    acumulado = np.cumsum(cc) / cc.sum()
    return float(mm[np.searchsorted(acumulado, 0.5)]), coh_mediana


def preparar_sti(sti):
    """Quita el fondo estatico y el parpadeo global, y normaliza. Igual que la Parte 3.

    Se aplica a cada VENTANA por separado, no al video entero: la media temporal que se
    resta tiene que ser la del tramo que se esta midiendo, si no el fondo que se elimina
    no es el que contamina esa ventana.
    """
    a = sti - sti.mean(axis=0, keepdims=True)   # fondo fijo de cada muestra
    a = a - a.mean(axis=1, keepdims=True)       # parpadeo de cada fotograma
    d = a.std()
    return a / d if d > 0 else a


# ------------------------------------------------------------------------------ dibujo
PALETA = cv2.applyColorMap(np.arange(256, dtype=np.uint8).reshape(-1, 1),
                           cv2.COLORMAP_TURBO).reshape(-1, 3)


def color_velocidad(v):
    """Color BGR de una velocidad. Gris si no hay medida."""
    if not np.isfinite(v):
        return (120, 120, 120)
    i = int(np.clip(v / V_COLOR_MAX, 0, 1) * 255)
    return tuple(int(x) for x in PALETA[i])


def texto(img, s, org, escala=0.5, col=(255, 255, 255), grosor=1):
    """Texto con reborde negro: sobre el agua el blanco solo no se lee."""
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, escala, (0, 0, 0), grosor + 2,
                cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, escala, col, grosor, cv2.LINE_AA)


def buscar_ffmpeg():
    """ffmpeg del PATH o el que trae RIVeR en la raiz del workspace."""
    ruta = shutil.which("ffmpeg")
    if ruta:
        return ruta
    empaquetado = Path(__file__).resolve().parent.parent / "RIVeR-STIV_1.0" / "ffmpeg.exe"
    return str(empaquetado) if empaquetado.exists() else None


def recodificar_h264(salida):
    """Reescribe el .mp4 en H.264 conservando la imagen fotograma a fotograma.

    OpenCV en este entorno solo puede escribir mp4v (MPEG-4 parte 2): su DLL de
    OpenH264 es de una version que no carga. Ese codec se ve en VLC y en poco mas,
    de modo que el archivo no se puede compartir ni incrustar en un navegador. La
    recodificacion es un paso aparte, no un cambio de VideoWriter, porque el codec
    que falta no lo pone el escritor sino ffmpeg.

    CRF 18 es visualmente sin perdida y ademas ocupa ~3x menos que el mp4v de
    partida, que gasta bits en una compresion mucho peor. `yuv420p` y perfil high
    son lo que exigen los reproductores de movil y web; `+faststart` mueve el
    indice al principio para que el video empiece antes de descargarse entero.
    """
    ffmpeg = buscar_ffmpeg()
    if ffmpeg is None:
        print("AVISO: no se encontro ffmpeg; el video queda en mp4v y no se podra "
              "reproducir fuera de VLC. Recodificar a mano con:\n"
              f"  ffmpeg -i {salida} -c:v libx264 -pix_fmt yuv420p -crf 18 ...")
        return
    tmp = salida.with_name(salida.stem + "_h264.mp4")
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(salida),
           "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
           "-crf", "18", "-preset", "medium", "-movflags", "+faststart", "-an", str(tmp)]
    t0 = time.perf_counter()
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        print(f"AVISO: fallo la recodificacion a H.264, el video queda en mp4v.\n{r.stderr}")
        return
    tmp.replace(salida)
    print(f"  recodificado a H.264 en {time.perf_counter()-t0:.1f} s")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", default=str(RUTA_VIDEO))
    ap.add_argument("--salida", default=str(DIR_CASO / "salidas" / "velocidad_tiempo_real.mp4"))
    ap.add_argument("--frames", type=int, default=0, help="0 = el video entero")
    a = ap.parse_args()

    salida = Path(a.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(a.video)
    if not cap.isOpened():
        raise SystemExit(f"No se pudo abrir {a.video}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    n = n_total if a.frames <= 0 else min(a.frames, n_total)
    dt = 1.0 / fps

    # --- geometria, exactamente como en la Parte 2 -----------------------------------
    seccion = pd.read_csv(RUTA_SECCION)
    s_est = seccion["Progresiva"].to_numpy(float)
    prof = seccion["Prof"].to_numpy(float)
    n_est = len(seccion)
    es_contorno = prof == 0.0

    escala = ANCHO_CANAL / (FILA_AGUA_INF - FILA_AGUA_SUP)
    filas_est = FILA_AGUA_SUP + s_est / escala
    ds = int(round(V_ESPERADA * dt / escala))
    sigma_antialias = 0.5 * ds
    area = float(np.trapezoid(prof, s_est))

    print(f"{Path(a.video).name}: {ancho}x{alto}, {n_total} fotogramas a {fps:.3f} fps "
          f"({n_total/fps:.1f} s)")
    print(f"se procesan {n} fotogramas ({n/fps:.1f} s)")
    print(f"escala {escala*1000:.4f} mm/px, DS = {ds} px, {n_est} verticales, "
          f"area {area:.4f} m2")
    print(f"ventana movil {VENTANA} fotogramas ({VENTANA/fps:.1f} s), medida cada {PASO}\n")

    # --- pasada 0: movimiento del dron -----------------------------------------------
    print("Pasada 0/2 - estimando el movimiento del dron (mismo metodo que estabilizar_stiv.py)")
    t0 = time.perf_counter()
    mascara = mascara_zona_fija(parsear_poligono(POLIGONO_AGUA), alto, ancho)
    matrices, n_validos, residuos = estimar_transformaciones(a.video, mascara, 0, n - 1)
    matrices = matrices[:n]
    while len(matrices) < n:                       # el video acabo antes de lo anunciado
        matrices.append(matrices[-1].copy())
    deriva = np.array([np.hypot(m[0, 2], m[1, 2]) for m in matrices])
    print(f"  {len(matrices)} transformaciones en {time.perf_counter()-t0:.1f} s")
    print(f"  rasgos seguidos: mediana {np.median(n_validos):.0f}, minimo {n_validos.min()}")
    print(f"  residuo del ajuste: mediana {np.nanmedian(residuos):.2f} px")
    print(f"  deriva acumulada del dron: maxima {deriva.max():.1f} px "
          f"({deriva.max()*escala*100:.1f} cm de canal)\n")

    # inversas: llevan un punto del sistema estabilizado al fotograma original
    inversas = [cv2.invertAffineTransform(m) for m in matrices]

    # --- pasada 1: construir la STI de todo el video ----------------------------------
    # Coordenadas de muestreo en el sistema estabilizado (fotograma 0), identicas a
    # mapa_lineas() del notebook: cada linea girada ANGULO_FLUJO sobre su punto medio.
    n_mu = int((COLUMNA_FIN - COLUMNA_INI) / ds)
    t_lin = (np.arange(n_mu) - (n_mu - 1) / 2) * ds
    cx = 0.5 * (COLUMNA_INI + COLUMNA_FIN)
    ang = np.radians(ANGULO_FLUJO)
    mapx0 = (cx + t_lin * np.cos(ang))[None, :].repeat(n_est, 0).astype(np.float32)
    mapy0 = (filas_est[:, None] + t_lin * np.sin(ang)).astype(np.float32)

    # Solo hace falta desenfocar y muestrear la banda de filas que ocupan las lineas.
    # El margen cubre el giro de las lineas, la deriva del dron y el radio del gaussiano.
    banda0 = max(int(FILA_AGUA_SUP - 3 * sigma_antialias - deriva.max() - 40), 0)
    banda1 = min(int(FILA_AGUA_INF + 3 * sigma_antialias + deriva.max() + 40), alto)

    print(f"Pasada 1/2 - muestreando las {n_est} lineas en {n} fotogramas "
          f"(banda de filas {banda0}-{banda1})")
    t0 = time.perf_counter()
    cap = cv2.VideoCapture(a.video)
    sti = np.zeros((n_est, n, n_mu), np.float32)
    for k in range(n):
        ok, fr = cap.read()
        if not ok:
            n = k
            sti = sti[:, :n, :]
            break
        gris = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY).astype(np.float32)[banda0:banda1]
        # Antialias ANTES de muestrear cada DS px: sin esto el submuestreo inventa
        # orientaciones. Es isotropo a proposito (ver el notebook).
        gris = cv2.GaussianBlur(gris, (0, 0), sigma_antialias)
        # La estabilizacion entra aqui: el punto que en el fotograma 0 estaba en (x, y)
        # esta en este fotograma en inv(M)(x, y). Componerla con el mapa de muestreo
        # equivale a estabilizar el fotograma, sin deformarlo ni interpolarlo dos veces.
        iv = inversas[k]
        mx = iv[0, 0] * mapx0 + iv[0, 1] * mapy0 + iv[0, 2]
        my = iv[1, 0] * mapx0 + iv[1, 1] * mapy0 + iv[1, 2] - banda0
        sti[:, k, :] = cv2.remap(gris, mx, my, cv2.INTER_LINEAR)
        if (k + 1) % 100 == 0:
            print(f"  {k+1}/{n} fotogramas")
    cap.release()
    print(f"  STI de {n} fotogramas en {time.perf_counter()-t0:.1f} s\n")

    # --- medida en ventanas deslizantes ------------------------------------------------
    inicios = np.arange(0, max(n - VENTANA, 0) + 1, PASO)
    centros = inicios + VENTANA // 2
    V = np.full((len(inicios), n_est), np.nan)      # velocidad final (medida o rellenada)
    MEDIDA = np.zeros((len(inicios), n_est), bool)  # True si paso el criterio de coherencia
    Q = np.full(len(inicios), np.nan)

    print(f"Midiendo {len(inicios)} ventanas x {n_est} verticales")
    t0 = time.perf_counter()
    n_absurdas = 0
    for w, i0 in enumerate(inicios):
        v = np.full(n_est, np.nan)
        coh = np.full(n_est, np.nan)
        for i in range(n_est):
            if es_contorno[i]:
                v[i] = 0.0                          # calado nulo y no deslizamiento
                continue
            m, c = medir_sti(preparar_sti(sti[i, i0:i0 + VENTANA, :]))
            coh[i] = c
            if np.isfinite(m):
                v[i] = m * ds * escala / dt
        # Mismo control de calidad que la Parte 4b: se aceptan las verticales con
        # coherencia suficiente y se rellenan las demas por interpolacion lineal sobre
        # las aceptadas, sin usar los ceros del contorno como apoyo.
        valida = ((~es_contorno) & (coh >= COH_MIN_ESTACION) & np.isfinite(v)
                  & (np.abs(v) <= V_MAX_FISICA))
        n_absurdas += int(((coh >= COH_MIN_ESTACION) & (np.abs(v) > V_MAX_FISICA)
                           & ~es_contorno).sum())
        v_final = v.copy()
        faltan = np.where(~(valida | es_contorno))[0]
        if valida.sum() >= 2 and len(faltan):
            v_final[faltan] = np.interp(s_est[faltan], s_est[valida], v[valida])
        elif len(faltan):
            v_final[faltan] = np.nan
        V[w] = v_final
        MEDIDA[w] = valida
        if np.isfinite(v_final).all():
            Q[w] = float(np.trapezoid(ALFA * v_final * prof, s_est))
        if (w + 1) % 20 == 0:
            print(f"  {w+1}/{len(inicios)} ventanas")
    print(f"  {len(inicios)} ventanas en {time.perf_counter()-t0:.1f} s\n")

    # La mediana de la seccion se toma solo sobre las verticales medibles: los ceros
    # impuestos del contorno no son medidas y la arrastrarian hacia abajo.
    v_mediana = np.nanmedian(V[:, ~es_contorno], axis=1)
    print(f"Verticales aceptadas por ventana: mediana {np.median(MEDIDA.sum(1)):.0f} "
          f"de las {(~es_contorno).sum()} medidas")
    print(f"Descartadas por la cota de {V_MAX_FISICA:.2f} m/s pese a tener coherencia "
          f"suficiente: {n_absurdas} de {len(inicios)*int((~es_contorno).sum())}")
    for i in range(n_est):
        if es_contorno[i]:
            continue
        print(f"  vertical {i:2d} (s = {s_est[i]:.2f} m): aceptada en "
              f"{100*MEDIDA[:, i].mean():5.1f} % de las ventanas, "
              f"v mediana {np.nanmedian(V[:, i]):.3f} m/s")
    print(f"\nCaudal instantaneo: mediana {np.nanmedian(Q):.4f} m3/s, "
          f"rango {np.nanmin(Q):.4f} - {np.nanmax(Q):.4f} m3/s")
    print(f"Velocidad superficial mediana de la seccion: {np.nanmedian(v_mediana):.4f} m/s\n")

    # --- pasada 2: render --------------------------------------------------------------
    # Recorte fijo en coordenadas del video ORIGINAL. La deriva del dron es de decenas de
    # pixeles, asi que un recorte fijo no deja fuera nada: lo que se mueve son las lineas.
    r0 = max(FILA_AGUA_SUP - MARGEN_CROP, 0)
    r1 = min(FILA_AGUA_INF + MARGEN_CROP, alto)
    pw = int(ancho * ESC_SALIDA)
    ph = int((r1 - r0) * ESC_SALIDA)
    cw, ch = pw, ALTO_CABECERA + ph + ALTO_PIE

    print(f"Pasada 2/2 - render de {n} fotogramas a {cw}x{ch}, {fps:.2f} fps (tiempo real)")
    # mp4v es lo unico que sabe escribir OpenCV aqui; `recodificar_h264` lo pasa a H.264
    # al terminar, que es lo que reproducen el navegador y el movil.
    vw = cv2.VideoWriter(str(salida), cv2.VideoWriter_fourcc(*"mp4v"), fps, (cw, ch))
    if not vw.isOpened():
        raise SystemExit("No se pudo abrir el escritor de video.")

    # Extremos de cada linea de busqueda y origen de las flechas, en el sistema
    # estabilizado. En el render se pasan al fotograma de turno con su inversa.
    p_ini = np.array([[cx + t_lin[0] * np.cos(ang), f + t_lin[0] * np.sin(ang)]
                      for f in filas_est], np.float32)
    p_fin = np.array([[cx + t_lin[-1] * np.cos(ang), f + t_lin[-1] * np.sin(ang)]
                      for f in filas_est], np.float32)
    x_flecha = cx + t_lin[0] * np.cos(ang) + 200
    p_flecha = np.array([[x_flecha, f + (x_flecha - cx) * np.tan(ang)] for f in filas_est],
                        np.float32)

    def a_panel(p, iv):
        """Punto del sistema estabilizado -> pixel del panel de salida."""
        x = iv[0, 0] * p[0] + iv[0, 1] * p[1] + iv[0, 2]
        y = iv[1, 0] * p[0] + iv[1, 1] * p[1] + iv[1, 2]
        return int(round(x * ESC_SALIDA)), int(round((y - r0) * ESC_SALIDA))

    t0 = time.perf_counter()
    cap = cv2.VideoCapture(a.video)
    for k in range(n):
        ok, fr = cap.read()
        if not ok:
            break
        panel = cv2.resize(fr[r0:r1], (pw, ph), interpolation=cv2.INTER_AREA)
        w = int(np.argmin(np.abs(centros - k)))     # ventana cuyo centro cae mas cerca
        iv = inversas[k]

        for i in range(n_est):
            v = V[w, i]
            col = color_velocidad(v)
            pi, pf = a_panel(p_ini[i], iv), a_panel(p_fin[i], iv)
            # La linea de busqueda: tenue, para ver de donde sale cada numero. Las de
            # contorno van punteadas porque ahi no se mide nada, se impone v = 0.
            if es_contorno[i]:
                for xa in range(pi[0], pf[0], 40):
                    ya = pi[1] + (pf[1] - pi[1]) * (xa - pi[0]) // max(pf[0] - pi[0], 1)
                    cv2.line(panel, (xa, ya), (xa + 20, ya), (200, 200, 200), 1, cv2.LINE_AA)
            else:
                cv2.line(panel, pi, pf, (255, 255, 255), 1, cv2.LINE_AA)

            # La flecha: longitud proporcional a la velocidad, direccion la impuesta por
            # ANGULO_FLUJO (STIV no mide direccion, la recibe como configuracion).
            px, py = a_panel(p_flecha[i], iv)
            if np.isfinite(v) and v > 0.01:
                lx = int(v * PX_POR_MS * np.cos(ang))
                ly = int(v * PX_POR_MS * np.sin(ang))
                grosor = 3 if MEDIDA[w, i] else 2
                cv2.arrowedLine(panel, (px, py), (px + lx, py + ly), col, grosor,
                                cv2.LINE_AA, tipLength=0.12)
                texto(panel, f"{v:.2f}", (px + lx + 12, py + ly + 5), 0.52, col, 2)
            # El estado de la vertical, que no se ve en el modulo de la flecha: circulo
            # blanco = medida, cuadro naranja = rellenada, cuadro negro = contorno.
            if es_contorno[i]:
                cv2.rectangle(panel, (px - 5, py - 5), (px + 5, py + 5), (30, 30, 30), -1)
                cv2.rectangle(panel, (px - 5, py - 5), (px + 5, py + 5), (255, 255, 255), 1)
            elif MEDIDA[w, i]:
                cv2.circle(panel, (px, py), 5, (255, 255, 255), -1)
                cv2.circle(panel, (px, py), 5, (20, 20, 20), 1)
            else:
                cv2.rectangle(panel, (px - 6, py - 6), (px + 6, py + 6), (0, 165, 255), -1)
                cv2.rectangle(panel, (px - 6, py - 6), (px + 6, py + 6), (20, 20, 20), 1)
            texto(panel, f"{i}", (px - 32, py + 5), 0.5, (230, 230, 230), 1)

        lienzo = np.zeros((ch, cw, 3), np.uint8)
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ph] = panel

        texto(lienzo, "Sile Main Canal - STIV en ventana movil sobre el video completo",
              (16, 30), 0.72, (255, 255, 255), 2)
        texto(lienzo, f"ventana {VENTANA/fps:.1f} s   alfa = {ALFA}   "
                      f"escala {escala*1000:.3f} mm/px",
              (cw - 520, 30), 0.55, (170, 170, 170), 1)

        # Barra de color: sin ella los colores de las flechas no significan nada.
        bx, by, bw_, bh_ = cw - 400, ch - 34, 260, 14
        for j in range(bw_):
            c = PALETA[int(255 * j / (bw_ - 1))]
            cv2.line(lienzo, (bx + j, by), (bx + j, by + bh_),
                     tuple(int(x) for x in c), 1)
        cv2.rectangle(lienzo, (bx, by), (bx + bw_, by + bh_), (90, 90, 90), 1)
        texto(lienzo, "0", (bx - 14, by + 12), 0.45, (170, 170, 170), 1)
        texto(lienzo, f"{V_COLOR_MAX:.1f} m/s", (bx + bw_ + 8, by + 12), 0.45,
              (170, 170, 170), 1)

        y_pie = ALTO_CABECERA + ph
        vm = v_mediana[w]
        q = Q[w]
        texto(lienzo, f"t = {k/fps:5.2f} s", (16, y_pie + 32), 0.7, (255, 255, 255), 2)
        texto(lienzo, f"v superficial mediana = {vm:.3f} m/s" if np.isfinite(vm)
              else "v superficial mediana = --", (200, y_pie + 32), 0.7, (120, 220, 255), 2)
        texto(lienzo, f"Q = {q:.3f} m3/s" if np.isfinite(q) else "Q = --",
              (640, y_pie + 32), 0.7, (150, 255, 150), 2)
        texto(lienzo, "circulo = vertical medida   cuadro naranja = rellenada por "
                      "interpolacion   cuadro negro = contorno, v = 0 impuesta",
              (16, y_pie + 62), 0.48, (170, 170, 170), 1)
        texto(lienzo, "la direccion de las flechas no se mide: es el ANGULO_FLUJO que "
                      "STIV recibe como configuracion",
              (16, y_pie + 84), 0.48, (140, 140, 140), 1)
        vw.write(lienzo)
        if (k + 1) % 100 == 0:
            print(f"  {k+1}/{n} fotogramas")

    vw.release()
    cap.release()
    print(f"  render en {time.perf_counter()-t0:.1f} s")
    recodificar_h264(salida)
    print(f"\nListo: {salida} ({salida.stat().st_size/1e6:.1f} MB, {n/fps:.1f} s)")

    # Las series por ventana, para poder rehacer cualquier grafica sin volver a medir.
    csv_out = salida.with_name("velocidad_ventanas.csv")
    with open(csv_out, "w", newline="", encoding="utf-8") as f:
        esc = csv.writer(f)
        esc.writerow(["ventana", "frame_centro", "t_s"]
                     + [f"v{i}_ms" for i in range(n_est)]
                     + [f"medida{i}" for i in range(n_est)]
                     + ["v_mediana_ms", "Q_m3s"])
        for w in range(len(inicios)):
            esc.writerow([w, int(centros[w]), round(centros[w] / fps, 3)]
                         + [round(float(x), 4) if np.isfinite(x) else "" for x in V[w]]
                         + [int(x) for x in MEDIDA[w]]
                         + [round(float(v_mediana[w]), 4) if np.isfinite(v_mediana[w]) else "",
                            round(float(Q[w]), 4) if np.isfinite(Q[w]) else ""])
    print(f"Series por ventana en: {csv_out}")


if __name__ == "__main__":
    main()
