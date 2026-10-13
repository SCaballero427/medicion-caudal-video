"""El experimento de alcance en video: las mismas estaciones medidas a tres distancias.

Que produce
-----------
`salidas/video_alcance.mp4` (H.264, tiempo real: un fotograma de salida por cada uno de
entrada) y `salidas/alcance_ventanas.csv` con la serie por ventana y banda.

Por que un video para un experimento
------------------------------------
El resultado de esta carpeta es un numero que cuesta creer: el campo lejano devuelve **20 veces
la velocidad real, con coherencia 0.98**, o sea que el indicador de calidad no solo no lo caza
sino que lo firma como la mejor medida del encuadre. Leido en una tabla parece un error de
programa. Visto sobre el agua -- flechas contiguas apuntando en sentidos opuestos sobre una franja
de rio que a simple vista baja entera hacia el mismo lado -- se entiende de un vistazo que lo que
falla es el muestreo, no el codigo.

Ademas, aqui se mide **por ventanas deslizantes** y no una vez sobre los 81 s como en
`experimento_alcance.py`. Eso anade una comprobacion que la tabla no da: el campo cercano repite
su valor ventana tras ventana y el lejano salta de signo, que es lo que hace un artefacto y no una
medida.

Que se ve
---------
Tres paneles. A la izquierda la vista de la camara con las tres bandas sombreadas -- ahi ya se ve
el problema sin numeros: la banda lejana son **61 filas de pixeles** contra las 250 de la cercana.
En el centro el plano rectificado de Y = 1.4 a Y = 8 alturas de camara, donde las flechas si son
proporcionales y comparables entre bandas. A la derecha la STI de una misma estacion en cada banda,
que es la prueba: arriba se ven las estelas inclinadas, abajo no hay ninguna y la recta que dibuja
el tensor esta puesta sobre ruido.

**Las flechas se colorean por coherencia**, no por velocidad, a proposito: es la unica forma de
ver que el rojo -- la coherencia mas alta -- esta justo donde la medida es absurda.

NO duplica constantes
---------------------
Geometria, realce, tensor y umbrales vienen de `analisis_canal_riego_stiv/stiv_canal.py`; las
bandas, las estaciones y el mapa de muestreo, de `experimento_alcance.py`, que es de quien este
video es ilustracion. Lo unico propio de aqui es el lenguaje visual.

Uso
---
    python video_alcance.py                 # video entero (~7 min)
    python video_alcance.py --frames 600    # prueba corta
"""
import argparse
import csv
import json
import os
import sys
import time

import cv2
import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "analisis_canal_riego_stiv"))
import escritor_video as ev      # noqa: E402
import stiv_canal as sc          # noqa: E402

import experimento_alcance as ea  # noqa: E402

DIR_CASO = os.path.dirname(os.path.abspath(__file__))
DIR_SALIDAS = os.path.join(DIR_CASO, "salidas")

# ----------------------------------------------------------------------------------
# >>> AJUSTABLE <<<  solo lo propio del video
# ----------------------------------------------------------------------------------
VENTANA = 360                  # 12 s, la misma que el video del caso principal
PASO = 15
ESCALA_RECT = 130.0            # px por altura de camara; con Y hasta 8 el lienzo se va de alto
MARGEN_RECT = 0.06
SEG_FLECHA = 10.0              # la flecha es el recorrido en 10 s
EST_STI = 11                   # estacion cuya STI se dibuja a la derecha
ANCHO_STI, ALTO_STI = 520, 258
CLIP_STI = 6.0                 # tope de gris de la STI, en unidades de respuesta top-hat
UMBRAL_DIBUJO = 6.0
COLOR_PARTICULA = (60, 255, 255)
# Color de la banda en la vista de camara. La cercana es la AOI del caso.
COLOR_BANDA = {"cerca": (90, 210, 120), "media": (70, 190, 235), "lejos": (90, 110, 245)}

_LUT = cv2.applyColorMap(np.arange(256, dtype=np.uint8).reshape(1, -1),
                         cv2.COLORMAP_TURBO)[0]
_LUT_T = [tuple(int(x) for x in _LUT[i]) for i in range(256)]


def color_coh(c):
    """Color por coherencia en [0, 1]. Deliberadamente NO por velocidad: ver el docstring."""
    if not np.isfinite(c):
        return (120, 120, 120)
    return _LUT_T[int(np.clip(c, 0, 1) * 255)]


def texto(img, s, org, esc=0.5, col=(255, 255, 255), gr=1):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, esc, (0, 0, 0), gr + 2, cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, esc, col, gr, cv2.LINE_AA)


def stretch_bgr(g, lo, hi):
    a = np.clip((g.astype(np.float32) - lo) / max(hi - lo, 1e-6), 0, 1)
    return cv2.cvtColor((a * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


# ==================================================================================
# pasada 1: STI de las tres bandas en una sola lectura
# ==================================================================================
def pasada_sti(ruta, geo, n_frames, verbose=True):
    cap, ntot, fps = sc.abrir_video(ruta)
    NF = ntot if n_frames is None else min(n_frames, ntot)
    ok, f = cap.read()
    g0 = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    mask = np.zeros(g0.shape, np.uint8)
    mask[0:sc.FILA_BORDE_FIN - 40, :] = 255
    cv2.fillPoly(mask, [geo.poligono_agua()], 0)
    p0 = cv2.goodFeaturesToTrack(g0, 600, 0.01, 7, mask=mask)

    ne = len(ea.ESTACIONES)
    planes = []
    for (y0, y1, nm) in ea.BANDAS:
        P = ea.preparar(geo, y0, y1, 1, fps, ea.ESTACIONES)
        P["et"] = nm
        P["px"] = P["DS"] / ea.resolucion(geo, (y0 + y1) / 2)
        P["sti"] = np.zeros((ne, NF, P["nmu"]), np.float32)
        P["cnt"] = np.zeros((ne, NF), np.int32)
        planes.append(P)
    afines = np.zeros((NF, 2, 3), np.float32)

    t0, leidos = time.time(), 0
    for i in range(NF):
        if i > 0:
            ok, f = cap.read()
            if not ok:
                break
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        else:
            g = g0
        leidos = i + 1
        A, _ = sc.estimar_estabilizacion(g0, g, p0)
        afines[i] = A
        t = sc.realzar(g)
        for P in planes:
            xy = P["pts"] @ A[:, :2].T + A[:, 2]
            nr = ne * sc.N_LINEAS
            v = cv2.remap(t, xy[:, 0].reshape(nr, P["nmu"]).astype(np.float32),
                          xy[:, 1].reshape(nr, P["nmu"]).astype(np.float32),
                          cv2.INTER_LINEAR).reshape(ne, sc.N_LINEAS, P["nmu"])
            P["sti"][:, i, :] = v.mean(axis=1)
            # el conteo va sobre el maximo entre lineas ANTES de promediar: una particula que
            # cae en 1 de las 11 lineas se diluye por 11 si se cuenta despues
            P["cnt"][:, i] = (v.max(axis=1) > sc.UMBRAL_PARTICULA).sum(axis=1)
        if verbose and (i + 1) % 300 == 0:
            print("   STI %d/%d (%.1fs)" % (i + 1, NF, time.time() - t0), flush=True)
    cap.release()
    for P in planes:
        P["sti"] = P["sti"][:, :leidos]
        P["cnt"] = P["cnt"][:, :leidos]
    return planes, afines[:leidos], fps, leidos


# ==================================================================================
# ventanas
# ==================================================================================
def medir_ventanas(planes, fps, NF):
    centros, res = [], []
    for w0 in range(0, max(1, NF - VENTANA + 1), PASO):
        w1 = w0 + VENTANA
        centros.append((w0 + w1) // 2)
        porbanda = []
        for P in planes:
            fila = []
            for a in range(len(ea.ESTACIONES)):
                im = P["sti"][a, w0:w1]
                im = im - im.mean(axis=0, keepdims=True)
                dens = float(P["cnt"][a, w0:w1].sum()) / (VENTANA * P["nmu"])
                pend, coh, nsel, ntot = sc.tensor_seleccion(im)
                v = pend * P["DS"] * fps if np.isfinite(pend) else np.nan
                ok = not sc.motivos_rechazo(dens, v, coh)
                fila.append((v, coh, dens, ok, pend))
            porbanda.append(fila)
        res.append(porbanda)
    return np.array(centros), res


# ==================================================================================
# la STI de una estacion, con la pendiente que el tensor afirma
# ==================================================================================
def panel_serie(centros, res, planes, w, h):
    """Mediana del tensor por banda a lo largo del video, en escala simlog.

    Hace falta escala simlog porque en el mismo grafico conviven +0.059 y +3: en lineal la
    banda cercana seria una raya pegada al cero. Se dibuja lo que el tensor DEVUELVE, aceptado o
    no -- en media y lejos no se acepta nada -- porque lo que se quiere ensenar es justo el
    valor que el control de calidad tiene que tirar.

    Se monta una sola vez y en cada fotograma solo se le anade el cursor.
    """
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = (18, 16, 15)

    def ymap(v):
        z = np.sign(v) * np.log10(1 + abs(v) / 0.01)
        return int(h / 2 - z / 2.7 * (h / 2 - 10))

    for lvl, col in ((0.0, (80, 80, 80)), (1.0, (60, 60, 90)), (-1.0, (60, 60, 90))):
        y = ymap(lvl)
        cv2.line(img, (0, y), (w, y), col, 1)
    # la referencia va a trazos y en gris: en verde continuo se confundia con la curva de cerca,
    # que es justo la que tiene que verse encima de ella
    yv = ymap(0.059)
    for x in range(0, w, 14):
        cv2.line(img, (x, yv), (min(x + 7, w), yv), (150, 150, 150), 1)
    texto(img, "+0.059  (la verdad)", (6, yv - 4), 0.36, (185, 185, 185), 1)
    texto(img, "+1", (6, ymap(1.0) - 4), 0.34, (110, 110, 160), 1)
    texto(img, "-1", (6, ymap(-1.0) - 4), 0.34, (110, 110, 160), 1)
    for b, P in enumerate(planes):
        pts = []
        for k in range(len(centros)):
            vals = [x[0] for x in res[k][b] if np.isfinite(x[0])]
            if not vals:
                continue
            x = int(k / max(len(centros) - 1, 1) * (w - 1))
            pts.append((x, ymap(float(np.median(vals)))))
        if len(pts) > 1:
            cv2.polylines(img, [np.int32(pts)], False, COLOR_BANDA[P["et"]], 2, cv2.LINE_AA)
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), (80, 80, 80), 1)
    return img


def franja_sti(im, pend, w=ANCHO_STI, h=ALTO_STI):
    """La STI en gris (filas = tiempo, columnas = espacio) con la recta del tensor encima."""
    a = np.clip(im / CLIP_STI, 0, 1)
    img = cv2.cvtColor((a * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    nt, ns = im.shape
    img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
    if np.isfinite(pend):
        # pendiente en muestras/fotograma -> px de pantalla, con las dos escalas del resize
        m = pend * (w / float(ns)) / (h / float(nt))
        cx, cy = w * 0.5, h * 0.5
        dy = h * 0.42
        p1 = (int(cx - m * dy), int(cy - dy))
        p2 = (int(cx + m * dy), int(cy + dy))
        cv2.line(img, p1, p2, (70, 220, 255), 2, cv2.LINE_AA)
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), (90, 90, 90), 1)
    return img


# ==================================================================================
# pasada 2: dibujo
# ==================================================================================
def render(ruta, geo, planes, centros, res, afines, NF, fps, salida, verbose=True):
    Y0R, Y1R = ea.BANDAS[0][0], ea.BANDAS[-1][1]
    rst = dict(X0=geo.X_izq - MARGEN_RECT, X1=geo.X_der + MARGEN_RECT, Y0=Y0R, Y1=Y1R,
               escala=ESCALA_RECT)
    rst["w"] = int(round((rst["X1"] - rst["X0"]) * ESCALA_RECT))
    rst["h"] = int(round((rst["Y1"] - rst["Y0"]) * ESCALA_RECT))
    mp_pts = np.ascontiguousarray(geo.mapa_rect(rst).reshape(-1, 2))
    Hr, Wr = rst["h"], rst["w"]
    Xs = geo.estaciones()
    iest = ea.ESTACIONES.index(EST_STI)

    cap, ntot, _ = sc.abrir_video(ruta)
    ok, f = cap.read()
    g0 = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    lo, hi = np.percentile(g0, [1.0, 99.0])
    Ho, Wo = g0.shape
    ALTO_FRANJA = ALTO_STI + 26
    GAP, CAB, PIE = 12, 46, 92
    Wc = Wo + GAP + Wr + GAP + ANCHO_STI
    Hc = CAB + max(Ho, Hr, 3 * ALTO_FRANJA) + PIE
    vw = ev.abrir(salida, fps, (Wc, Hc))

    # mascara del agua de cada banda, para recortar los detritos dibujados
    Xa, Xb = geo.X_izq + sc.RETRANQUEO, geo.X_der - sc.RETRANQUEO
    esq_todo = np.array([[Xa, Y0R], [Xb, Y0R], [Xb, Y1R], [Xa, Y1R]])
    msk_rect = np.zeros((Hr, Wr), np.uint8)
    cv2.fillPoly(msk_rect, [np.int32(geo.rect_a_pix(rst, esq_todo))], 1)
    msk_rect = msk_rect.astype(bool)
    dil = np.ones((3, 3), np.uint8)
    barra = np.array([[color_coh(x / 200.0) for x in range(200)]] * 12, np.uint8)
    # el hueco bajo la vista de camara (el panel rectificado es mas alto) se usa para la serie
    ALTO_SERIE = max(0, max(Ho, Hr, 3 * ALTO_FRANJA) - Ho - 24)
    serie_fondo = (panel_serie(centros, res, planes, Wo, ALTO_SERIE)
                   if ALTO_SERIE >= 60 else None)

    t0, serie = time.time(), []
    for i in range(NF):
        if i > 0:
            ok, f = cap.read()
            if not ok:
                break
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        else:
            g = g0
        A = afines[i]
        k = int(np.argmin(np.abs(centros - i)))
        lienzo = np.zeros((Hc, Wc, 3), np.uint8)
        lienzo[:] = (26, 22, 20)

        po = stretch_bgr(g, lo, hi)
        real = sc.realzar(g)
        qq = mp_pts @ A[:, :2].T + A[:, 2]
        mrx = qq[:, 0].reshape(Hr, Wr).astype(np.float32)
        mry = qq[:, 1].reshape(Hr, Wr).astype(np.float32)
        pr = stretch_bgr(cv2.remap(g, mrx, mry, cv2.INTER_LINEAR), lo, hi)

        msk_img = np.zeros(g.shape, np.uint8)
        cv2.fillPoly(msk_img, [np.int32(geo.a_imagen(esq_todo) @ A[:, :2].T + A[:, 2])], 1)
        det_o = cv2.dilate((real > UMBRAL_DIBUJO).astype(np.uint8), dil) > 0
        po[det_o & (msk_img > 0)] = COLOR_PARTICULA
        realr = cv2.remap(real, mrx, mry, cv2.INTER_LINEAR)
        det_r = cv2.dilate((realr > UMBRAL_DIBUJO).astype(np.uint8), dil) > 0
        pr[det_r & msk_rect] = COLOR_PARTICULA

        # -- bandas y estaciones -----------------------------------------------------
        capa = po.copy()
        for P in planes:
            col = COLOR_BANDA[P["et"]]
            esq = np.array([[Xa, P["y0"]], [Xb, P["y0"]], [Xb, P["y1"]], [Xa, P["y1"]]])
            cv2.fillPoly(capa, [np.int32(geo.a_imagen(esq) @ A[:, :2].T + A[:, 2])], col)
        po = cv2.addWeighted(capa, 0.16, po, 0.84, 0)
        for P in planes:
            col = COLOR_BANDA[P["et"]]
            esq = np.array([[Xa, P["y0"]], [Xb, P["y0"]], [Xb, P["y1"]], [Xa, P["y1"]]])
            cv2.polylines(po, [np.int32(geo.a_imagen(esq) @ A[:, :2].T + A[:, 2])], True,
                          col, 1, cv2.LINE_AA)
            cv2.polylines(pr, [np.int32(geo.rect_a_pix(rst, esq))], True, col, 1, cv2.LINE_AA)
            eo = (geo.a_imagen([[Xa, (P["y0"] + P["y1"]) / 2]]) @ A[:, :2].T + A[:, 2])[0]
            texto(po, P["et"], (int(eo[0]) + 6, int(eo[1])), 0.5, col, 1)

        for b, P in enumerate(planes):
            fila = res[k][b]
            for a, e in enumerate(ea.ESTACIONES):
                v, coh, dens, okk, pend = fila[a]
                X = Xs[e]
                col = color_coh(coh)
                # la linea de busqueda va atenuada: con 18 en pantalla, al mismo tono que
                # las flechas no se distingue cual es la medida y cual el soporte
                cold = tuple(int(c * 0.45) for c in col)
                Q = np.column_stack([np.full(16, X), np.linspace(P["y0"], P["y1"], 16)])
                Io = geo.a_imagen(Q) @ A[:, :2].T + A[:, 2]
                cv2.polylines(po, [np.int32(Io)], False, cold, 1, cv2.LINE_AA)
                Ir = geo.rect_a_pix(rst, Q)
                cv2.polylines(pr, [np.int32(Ir)], False, cold, 1, cv2.LINE_AA)
                if not np.isfinite(v):
                    continue
                Ym = (P["y0"] + P["y1"]) / 2
                Yb = Ym + v * SEG_FLECHA
                # la flecha se recorta a SU banda, no al lienzo entero: si se dejan correr, las
                # de media y lejos cruzan por encima de las de cerca y no se sabe cual es cual.
                # Cuanto recorta es justo la medida del disparate, y por eso se marca.
                lo_b, hi_b = P["y0"] + 0.02, P["y1"] - 0.02
                cortada = not (lo_b <= Yb <= hi_b)
                Yb = float(np.clip(Yb, lo_b, hi_b))
                b0 = geo.rect_a_pix(rst, [[X, Ym]])[0]
                b1 = geo.rect_a_pix(rst, [[X, Yb]])[0]
                cv2.arrowedLine(pr, tuple(np.int32(b0)), tuple(np.int32(b1)), col,
                                2 if okk else 1, cv2.LINE_AA, tipLength=0.22)
                if cortada:
                    # la flecha se sale del lienzo: se marca en vez de recortarla en silencio
                    d = 1 if Yb > Ym else -1
                    for j in (0, 5, 10):
                        cv2.line(pr, (int(b1[0]) - 6, int(b1[1]) + d * j),
                                 (int(b1[0]) + 6, int(b1[1]) + d * j), col, 1, cv2.LINE_AA)
                a0 = geo.a_imagen([[X, Ym]]) @ A[:, :2].T + A[:, 2]
                a1 = geo.a_imagen([[X, Yb]]) @ A[:, :2].T + A[:, 2]
                cv2.arrowedLine(po, tuple(np.int32(a0[0])), tuple(np.int32(a1[0])), col,
                                2 if okk else 1, cv2.LINE_AA, tipLength=0.22)
                # una de cada dos y escalonadas: en 300 px de ancho seis etiquetas seguidas
                # se pisan unas a otras
                if a % 2 == 0:
                    texto(pr, "%+.3f" % v, (int(b0[0]) - 22, int(b0[1]) + 13 + 13 * (a // 2)),
                          0.36, col, 1)

        lienzo[CAB:CAB + Ho, 0:Wo] = po
        x2 = Wo + GAP
        lienzo[CAB:CAB + Hr, x2:x2 + Wr] = pr
        if serie_fondo is not None:
            ys = CAB + Ho + 22
            s = serie_fondo.copy()
            xc = int(i / max(NF - 1, 1) * (Wo - 1))
            cv2.line(s, (xc, 0), (xc, ALTO_SERIE), (255, 255, 255), 1)
            lienzo[ys:ys + ALTO_SERIE, 0:Wo] = s
            texto(lienzo, "mediana que devuelve el tensor en cada banda, ventana a ventana "
                          "(escala simlog)", (6, ys - 6), 0.42, (215, 215, 215), 1)

        # -- las tres STI ------------------------------------------------------------
        x3 = x2 + Wr + GAP
        w0v = max(0, min(i - VENTANA // 2, NF - VENTANA))
        for b, P in enumerate(planes):
            v, coh, dens, okk, pend = res[k][b][iest]
            im = P["sti"][iest, w0v:w0v + VENTANA]
            im = im - im.mean(axis=0, keepdims=True)
            fr = franja_sti(im, pend)
            y = CAB + b * ALTO_FRANJA
            texto(lienzo, "%s  Y %.1f-%.1f   DS = %.2f px de imagen"
                  % (P["et"], P["y0"], P["y1"], P["px"]), (x3, y + 15), 0.42,
                  COLOR_BANDA[P["et"]], 1)
            lienzo[y + 21:y + 21 + ALTO_STI, x3:x3 + ANCHO_STI] = fr
            if b == 0:
                texto(lienzo, "espacio ->", (x3 + ANCHO_STI - 90, y + 34), 0.36,
                      (170, 170, 170), 1)
                texto(lienzo, "tiempo v", (x3 + 8, y + 34), 0.36, (170, 170, 170), 1)
            et = ("v %+.4f   coh %.2f" % (v, coh)) if np.isfinite(v) else "sin tensor"
            texto(lienzo, et, (x3 + 8, y + 21 + ALTO_STI - 8), 0.44, color_coh(coh), 1)

        # -- cabecera y pie ----------------------------------------------------------
        texto(lienzo, "Hasta donde alcanza STIV canal arriba - la misma agua medida a tres "
                      "distancias", (12, 28), 0.62, (255, 255, 255), 1)
        texto(lienzo, "vista de la camara", (12, CAB - 8), 0.44, (235, 235, 235), 1)
        texto(lienzo, "rectificado Y %.1f-%.1f" % (Y0R, Y1R), (x2, CAB - 8), 0.40,
              (170, 255, 190), 1)
        texto(lienzo, "STI de la estacion %d, banda a banda" % EST_STI, (x3, CAB - 8), 0.44,
              (200, 220, 255), 1)
        yb = CAB + max(Ho, Hr, 3 * ALTO_FRANJA)
        texto(lienzo, "t = %5.1f s" % (i / fps), (12, yb + 24), 0.54, (255, 255, 255), 1)
        px = 132
        for b, P in enumerate(planes):
            fila = res[k][b]
            ac = [x[0] for x in fila if x[3]]
            vv = [x[0] for x in fila if np.isfinite(x[0])]
            s = ("%s: %d/%d aceptadas" % (P["et"], len(ac), len(fila)))
            if ac:
                s += "  mediana %+.4f" % np.median(ac)
            elif vv:
                s += "  |v| hasta %.2f" % max(abs(x) for x in vv)
            texto(lienzo, s, (px, yb + 24), 0.5, COLOR_BANDA[P["et"]], 1)
            px += 400
        texto(lienzo, "la verdad es la banda cercana: +0.059 alturas de camara/s. las tres "
                      "bandas miran la MISMA agua, asi que tienen que dar lo mismo",
              (12, yb + 46), 0.44, (200, 200, 200), 1)
        texto(lienzo, "el color es la COHERENCIA, no la velocidad: el rojo -- la mejor nota de "
                      "calidad -- cae justo donde la medida es absurda",
              (12, yb + 64), 0.44, (170, 170, 170), 1)
        texto(lienzo, "amarillo = detrito detectado. la banda lejana no tiene ninguno: no hay "
                      "trazador y el agua avanza 0.04 px por fotograma",
              (12, yb + 82), 0.42, (150, 150, 150), 1)
        bx, by, bw_, bh_ = Wc - 250, yb + 34, 200, 12
        lienzo[by:by + bh_, bx:bx + bw_] = barra
        texto(lienzo, "coh 0", (bx - 44, by + bh_), 0.38, (200, 200, 200), 1)
        texto(lienzo, "1", (bx + bw_ + 4, by + bh_), 0.38, (200, 200, 200), 1)

        vw.write(lienzo)
        serie.append(i)
        if verbose and (i + 1) % 300 == 0:
            print("   dibujo %d/%d (%.1fs)" % (i + 1, NF, time.time() - t0), flush=True)
    cap.release()
    vw.release()
    return len(serie), (Wc, Hc)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--video", default=sc.ARCHIVO_VIDEO)
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--salida", default=os.path.join(DIR_SALIDAS, "video_alcance.mp4"))
    a = ap.parse_args()
    os.makedirs(DIR_SALIDAS, exist_ok=True)
    cap, ntot, fps = sc.abrir_video(a.video)
    sc.FPS_REAL[0] = fps
    ok, f0 = cap.read()
    cap.release()
    geo = sc.Geometria(cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY))
    print("pasada 1: STI de las tres bandas...")
    planes, afines, fps, NF = pasada_sti(a.video, geo, a.frames)
    for P in planes:
        print("  %-6s Y %.2f-%.2f  %5d muestras  DS = %.2f px"
              % (P["et"], P["y0"], P["y1"], P["nmu"], P["px"]))
    centros, res = medir_ventanas(planes, fps, NF)
    print("  %d ventanas de %d fotogramas" % (len(centros), VENTANA))
    with open(os.path.join(DIR_SALIDAS, "alcance_ventanas.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ventana", "centro_frame", "t_s", "banda", "estacion", "v", "coherencia",
                    "densidad", "aceptada"])
        for k, c in enumerate(centros):
            for b, P in enumerate(planes):
                for a2, e in enumerate(ea.ESTACIONES):
                    v, coh, dens, okk, _ = res[k][b][a2]
                    w.writerow([k, int(c), "%.3f" % (c / fps), P["et"], e,
                                "%.6f" % v if np.isfinite(v) else "", "%.4f" % coh,
                                "%.6f" % dens, int(okk)])
    for b, P in enumerate(planes):
        acc, vv = [], []
        for k in range(len(centros)):
            f_ = [x[0] for x in res[k][b] if x[3]]
            if f_:
                acc.append(np.median(f_))
            vv += [x[0] for x in res[k][b] if np.isfinite(x[0])]
        n_ac = sum(1 for k in range(len(centros)) for x in res[k][b] if x[3])
        print("  %-6s aceptadas %4d/%4d  mediana %s  |v| max %.2f"
              % (P["et"], n_ac, len(centros) * len(ea.ESTACIONES),
                 ("%+.4f" % np.median(acc)) if acc else "--",
                 max(abs(x) for x in vv) if vv else float("nan")))
    print("pasada 2: dibujando...")
    n, dim = render(a.video, geo, planes, centros, res, afines, NF, fps, a.salida)
    print("escrito: %s  (%dx%d, %d fotogramas)" % (a.salida, dim[0], dim[1], n))
    with open(os.path.join(DIR_SALIDAS, "config_video_alcance.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"ventana": VENTANA, "paso": PASO, "escala_rect": ESCALA_RECT,
                   "seg_flecha": SEG_FLECHA, "estacion_sti": EST_STI, "n_frames": NF,
                   "fps": fps, "n_ventanas": len(centros), "dimension": list(dim),
                   "hereda_de": ["analisis_canal_riego_stiv/stiv_canal.py",
                                 "experimento_alcance.py"]}, fh, indent=2)


if __name__ == "__main__":
    main()
