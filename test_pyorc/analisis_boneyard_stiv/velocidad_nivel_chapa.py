"""Igual que `velocidad_nivel.py`, pero midiendo el nivel sobre la chapa RECTIFICADA.

Que cambia
----------
`velocidad_nivel.py` muestrea una linea recta sobre la mira en la imagen original. Aqui
se rectifica primero la cara de la chapa -- cuatro esquinas a un rectangulo, el mismo
truco que la vista del agua -- y se mide sobre ella. Eso trae dos cosas:

1. **Una escala interna.** En la chapa rectificada las graduaciones quedan igualmente
   espaciadas, asi que su periodo se mide por autocorrelacion: **5.37 px de imagen por
   marca**. Sobre la linea sin rectificar no era fiable, porque la perspectiva comprime
   las marcas de forma desigual a lo largo de la chapa. Con ese periodo, el nivel se
   reporta ademas en GRADUACIONES, y el dia que se sepa cuanto vale una graduacion de
   esta mira la conversion a pies es una multiplicacion.
2. **Se puede ver lo que se mide.** El recuadro de la esquina es la chapa rectificada con
   la linea de agua detectada encima.

Por que el nivel NO sale de contar marcas
-----------------------------------------
Se probo. Contar las marcas visibles por encima del agua da 6 valores distintos en todo
el video (26 a 31) con una dispersion de **0.87 marcas = 4.7 px**, mientras que la
oscilacion fisica del agua es de **0.74 px = 0.14 marcas**. La cuenta fluctua seis veces
mas que la señal, y esa fluctuacion no es nivel: es el detector encendiendo y apagando
marcas dudosas segun la iluminacion y la espuma. Ademas *visible* depende de la luz --
el tercio superior de la chapa esta en sombra y sus marcas no se detectan nunca.

Asi que el nivel lo sigue midiendo el **cruce al 50 %** entre el gris de la chapa seca y
el del agua, interpolado entre muestras, que es continuo y diez veces mas fino. La cuenta
de marcas se calcula igualmente y se guarda en el CSV como diagnostico, para que se pueda
comprobar todo lo anterior, pero no manda sobre nada.

Contar marcas si seria la herramienta correcta para comparar ENTRE videos, donde el agua
se mueve muchas marcas y la cuantizacion deja de importar.

Uso
---
    python velocidad_nivel_chapa.py                  # video entero
    python velocidad_nivel_chapa.py --frames 200     # prueba corta
"""
import argparse
import csv
import json
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import escritor_video as ev
import stiv_interactivo as si
import velocidad_nivel as vn

RUTA_SALIDA = os.path.join(si.DIR_CASO, "salidas", "velocidad_nivel_chapa.mp4")

# ===========================================================================================
#  >>> AJUSTABLE <<<  La chapa de la mira
# ===========================================================================================
# Cuatro esquinas de la CARA de la chapa en la imagen original, en el orden
# arriba-izq, arriba-der, abajo-der, abajo-izq. Medidas a mano sobre el fotograma 300 de
# 03337000_bullet_20171118-095500.mp4. Si se cambia de encuadre hay que volver a medirlas.
CHAPA = [[1205.0, 266.0], [1228.0, 269.0], [1192.0, 472.0], [1172.0, 469.0]]
# Tamaño del rectificado. El alto va sobreescalado ~2x respecto a los ~206 px que mide la
# chapa en la imagen: no añade informacion, pero deja el cruce del agua y las marcas sobre
# una rejilla mas fina, que es lo que interpola el detector.
CHAPA_W, CHAPA_H = 60, 420
# Prolongacion por debajo del extremo inferior de la chapa, en fraccion de su alto, para
# que el corte con el agua caiga dentro aunque el nivel baje.
CHAPA_EXTRA = 0.10
# Franja de columnas del rectificado que se promedia, en fraccion del ancho. No es 0-1
# porque el cuadrilatero, medido a ojo, muerde unos pixeles de muro por el lado izquierdo:
# medido sobre el tramo seco, las columnas 0-10 dan 34-45 niveles de gris (muro) frente a
# los 79-96 de la chapa. Incluirlas rebajaba el contraste chapa/agua de 71 a 38 y empeoraba
# la deteccion del borde.
FRANJA_COL = (0.30, 0.95)

# Limites en los que se busca el periodo de las graduaciones, en filas rectificadas. El
# medido es 11; la horquilla solo esta para que la autocorrelacion no se enganche al
# primer lag ni a un armonico lejano.
PERIODO_MIN, PERIODO_MAX = 6, 25

# --- Presentacion --------------------------------------------------------------------------
ALTO_PANEL = si.ALTO_PANEL
HUECO = si.HUECO
ALTO_CABECERA = si.ALTO_CABECERA
ALTO_PIE = 114
INSET_W, INSET_H = 46, 322        # recuadro de la chapa rectificada dentro de la vista original


def homografia_chapa():
    """Cara de la chapa -> rectangulo. Devuelve tambien px de imagen por fila rectificada."""
    q = np.float32(CHAPA)
    alto = int(round(CHAPA_H * (1 + CHAPA_EXTRA)))
    M = cv2.getPerspectiveTransform(
        q, np.float32([[0, 0], [CHAPA_W, 0], [CHAPA_W, CHAPA_H], [0, CHAPA_H]]))
    largo_img = 0.5 * (np.hypot(*(q[3] - q[0])) + np.hypot(*(q[2] - q[1])))
    return M, alto, float(largo_img / CHAPA_H)


def perfiles_chapa(video, n, M, alto):
    """Brillo medio de cada fila de la chapa rectificada, fotograma a fotograma."""
    cap = cv2.VideoCapture(video)
    P = np.zeros((n, alto), np.float32)
    for k in range(n):
        ok, fr = cap.read()
        if not ok:
            P = P[:k]
            break
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        r = cv2.warpPerspective(g, M, (CHAPA_W, alto), flags=cv2.INTER_LINEAR)
        # Media a lo ancho de la chapa: las graduaciones la cruzan de lado a lado, asi que
        # promediar en esa direccion sube la señal sin desdibujarlas. Solo la franja
        # central, para no meter el muro que el cuadrilatero roza por la izquierda.
        c0 = int(FRANJA_COL[0] * CHAPA_W)
        c1 = int(FRANJA_COL[1] * CHAPA_W)
        P[k] = r.astype(np.float32)[:, c0:c1].mean(1)
    cap.release()
    return P


def realzar(perfil, sigma=10.0):
    """Quita la iluminacion de fondo y deja solo el rayado de las graduaciones."""
    fondo = cv2.GaussianBlur(perfil.reshape(-1, 1), (0, 0), sigma).ravel()
    return perfil - fondo


def periodo_marcas(mu, i_agua):
    """Periodo de las graduaciones, en filas, por autocorrelacion del tramo seco.

    Se mide sobre la parte iluminada y por encima del agua, que es donde las marcas se
    resuelven; el tercio superior de la chapa esta en sombra y no aporta.
    """
    a = max(int(0.15 * len(mu)), 0)
    b = max(i_agua - 20, a + 60)
    seg = realzar(mu[a:b])
    ac = np.correlate(seg, seg, "full")[len(seg) - 1:]
    return int(np.argmax(ac[PERIODO_MIN:PERIODO_MAX]) + PERIODO_MIN)


def contar_marcas(perfil, hasta, periodo):
    """Numero de graduaciones detectadas por encima de la fila `hasta`.

    Minimos locales del perfil realzado, separados al menos 0.7 periodos y con un salto
    minimo de 2 niveles de gris. Es solo diagnostico: no interviene en el nivel.
    """
    s = realzar(perfil)[:max(int(hasta), 3)]
    if len(s) < 3:
        return 0
    sep = max(int(0.7 * periodo), 1)
    n = 0
    ultimo = -10 ** 6
    for i in range(1, len(s) - 1):
        if s[i] <= s[i - 1] and s[i] < s[i + 1] and i - ultimo >= sep:
            j0, j1 = max(i - sep, 0), min(i + sep + 1, len(s))
            if s[j0:j1].max() - s[i] >= 2.0:
                n += 1
                ultimo = i
    return n


def detectar_nivel_chapa(P):
    """Fila del corte agua-chapa en cada fotograma. Mismo criterio que `velocidad_nivel`.

    La banda de busqueda la marca la desviacion tipica temporal: en el borde, esa fila
    salta entre chapa iluminada y agua oscura y su desviacion se dispara. Alrededor del
    maximo se toman los grises de la chapa seca y del agua, y el borde es el cruce al 50 %
    entre ambos, interpolado entre filas.
    """
    n_f = P.shape[1]
    sd, mu = P.std(0), P.mean(0)
    borde = int(0.08 * n_f)
    i_pico = borde + int(np.argmax(sd[borde:n_f - borde]))
    sep, anc = int(0.04 * n_f), int(0.18 * n_f)
    seca = float(np.median(mu[max(i_pico - anc, 0):max(i_pico - sep, 1)]))
    moja = float(np.median(mu[min(i_pico + sep, n_f - 2):min(i_pico + anc, n_f - 1)]))
    umbral = 0.5 * (seca + moja)
    b0 = max(i_pico - int(0.14 * n_f), 1)
    b1 = min(i_pico + int(0.14 * n_f), n_f - 2)
    nucleo = np.ones(9) / 9.0
    pos = np.full(len(P), np.nan)
    for k, perfil in enumerate(P):
        g = np.convolve(perfil, nucleo, mode="same")
        cruces = np.where((g[b0:b1] >= umbral) & (g[b0 + 1:b1 + 1] < umbral))[0]
        if len(cruces):
            i = b0 + int(cruces[-1])
            d = (g[i] - umbral) / max(g[i] - g[i + 1], 1e-6)
            pos[k] = i + d
    return pos, dict(i_pico=i_pico, seca=seca, moja=moja, umbral=umbral,
                     sd_pico=float(sd[i_pico]))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", default=si.RUTA_VIDEO)
    ap.add_argument("--salida", default=RUTA_SALIDA)
    ap.add_argument("--config", default=si.RUTA_CONFIG)
    ap.add_argument("--frames", type=int, default=0, help="0 = todo el video")
    a = ap.parse_args()

    cfg = dict(si.CFG_INICIAL)
    if os.path.exists(a.config):
        cfg.update(json.load(open(a.config, encoding="utf-8")))
        print(f"configuracion cargada de {a.config}")
    if cfg["cuadrilatero"] is None:
        raise SystemExit("La configuracion no tiene cuadrilatero: ajustalo con "
                         "stiv_interactivo.py")
    # Mismo muestreo del tensor que velocidad_nivel.py, por lo explicado alli: con 3
    # bloques por medida se caia el 20 % de las ventanas y lo que se tiraba eran medidas
    # buenas con coherencia justo por debajo del corte.
    print(f"muestreo del tensor: STI {vn.LARGO_STI} {cfg['unidad']}, bloque {vn.BLOQUE}, "
          f"coherencia minima {vn.COH_MIN}")
    cfg.update(largo_sti=vn.LARGO_STI, bloque=vn.BLOQUE, coh_min=vn.COH_MIN)

    cap = cv2.VideoCapture(a.video)
    if not cap.isOpened():
        raise SystemExit(f"No se pudo abrir {a.video}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    ntot = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto_img = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    n = ntot if a.frames <= 0 else min(a.frames, ntot)
    u = cfg["unidad"]
    GH, Q_ref = vn.gh_del_video(os.path.basename(a.video))

    i2o, ow, oh, caja = si.homografia(cfg)
    o2i = np.linalg.inv(i2o)
    centros, flujo, pts, n_mu = si.geometria_medida(cfg, caja)
    _, _, _, L_ = caja

    print(f"\n{os.path.basename(a.video)}: {ntot} fotogramas a {fps:.2f} fps "
          f"({ntot/fps:.1f} s); se procesan {n}")
    if GH is not None:
        print(f"referencia del release (solo rotulo): GH {GH:.2f} ft, Q {Q_ref:.0f} cfs")

    # --- pasada 1: velocidad ------------------------------------------------------------
    print(f"\nPasada 1/3 - rectificando el agua y muestreando las {cfg['n_est']} estaciones")
    t0 = time.time()
    sti, cob = si.construir_sti(a.video, cfg, 0, n, i2o, ow, oh, caja)
    n = sti.shape[0]
    stin, contraste = si.normalizar(sti)
    print(f"  STI de {n} fotogramas en {time.time()-t0:.1f} s")
    inicios, V, E = vn.medir_estaciones(stin, cob, cfg, fps)
    centros_t = inicios + cfg["ventana"] // 2

    perfil_v = np.nanmedian(V, axis=0)
    muro = np.isfinite(perfil_v) & (np.abs(perfil_v) < vn.FRAC_MURO * np.nanmedian(perfil_v))
    E[:, muro] = 3
    agua = ~muro
    print(f"\nEstaciones: {int(agua.sum())} de agua, {int(muro.sum())} de muro "
          f"({', '.join(str(i) for i in np.where(muro)[0]) or 'ninguna'})")
    Va = np.where(agua[None, :], V, np.nan)
    vmed = np.nanmedian(Va, axis=1)
    lo, hi = np.nanpercentile(np.abs(Va), [2, 98])
    hi = max(hi, lo + 1e-6)
    print(f"Velocidad mediana de la seccion (sin los muros): {np.nanmedian(vmed):.4f} {u}/s")
    print(f"Estados: medida {100*(E[:, agua]==1).mean():.1f} %, sostenida "
          f"{100*(E[:, agua]==2).mean():.1f} %, caida {100*(E[:, agua]==0).mean():.1f} %")

    # --- pasada 2: la chapa rectificada --------------------------------------------------
    print(f"\nPasada 2/3 - rectificando la chapa de la mira")
    t0 = time.time()
    M_ch, alto_ch, px_por_fila = homografia_chapa()
    P = perfiles_chapa(a.video, n, M_ch, alto_ch)
    n = min(n, P.shape[0])
    pos, info = detectar_nivel_chapa(P)
    periodo = periodo_marcas(P.mean(0), info["i_pico"])
    periodo_px = periodo * px_por_fila
    # El filtro de salpicaduras trabaja en px de imagen, asi que se le pasa la escala
    nivel, est_niv, fuera = vn.filtrar_nivel(pos, px_por_fila)
    ref_niv = np.nanmedian(nivel)
    niv_px = (ref_niv - nivel) * px_por_fila
    niv_gr = niv_px / periodo_px
    marcas = np.array([contar_marcas(P[k], nivel[k] if np.isfinite(nivel[k])
                                     else info["i_pico"], periodo) for k in range(n)])
    print(f"  {n} fotogramas en {time.time()-t0:.1f} s")
    print(f"  chapa rectificada {CHAPA_W}x{alto_ch} px para {CHAPA_H*px_por_fila:.0f} px de "
          f"imagen -> {px_por_fila:.4f} px de imagen por fila")
    print(f"  chapa seca {info['seca']:.1f}, agua {info['moja']:.1f}, umbral "
          f"{info['umbral']:.1f}; desviacion en el borde {info['sd_pico']:.1f}")
    print(f"  periodo de las graduaciones: {periodo} filas = {periodo_px:.2f} px de imagen")
    print(f"  detectado en {100*np.isfinite(pos[:n]).mean():.1f} % de los fotogramas; "
          f"{int(fuera[:n].sum())} salpicaduras descartadas, "
          f"{int((est_niv[:n]==2).sum())} sostenidas")
    print(f"  nivel: desviacion tipica {np.nanstd(niv_px[:n]):.2f} px = "
          f"{np.nanstd(niv_gr[:n]):.3f} graduaciones; q05-q95 "
          f"{np.nanpercentile(niv_px[:n],5):+.2f} a {np.nanpercentile(niv_px[:n],95):+.2f} px")
    print(f"  DIAGNOSTICO (no se usa) cuenta de marcas: mediana {np.median(marcas):.0f}, "
          f"rango {marcas.min()}-{marcas.max()}, desviacion {marcas.std():.2f} marcas "
          f"= {marcas.std()*periodo_px:.1f} px, {marcas.std()*periodo_px/max(np.nanstd(niv_px[:n]),1e-9):.1f}x "
          f"la oscilacion real")

    # --- pasada 3: render ------------------------------------------------------------------
    eo = ALTO_PANEL / alto_img
    er = ALTO_PANEL / oh
    pw_o, pw_r = int(ancho * eo), int(ow * er)
    x_o, x_r = HUECO, HUECO + pw_o + HUECO
    cw = x_r + pw_r + HUECO
    y_pie = ALTO_CABECERA + ALTO_PANEL
    ch = y_pie + ALTO_PIE

    print(f"\nPasada 3/3 - render de {n} fotogramas a {cw}x{ch}, {fps:.2f} fps (tiempo real)")
    os.makedirs(os.path.dirname(a.salida) or ".", exist_ok=True)
    vw = ev.abrir(a.salida, fps, (cw, ch))
    if not vw.isOpened():
        raise SystemExit("No se pudo abrir el escritor de video.")

    ext_r = np.float32([[pts[e, 0], pts[e, -1], centros[e]] for e in range(cfg["n_est"])])
    ext_o = cv2.perspectiveTransform(ext_r.reshape(1, -1, 2), o2i).reshape(-1, 3, 2)
    qch = np.float32(CHAPA)
    A_m = qch[0] + (qch[1] - qch[0]) * 0.5           # centro del borde superior
    B_m = qch[3] + (qch[2] - qch[3]) * 0.5           # centro del borde inferior
    dir_m = (B_m - A_m) / max(np.hypot(*(B_m - A_m)), 1e-9)
    perp_m = np.array([-dir_m[1], dir_m[0]])
    ix, iy = 14, 22                                   # esquina del recuadro de la chapa

    cap = cv2.VideoCapture(a.video)
    t0 = time.time()
    for k in range(n):
        ok, fr = cap.read()
        if not ok:
            break
        rect = cv2.warpPerspective(fr, i2o, (ow, oh), flags=cv2.INTER_LINEAR)
        pano = cv2.resize(fr, (pw_o, ALTO_PANEL), interpolation=cv2.INTER_AREA)
        prec = cv2.resize(rect, (pw_r, ALTO_PANEL), interpolation=cv2.INTER_AREA)
        w = int(np.argmin(np.abs(centros_t - k)))

        for e in range(cfg["n_est"]):
            v, est = V[w, e], E[w, e]
            col = si.color_velocidad(v, lo, hi)
            for panel, esc, p in ((prec, er, ext_r[e]), (pano, eo, ext_o[e])):
                p0 = (int(p[0][0] * esc), int(p[0][1] * esc))
                p1 = (int(p[1][0] * esc), int(p[1][1] * esc))
                if est == 3:
                    for f in np.linspace(0, 1, 10):
                        cv2.circle(panel, (int(p0[0] + (p1[0] - p0[0]) * f),
                                           int(p0[1] + (p1[1] - p0[1]) * f)), 1,
                                   (170, 170, 170), -1)
                else:
                    cv2.line(panel, p0, p1, (255, 255, 255), 1, cv2.LINE_AA)
            if np.isfinite(v) and est != 3:
                punta_r = centros[e] + flujo * (abs(v) / hi) * 0.45 * L_
                punta_o = cv2.perspectiveTransform(
                    punta_r.astype(np.float32).reshape(1, 1, 2), o2i).reshape(2)
                grosor = 3 if est == 1 else 2
                dy = 4 if e % 2 == 0 else -14
                for panel, esc, c0, c1 in ((prec, er, centros[e], punta_r),
                                           (pano, eo, ext_o[e][2], punta_o)):
                    b = (int(c0[0] * esc), int(c0[1] * esc))
                    p = (int(c1[0] * esc), int(c1[1] * esc))
                    cv2.arrowedLine(panel, b, p, col, grosor, cv2.LINE_AA, tipLength=0.18)
                    si.texto(panel, f"{abs(v):.3f}", (p[0] + 7, p[1] + dy), 0.44, col, 1)
            for panel, esc, c0 in ((prec, er, centros[e]), (pano, eo, ext_o[e][2])):
                q = (int(c0[0] * esc), int(c0[1] * esc))
                if est == 3:
                    cv2.rectangle(panel, (q[0] - 5, q[1] - 5), (q[0] + 5, q[1] + 5),
                                  (30, 30, 30), -1)
                    cv2.rectangle(panel, (q[0] - 5, q[1] - 5), (q[0] + 5, q[1] + 5),
                                  (255, 255, 255), 1)
                    if np.isfinite(v):
                        si.texto(panel, f"{abs(v):.2f}", (q[0] - 12, q[1] - 12), 0.42,
                                 (170, 170, 170), 1)
                elif est == 1:
                    cv2.circle(panel, q, 5, (255, 255, 255), -1)
                    cv2.circle(panel, q, 5, (20, 20, 20), 1)
                elif est == 2:
                    cv2.circle(panel, q, 6, (255, 255, 255), 2)
                    cv2.circle(panel, q, 3, (20, 20, 20), -1)
                else:
                    cv2.rectangle(panel, (q[0] - 6, q[1] - 6), (q[0] + 6, q[1] + 6),
                                  (0, 165, 255), -1)
                    cv2.rectangle(panel, (q[0] - 6, q[1] - 6), (q[0] + 6, q[1] + 6),
                                  (20, 20, 20), 1)

        # --- la mira: cuadrilatero, marca del nivel y recuadro rectificado -------------
        for i in range(4):
            cv2.line(pano, (int(qch[i][0] * eo), int(qch[i][1] * eo)),
                     (int(qch[(i + 1) % 4][0] * eo), int(qch[(i + 1) % 4][1] * eo)),
                     (255, 220, 120), 1, cv2.LINE_AA)
        col_n = (120, 255, 120) if est_niv[k] == 1 else (0, 200, 255)
        if est_niv[k] > 0:
            pm = A_m + dir_m * (nivel[k] * px_por_fila)
            c1 = (int((pm[0] - perp_m[0] * 10) * eo), int((pm[1] - perp_m[1] * 10) * eo))
            c2 = (int((pm[0] + perp_m[0] * 10) * eo), int((pm[1] + perp_m[1] * 10) * eo))
            cv2.line(pano, c1, c2, col_n, 2, cv2.LINE_AA)

        # El recuadro es la chapa rectificada de verdad, no un recorte: se ve el agua
        # subir y bajar sobre las graduaciones, que es la comprobacion de la medida.
        g_ch = cv2.warpPerspective(fr, M_ch, (CHAPA_W, alto_ch), flags=cv2.INTER_LINEAR)
        ins = cv2.resize(g_ch, (INSET_W, INSET_H), interpolation=cv2.INTER_LINEAR)
        pano[iy:iy + INSET_H, ix:ix + INSET_W] = ins
        cv2.rectangle(pano, (ix - 1, iy - 1), (ix + INSET_W, iy + INSET_H),
                      (255, 220, 120), 1)
        if est_niv[k] > 0:
            yl = iy + int(INSET_H * nivel[k] / alto_ch)
            cv2.line(pano, (ix - 6, yl), (ix + INSET_W + 6, yl), col_n, 2, cv2.LINE_AA)
            si.texto(pano, f"{niv_px[k]:+.2f} px", (ix + INSET_W + 10, yl + 5), 0.46,
                     col_n, 1)
            si.texto(pano, f"{niv_gr[k]:+.3f} grad", (ix + INSET_W + 10, yl + 24), 0.46,
                     col_n, 1)
        si.texto(pano, "mira rectificada", (ix - 4, iy - 6), 0.42, (255, 220, 120), 1)

        lienzo = np.zeros((ch, cw, 3), np.uint8)
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ALTO_PANEL, x_o:x_o + pw_o] = pano
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ALTO_PANEL, x_r:x_r + pw_r] = prec
        si.texto(lienzo, "vista original de la camara", (x_o, 24), 0.62, (255, 255, 255), 2)
        si.texto(lienzo, "plano rectificado (aqui se mide)", (x_r, 24), 0.62,
                 (255, 255, 255), 2)
        si.texto(lienzo, f"ventana {cfg['ventana']/fps:.1f} s   DS = {cfg['ds']} px   "
                         f"1 graduacion = {periodo_px:.2f} px",
                 (x_o + 300, 24), 0.5, (170, 170, 170), 1)
        si.barra_color(lienzo, lo, hi, u, cw - 330, ch - 28)

        vm = vmed[w]
        si.texto(lienzo, f"t = {k/fps:6.2f} s", (x_o, y_pie + 28), 0.66, (255, 255, 255), 2)
        si.texto(lienzo, f"v mediana de la seccion = {vm:.4f} {u}/s"
                 if np.isfinite(vm) else "v mediana = --",
                 (x_o + 180, y_pie + 28), 0.66, (120, 220, 255), 2)
        si.texto(lienzo, f"nivel {niv_px[k]:+.2f} px = {niv_gr[k]:+.3f} graduaciones"
                 if np.isfinite(niv_px[k]) else "nivel --",
                 (x_o + 640, y_pie + 28), 0.66, (120, 255, 120), 2)
        si.texto(lienzo, "circulo lleno = medida en esta ventana   anillo = ultimo valor "
                         "valido (max 0.6 s)   cuadro naranja = caida   cuadro negro = muro, "
                         "su 0 no entra en la mediana",
                 (x_o, y_pie + 54), 0.44, (170, 170, 170), 1)
        si.texto(lienzo, "el nivel sale del cruce agua-chapa sobre la mira rectificada, no de "
                         "contar marcas: la cuenta fluctua 6 veces mas que la oscilacion real",
                 (x_o, y_pie + 76), 0.44, (140, 140, 140), 1)
        if GH is not None:
            si.texto(lienzo, f"GH {GH:.2f} ft   Q {Q_ref:.0f} cfs   del release, no se usa "
                             f"para nada", (x_o, y_pie + 98), 0.44, (140, 140, 140), 1)
        vw.write(lienzo)
        if (k + 1) % 100 == 0:
            print(f"  {k+1}/{n} fotogramas")
    vw.release()
    cap.release()
    print(f"  render en {time.time()-t0:.1f} s")
    print(f"\nListo: {a.salida} ({os.path.getsize(a.salida)/1e6:.1f} MB, {n/fps:.1f} s)")

    base = os.path.splitext(a.salida)[0]
    with open(base + "_ventanas.csv", "w", newline="", encoding="utf-8") as f:
        esc = csv.writer(f)
        esc.writerow(["ventana", "frame_centro", "t_s"]
                     + [f"v{e}_{u}_s" for e in range(cfg["n_est"])]
                     + [f"estado{e}" for e in range(cfg["n_est"])] + [f"v_mediana_{u}_s"])
        for w in range(len(inicios)):
            esc.writerow([w, int(centros_t[w]), round(centros_t[w] / fps, 3)]
                         + [round(float(x), 5) if np.isfinite(x) else "" for x in V[w]]
                         + [int(x) for x in E[w]]
                         + [round(float(vmed[w]), 5) if np.isfinite(vmed[w]) else ""])
    print(f"Velocidades por ventana en: {base}_ventanas.csv")
    with open(base + "_nivel.csv", "w", newline="", encoding="utf-8") as f:
        esc = csv.writer(f)
        esc.writerow(["frame", "t_s", "fila_chapa", "nivel_px", "nivel_graduaciones",
                      "estado", "salpicadura", "marcas_visibles"])
        for k in range(n):
            esc.writerow([k, round(k / fps, 3),
                          round(float(nivel[k]), 3) if np.isfinite(nivel[k]) else "",
                          round(float(niv_px[k]), 4) if np.isfinite(niv_px[k]) else "",
                          round(float(niv_gr[k]), 5) if np.isfinite(niv_gr[k]) else "",
                          int(est_niv[k]), int(fuera[k]), int(marcas[k])])
    print(f"Nivel por fotograma en: {base}_nivel.csv "
          f"(marcas_visibles es diagnostico, no interviene)")


if __name__ == "__main__":
    main()
