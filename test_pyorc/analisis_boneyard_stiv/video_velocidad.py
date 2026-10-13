"""Video de la velocidad superficial por STIV sobre el video entero, en tiempo real.

Que hace
--------
Repite el STIV del notebook (`Boneyard_STIV_pipeline.ipynb`) en ventanas temporales
deslizantes a lo largo del video completo y dibuja el resultado sobre las DOS
vistas a la vez: la imagen original de la camara y el plano de agua rectificado.
En cada una se dibuja lo mismo -- las lineas de busqueda de las 21 estaciones, una
flecha por estacion con la velocidad instantanea y su valor al lado -- de modo que
se puede comprobar de un vistazo que lo medido cae donde uno cree.

Las dos vistas hacen falta aqui, al reves que en el caso SMC. Alli la camara es
cenital, la escala ya es uniforme y el fotograma ES el plano de agua, asi que un
solo panel basta. Aqui la camara es oblicua: se mide en la rectificada, porque es
donde una longitud vale lo mismo en todas partes, y la original esta para juzgar.

Tiempo real
-----------
El video de salida tiene UN fotograma por cada fotograma de entrada, a los fps del
original, de modo que se reproduce a la velocidad real del rio. La medida no se
rehace en cada uno: cada fotograma toma la de la ventana cuyo centro le queda mas
cerca. Antes el video salia a fps/PASO y se veia acelerado, que enganaba sobre lo
rapido que va el agua.

Unidades
--------
La rectificacion se construye con el horizonte del plano de agua y una focal
supuesta, asi que es una AFINIDAD del plano real: escala por igual todas las
longitudes de una misma direccion, luego la velocidad sale correcta salvo una
constante global desconocida. Se reporta en alturas de camara por segundo, unidad
estable frente a `ESC` y a los fps, pero no metrica: falta un ancho real.

Constantes compartidas con el notebook
--------------------------------------
La geometria (V1, FOCAL, el recorte del plano, ESC), DS, el numero de estaciones y
los umbrales de control de calidad son LOS MISMOS que en el notebook. Estan
duplicados aqui a proposito para que el script sea autonomo: si se cambian alli hay
que cambiarlos aqui.

Uso:
    python video_velocidad.py                      # video por defecto, entero
    python video_velocidad.py --video RUTA.mp4 --salida salidas/otro.mp4
    python video_velocidad.py --frames 300         # solo los primeros 300 fotogramas
"""
import argparse
import csv
import os
import time

import cv2
import numpy as np

import escritor_video as ev

# ===========================================================================================
#  >>> AJUSTABLE <<<  Geometria de la escena. IDENTICA a la Parte 2 del notebook.
# ===========================================================================================
# V1 sale de las hiladas de mamposteria de los dos muros; FOCAL solo afecta al aspecto,
# porque una homografia que manda el horizonte al infinito es una afinidad del plano.
V1 = (653.0, -30.9)          # punto de fuga longitudinal, px
FOCAL = 640.0                # focal supuesta, px; cosmetica
ANCHO_IMG, ALTO_IMG = 1280, 720

# >>> AJUSTABLE <<< recorte del plano de agua, en alturas de camara
XMIN, XMAX = -2.10, 1.85     # transversal: alcanza los dos muros
YMIN, YMAX = 0.40, 2.80      # longitudinal: solo el campo cercano, donde hay textura
ESC = 450.0                  # px de salida por altura de camara

# ===========================================================================================
#  >>> AJUSTABLE <<<  Muestreo, tensor y control de calidad. IDENTICOS a las Partes 3, 4 y 4b.
# ===========================================================================================
DS = 5                       # paso espacial del STI; deja las trazas cerca de 45 grados
N_EST = 21                   # estaciones transversales
BLOQUE = 48                  # bloque del tensor de estructura
COH_MIN = 0.40               # coherencia minima; mas laxo que el caso SMC porque
                             # aqui la textura es de espuma fina, no de tracer grueso
CONTRASTE_MIN = 1.5          # desviacion temporal minima (niveles de gris). Es el
                             # filtro que descarta los muros: una estructura estatica
                             # da coherencia ~1 con velocidad 0 y el umbral de
                             # coherencia la aprueba en vez de rechazarla.
COBERTURA_MIN = 0.60         # fraccion de la linea que la camara realmente ve. Laxo
                             # a proposito: el tensor ya descarta bloque a bloque lo
                             # que cae fuera de campo, asi que exigir 0.90 aqui solo
                             # servia para perder las estaciones junto a los muros,
                             # que son las que dan la forma del perfil.

# ===========================================================================================
#  >>> AJUSTABLE <<<  Lo unico propio de este script: la ventana movil
# ===========================================================================================
# Fotogramas por medida (~4 s). Compromiso central: mas corta da mas resolucion temporal
# pero trazas mas cortas y menos bloques del tensor.
VENTANA = 96
# Fotogramas entre medidas consecutivas. NO es la cadencia del video de salida: el video
# se escribe fotograma a fotograma a los fps originales y cada uno toma la medida de la
# ventana cuyo centro le queda mas cerca.
PASO = 3
# ===========================================================================================

# los videos no estan en el workspace: son el data release del USGS, 4.7 GB, y
# viven donde se descomprimieron. Ruta absoluta a proposito.
DIR_VIDEOS = r'C:\Users\Sergio\Desktop\Boneyardcreek\boneyardcreek_video'
RUTA_VIDEO = os.path.join(DIR_VIDEOS, '03337000_bullet_20180610-082000.mp4')

# --- Presentacion -------------------------------------------------------------------------
ALTO_PANEL = 520             # las dos vistas se escalan a esta altura comun
HUECO = 22                   # separacion entre paneles y margen lateral
PX_POR_UNIDAD = 520          # pixeles de flecha (ya en el panel) por cada altura de camara/s
ALTO_CABECERA = 46
ALTO_PIE = 112


# ------------------------------------------------------------------------------- geometria
def homografia():
    """Imagen -> salida rectificada. Con balanceo nulo el horizonte del plano de
    agua es la horizontal por V1, de donde sale el cabeceo; la componente x de V1
    da la guinada, que se compensa para que el canal quede vertical."""
    cx, cy = ANCHO_IMG / 2, ALTO_IMG / 2
    theta = np.arctan((cy - V1[1]) / FOCAL)
    K = np.array([[FOCAL, 0, cx], [0, FOCAL, cy], [0, 0, 1.0]])
    R = np.array([[1, 0, 0],
                  [0, -np.sin(theta), -np.cos(theta)],
                  [0, np.cos(theta), -np.sin(theta)]])
    t = [0, np.cos(theta), np.sin(theta)]          # altura de camara = 1
    g2i = K @ np.column_stack([R[:, 0], R[:, 1], t])
    d = R.T @ np.linalg.inv(K) @ np.array([V1[0], V1[1], 1.0])
    psi = np.arctan2(d[0], d[1])
    rot = np.array([[np.cos(psi), np.sin(psi), 0],
                    [-np.sin(psi), np.cos(psi), 0], [0, 0, 1.0]])
    s = np.array([[ESC, 0, -XMIN * ESC], [0, -ESC, YMAX * ESC], [0, 0, 1.0]])
    return s @ np.linalg.inv(g2i @ np.linalg.inv(rot))


# --------------------------------------------------------------------- tensor por bloques
def velocidad(sti, cobertura):
    """Velocidad (px de salida por fotograma) y coherencia de un trozo de STI, por
    bloques solapados combinados con mediana ponderada por coherencia. Un tensor
    global dejaria que un parche brillante dictara la respuesta.

    Convenio: fila = fotograma, columna = muestra cada DS px a lo largo del flujo.
    Una particula a v px/fotograma avanza v/DS columnas por fila, luego el angulo
    theta de la traza medido desde el eje de columnas cumple tan(theta) = DS/v.
    """
    if sti.shape[0] < BLOQUE or sti.shape[1] < BLOQUE:
        return np.nan, 0.0
    img = sti.astype(np.float32)
    gy, gx = np.gradient(img)
    k = (BLOQUE, BLOQUE)
    jxx = cv2.boxFilter(gx * gx, -1, k, normalize=False)
    jyy = cv2.boxFilter(gy * gy, -1, k, normalize=False)
    jxy = cv2.boxFilter(gx * gy, -1, k, normalize=False)
    h = BLOQUE // 2
    p = BLOQUE // 2                                 # 50% de solape
    fi = np.arange(h, img.shape[0] - h, p)
    co = np.arange(h, img.shape[1] - h, p)
    if not len(fi) or not len(co):
        return np.nan, 0.0
    ii, jj = np.meshgrid(fi, co, indexing='ij')
    a, b, c = jxx[ii, jj], jyy[ii, jj], jxy[ii, jj]
    ok = cobertura[jj] > 0.99
    tr = a + b
    val = ok & (tr > 1e-9)
    if val.sum() < 2:
        return np.nan, 0.0
    a, b, c, tr = a[val], b[val], c[val], tr[val]
    dif = np.sqrt(np.maximum((a - b) ** 2 + 4 * c * c, 0.0))
    coh = (dif / tr) ** 2
    ang = 0.5 * np.arctan2(2 * c, a - b) + np.pi / 2
    o = np.argsort(ang)
    ang, coh = ang[o], coh[o]
    ac = np.cumsum(coh)
    th = ang[np.searchsorted(ac, ac[-1] / 2)]       # mediana ponderada
    tn = np.tan(th)
    v = DS / tn if abs(tn) > 1e-6 else np.nan
    return float(v), float(np.median(coh))


# ---------------------------------------------------------------------------------- dibujo
PALETA = cv2.applyColorMap(np.arange(256, dtype=np.uint8).reshape(-1, 1),
                           cv2.COLORMAP_TURBO).reshape(-1, 3)


def color_velocidad(v, lo, hi):
    """Color BGR de una velocidad. Gris si no hay medida.

    Se mapea sobre el rango real de los datos, no sobre [0, vmax]: el abanico de
    velocidades de una seccion es estrecho y anclar el cero desperdicia casi toda
    la paleta. Por eso la barra de color lleva sus dos extremos rotulados.
    """
    if not np.isfinite(v):
        return (120, 120, 120)
    i = int(np.clip((abs(v) - lo) / max(hi - lo, 1e-9), 0, 1) * 255)
    return tuple(int(x) for x in PALETA[i])


def texto(img, s, org, escala=0.5, col=(255, 255, 255), grosor=1):
    """Texto con reborde negro: sobre el agua el blanco solo no se lee."""
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, escala, (0, 0, 0), grosor + 2,
                cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, escala, col, grosor, cv2.LINE_AA)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--video', default=RUTA_VIDEO)
    ap.add_argument('--salida', default=os.path.join('salidas', 'velocidad_tiempo_real.mp4'))
    ap.add_argument('--frames', type=int, default=0, help='0 = todo el video')
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.salida) or '.', exist_ok=True)
    i2o = homografia()
    o2i = np.linalg.inv(i2o)
    ow, oh = int((XMAX - XMIN) * ESC), int((YMAX - YMIN) * ESC)
    cols = (np.linspace(0.04, 0.96, N_EST) * ow).astype(int)
    filas = np.arange(0, oh, DS)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f'No se pudo abrir {args.video}')
    fps = cap.get(cv2.CAP_PROP_FPS)
    ntot = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    n = ntot if args.frames <= 0 else min(args.frames, ntot)
    print(f'{os.path.basename(args.video)}: {ntot} fotogramas a {fps:.2f} fps '
          f'({ntot/fps:.1f} s)')
    print(f'se procesan {n} fotogramas ({n/fps:.1f} s)')
    print(f'rectificada {ow}x{oh} px, {N_EST} estaciones, DS = {DS} px')
    print(f'ventana movil {VENTANA} fotogramas ({VENTANA/fps:.1f} s), medida cada {PASO}\n')

    # ---- pasada 1: construir el STI completo ---------------------------------------------
    print(f'Pasada 1/2 - rectificando y muestreando {n} fotogramas')
    t0 = time.time()
    sti = np.zeros((n, N_EST, len(filas)), np.float32)
    mascara = cv2.warpPerspective(np.full((ALTO_IMG, ANCHO_IMG), 255, np.uint8), i2o, (ow, oh))
    cobertura = (mascara[np.ix_(filas, cols)].T > 128).astype(np.float32)
    for k in range(n):
        ok, fr = cap.read()
        if not ok:
            n = k
            sti = sti[:n]
            break
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        r = cv2.warpPerspective(g, i2o, (ow, oh), flags=cv2.INTER_LINEAR)
        # Antialias ANTES de muestrear cada DS px: sin esto el submuestreo inventa
        # orientaciones. Es isotropo a proposito (ver el notebook).
        sti[k] = cv2.GaussianBlur(r, (0, 0), DS / 2)[np.ix_(filas, cols)].T
        if (k + 1) % 100 == 0:
            print(f'  {k+1}/{n} fotogramas')
    print(f'  STI de {n} fotogramas en {time.time()-t0:.1f} s\n')

    # normalizacion temporal por posicion: el reflejo especular es estatico en el
    # espacio, restarlo posicion a posicion lo elimina sin ningun parametro
    mu, sd = sti.mean(0), sti.std(0)
    contraste = np.median(sd, axis=1)                       # por estacion
    stin = (sti - mu) / np.maximum(sd, 1e-3)
    stin[:, sd < 1.0] = 0.0

    # ---- medidas en ventanas deslizantes -------------------------------------------------
    inicios = np.arange(0, max(n - VENTANA, 0) + 1, PASO)
    centros = inicios + VENTANA // 2
    V = np.full((len(inicios), N_EST), np.nan)
    C = np.zeros((len(inicios), N_EST))
    print(f'Midiendo {len(inicios)} ventanas x {N_EST} estaciones')
    t0 = time.time()
    for w, i0 in enumerate(inicios):
        for e in range(N_EST):
            v, c = velocidad(stin[i0:i0 + VENTANA, e, :], cobertura[e])
            V[w, e], C[w, e] = v, c
    print(f'  {len(inicios)} ventanas en {time.time()-t0:.1f} s\n')

    # ---- control de calidad ---------------------------------------------------------------
    est_ok = (cobertura.mean(1) >= COBERTURA_MIN) & (contraste >= CONTRASTE_MIN)
    print(f'Estaciones aceptadas por geometria y contraste: {est_ok.sum()} de {N_EST}')
    print(f'  {"est":>3s} {"x suelo":>8s} {"cobert":>7s} {"contraste":>10s}  estado')
    for e in range(N_EST):
        motivo = []
        if cobertura[e].mean() < COBERTURA_MIN:
            motivo.append('fuera de campo')
        if contraste[e] < CONTRASTE_MIN:
            motivo.append('estructura estatica (muro)')
        print(f'  {e:3d} {XMIN + cols[e]/ESC:+8.3f} {cobertura[e].mean():7.2f} '
              f'{contraste[e]:10.2f}  {"OK" if est_ok[e] else "RECHAZADA: " + ", ".join(motivo)}')

    # Las estaciones rechazadas NO se rellenan: sin seccion transversal que integrar,
    # rellenar solo inventaria datos. Es la diferencia con el caso SMC.
    MEDIDA = est_ok[None, :] & (C >= COH_MIN) & np.isfinite(V)
    V[~MEDIDA] = np.nan
    # en unidades de suelo por segundo (salvo constante global)
    Vg = V * fps / ESC
    if np.isfinite(Vg).any():
        vlo, vhi = np.nanpercentile(np.abs(Vg), [2, 98])
    else:
        vlo, vhi = 0.0, 1.0
    vmed = np.nanmedian(np.abs(Vg), axis=1)
    print(f'\nEstaciones medidas por ventana: mediana {np.median(MEDIDA.sum(1)):.0f} '
          f'de las {est_ok.sum()} admisibles')
    print(f'Rango de color: {vlo:.4f} - {vhi:.4f} alturas de camara/s')
    print(f'Velocidad mediana de la seccion: {np.nanmedian(vmed):.4f} alturas de camara/s '
          f'(rango {np.nanmin(vmed):.4f} - {np.nanmax(vmed):.4f})\n')

    # ---- pasada 2: render ------------------------------------------------------------------
    # Un fotograma de salida por fotograma de entrada, a los fps originales: tiempo real.
    eo = ALTO_PANEL / ALTO_IMG                     # escala del panel original
    er = ALTO_PANEL / oh                           # escala del panel rectificado
    pw_o, pw_r = int(ANCHO_IMG * eo), int(ow * er)
    x_o, x_r = HUECO, HUECO + pw_o + HUECO
    cw = x_r + pw_r + HUECO
    ch = ALTO_CABECERA + ALTO_PANEL + ALTO_PIE

    print(f'Pasada 2/2 - render de {n} fotogramas a {cw}x{ch}, {fps:.2f} fps (tiempo real)')
    vw = ev.abrir(args.salida, fps, (cw, ch))
    if not vw.isOpened():
        raise SystemExit('No se pudo abrir el escritor de video.')

    # Extremos de la linea de busqueda de cada estacion y origen de las flechas, en
    # coordenadas de la vista rectificada. Los mismos puntos se dibujan en las dos
    # vistas: en la rectificada tal cual, en la original pasados por o2i, que es donde
    # la perspectiva les da su inclinacion real.
    y_ini, y_fin = float(filas[0]), float(filas[-1])
    y_flecha = oh * 0.55
    p_rect = np.float32([[[c, y_ini], [c, y_fin], [c, y_flecha]] for c in cols])
    p_orig = cv2.perspectiveTransform(p_rect.reshape(1, -1, 2), o2i).reshape(N_EST, 3, 2)

    def en_rect(p):
        return int(round(p[0] * er)), int(round(p[1] * er))

    def en_orig(p):
        return int(round(p[0] * eo)), int(round(p[1] * eo))

    t0 = time.time()
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    for k in range(n):
        ok, fr = cap.read()
        if not ok:
            break
        rect = cv2.warpPerspective(fr, i2o, (ow, oh), flags=cv2.INTER_LINEAR)
        pano = cv2.resize(fr, (pw_o, ALTO_PANEL), interpolation=cv2.INTER_AREA)
        prec = cv2.resize(rect, (pw_r, ALTO_PANEL), interpolation=cv2.INTER_AREA)
        w = int(np.argmin(np.abs(centros - k)))     # ventana cuyo centro cae mas cerca

        for e in range(N_EST):
            v = Vg[w, e]
            col = color_velocidad(v, vlo, vhi)

            # La linea de busqueda: tenue, para ver de donde sale cada numero. Las
            # estaciones inadmisibles (muro o fuera de campo) van punteadas, porque ahi
            # no se mide nunca.
            for panel, mapear, pts in ((prec, en_rect, p_rect[e]), (pano, en_orig, p_orig[e])):
                pi, pf = mapear(pts[0]), mapear(pts[1])
                if est_ok[e]:
                    cv2.line(panel, pi, pf, (255, 255, 255), 1, cv2.LINE_AA)
                else:
                    for f in np.linspace(0, 1, 14):
                        xa = int(pi[0] + (pf[0] - pi[0]) * f)
                        ya = int(pi[1] + (pf[1] - pi[1]) * f)
                        cv2.circle(panel, (xa, ya), 1, (170, 170, 170), -1)

            # La flecha: longitud proporcional a la velocidad, direccion la del flujo.
            # En la rectificada el flujo es vertical por construccion; en la original la
            # flecha se obtiene proyectando su punta, no rotandola, para que la
            # perspectiva la incline sola.
            if np.isfinite(v):
                largo = abs(v) * PX_POR_UNIDAD / er     # en px de la rectificada
                signo = -1 if v < 0 else 1              # v < 0 = se aleja de la camara
                base_r = p_rect[e, 2]
                punta_r = np.float32([base_r[0], base_r[1] + signo * largo])
                punta_o = cv2.perspectiveTransform(
                    punta_r.reshape(1, 1, 2), o2i).reshape(2)
                for panel, mapear, base, punta in (
                        (prec, en_rect, base_r, punta_r),
                        (pano, en_orig, p_orig[e, 2], punta_o)):
                    b, p = mapear(base), mapear(punta)
                    cv2.arrowedLine(panel, b, p, col, 3, cv2.LINE_AA, tipLength=0.18)
                    # Las puntas quedan casi a la misma altura y las etiquetas se pisan
                    # unas a otras: se alternan dos alturas segun la paridad de la estacion.
                    dy = 4 if e % 2 == 0 else -14
                    texto(panel, f'{abs(v):.3f}', (p[0] + 7, p[1] + dy), 0.44, col, 1)

            # El estado de la estacion: circulo blanco = medida en esta ventana, cuadro
            # naranja = admisible pero sin coherencia suficiente aqui, cuadro negro =
            # rechazada de raiz (muro o fuera de campo).
            for panel, mapear, pts in ((prec, en_rect, p_rect[e]), (pano, en_orig, p_orig[e])):
                px, py = mapear(pts[2])
                if not est_ok[e]:
                    cv2.rectangle(panel, (px - 5, py - 5), (px + 5, py + 5), (30, 30, 30), -1)
                    cv2.rectangle(panel, (px - 5, py - 5), (px + 5, py + 5), (255, 255, 255), 1)
                elif MEDIDA[w, e]:
                    cv2.circle(panel, (px, py), 5, (255, 255, 255), -1)
                    cv2.circle(panel, (px, py), 5, (20, 20, 20), 1)
                else:
                    cv2.rectangle(panel, (px - 6, py - 6), (px + 6, py + 6), (0, 165, 255), -1)
                    cv2.rectangle(panel, (px - 6, py - 6), (px + 6, py + 6), (20, 20, 20), 1)

        lienzo = np.zeros((ch, cw, 3), np.uint8)
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ALTO_PANEL, x_o:x_o + pw_o] = pano
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ALTO_PANEL, x_r:x_r + pw_r] = prec

        texto(lienzo, 'Boneyard Creek - vista original de la camara', (x_o, 30), 0.66,
              (255, 255, 255), 2)
        texto(lienzo, 'plano de agua rectificado (aqui se mide)', (x_r, 30), 0.66,
              (255, 255, 255), 2)
        texto(lienzo, f'ventana {VENTANA/fps:.1f} s   DS = {DS} px   '
                      f'coherencia min = {COH_MIN}', (cw - 430, 30), 0.5, (170, 170, 170), 1)

        # Barra de color: sin ella los colores de las flechas no significan nada. Rotula
        # sus dos extremos porque el rango no empieza en cero.
        bx, by, bw_, bh_ = cw - 330, ch - 34, 220, 14
        for j in range(bw_):
            c = PALETA[int(255 * j / (bw_ - 1))]
            cv2.line(lienzo, (bx + j, by), (bx + j, by + bh_), tuple(int(x) for x in c), 1)
        cv2.rectangle(lienzo, (bx, by), (bx + bw_, by + bh_), (90, 90, 90), 1)
        texto(lienzo, f'{vlo:.2f}', (bx - 42, by + 12), 0.45, (170, 170, 170), 1)
        texto(lienzo, f'{vhi:.2f} alt/s', (bx + bw_ + 8, by + 12), 0.45, (170, 170, 170), 1)

        y_pie = ALTO_CABECERA + ALTO_PANEL
        vm = vmed[w]
        texto(lienzo, f't = {k/fps:6.2f} s', (x_o, y_pie + 32), 0.7, (255, 255, 255), 2)
        texto(lienzo, f'v mediana de la seccion = {vm:.4f} alturas de camara/s'
              if np.isfinite(vm) else 'v mediana de la seccion = --',
              (x_o + 200, y_pie + 32), 0.7, (120, 220, 255), 2)
        texto(lienzo, f'estaciones medidas: {int(MEDIDA[w].sum())} de {N_EST}',
              (x_o + 930, y_pie + 32), 0.7, (150, 255, 150), 2)
        texto(lienzo, 'circulo = estacion medida   cuadro naranja = sin coherencia en esta '
                      'ventana   cuadro negro = rechazada (muro o fuera de campo)',
              (x_o, y_pie + 62), 0.48, (170, 170, 170), 1)
        texto(lienzo, 'la direccion de las flechas no se mide: es la del flujo que la '
                      'rectificacion impone.  Unidades afines: correctas salvo una '
                      'constante global, no hay metros.',
              (x_o, y_pie + 86), 0.48, (140, 140, 140), 1)
        vw.write(lienzo)
        if (k + 1) % 100 == 0:
            print(f'  {k+1}/{n} fotogramas')

    vw.release()
    cap.release()
    print(f'  render en {time.time()-t0:.1f} s')
    print(f'\nListo: {args.salida} ({os.path.getsize(args.salida)/1e6:.1f} MB, {n/fps:.1f} s)')

    # Las series por ventana, para poder rehacer cualquier grafica sin volver a medir.
    csv_out = os.path.join(os.path.dirname(args.salida) or '.', 'velocidad_ventanas.csv')
    with open(csv_out, 'w', newline='', encoding='utf-8') as f:
        esc = csv.writer(f)
        esc.writerow(['ventana', 'frame_centro', 't_s']
                     + [f'v{e}_alt_s' for e in range(N_EST)]
                     + [f'medida{e}' for e in range(N_EST)]
                     + ['v_mediana_alt_s'])
        for w in range(len(inicios)):
            esc.writerow([w, int(centros[w]), round(centros[w] / fps, 3)]
                         + [round(float(x), 5) if np.isfinite(x) else '' for x in Vg[w]]
                         + [int(x) for x in MEDIDA[w]]
                         + [round(float(vmed[w]), 5) if np.isfinite(vmed[w]) else ''])
    print(f'Series por ventana en: {csv_out}')


if __name__ == '__main__':
    main()
