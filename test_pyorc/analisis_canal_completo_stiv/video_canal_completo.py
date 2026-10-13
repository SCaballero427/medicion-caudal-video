"""El canal completo en video: lo medido y lo simulado, uno al lado del otro y a la vez.

Que produce
-----------
`salidas/canal_completo.mp4` (H.264, tiempo real) sobre el video original.

La idea
-------
STIV solo alcanza el tercio derecho. `simulacion_canal.py` extrapola el resto con un modelo
fisico. Un perfil dibujado en una grafica no deja juzgar si esa extrapolacion es razonable; **agua
moviendose, si**. Asi que aqui se siembran **particulas virtuales por todo el ancho** y se dejan
correr a la velocidad que el modelo predice en su X, con una estela proporcional a su velocidad.

Y la comprobacion visual esta metida en el diseno, no anadida: las particulas virtuales se dibujan
**tambien sobre el tercio derecho**, donde hay detrito real. Ahi las dos poblaciones comparten
pantalla y tienen que ir al mismo paso. Si el modelo se despega de la realidad donde hay datos, se
ve sin leer un numero; y si va acompasado, la extrapolacion de la izquierda merece algo mas de
credito.

Lo que **nunca** se puede confundir: el detrito real va en amarillo, lo simulado en azul, la zona
sin medir esta sombreada y el rotulo lo repite todo el rato. Esto es una simulacion, no una medida.

NO duplica constantes
---------------------
Geometria, realce, tensor y umbrales vienen de `analisis_canal_riego_stiv/stiv_canal.py`; el
perfil medido y el simulado se leen de los CSV que dejan `stiv_mejorado.py` y
`simulacion_canal.py`. Lo unico propio de aqui es el lenguaje visual y la siembra.

Uso
---
    python video_canal_completo.py                 # ~7 min
    python video_canal_completo.py --frames 600    # prueba corta
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

DIR_CASO = os.path.dirname(os.path.abspath(__file__))
DIR_SALIDAS = os.path.join(DIR_CASO, "salidas")

# ----------------------------------------------------------------------------------
# >>> AJUSTABLE <<<  solo lo propio del video
# ----------------------------------------------------------------------------------
N_PARTICULAS = 520
SEMILLA = 20260819
ESCALA_RECT = 320.0
MARGEN_RECT = 0.06
ESTELA_SEG = 1.2               # la estela es el recorrido del ultimo 1.2 s: su largo ES la v
ALTO_PERFIL = 190
UMBRAL_DIBUJO = 6.0
COLOR_REAL = (60, 255, 255)    # detrito real detectado (amarillo)
COLOR_SIM = (255, 175, 70)     # particula simulada (azul)
COLOR_MEDIDO = (120, 235, 150)   # verde: lo medido
# El azul de la curva tiene que ser el MISMO azul de las particulas simuladas: es lo que ata
# la grafica al agua que se ve moverse. (BGR, no RGB.)
COLOR_EXTRAP = (255, 200, 130)
COLOR_SOMBRA = (120, 95, 60)     # sombreado del tramo sin medir


def texto(img, s, org, esc=0.5, col=(255, 255, 255), gr=1):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, esc, (0, 0, 0), gr + 2, cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, esc, col, gr, cv2.LINE_AA)


def stretch_bgr(g, lo, hi):
    a = np.clip((g.astype(np.float32) - lo) / max(hi - lo, 1e-6), 0, 1)
    return cv2.cvtColor((a * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


def cargar():
    """Perfil simulado (el modelo elegido y la banda) y las estaciones medidas."""
    cfg = json.load(open(os.path.join(DIR_SALIDAS, "config_simulacion.json"), encoding="utf-8"))
    col = "u_A_skm"
    X, U, LO, HI = [], [], [], []
    for r in csv.DictReader(open(os.path.join(DIR_SALIDAS, "perfil_simulado.csv"),
                                 encoding="utf-8")):
        X.append(float(r["X"]))
        U.append(float(r[col]))
        LO.append(float(r["banda_lo"]))
        HI.append(float(r["banda_hi"]))
    med = []
    for r in csv.DictReader(open(os.path.join(DIR_SALIDAS, "perfil_mejorado.csv"),
                                 encoding="utf-8")):
        if r["aceptada"] in ("True", "1") and r["v_ventanas"] not in ("", "nan"):
            med.append((float(r["X"]), float(r["v_ventanas"]), float(r["q05"]),
                        float(r["q95"])))
    return cfg, np.array(X), np.array(U), np.array(LO), np.array(HI), np.array(med)


def panel_perfil(cfg, Xs, U, LO, HI, med, rst, w, h):
    """El perfil, con el eje X alineado con el panel rectificado que tiene encima."""
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = (20, 18, 17)
    x0, x1 = rst["X0"], rst["X1"]
    umax = max(U.max(), HI.max(), med[:, 3].max()) * 1.15
    ml, mr, ma, mb = 6, 6, 14, 22

    def px(X, u):
        return (ml + (np.asarray(X, float) - x0) / (x1 - x0) * (w - ml - mr),
                ma + (1 - np.asarray(u, float) / umax) * (h - ma - mb))

    xm0, xm1 = med[:, 0].min(), med[:, 0].max()
    # la zona sin medir, sombreada igual que en los paneles de arriba
    for a, b in ((x0, xm0), (xm1, x1)):
        p0 = px(a, umax)[0]
        p1 = px(b, umax)[0]
        cv2.rectangle(img, (int(p0), ma), (int(p1), h - mb), (46, 38, 28), -1)
    for u in np.arange(0, umax, 0.02):
        y = px(0, u)[1]
        cv2.line(img, (ml, int(y)), (w - mr, int(y)), (44, 42, 40), 1)
        texto(img, "%.2f" % u, (ml + 2, int(y) - 3), 0.32, (110, 110, 110), 1)
    # banda del barrido de Gamma
    pxx, pyl = px(Xs, LO)
    _, pyh = px(Xs, HI)
    poly = np.int32(np.r_[np.c_[pxx, pyl], np.c_[pxx[::-1], pyh[::-1]]])
    cv2.fillPoly(img, [poly], (86, 66, 42))
    # el modelo: continuo donde hay datos, a trazos donde se extrapola
    pxu, pyu = px(Xs, U)
    dentro = (Xs >= xm0) & (Xs <= xm1)
    seg = np.int32(np.c_[pxu, pyu])
    for i in range(len(seg) - 1):
        if dentro[i] and dentro[i + 1]:
            cv2.line(img, tuple(seg[i]), tuple(seg[i + 1]), COLOR_EXTRAP, 2, cv2.LINE_AA)
        elif i % 8 < 4:
            cv2.line(img, tuple(seg[i]), tuple(seg[i + 1]), COLOR_EXTRAP, 2, cv2.LINE_AA)
    # las estaciones medidas, con su q05-q95
    for X, u, q5, q95 in med:
        cx, cy = px(X, u)
        _, y5 = px(X, q5)
        _, y95 = px(X, q95)
        cv2.line(img, (int(cx), int(y5)), (int(cx), int(y95)), COLOR_MEDIDO, 1, cv2.LINE_AA)
        cv2.circle(img, (int(cx), int(cy)), 3, COLOR_MEDIDO, -1, cv2.LINE_AA)
    texto(img, "medido (STIV, q05-q95)", (ml + 40, h - 6), 0.36, COLOR_MEDIDO, 1)
    texto(img, "simulado Shiono-Knight  (a trazos = extrapolado, sin datos)",
          (ml + 240, h - 6), 0.36, COLOR_EXTRAP, 1)
    texto(img, "alt.cam/s", (ml + 2, ma - 3), 0.32, (140, 140, 140), 1)
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), (85, 85, 85), 1)
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--video", default=sc.ARCHIVO_VIDEO)
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--salida", default=os.path.join(DIR_SALIDAS, "canal_completo.mp4"))
    a = ap.parse_args()
    os.makedirs(DIR_SALIDAS, exist_ok=True)
    cfg, Xs, U, LO, HI, med = cargar()
    cap, ntot, fps = sc.abrir_video(a.video)
    sc.FPS_REAL[0] = fps
    ok, f0 = cap.read()
    cap.release()
    geo = sc.Geometria(cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY))
    NF = ntot if a.frames is None else min(a.frames, ntot)
    xm0, xm1 = med[:, 0].min(), med[:, 0].max()
    print("modelo SKM, W efectivo %.3f, B/H <= %.1f, %d estaciones de anclaje entre X %+.2f "
          "y %+.2f" % (cfg["A"]["W"], cfg["aspecto_cota_superior"], len(med), xm0, xm1))

    # siembra: uniforme en X sobre TODO el ancho, uniforme en Y. Cada particula recicla en su
    # propia calle, asi que la densidad transversal se mantiene uniforme y lo unico que cambia
    # entre calles es la velocidad, que es lo que se quiere leer.
    rng = np.random.default_rng(SEMILLA)
    pX = rng.uniform(geo.X_izq + 0.04, geo.X_der - 0.04, N_PARTICULAS)
    pY = rng.uniform(sc.Y_MIN, sc.Y_MAX, N_PARTICULAS)
    pU = np.interp(pX, Xs, U)

    rst = dict(X0=geo.X_izq - MARGEN_RECT, X1=geo.X_der + MARGEN_RECT, Y0=sc.Y_MIN,
               Y1=sc.Y_MAX, escala=ESCALA_RECT)
    rst["w"] = int(round((rst["X1"] - rst["X0"]) * ESCALA_RECT))
    rst["h"] = int(round((rst["Y1"] - rst["Y0"]) * ESCALA_RECT))
    Hr, Wr = rst["h"], rst["w"]
    mp_pts = np.ascontiguousarray(geo.mapa_rect(rst).reshape(-1, 2))

    cap, _, _ = sc.abrir_video(a.video)
    ok, f = cap.read()
    g0 = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    lo_p, hi_p = np.percentile(g0, [1.0, 99.0])
    Ho, Wo = g0.shape
    mask = np.zeros(g0.shape, np.uint8)
    mask[0:sc.FILA_BORDE_FIN - 40, :] = 255
    cv2.fillPoly(mask, [geo.poligono_agua()], 0)
    p0 = cv2.goodFeaturesToTrack(g0, 600, 0.01, 7, mask=mask)

    GAP, CAB, PIE = 12, 46, 64
    Wc = Wo + GAP + Wr
    Hc = CAB + max(Ho, Hr) + GAP + ALTO_PERFIL + PIE
    perfil = panel_perfil(cfg, Xs, U, LO, HI, med, rst, Wr, ALTO_PERFIL)
    vw = ev.abrir(a.salida, fps, (Wc, Hc))

    Xa, Xb = geo.X_izq + sc.RETRANQUEO, geo.X_der - sc.RETRANQUEO
    esq = np.array([[Xa, sc.Y_MIN], [Xb, sc.Y_MIN], [Xb, sc.Y_MAX], [Xa, sc.Y_MAX]])
    msk_rect = np.zeros((Hr, Wr), np.uint8)
    cv2.fillPoly(msk_rect, [np.int32(geo.rect_a_pix(rst, esq))], 1)
    msk_rect = msk_rect.astype(bool)
    dil = np.ones((3, 3), np.uint8)
    dt = 1.0 / fps
    t0 = time.time()
    for i in range(NF):
        if i > 0:
            ok, f = cap.read()
            if not ok:
                break
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        else:
            g = g0
        A, _ = sc.estimar_estabilizacion(g0, g, p0)
        lienzo = np.zeros((Hc, Wc, 3), np.uint8)
        lienzo[:] = (26, 22, 20)

        po = stretch_bgr(g, lo_p, hi_p)
        real = sc.realzar(g)
        qq = mp_pts @ A[:, :2].T + A[:, 2]
        mrx = qq[:, 0].reshape(Hr, Wr).astype(np.float32)
        mry = qq[:, 1].reshape(Hr, Wr).astype(np.float32)
        pr = stretch_bgr(cv2.remap(g, mrx, mry, cv2.INTER_LINEAR), lo_p, hi_p)

        # -- la zona SIN medir, sombreada en los dos paneles -------------------------
        for cA, cB in ((geo.X_izq, xm0), (xm1, geo.X_der)):
            q = np.array([[cA, sc.Y_MIN], [cB, sc.Y_MIN], [cB, sc.Y_MAX], [cA, sc.Y_MAX]])
            capa = po.copy()
            cv2.fillPoly(capa, [np.int32(geo.a_imagen(q) @ A[:, :2].T + A[:, 2])],
                         (90, 70, 45))
            po = cv2.addWeighted(capa, 0.22, po, 0.78, 0)
            capa = pr.copy()
            cv2.fillPoly(capa, [np.int32(geo.rect_a_pix(rst, q))], (90, 70, 45))
            pr = cv2.addWeighted(capa, 0.22, pr, 0.78, 0)

        # -- detrito REAL, en amarillo ------------------------------------------------
        msk_img = np.zeros(g.shape, np.uint8)
        cv2.fillPoly(msk_img, [np.int32(geo.a_imagen(esq) @ A[:, :2].T + A[:, 2])], 1)
        det = cv2.dilate((real > UMBRAL_DIBUJO).astype(np.uint8), dil) > 0
        po[det & (msk_img > 0)] = COLOR_REAL
        realr = cv2.remap(real, mrx, mry, cv2.INTER_LINEAR)
        detr = cv2.dilate((realr > UMBRAL_DIBUJO).astype(np.uint8), dil) > 0
        pr[detr & msk_rect] = COLOR_REAL

        # -- particulas SIMULADAS, en azul, con estela ---------------------------------
        pY += pU * dt
        fuera = pY > sc.Y_MAX
        if fuera.any():
            pY[fuera] = sc.Y_MIN + rng.uniform(0, 0.02, int(fuera.sum()))
        Yc = np.maximum(pY - pU * ESTELA_SEG, sc.Y_MIN)
        cab_i = geo.a_imagen(np.c_[pX, pY]) @ A[:, :2].T + A[:, 2]
        col_i = geo.a_imagen(np.c_[pX, Yc]) @ A[:, :2].T + A[:, 2]
        cab_r = geo.rect_a_pix(rst, np.c_[pX, pY])
        col_r = geo.rect_a_pix(rst, np.c_[pX, Yc])
        for k in range(N_PARTICULAS):
            cv2.line(po, tuple(np.int32(col_i[k])), tuple(np.int32(cab_i[k])),
                     COLOR_SIM, 1, cv2.LINE_AA)
            cv2.circle(po, tuple(np.int32(cab_i[k])), 2, COLOR_SIM, -1, cv2.LINE_AA)
            cv2.line(pr, tuple(np.int32(col_r[k])), tuple(np.int32(cab_r[k])),
                     COLOR_SIM, 1, cv2.LINE_AA)
            cv2.circle(pr, tuple(np.int32(cab_r[k])), 2, COLOR_SIM, -1, cv2.LINE_AA)
        # los limites del tramo medido, en los dos paneles
        for Xl in (xm0, xm1):
            q = np.column_stack([np.full(12, Xl), np.linspace(sc.Y_MIN, sc.Y_MAX, 12)])
            cv2.polylines(po, [np.int32(geo.a_imagen(q) @ A[:, :2].T + A[:, 2])], False,
                          COLOR_MEDIDO, 1, cv2.LINE_AA)
            cv2.polylines(pr, [np.int32(geo.rect_a_pix(rst, q))], False, COLOR_MEDIDO, 1,
                          cv2.LINE_AA)

        lienzo[CAB:CAB + Ho, 0:Wo] = po
        x2 = Wo + GAP
        lienzo[CAB:CAB + Hr, x2:x2 + Wr] = pr
        yp = CAB + max(Ho, Hr) + GAP
        lienzo[yp:yp + ALTO_PERFIL, x2:x2 + Wr] = perfil

        texto(lienzo, "El canal completo: STIV donde hay trazador, modelo hidraulico donde no",
              (12, 28), 0.62, (255, 255, 255), 1)
        texto(lienzo, "vista de la camara", (12, CAB - 8), 0.44, (235, 235, 235), 1)
        texto(lienzo, "plano del agua rectificado", (x2, CAB - 8), 0.44, (170, 255, 190), 1)
        texto(lienzo, "t = %5.1f s" % (i / fps), (12, CAB + Ho + 26), 0.56, (255, 255, 255), 1)
        L = [("amarillo: detrito REAL detectado en el video   (esto es la medida)", COLOR_REAL),
             ("azul: particula SIMULADA, avanza a la velocidad que el modelo da en su X",
              COLOR_SIM),
             ("la estela es el recorrido de %.1f s, asi que su largo ES la velocidad"
              % ESTELA_SEG, (190, 190, 190)),
             ("sombreado: tramo SIN medir. Ahi no hay trazador y no lo habra: el detrito cae",
              COLOR_SOMBRA),
             ("de la vegetacion de la orilla derecha. El azul de esa zona es extrapolacion.",
              COLOR_SOMBRA),
             ("", (0, 0, 0)),
             ("Donde coinciden las dos poblaciones -- el tercio derecho -- tienen que ir al",
              (215, 215, 215)),
             ("mismo paso. Esa es la comprobacion, y se hace mirando, no leyendo numeros.",
              (215, 215, 215))]
        for j, (s, c) in enumerate(L):
            if s:
                texto(lienzo, s, (12, CAB + Ho + 54 + 20 * j), 0.44, c, 1)
        texto(lienzo, "SIMULACION - no es un caudal medido - unidades afines (alturas de camara)",
              (12, Hc - 34), 0.5, (120, 170, 255), 1)
        texto(lienzo, "modelo Shiono-Knight ajustado a %d estaciones (chi2red %.2f). La "
                      "posicion del eje NO esta determinada: mueve la media un 21 %%"
              % (len(med), cfg["A"]["chi2"]), (12, Hc - 14), 0.42, (150, 150, 150), 1)
        vw.write(lienzo)
        if (i + 1) % 300 == 0:
            print("   %d/%d (%.1fs)" % (i + 1, NF, time.time() - t0), flush=True)
    cap.release()
    vw.release()
    print("escrito: %s  (%dx%d)" % (a.salida, Wc, Hc))
    with open(os.path.join(DIR_SALIDAS, "config_video_completo.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"n_particulas": N_PARTICULAS, "semilla": SEMILLA,
                   "estela_seg": ESTELA_SEG, "escala_rect": ESCALA_RECT,
                   "modelo": "SKM", "dimension": [Wc, Hc], "n_frames": NF,
                   "fps": fps}, fh, indent=2)


if __name__ == "__main__":
    main()
