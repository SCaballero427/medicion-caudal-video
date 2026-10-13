"""STIV sobre el video original de Hommerich (Geul, NL), con rectificacion metrica.

Que hace
--------
Mide la velocidad superficial por STIV (Space-Time Image Velocimetry) sobre el
video ORIGINAL de la camara -- no sobre el ortomosaico que trae el dataset -- y
dibuja el resultado sobre las DOS vistas a la vez: la imagen de la camara y el
plano de agua rectificado. Integra el perfil con la seccion transversal del
propio dataset y da un caudal instantaneo.

Que lo separa de los dos casos STIV anteriores
----------------------------------------------
* Frente a `analisis_boneyard_stiv/`: alli la rectificacion se construia con el
  horizonte y una focal supuesta, o sea una AFINIDAD del plano, y las velocidades
  salian en alturas de camara por segundo. Aqui el dataset trae los intrinsecos,
  los coeficientes de distorsion y 6 GCPs con coordenadas RTK, asi que la pose se
  resuelve entera con `solvePnP` y la rectificacion es METRICA: hay metros, y por
  tanto hay m3/s.
* Frente a `analisis_USGS_SMC_stiv/`: alli la camara es cenital y el fotograma ES
  el plano de agua, asi que un solo panel basta y no hay nada que rectificar.
  Aqui la camara es oblicua y con barril fuerte (k1 = -0.48), de modo que se mide
  en la rectificada -- que es donde una longitud vale lo mismo en todas partes --
  y la original esta para juzgar que lo medido cae donde uno cree.

La cadena de geometria, paso a paso
-----------------------------------
1. `solvePnP` con los 6 GCPs (pixel <-> XYZ en EPSG:28992), los intrinsecos y la
   distorsion del `cam_config`: da la pose completa de la camara. Se resuelve en
   coordenadas locales (restando el centroide de los GCPs) porque en coordenadas
   RD New absolutas, del orden de 3e5, la condicion numerica es mala.
2. La superficie del agua es el plano z = z_0 + (h_a - h_ref) = 151.385 m, con
   la lectura de escala `h_a` que el propio dataset usa en su script de proceso.
3. La seccion transversal (24 puntos WGS84 con cota) se reproyecta a EPSG:28992 y
   se le ajusta una recta: su direccion define el eje transversal, y la
   perpendicular es la linea de flujo sobre la que se construye cada STI.
4. El raster rectificado se construye en ese sistema (transversal, flujo) a
   RESOLUCION m/px. Cada punto del raster se lleva a pixel con `projectPoints`,
   que SI incluye la distorsion; por eso el mapa se calcula punto a punto una vez
   y se aplica con `remap`, en vez de usar una homografia, que no podria.

Con esa construccion cada estacion es una COLUMNA del raster rectificado y su STI
sale de leer esa columna cada DS px, fotograma a fotograma.

El sentido del flujo no se impone
---------------------------------
La direccion de la linea de busqueda si es configuracion (la normal a la seccion),
como en todo STIV. El SENTIDO no: sale del signo de la pendiente que devuelve el
tensor. Se toma el signo mayoritario de la seccion como sentido aguas abajo y las
verticales que salen al reves quedan como velocidad negativa, que es lo fisico si
hay un remolino.

Uso
---
    python video_velocidad.py                 # video entero (122 fotogramas, 4 s)
    python video_velocidad.py --frames 60
"""

import argparse
import csv
import json
import time
from pathlib import Path

import cv2
import numpy as np
import pyproj

import escritor_video as ev

# ===========================================================================================
#  Datos de entrada. Viven fuera del workspace, ruta absoluta a proposito.
# ===========================================================================================
DIR_DATOS = Path(r"C:\Users\Sergio\Desktop\datasets vision velocimetria\Hommerich")
DIR_PYORC = DIR_DATOS / "hommerich_20241010_081717_pyorc_data.zip"
ARCHIVO_VIDEO = DIR_DATOS / "20241010_081717.mp4"
ARCHIVO_CAMCONF = DIR_PYORC / "cam_config_gcp1.json"
ARCHIVO_SECCION = DIR_PYORC / "cs1_ordered.geojson"

DIR_CASO = Path(__file__).resolve().parent

# ===========================================================================================
#  >>> AJUSTABLE <<<  Nivel de agua
# ===========================================================================================
# Lectura de la escala en el momento del video, en cm de la regla del limnimetro.
# (obtenido del dataset: es el --h_a del script process_20241010_081717_h_a.sh). Con
# h_ref y z_0 del cam_config sale la cota de la lamina de agua. El otro script del
# dataset, sin --h_a, deja el agua por debajo del talweg de la seccion: no es el bueno.
H_A = 93.345

# ===========================================================================================
#  >>> AJUSTABLE <<<  Geometria del muestreo
# ===========================================================================================
RESOLUCION = 0.01        # m/px del raster rectificado. La misma que usa el cam_config
                         # del dataset, de modo que la vista rectificada es comparable
                         # con el ortomosaico que el propio dataset publica.
LARGO_LINEA = 5.0        # m de linea de busqueda, centrada en la seccion. Con 1.2 m/s
                         # el agua recorre 4 s de video en 4.8 m: la linea tiene que ser
                         # al menos asi de larga para que una particula la cruce entera.
MARGEN_RASTER = 0.6      # m de aire alrededor, para que la seccion no toque el borde

# Desplazamiento de la seccion RIO ABAJO, en metros. La seccion levantada cae en el borde
# superior del cuadro y las verticales de la orilla lejana se quedan sin linea que medir;
# bajandola hacia la camara entran todas. Positivo = aguas abajo (+e_v), que es el sentido
# que la propia medida deduce del signo del tensor.
#
# El precio hay que decirlo: los calados siguen siendo los de la seccion levantada, asi que
# desplazarla supone que el cauce es prismatico en ese tramo. Para la velocidad no cambia
# nada -- se mide donde se dibuja -- pero el caudal pasa a ser aproximado en esa medida.
#
# 2.5 m es el minimo que deja TODAS las lineas medibles con cobertura 1.00 (a 0 m las
# cuatro de la orilla lejana veian entre el 42 % y el 75 % de su linea). Mas lejos no
# aporta: a 3.5 m solo cambia el punto de orilla, que no se mide. Las dos verticales que
# siguen rechazadas lo son por contraste (0.50 y 1.04), no por campo: estan sobre la
# orilla, con 21 y 25 cm de calado y sin trazador, y eso no lo arregla mover la seccion.
DESPLAZAMIENTO_SECCION = 2.5

# Estimacion a ojo de la velocidad. De aqui sale DS, el paso de muestreo del STI, y no
# se teclea directamente: DS = V*dt deja las estelas a 45 grados, que es donde el error
# angular pesa menos (d(u)/u = d(theta)/(sin.cos), minimo en 45). La curva es plana
# alrededor de 45, asi que un error del 30 % en esta estimacion casi no importa.
V_ESPERADA = 1.2

# ===========================================================================================
#  >>> AJUSTABLE <<<  Tensor de estructura y control de calidad
# ===========================================================================================
LADO_BLOQUE = 32         # px de bloque del tensor. Mas pequeno que el 64 del caso SMC
                         # porque la ventana temporal tambien lo es: con 72 fotogramas,
                         # bloques de 64 solo dejarian una fila y la mediana ponderada
                         # dejaria de serlo.
SIGMA_DERIVADA = 1.5
COH_MIN_BLOQUE = 0.50
COH_MIN_ESTACION = 0.60  # criterio de aceptacion de una vertical. Mas laxo que el 0.70
                         # del caso SMC: las ventanas son de 2.4 s en vez de 5 s y las
                         # estelas son mas cortas.
CONTRASTE_MIN = 3.0      # desviacion temporal minima, en niveles de gris. Es el filtro
                         # que aprendio el caso Boneyard: una estructura estatica (aqui
                         # la orilla, o el cable que cruza la esquina inferior) da
                         # coherencia altisima con velocidad cero, y el umbral de
                         # coherencia la aprueba en vez de rechazarla. Medido en este
                         # video los valores son 1.06, 1.14, 2.28, 2.63 | 3.14, 3.81,
                         # 3.86, 3.99... o sea hay hueco, y las dos verticales del lado
                         # malo del hueco devolvian 0.06 y 0.03 m/s pegadas a una que da
                         # 0.65: el sintoma exacto. El umbral no es critico: ponerlo en
                         # 2.0 y admitirlas mueve Q un +1.4 %.
COBERTURA_MIN = 0.55     # fraccion de la linea que la camara ve de verdad. Laxo a
                         # proposito: la linea no se descarta por asomar fuera del
                         # cuadro, se RECORTA a su tramo visible (ver `tramo_visible`),
                         # asi que este umbral solo rechaza lo que ya no da para medir.
ALFA = 0.85              # velocidad media en la vertical / superficial. Es el valor
                         # estandar del USGS y ademas el v_corr que el propio dataset usa
                         # en su hommerich.yml, o sea fijado antes de mirar nada.
V_MAX_FISICA = 3.0 * V_ESPERADA   # cota de plausibilidad, a partir de la estimacion a
                                  # ojo y no de ninguna referencia

# ===========================================================================================
#  >>> AJUSTABLE <<<  Ventana movil, lo unico propio de este script
# ===========================================================================================
# El video entero son 122 fotogramas (4.1 s). La ventana es el compromiso central: mas
# corta da mas resolucion temporal pero estelas mas cortas y menos bloques del tensor.
VENTANA = 72             # fotogramas por medida (~2.4 s)
PASO = 2                 # fotogramas entre medidas. NO es la cadencia del video de
                         # salida: se escribe un fotograma por fotograma de entrada, a
                         # los fps originales, y cada uno toma la medida de la ventana
                         # cuyo centro le queda mas cerca.
# ===========================================================================================

# --- Presentacion -------------------------------------------------------------------------
ALTO_PANEL = 540
HUECO = 20
SEG_FLECHA = 1.0         # la flecha mide lo que el agua recorre en 1 s. Asi la misma
                         # flecha es fisicamente lo mismo en los dos paneles, y en el
                         # original la perspectiva la acorta sola.
V_COLOR_MAX = 1.8        # m/s a los que satura la paleta
ALTO_CABECERA = 46
ALTO_PIE = 112


# ------------------------------------------------------------------------------- geometria
def cargar_camara():
    """Pose completa de la camara a partir del cam_config del dataset.

    Devuelve una funcion mundo -> pixel que incluye la distorsion, mas la cota de la
    lamina de agua y el error de reproyeccion de los GCPs.
    """
    cfg = json.loads(Path(ARCHIVO_CAMCONF).read_text(encoding="utf-8"))
    K = np.array(cfg["camera_matrix"], float)
    D = np.array(cfg["dist_coeffs"], float).reshape(-1, 1)
    src = np.array(cfg["gcps"]["src"], float)
    dst = np.array(cfg["gcps"]["dst"], float)
    # h_ref y h_a son dos lecturas de la MISMA escala, asi que su diferencia es
    # directamente el ascenso de la lamina en metros sobre z_0.
    z_agua = float(cfg["gcps"]["z_0"]) + (H_A - float(cfg["gcps"]["h_ref"]))

    # Coordenadas locales: en RD New absolutas (~2e5, 3e5) la matriz normal de solvePnP
    # queda mal condicionada y la pose sale a varios metros de su sitio.
    origen = dst.mean(axis=0)
    obj = np.ascontiguousarray(dst - origen)

    # SQPNP en vez del iterativo por defecto: los 6 GCPs estan casi en un plano (20 cm de
    # desnivel en 12 m) y la inicializacion DLT del iterativo es inestable en ese caso.
    ok, rvec, tvec = cv2.solvePnP(obj, src, K, D, flags=cv2.SOLVEPNP_SQPNP)
    if not ok:
        raise SystemExit("solvePnP no convergio con los GCPs del cam_config")
    rvec, tvec = cv2.solvePnPRefineLM(obj, src, K, D, rvec, tvec)
    rep = cv2.projectPoints(obj, rvec, tvec, K, D)[0].reshape(-1, 2)
    err = np.linalg.norm(rep - src, axis=1)

    def mundo_a_pixel(pts_xy, z):
        """(N,2) en EPSG:28992 sobre el plano z -> (N,2) en pixeles del video."""
        pts = np.column_stack([pts_xy[:, 0], pts_xy[:, 1], np.full(len(pts_xy), z)])
        pts = np.ascontiguousarray(pts - origen)
        return cv2.projectPoints(pts, rvec, tvec, K, D)[0].reshape(-1, 2)

    return mundo_a_pixel, z_agua, err, cfg


def cargar_seccion(z_agua, desplazamiento=DESPLAZAMIENTO_SECCION):
    """Seccion transversal del dataset, reproyectada y puesta en el sistema del flujo.

    Devuelve la posicion transversal u de cada vertical, su calado, su punto en el
    mundo, y los versores transversal / de flujo. Las dos orillas se anaden como
    puntos interpolados con calado nulo: ahi no se mide, se impone v = 0.
    """
    gj = json.loads(Path(ARCHIVO_SECCION).read_text(encoding="utf-8"))
    lon, lat, z = np.array([f["geometry"]["coordinates"]
                            for f in gj["features"]], float).T
    tr = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:28992", always_xy=True)
    x, y = tr.transform(lon, lat)
    P = np.column_stack([x, y])

    mojado = z < z_agua
    if mojado.sum() < 3:
        raise SystemExit("la lamina de agua no cubre la seccion; revisar H_A")

    # Recta de la seccion por PCA sobre los puntos mojados: los de la orilla se alejan
    # de la alineacion y la torcerian.
    centro = P[mojado].mean(axis=0)
    _, _, vt = np.linalg.svd(P[mojado] - centro)
    e_u = vt[0] / np.linalg.norm(vt[0])
    if np.dot(P[-1] - P[0], e_u) < 0:          # orientada como el fichero, izq -> der
        e_u = -e_u
    e_v = np.array([-e_u[1], e_u[0]])          # normal: la linea de flujo

    u = (P - centro) @ e_u

    # Orillas: donde la cota corta el nivel del agua, entre la ultima vertical seca y la
    # primera mojada de cada extremo.
    idx = np.where(mojado)[0]
    i0, i1 = idx[0], idx[-1]
    bordes = []
    for a, b in ((i0 - 1, i0), (i1 + 1, i1)):
        if a < 0 or a >= len(z):               # la seccion empieza o acaba mojada
            continue
        f = (z_agua - z[b]) / (z[a] - z[b])
        bordes.append((u[b] + f * (u[a] - u[b]), P[b] + f * (P[a] - P[b])))

    u_est = np.concatenate([[bordes[0][0]], u[idx], [bordes[-1][0]]])
    prof = np.concatenate([[0.0], z_agua - z[idx], [0.0]])
    pts = np.vstack([bordes[0][1], P[idx], bordes[-1][1]])
    contorno = np.zeros(len(u_est), bool)
    contorno[0] = contorno[-1] = True

    # La seccion entera se traslada rio abajo. Se mueve tambien el origen del sistema, de
    # modo que las coordenadas u no cambian y el raster rectificado sigue centrado en ella.
    pts = pts + desplazamiento * e_v
    centro = centro + desplazamiento * e_v

    orden = np.argsort(u_est)
    return (u_est[orden], prof[orden], pts[orden], contorno[orden],
            centro, e_u, e_v, z_agua)


# ------------------------------------------------------------------ tensor de estructura
def tensor_estructura(bloque, sigma=SIGMA_DERIVADA):
    """Pendiente m (muestras/fotograma) y coherencia C de un trozo de STI.

    Autovector del autovalor menor del tensor del gradiente, que es la direccion a lo
    largo de las estelas. El mismo codigo que en los otros dos casos STIV.
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


def tramo_visible(mascara):
    """Tramo contiguo mas largo de una linea que la camara ve. Devuelve (j0, j1).

    Las verticales de la orilla lejana tienen un extremo de su linea fuera del cuadro:
    descartarlas enteras por eso perderia justo las que dan la forma del perfil, y
    quedarse con las muestras sueltas rompería la continuidad temporal que el tensor
    necesita. Se mide en el trozo seguido mas largo.
    """
    mejor = (0, 0)
    j = 0
    while j < len(mascara):
        if mascara[j]:
            k = j
            while k < len(mascara) and mascara[k]:
                k += 1
            if k - j > mejor[1] - mejor[0]:
                mejor = (j, k)
            j = k
        else:
            j += 1
    return mejor


def preparar_sti(sti):
    """Quita el fondo estatico y el parpadeo global, y normaliza.

    Se aplica a cada ventana por separado: la media temporal que se resta tiene que ser
    la del tramo que se esta midiendo, si no el fondo que se elimina no es el que
    contamina esa ventana.
    """
    a = sti - sti.mean(axis=0, keepdims=True)   # fondo fijo de cada muestra
    a = a - a.mean(axis=1, keepdims=True)       # parpadeo de cada fotograma
    d = a.std()
    return a / d if d > 0 else a


# ---------------------------------------------------------------------------------- dibujo
PALETA = cv2.applyColorMap(np.arange(256, dtype=np.uint8).reshape(-1, 1),
                           cv2.COLORMAP_TURBO).reshape(-1, 3)


def color_velocidad(v):
    """Color BGR de una velocidad. Gris si no hay medida."""
    if not np.isfinite(v):
        return (120, 120, 120)
    i = int(np.clip(abs(v) / V_COLOR_MAX, 0, 1) * 255)
    return tuple(int(x) for x in PALETA[i])


def texto(img, s, org, escala=0.5, col=(255, 255, 255), grosor=1):
    """Texto con reborde negro: sobre el agua el blanco solo no se lee."""
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, escala, (0, 0, 0), grosor + 2,
                cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, escala, col, grosor, cv2.LINE_AA)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", default=str(ARCHIVO_VIDEO))
    ap.add_argument("--salida", default=str(DIR_CASO / "salidas" / "velocidad_tiempo_real.mp4"))
    ap.add_argument("--frames", type=int, default=0, help="0 = el video entero")
    ap.add_argument("--desplazamiento", type=float, default=DESPLAZAMIENTO_SECCION,
                    help="m de traslado de la seccion rio abajo (+e_v)")
    a = ap.parse_args()

    salida = Path(a.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)

    # --- camara y seccion ---------------------------------------------------------------
    mundo_a_pixel, z_agua, err_gcp, cfg = cargar_camara()
    u_est, prof, pts_est, contorno, centro, e_u, e_v, z_agua = cargar_seccion(
        z_agua, a.desplazamiento)
    n_est = len(u_est)
    ancho_mojado = u_est[-1] - u_est[0]
    area = float(np.trapezoid(prof, u_est))

    print(f"Camara: {cfg['width']}x{cfg['height']}, focal {cfg['camera_matrix'][0][0]:.1f} px, "
          f"k1 = {cfg['dist_coeffs'][0][0]:+.4f}")
    print(f"  reproyeccion de los 6 GCPs: mediana {np.median(err_gcp):.2f} px, "
          f"maxima {err_gcp.max():.2f} px")
    print(f"Lamina de agua en z = {z_agua:.3f} m (z_0 {cfg['gcps']['z_0']} + h_a {H_A} "
          f"- h_ref {cfg['gcps']['h_ref']})")
    print(f"Seccion: {n_est} verticales, ancho mojado {ancho_mojado:.2f} m, "
          f"area {area:.3f} m2, calado maximo {prof.max():.2f} m")
    print(f"  desplazada {a.desplazamiento:+.2f} m rio abajo respecto a la levantada\n")

    # --- video --------------------------------------------------------------------------
    cap = cv2.VideoCapture(a.video)
    if not cap.isOpened():
        raise SystemExit(f"No se pudo abrir {a.video}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    ancho_img = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto_img = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    n = n_total if a.frames <= 0 else min(a.frames, n_total)
    dt = 1.0 / fps

    # --- raster rectificado --------------------------------------------------------------
    # Sistema (u = transversal a lo largo de la seccion, v = linea de flujo). Cada vertical
    # es una COLUMNA del raster, de modo que su STI sale de leer esa columna cada DS px.
    u0 = u_est[0] - MARGEN_RASTER
    u1 = u_est[-1] + MARGEN_RASTER
    v1 = LARGO_LINEA / 2 + MARGEN_RASTER
    ancho_r = int(round((u1 - u0) / RESOLUCION))
    alto_r = int(round(2 * v1 / RESOLUCION))

    jj, ii = np.meshgrid(np.arange(ancho_r), np.arange(alto_r))
    U = u0 + (jj + 0.5) * RESOLUCION
    V = v1 - (ii + 0.5) * RESOLUCION                     # fila 0 arriba = v maxima
    XY = (centro[None, None, :] + U[..., None] * e_u[None, None, :]
          + V[..., None] * e_v[None, None, :])
    px = mundo_a_pixel(XY.reshape(-1, 2), z_agua).reshape(alto_r, ancho_r, 2)
    mapx = np.ascontiguousarray(px[..., 0], np.float32)
    mapy = np.ascontiguousarray(px[..., 1], np.float32)
    dentro = ((mapx >= 0) & (mapx < ancho_img - 1) & (mapy >= 0) & (mapy < alto_img - 1))

    # DS sale de V_ESPERADA, no se teclea: deja las estelas cerca de 45 grados.
    ds = max(int(round(V_ESPERADA * dt / RESOLUCION)), 1)
    ds_m = ds * RESOLUCION
    n_mu = int(LARGO_LINEA / ds_m)
    fila_c = alto_r // 2
    filas = fila_c - (np.arange(n_mu) - (n_mu - 1) // 2) * ds   # j creciente = +e_v
    cols = np.round((u_est - u0) / RESOLUCION).astype(int)
    filas = np.clip(filas, 0, alto_r - 1)
    cols = np.clip(cols, 0, ancho_r - 1)
    cobertura = dentro[np.ix_(filas, cols)].T.astype(float)     # (n_est, n_mu)

    print(f"{Path(a.video).name}: {ancho_img}x{alto_img}, {n_total} fotogramas a "
          f"{fps:.3f} fps ({n_total/fps:.1f} s)")
    print(f"se procesan {n} fotogramas ({n/fps:.1f} s)")
    print(f"rectificada {ancho_r}x{alto_r} px a {RESOLUCION*1000:.0f} mm/px "
          f"({u1-u0:.2f} x {2*v1:.2f} m)")
    print(f"DS = {ds} px = {ds_m*100:.1f} cm, {n_mu} muestras por linea "
          f"({n_mu*ds_m:.2f} m)")
    print(f"ventana movil {VENTANA} fotogramas ({VENTANA/fps:.1f} s), medida cada {PASO}\n")

    # --- pasada 1: rectificar y muestrear -------------------------------------------------
    print(f"Pasada 1/2 - rectificando y muestreando {n} fotogramas")
    t0 = time.perf_counter()
    sti = np.zeros((n, n_est, n_mu), np.float32)
    for k in range(n):
        ok, fr = cap.read()
        if not ok:
            n = k
            sti = sti[:n]
            break
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        r = cv2.remap(g, mapx, mapy, cv2.INTER_LINEAR)
        # Antialias ANTES de muestrear cada DS px: sin esto el submuestreo inventa
        # orientaciones. Es isotropo a proposito (ver el notebook del caso SMC).
        sti[k] = cv2.GaussianBlur(r, (0, 0), ds / 2)[np.ix_(filas, cols)].T
    print(f"  STI de {n} fotogramas en {time.perf_counter()-t0:.1f} s")

    # Cada linea se recorta a su tramo visible, y el contraste se mide solo ahi: fuera
    # del cuadro el `remap` devuelve negro, que rebajaria el contraste de una vertical
    # que en su parte visible tiene textura de sobra.
    tramos = [tramo_visible(cobertura[i] > 0.99) for i in range(n_est)]
    frac = np.array([(j1 - j0) / n_mu for j0, j1 in tramos])
    # Una vertical enteramente fuera del cuadro daria un tramo vacio y no habria linea
    # que dibujar; se le deja la linea nominal, que es lo que se ve punteado.
    tramos = [(0, n_mu) if j1 <= j0 else (j0, j1) for j0, j1 in tramos]
    contraste = np.array([np.median(sti[:, i, j0:j1].std(axis=0)) if j1 > j0 else 0.0
                          for i, (j0, j1) in enumerate(tramos)])
    # Ademas del umbral relativo, un minimo absoluto: con menos de dos bloques del tensor
    # a lo largo del tiempo la mediana ponderada no tiene nada que promediar.
    largo_min = 2 * LADO_BLOQUE
    admisible = ((~contorno) & (frac >= COBERTURA_MIN)
                 & (np.array([j1 - j0 for j0, j1 in tramos]) >= largo_min)
                 & (contraste >= CONTRASTE_MIN))
    print(f"  verticales admisibles por cobertura y contraste: {admisible.sum()} de "
          f"{int((~contorno).sum())} medibles")
    for i in range(n_est):
        j0, j1 = tramos[i]
        if contorno[i]:
            estado = "orilla, v = 0 impuesta"
        elif admisible[i]:
            estado = "OK"
        else:
            motivo = []
            if frac[i] < COBERTURA_MIN or (j1 - j0) < largo_min:
                motivo.append("fuera de campo")
            if contraste[i] < CONTRASTE_MIN:
                motivo.append("sin textura (estructura estatica)")
            estado = "RECHAZADA: " + ", ".join(motivo)
        print(f"    {i:2d}  u = {u_est[i]:+6.2f} m  calado {prof[i]:4.2f} m  "
              f"tramo visible {frac[i]:4.2f} ({(j1-j0)*ds_m:4.2f} m)  "
              f"contraste {contraste[i]:6.2f}  {estado}")
    print()

    # --- medida en ventanas deslizantes ---------------------------------------------------
    inicios = np.arange(0, max(n - VENTANA, 0) + 1, PASO)
    centros = inicios + VENTANA // 2
    VEL = np.full((len(inicios), n_est), np.nan)      # final: medida o rellenada
    MEDIDA = np.zeros((len(inicios), n_est), bool)
    COH = np.full((len(inicios), n_est), np.nan)
    Q = np.full(len(inicios), np.nan)
    angulos = []

    print(f"Midiendo {len(inicios)} ventanas x {int(admisible.sum())} verticales")
    t0 = time.perf_counter()
    crudo = np.full((len(inicios), n_est), np.nan)
    for w, i0 in enumerate(inicios):
        for i in range(n_est):
            if not admisible[i]:
                continue
            j0, j1 = tramos[i]
            m, c = medir_sti(preparar_sti(sti[i0:i0 + VENTANA, i, j0:j1]))
            COH[w, i] = c
            if np.isfinite(m):
                crudo[w, i] = m * ds_m / dt
                angulos.append(np.degrees(np.arctan2(1.0, abs(m))))
    print(f"  {len(inicios)} ventanas en {time.perf_counter()-t0:.1f} s")

    # El SENTIDO del flujo no es configuracion: sale del signo mayoritario de la pendiente.
    signo = 1.0 if np.nansum(np.sign(crudo)) >= 0 else -1.0
    crudo *= signo
    ang_med = np.median(angulos) if angulos else np.nan
    print(f"  angulo mediano de las estelas: {ang_med:.1f} grados "
          f"(el optimo es 45; se ajusta con V_ESPERADA)")
    print(f"  sentido del flujo deducido del signo: {'+' if signo > 0 else '-'}e_v\n")

    # Control de calidad y relleno, igual que en el caso SMC: se aceptan las verticales
    # con coherencia suficiente y velocidad plausible, y las demas se rellenan por
    # interpolacion lineal sobre las aceptadas mas los ceros impuestos de las orillas.
    # No hay modelo de pared: rellenar sin modelo es lo honesto, y su coste se conoce.
    n_absurdas = 0
    for w in range(len(inicios)):
        v = crudo[w].copy()
        valida = (admisible & (COH[w] >= COH_MIN_ESTACION) & np.isfinite(v)
                  & (np.abs(v) <= V_MAX_FISICA))
        n_absurdas += int((admisible & (COH[w] >= COH_MIN_ESTACION)
                           & (np.abs(v) > V_MAX_FISICA)).sum())
        v_final = np.where(contorno, 0.0, v)
        faltan = np.where(~(valida | contorno))[0]
        if valida.sum() >= 2 and len(faltan):
            apoyo = valida | contorno
            v_final[faltan] = np.interp(u_est[faltan], u_est[apoyo],
                                        np.where(contorno, 0.0, v)[apoyo])
        elif len(faltan):
            v_final[faltan] = np.nan
        VEL[w] = v_final
        MEDIDA[w] = valida
        if np.isfinite(v_final).all():
            Q[w] = float(np.trapezoid(ALFA * v_final * prof, u_est))

    v_mediana = np.nanmedian(np.where(contorno, np.nan, VEL), axis=1)
    print(f"Verticales aceptadas por ventana: mediana {np.median(MEDIDA.sum(1)):.0f} "
          f"de las {int(admisible.sum())} admisibles")
    print(f"Descartadas por la cota de {V_MAX_FISICA:.2f} m/s pese a tener coherencia "
          f"suficiente: {n_absurdas}")
    for i in range(n_est):
        if contorno[i]:
            continue
        print(f"  vertical {i:2d} (u = {u_est[i]:+6.2f} m): aceptada en "
              f"{100*MEDIDA[:, i].mean():5.1f} % de las ventanas, "
              f"v mediana {np.nanmedian(VEL[:, i]):6.3f} m/s")
    print(f"\nVelocidad superficial mediana de la seccion: "
          f"{np.nanmedian(v_mediana):.4f} m/s")
    print(f"Caudal instantaneo: mediana {np.nanmedian(Q):.4f} m3/s, "
          f"q05-q95 {np.nanpercentile(Q, 5):.4f} - {np.nanpercentile(Q, 95):.4f}, "
          f"rango {np.nanmin(Q):.4f} - {np.nanmax(Q):.4f} m3/s\n")

    # --- pasada 2: render ------------------------------------------------------------------
    # Un fotograma de salida por fotograma de entrada, a los fps originales: tiempo real.
    eo = ALTO_PANEL / alto_img                    # escala del panel original
    er = ALTO_PANEL / alto_r                      # escala del panel rectificado
    pw_o, pw_r = int(ancho_img * eo), int(ancho_r * er)
    x_o, x_r = HUECO, HUECO + int(ancho_img * eo) + HUECO
    cw = x_r + pw_r + HUECO
    ch = ALTO_CABECERA + ALTO_PANEL + ALTO_PIE

    print(f"Pasada 2/2 - render de {n} fotogramas a {cw}x{ch}, {fps:.2f} fps (tiempo real)")
    vw = ev.abrir(str(salida), fps, (cw, ch))
    if not vw.isOpened():
        raise SystemExit("No se pudo abrir el escritor de video.")

    # Extremos de cada linea de busqueda y base de las flechas, en los dos sistemas. La
    # camara es fija, asi que se proyectan una sola vez.
    # Se dibuja el tramo que de verdad se midio, no la linea nominal de LARGO_LINEA: en
    # las verticales de la orilla lejana no son lo mismo.
    t_mu = (np.arange(n_mu) - (n_mu - 1) // 2) * ds_m
    mundo_ini = pts_est + np.array([t_mu[tramos[i][0]] for i in range(n_est)])[:, None] * e_v
    mundo_fin = pts_est + np.array([t_mu[tramos[i][1] - 1] for i in range(n_est)])[:, None] * e_v
    mundo_base = pts_est - 0.35 * LARGO_LINEA / 2 * e_v * signo
    pix_ini = mundo_a_pixel(mundo_ini, z_agua)
    pix_fin = mundo_a_pixel(mundo_fin, z_agua)
    pix_base = mundo_a_pixel(mundo_base, z_agua)

    def a_rect(p_mundo):
        """Punto del mundo -> pixel del panel rectificado."""
        d = p_mundo - centro
        return (int(round(((d @ e_u) - u0) / RESOLUCION * er)),
                int(round((v1 - (d @ e_v)) / RESOLUCION * er)))

    def a_orig(p_pix):
        return int(round(p_pix[0] * eo)), int(round(p_pix[1] * eo))

    t0 = time.perf_counter()
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    for k in range(n):
        ok, fr = cap.read()
        if not ok:
            break
        rect = cv2.remap(fr, mapx, mapy, cv2.INTER_LINEAR)
        pano = cv2.resize(fr, (pw_o, ALTO_PANEL), interpolation=cv2.INTER_AREA)
        prec = cv2.resize(rect, (pw_r, ALTO_PANEL), interpolation=cv2.INTER_AREA)
        w = int(np.argmin(np.abs(centros - k)))     # ventana cuyo centro cae mas cerca

        for i in range(n_est):
            v = VEL[w, i]
            col = color_velocidad(v)

            # La linea de busqueda: tenue, para ver de donde sale cada numero. Punteada
            # donde no se mide (orilla, fuera de campo o sin textura).
            for panel, pi, pf in ((prec, a_rect(mundo_ini[i]), a_rect(mundo_fin[i])),
                                  (pano, a_orig(pix_ini[i]), a_orig(pix_fin[i]))):
                if admisible[i]:
                    cv2.line(panel, pi, pf, (255, 255, 255), 1, cv2.LINE_AA)
                else:
                    for f in np.linspace(0, 1, 16):
                        cv2.circle(panel, (int(pi[0] + (pf[0] - pi[0]) * f),
                                           int(pi[1] + (pf[1] - pi[1]) * f)),
                                   1, (170, 170, 170), -1)

            # La flecha mide lo que el agua recorre en SEG_FLECHA segundos, o sea es una
            # longitud del mundo real: en la original la perspectiva la acorta sola, sin
            # rotarla a mano, porque se proyecta su punta.
            if np.isfinite(v) and abs(v) > 0.01:
                punta_m = mundo_base[i] + v * SEG_FLECHA * signo * e_v
                punta_p = mundo_a_pixel(punta_m[None, :], z_agua)[0]
                grosor = 3 if MEDIDA[w, i] else 2
                for panel, b, p in ((prec, a_rect(mundo_base[i]), a_rect(punta_m)),
                                    (pano, a_orig(pix_base[i]), a_orig(punta_p))):
                    cv2.arrowedLine(panel, b, p, col, grosor, cv2.LINE_AA, tipLength=0.16)
                    dy = 5 if i % 2 == 0 else -12
                    texto(panel, f"{v:.2f}", (p[0] + 8, p[1] + dy), 0.46, col, 1)

            # Estado de la vertical: circulo blanco = medida, cuadro naranja = rellenada,
            # cuadro negro = orilla con v = 0 impuesta o vertical inadmisible.
            for panel, pb in ((prec, a_rect(mundo_base[i])), (pano, a_orig(pix_base[i]))):
                if not admisible[i]:
                    cv2.rectangle(panel, (pb[0] - 5, pb[1] - 5), (pb[0] + 5, pb[1] + 5),
                                  (30, 30, 30), -1)
                    cv2.rectangle(panel, (pb[0] - 5, pb[1] - 5), (pb[0] + 5, pb[1] + 5),
                                  (255, 255, 255), 1)
                elif MEDIDA[w, i]:
                    cv2.circle(panel, pb, 5, (255, 255, 255), -1)
                    cv2.circle(panel, pb, 5, (20, 20, 20), 1)
                else:
                    cv2.rectangle(panel, (pb[0] - 6, pb[1] - 6), (pb[0] + 6, pb[1] + 6),
                                  (0, 165, 255), -1)
                    cv2.rectangle(panel, (pb[0] - 6, pb[1] - 6), (pb[0] + 6, pb[1] + 6),
                                  (20, 20, 20), 1)

        lienzo = np.zeros((ch, cw, 3), np.uint8)
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ALTO_PANEL, x_o:x_o + pw_o] = pano
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ALTO_PANEL, x_r:x_r + pw_r] = prec

        texto(lienzo, "Hommerich (Geul, NL) - vista original de la camara", (x_o, 30),
              0.66, (255, 255, 255), 2)
        texto(lienzo, "plano de agua rectificado (aqui se mide)", (x_r, 30), 0.66,
              (255, 255, 255), 2)
        texto(lienzo, f"ventana {VENTANA/fps:.1f} s   DS = {ds} px   alfa = {ALFA}",
              (cw - 360, 30), 0.5, (170, 170, 170), 1)

        # Barra de color: sin ella los colores de las flechas no significan nada.
        bx, by, bw_, bh_ = cw - 330, ch - 32, 230, 14
        for j in range(bw_):
            c = PALETA[int(255 * j / (bw_ - 1))]
            cv2.line(lienzo, (bx + j, by), (bx + j, by + bh_), tuple(int(x) for x in c), 1)
        cv2.rectangle(lienzo, (bx, by), (bx + bw_, by + bh_), (90, 90, 90), 1)
        texto(lienzo, "0", (bx - 14, by + 12), 0.45, (170, 170, 170), 1)
        texto(lienzo, f"{V_COLOR_MAX:.1f} m/s", (bx + bw_ + 8, by + 12), 0.45,
              (170, 170, 170), 1)

        y_pie = ALTO_CABECERA + ALTO_PANEL
        vm, q = v_mediana[w], Q[w]
        texto(lienzo, f"t = {k/fps:5.2f} s", (x_o, y_pie + 32), 0.7, (255, 255, 255), 2)
        texto(lienzo, f"v superficial mediana = {vm:.3f} m/s" if np.isfinite(vm)
              else "v superficial mediana = --", (x_o + 190, y_pie + 32), 0.7,
              (120, 220, 255), 2)
        texto(lienzo, f"Q = {q:.3f} m3/s" if np.isfinite(q) else "Q = --",
              (x_o + 640, y_pie + 32), 0.7, (150, 255, 150), 2)
        texto(lienzo, f"seccion del dataset: {ancho_mojado:.2f} m de ancho mojado, "
                      f"{area:.2f} m2, calado max {prof.max():.2f} m",
              (x_o + 900, y_pie + 32), 0.55, (200, 200, 200), 1)
        texto(lienzo, "circulo = vertical medida en esta ventana   cuadro naranja = "
                      "admisible pero sin coherencia aqui   cuadro negro = orilla (v = 0 "
                      "impuesta) o vertical inadmisible.  Las dos ultimas se rellenan por "
                      "interpolacion lineal.",
              (x_o, y_pie + 62), 0.48, (170, 170, 170), 1)
        texto(lienzo, "la LINEA de flujo es configuracion (la normal a la seccion); el "
                      "SENTIDO sale del signo que mide el tensor.  La flecha mide lo que "
                      f"el agua recorre en {SEG_FLECHA:.0f} s.",
              (x_o, y_pie + 86), 0.48, (140, 140, 140), 1)
        vw.write(lienzo)

    vw.release()
    cap.release()
    print(f"  render en {time.perf_counter()-t0:.1f} s")
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
                         + [round(float(x), 4) if np.isfinite(x) else "" for x in VEL[w]]
                         + [int(x) for x in MEDIDA[w]]
                         + [round(float(v_mediana[w]), 4) if np.isfinite(v_mediana[w]) else "",
                            round(float(Q[w]), 4) if np.isfinite(Q[w]) else ""])
    print(f"Series por ventana en: {csv_out}")

    # La configuracion entera, congelada, para poder repetir la medida.
    cfg_out = salida.with_name("config_stiv_hommerich.json")
    cfg_out.write_text(json.dumps({
        "video": str(a.video), "fotogramas": int(n), "fps": fps,
        "h_a": H_A, "z_agua_m": z_agua,
        "desplazamiento_seccion_m": a.desplazamiento,
        "reproyeccion_gcp_px": {"mediana": float(np.median(err_gcp)),
                                "maxima": float(err_gcp.max())},
        "resolucion_m_px": RESOLUCION, "largo_linea_m": LARGO_LINEA,
        "v_esperada_ms": V_ESPERADA, "ds_px": int(ds), "ds_m": ds_m,
        "angulo_mediano_estelas_grados": float(ang_med),
        "lado_bloque": LADO_BLOQUE, "coh_min_bloque": COH_MIN_BLOQUE,
        "coh_min_estacion": COH_MIN_ESTACION, "contraste_min": CONTRASTE_MIN,
        "cobertura_min": COBERTURA_MIN, "v_max_fisica_ms": V_MAX_FISICA,
        "alfa": ALFA, "ventana": VENTANA, "paso": PASO,
        "seccion": {"n_verticales": int(n_est), "ancho_mojado_m": float(ancho_mojado),
                    "area_m2": area, "calado_max_m": float(prof.max()),
                    "u_m": [round(float(x), 4) for x in u_est],
                    "calado_m": [round(float(x), 4) for x in prof]},
        "resultado": {"v_superficial_mediana_ms": float(np.nanmedian(v_mediana)),
                      "Q_mediana_m3s": float(np.nanmedian(Q)),
                      "Q_q05_m3s": float(np.nanpercentile(Q, 5)),
                      "Q_q95_m3s": float(np.nanpercentile(Q, 95))},
    }, indent=2), encoding="utf-8")
    print(f"Configuracion congelada en: {cfg_out}")


if __name__ == "__main__":
    main()
