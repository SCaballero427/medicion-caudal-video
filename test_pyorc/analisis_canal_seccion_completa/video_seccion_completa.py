"""El canal medido de orilla a orilla: una flecha por estacion, en toda la anchura.

Que produce
-----------
`salidas/seccion_completa.mp4` (H.264, tiempo real) y `salidas/perfil_seccion.csv`.

De donde sale cada flecha
-------------------------
Leelo antes de tocar nada, porque no todas las flechas tienen el mismo origen.

- **Estaciones 8 a 13** (X de +0.12 a +0.85): velocidad medida por STIV sobre el detrito real, con
  el mismo codigo del caso -- `pasada_sti` y `medir_ventanas` se importan de
  `analisis_canal_riego_stiv/video_velocidad.py`.
- **Las otras nueve**: por ahi no pasa detrito, asi que el tensor no tiene nada que medir. Su
  velocidad se obtiene de la **forma** del perfil transversal ajustado en
  `analisis_canal_completo_stiv/` (Shiono-Knight con la pared en la orilla detectada), escalada
  ventana a ventana por lo que marcan las estaciones que si miden.

O sea: **el modelo pone la forma y la medida pone la amplitud, en cada una de las 138 ventanas.**

Por que la amplitud tiene que venir de la medida
------------------------------------------------
Si a las nueve estaciones sin trazador se les pone un valor fijo, sus flechas quedan clavadas
mientras las seis medidas suben y bajan de ventana en ventana, y el resultado se ve raro
inmediatamente. Ademas seria fisicamente falso: cuando la seccion acelera, acelera entera.

Asi que en cada ventana se calcula un unico factor de escala -- la mediana de
`v_medida / forma(X)` sobre las estaciones que miden -- y se aplica a toda la seccion. Encima se
anade un pequeno temblor por estacion cuya **desviacion tipica y cuya autocorrelacion estan
medidas** sobre los residuos de las estaciones que si miden, no elegidas a ojo: sin el, las quince
flechas se moverian en bloque perfecto, que tampoco es lo que hace un rio.

Se usa el ajuste de **pared rigida** (la orilla detectada) y no el de semiancho efectivo libre
porque este ultimo pone el borde del agua en X = +-0.963, o sea por dentro de las estaciones 0 y
14, y les daria velocidad exactamente cero.

Uso
---
    python video_seccion_completa.py                 # ~7 min
    python video_seccion_completa.py --frames 600    # prueba corta
"""
import argparse
import csv
import json
import os
import sys
import time

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "analisis_canal_riego_stiv"))
sys.path.insert(0, os.path.join(_RAIZ, "analisis_canal_completo_stiv"))
import escritor_video as ev        # noqa: E402
import stiv_canal as sc            # noqa: E402
import video_velocidad as vv       # noqa: E402
import simulacion_canal as sim     # noqa: E402

DIR_CASO = os.path.dirname(os.path.abspath(__file__))
DIR_SALIDAS = os.path.join(DIR_CASO, "salidas")
CFG_PERFIL = os.path.join(os.path.dirname(DIR_CASO), "analisis_canal_completo_stiv", "salidas",
                          "config_simulacion.json")

# ----------------------------------------------------------------------------------
# >>> AJUSTABLE <<<  solo lo propio del video
# ----------------------------------------------------------------------------------
ESCALA_RECT = 320.0
MARGEN_RECT = 0.06
SEG_FLECHA = 10.0              # la flecha es el recorrido en 10 s: su largo ES la velocidad
V_COLOR_MAX = 0.075
ALTO_PERFIL, ALTO_SERIE = 210, 210
SEMILLA = 20260821
UMBRAL_DIBUJO = 6.0
COLOR_PARTICULA = (60, 255, 255)

_LUT = cv2.applyColorMap(np.arange(256, dtype=np.uint8).reshape(1, -1),
                         cv2.COLORMAP_TURBO)[0]
_LUT_T = [tuple(int(x) for x in _LUT[i]) for i in range(256)]


def color_v(v):
    if not np.isfinite(v):
        return (120, 120, 120)
    return _LUT_T[int(np.clip(v / V_COLOR_MAX, 0, 1) * 255)]


def texto(img, s, org, esc=0.5, col=(255, 255, 255), gr=1):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, esc, (0, 0, 0), gr + 2, cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, esc, col, gr, cv2.LINE_AA)


def stretch_bgr(g, lo, hi):
    a = np.clip((g.astype(np.float32) - lo) / max(hi - lo, 1e-6), 0, 1)
    return cv2.cvtColor((a * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


# ==================================================================================
def forma_transversal(Xs):
    """Forma del perfil en las 15 estaciones, normalizada a su maximo."""
    cfg = json.load(open(CFG_PERFIL, encoding="utf-8"))
    p = cfg["pared_rigida"]
    semi = 0.5 * cfg["ancho"]
    u = sim.skm(np.asarray(Xs, float), cfg["eje_geometrico"], p["Gamma"], p["Umax"], semi,
                semi_ref=semi)
    return np.maximum(u, 1e-6) / u.max(), cfg


def construir_perfiles(res, Xs, forma, rng, verbose=True):
    """Velocidad de las 15 estaciones en cada ventana.

Devuelve (V, mide, f, est): la matriz (ventanas x estaciones), que estaciones
    proceden de una medida directa, el factor de escala de cada ventana y un dict con los
    estadisticos medidos sobre los residuos de las estaciones que si miden.
    """
    nk, ne = len(res), len(Xs)
    V = np.full((nk, ne), np.nan)
    mide = np.zeros((nk, ne), bool)
    for k in range(nk):
        for a in range(ne):
            v, coh, dens, ok = res[k][a]
            if ok:
                V[k, a], mide[k, a] = v, True

    # factor de escala de cada ventana: la mediana de v_medida / forma(X) sobre las que miden
    f = np.full(nk, np.nan)
    for k in range(nk):
        m = mide[k]
        if m.any():
            f[k] = np.median(V[k, m] / forma[m])
    idx = np.arange(nk)
    ok_f = np.isfinite(f)
    if not ok_f.any():
        raise SystemExit("ninguna ventana tiene medida: no hay de donde sacar la amplitud")
    f = np.interp(idx, idx[ok_f], f[ok_f])

    # Residuos de las estaciones que miden respecto a f*forma. De aqui salen los parametros del
    # temblor, pero NO en bruto: hay que separarlos en dos, porque son cosas distintas.
    #
    #   - El **desvio persistente** de cada estacion (su media sobre las 138 ventanas) es lo que
    #     la forma del modelo se equivoca ahi de manera fija. La estacion 13 sale -0.41: junto a
    #     la orilla el modelo se pasa de largo. Eso NO es ruido.
    #   - El **bamboleo temporal** (lo que queda al quitar esa media) si es la variabilidad real
    #     de ventana a ventana, que es lo unico que hay que reproducir.
    #
    # Medido: total 0.219, persistente 0.173, temporal 0.136. Usar el total -- que fue el primer
    # intento -- inyecta un error de FORMA como si fuera ruido TEMPORAL, y hace que las nueve
    # estaciones deducidas parpadeen bastante mas de lo que parpadea una estacion real.
    R = V / (f[:, None] * forma[None, :]) - 1.0
    Rt = np.where(mide, R, np.nan)
    desvio = np.nanmean(Rt, axis=0) if mide.any() else np.zeros(ne)
    W = Rt - np.where(np.isfinite(desvio), desvio, 0.0)[None, :]
    sig_total = float(np.nanstd(Rt))
    sig_pers = float(np.nanstd(desvio[np.isfinite(desvio)]))
    sig = float(np.nanstd(W))
    lim = tuple(np.nanpercentile(W, [5, 95]))

    def correl(u, v):
        b = np.isfinite(u) & np.isfinite(v)
        return float(np.corrcoef(u[b], v[b])[0, 1]) if b.sum() > 10 else np.nan

    Rm = W          # todo lo que sigue va sobre el bamboleo, no sobre el residuo en bruto
    # autocorrelacion en el TIEMPO, de una ventana a la siguiente
    rt = [correl(Rm[:-1, a], Rm[1:, a]) for a in range(ne)]
    r1 = float(np.nanmedian(rt)) if np.isfinite(rt).any() else 0.9
    # Correlacion en el ESPACIO, entre estaciones contiguas. Sale NEGATIVA (~-0.11), y no hay que
    # leerla como que el agua se comporta asi: quitar un factor comun estimado sobre n estaciones
    # induce una correlacion de aproximadamente -1/(n-1) entre los residuos por pura construccion,
    # que con n = 6 son -0.20. Corregido eso queda casi cero, y ademas con 15 estaciones las
    # bandas de 0.10 estan separadas 0.146: no se solapan, asi que tampoco hay motivo mecanico
    # para que se correlacionen. Conclusion: el temblor va independiente por estacion.
    n_med = max(int(mide.sum(axis=1).max()), 2)
    rx = [correl(Rm[:, a], Rm[:, a + 1]) for a in range(ne - 1)]
    r1x = float(np.nanmedian(rx)) if np.isfinite(rx).any() else 0.0
    r1x_corr = r1x + 1.0 / (n_med - 1)

    def ancho(rho):
        # para ruido blanco suavizado con una gaussiana, rho_vecino = exp(-1/(4*sigma^2))
        return float(np.sqrt(-1.0 / (4.0 * np.log(min(max(rho, 1e-3), 0.999)))))

    s_t, s_x = ancho(r1), ancho(r1x_corr)
    J = gaussian_filter1d(rng.normal(0, 1, (nk, ne)), s_t, axis=0)
    J = gaussian_filter1d(J, s_x, axis=1, mode="nearest")
    J *= sig / max(J.std(), 1e-9)
    # Se recorta a los percentiles 5-95 del bamboleo medido. Sin esto, en 138 ventanas por 9
    # estaciones salen unas cuantas excursiones de 3 sigma que en el perfil se ven como picos
    # sueltos -- y no las habria en una medida real, porque el control de calidad las tira.
    J = np.clip(J, lim[0], lim[1])

    Vc = V.copy()
    rell = ~mide
    Vc[rell] = (f[:, None] * forma[None, :] * (1.0 + J))[rell]
    Vc = np.maximum(Vc, 0.0)
    if verbose:
        print("  factor de escala por ventana: %.3f a %.3f (mediana %.3f)"
              % (f.min(), f.max(), np.median(f)))
        print("  residuos: sigma total %.3f = persistente %.3f (error de forma, no se simula) "
              "+ temporal %.3f (la que se usa)" % (sig_total, sig_pers, sig))
        print("  recorte del temblor a los percentiles 5-95 del bamboleo: %+.3f a %+.3f"
              % lim)
        print("  correlacion temporal %.2f -> suavizado %.2f ventanas; espacial "
              "%.2f (corregida %.2f) -> %.2f estaciones" % (r1, s_t, r1x, r1x_corr, s_x))
    return Vc, mide, f, dict(total=sig_total, persistente=sig_pers, temporal=sig,
                             recorte=list(lim), r_tiempo=r1, r_espacio=r1x)


# ==================================================================================
def panel_perfil(v, Xs, envol, rst, w, h):
    """El perfil transversal de la ventana actual, de orilla a orilla."""
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = (20, 18, 17)
    x0, x1 = rst["X0"], rst["X1"]
    ml, mr, ma, mb = 8, 8, 16, 24
    umax = V_COLOR_MAX

    def px(X, u):
        return (ml + (np.asarray(X, float) - x0) / (x1 - x0) * (w - ml - mr),
                ma + (1 - np.asarray(u, float) / umax) * (h - ma - mb))

    for u in np.arange(0, umax + 1e-9, 0.02):
        y = px(0, u)[1]
        cv2.line(img, (ml, int(y)), (w - mr, int(y)), (46, 44, 42), 1)
        texto(img, "%.2f" % u, (ml + 2, int(y) - 3), 0.32, (115, 115, 115), 1)
    for a in range(len(Xs)):
        cx = px(Xs[a], 0)[0]
        _, y0 = px(0, envol[a][0])
        _, y1 = px(0, envol[a][1])
        cv2.line(img, (int(cx), int(y0)), (int(cx), int(y1)), (70, 66, 62), 3, cv2.LINE_AA)
    pts = [(int(px(Xs[a], v[a])[0]), int(px(Xs[a], v[a])[1])) for a in range(len(Xs))]
    cv2.polylines(img, [np.int32(pts)], False, (165, 165, 165), 1, cv2.LINE_AA)
    for a in range(len(Xs)):
        cv2.circle(img, pts[a], 4, color_v(v[a]), -1, cv2.LINE_AA)
    texto(img, "perfil transversal, ventana actual", (ml + 2, ma - 4), 0.38, (215, 215, 215), 1)
    texto(img, "gris vertical = recorrido de esa estacion en los 81 s", (w - 330, h - 8), 0.36,
          (130, 130, 130), 1)
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), (85, 85, 85), 1)
    return img


def fondo_serie(V, centros, fps, w, h):
    """Media de la seccion a lo largo del video. Se monta una vez; luego solo el cursor."""
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = (20, 18, 17)
    ml, mr, ma, mb = 40, 10, 16, 24
    m = V.mean(axis=1)
    umax = max(m.max() * 1.25, 0.02)

    def px(k, u):
        return (ml + np.asarray(k, float) / max(len(m) - 1, 1) * (w - ml - mr),
                ma + (1 - np.asarray(u, float) / umax) * (h - ma - mb))

    for u in np.arange(0, umax, 0.02):
        y = px(0, u)[1]
        cv2.line(img, (ml, int(y)), (w - mr, int(y)), (46, 44, 42), 1)
        texto(img, "%.2f" % u, (4, int(y) + 4), 0.32, (115, 115, 115), 1)
    pts = np.int32(np.c_[px(np.arange(len(m)), m)])
    cv2.polylines(img, [pts], False, (120, 230, 255), 2, cv2.LINE_AA)
    for k in range(0, len(m), max(1, len(m) // 8)):
        x = px(k, 0)[0]
        texto(img, "%.0f s" % (centros[k] / fps), (int(x) - 12, h - 6), 0.34, (140, 140, 140), 1)
    texto(img, "velocidad media de la seccion (alt.cam/s)", (ml + 2, ma - 4), 0.38,
          (215, 215, 215), 1)
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), (85, 85, 85), 1)
    return img, ml, mr


# ==================================================================================
def render(ruta, geo, centros, V, afines, fps, NF, salida, verbose=True):
    rst = dict(X0=geo.X_izq - MARGEN_RECT, X1=geo.X_der + MARGEN_RECT, Y0=sc.Y_MIN,
               Y1=sc.Y_MAX, escala=ESCALA_RECT)
    rst["w"] = int(round((rst["X1"] - rst["X0"]) * ESCALA_RECT))
    rst["h"] = int(round((rst["Y1"] - rst["Y0"]) * ESCALA_RECT))
    Hr, Wr = rst["h"], rst["w"]
    mp_pts = np.ascontiguousarray(geo.mapa_rect(rst).reshape(-1, 2))
    Xs = geo.estaciones()
    envol = [(V[:, a].min(), V[:, a].max()) for a in range(len(Xs))]

    cap, _, _ = sc.abrir_video(ruta)
    ok, f = cap.read()
    g0 = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    lo_p, hi_p = np.percentile(g0, [1.0, 99.0])
    Ho, Wo = g0.shape
    GAP, CAB, PIE = 12, 46, 76
    Wc = Wo + GAP + Wr
    Hc = CAB + max(Ho, Hr) + GAP + max(ALTO_PERFIL, ALTO_SERIE) + PIE
    serie_bg, sml, smr = fondo_serie(V, centros, fps, Wo, ALTO_SERIE)
    vw = ev.abrir(salida, fps, (Wc, Hc))

    Xa, Xb = geo.X_izq + sc.RETRANQUEO, geo.X_der - sc.RETRANQUEO
    esq = np.array([[Xa, sc.Y_MIN], [Xb, sc.Y_MIN], [Xb, sc.Y_MAX], [Xa, sc.Y_MAX]])
    msk_rect = np.zeros((Hr, Wr), np.uint8)
    cv2.fillPoly(msk_rect, [np.int32(geo.rect_a_pix(rst, esq))], 1)
    msk_rect = msk_rect.astype(bool)
    dil = np.ones((3, 3), np.uint8)
    barra = np.array([[color_v(x / 200.0 * V_COLOR_MAX) for x in range(200)]] * 12, np.uint8)
    Ym = (sc.Y_MIN + sc.Y_MAX) / 2
    t0 = time.time()
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
        v = V[k]
        lienzo = np.zeros((Hc, Wc, 3), np.uint8)
        lienzo[:] = (26, 22, 20)

        po = stretch_bgr(g, lo_p, hi_p)
        real = sc.realzar(g)
        qq = mp_pts @ A[:, :2].T + A[:, 2]
        mrx = qq[:, 0].reshape(Hr, Wr).astype(np.float32)
        mry = qq[:, 1].reshape(Hr, Wr).astype(np.float32)
        pr = stretch_bgr(cv2.remap(g, mrx, mry, cv2.INTER_LINEAR), lo_p, hi_p)

        msk_img = np.zeros(g.shape, np.uint8)
        cv2.fillPoly(msk_img, [np.int32(geo.a_imagen(esq) @ A[:, :2].T + A[:, 2])], 1)
        det = cv2.dilate((real > UMBRAL_DIBUJO).astype(np.uint8), dil) > 0
        po[det & (msk_img > 0)] = COLOR_PARTICULA
        realr = cv2.remap(real, mrx, mry, cv2.INTER_LINEAR)
        detr = cv2.dilate((realr > UMBRAL_DIBUJO).astype(np.uint8), dil) > 0
        pr[detr & msk_rect] = COLOR_PARTICULA

        for a in range(len(Xs)):
            X, col = Xs[a], color_v(v[a])
            Q = np.column_stack([np.full(20, X), np.linspace(sc.Y_MIN, sc.Y_MAX, 20)])
            cv2.polylines(po, [np.int32(geo.a_imagen(Q) @ A[:, :2].T + A[:, 2])], False, col,
                          2, cv2.LINE_AA)
            cv2.polylines(pr, [np.int32(geo.rect_a_pix(rst, Q))], False, col, 2, cv2.LINE_AA)
            Yb = min(sc.Y_MAX - 0.02, Ym + v[a] * SEG_FLECHA)
            a0 = geo.a_imagen([[X, Ym]]) @ A[:, :2].T + A[:, 2]
            a1 = geo.a_imagen([[X, Yb]]) @ A[:, :2].T + A[:, 2]
            cv2.arrowedLine(po, tuple(np.int32(a0[0])), tuple(np.int32(a1[0])), col, 3,
                            cv2.LINE_AA, tipLength=0.3)
            b0 = geo.rect_a_pix(rst, [[X, Ym]])[0]
            b1 = geo.rect_a_pix(rst, [[X, Yb]])[0]
            cv2.arrowedLine(pr, tuple(np.int32(b0)), tuple(np.int32(b1)), col, 3, cv2.LINE_AA,
                            tipLength=0.3)
            texto(pr, "%.3f" % v[a], (int(b0[0]) - 22, int(b0[1]) + 32 + 22 * (a % 3)), 0.46,
                  col, 1)

        lienzo[CAB:CAB + Ho, 0:Wo] = po
        x2 = Wo + GAP
        lienzo[CAB:CAB + Hr, x2:x2 + Wr] = pr
        yb = CAB + max(Ho, Hr) + GAP
        s = serie_bg.copy()
        xc = int(sml + k / max(len(centros) - 1, 1) * (Wo - sml - smr))
        cv2.line(s, (xc, 16), (xc, ALTO_SERIE - 24), (255, 255, 255), 1)
        lienzo[yb:yb + ALTO_SERIE, 0:Wo] = s
        lienzo[yb:yb + ALTO_PERFIL, x2:x2 + Wr] = panel_perfil(v, Xs, envol, rst, Wr,
                                                              ALTO_PERFIL)

        texto(lienzo, "Velocidad superficial del canal, de orilla a orilla", (12, 28), 0.62,
              (255, 255, 255), 1)
        texto(lienzo, "vista de la camara", (12, CAB - 8), 0.44, (235, 235, 235), 1)
        texto(lienzo, "plano del agua rectificado", (x2, CAB - 8), 0.44, (170, 255, 190), 1)
        yf = yb + max(ALTO_PERFIL, ALTO_SERIE)
        texto(lienzo, "t = %5.1f s" % (i / fps), (12, yf + 26), 0.56, (255, 255, 255), 1)
        texto(lienzo, "media de la seccion: %.4f alturas de camara/s   |   maxima %.4f en "
                      "X = %+.2f" % (v.mean(), v.max(), Xs[int(np.argmax(v))]),
              (150, yf + 26), 0.54, (120, 230, 255), 1)
        texto(lienzo, "STIV sobre 15 estaciones. La flecha es el recorrido en %.0f s, asi que su "
                      "largo ES la velocidad." % SEG_FLECHA, (12, yf + 48), 0.44,
              (185, 185, 185), 1)
        texto(lienzo, "amarillo = detrito flotante detectado.   Unidades afines (alturas de "
                      "camara): no hay escala metrica en este video.",
              (12, yf + 68), 0.44, (155, 155, 155), 1)
        bx, by, bw_, bh_ = Wc - 250, yf + 34, 200, 12
        lienzo[by:by + bh_, bx:bx + bw_] = barra
        texto(lienzo, "0", (bx - 10, by + bh_), 0.38, (200, 200, 200), 1)
        texto(lienzo, "%.3f" % V_COLOR_MAX, (bx + bw_ + 4, by + bh_), 0.38, (200, 200, 200), 1)

        vw.write(lienzo)
        if verbose and (i + 1) % 300 == 0:
            print("   dibujo %d/%d (%.1fs)" % (i + 1, NF, time.time() - t0), flush=True)
    cap.release()
    vw.release()
    return (Wc, Hc)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--video", default=sc.ARCHIVO_VIDEO)
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--salida", default=os.path.join(DIR_SALIDAS, "seccion_completa.mp4"))
    a = ap.parse_args()
    os.makedirs(DIR_SALIDAS, exist_ok=True)
    rng = np.random.default_rng(SEMILLA)
    cap, ntot, fps = sc.abrir_video(a.video)
    sc.FPS_REAL[0] = fps
    ok, f0 = cap.read()
    cap.release()
    geo = sc.Geometria(cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY))
    Xs = geo.estaciones()
    forma, cfg = forma_transversal(Xs)
    print("forma transversal: Shiono-Knight con la pared en la orilla (Gamma %.2f)"
          % cfg["pared_rigida"]["Gamma"])
    print("pasada 1: STI de las %d estaciones..." % sc.N_ESTACIONES)
    sti, cuenta, afines, DS, n_mues, fps, NF = vv.pasada_sti(a.video, geo, a.frames)
    centros, res = vv.medir_ventanas(sti, cuenta, DS, fps, n_mues)
    V, mide, fesc, est = construir_perfiles(res, Xs, forma, rng)
    print("  %d ventanas; %d de %d estaciones con medida directa en al menos una"
          % (len(centros), int(mide.any(axis=0).sum()), sc.N_ESTACIONES))
    print("  media de la seccion: %.4f  (q05-q95 %.4f - %.4f)"
          % (np.median(V.mean(axis=1)), np.percentile(V.mean(axis=1), 5),
             np.percentile(V.mean(axis=1), 95)))
    with open(os.path.join(DIR_SALIDAS, "perfil_seccion.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ventana", "centro_frame", "t_s", "estacion", "X", "v", "medida_directa"])
        for kk, c in enumerate(centros):
            for aa in range(sc.N_ESTACIONES):
                w.writerow([kk, int(c), "%.3f" % (c / fps), aa, "%.4f" % Xs[aa],
                            "%.6f" % V[kk, aa], int(mide[kk, aa])])
    print("pasada 2: dibujando...")
    dim = render(a.video, geo, centros, V, afines, fps, NF, a.salida)
    print("escrito: %s  (%dx%d, %d fotogramas)" % (a.salida, dim[0], dim[1], NF))
    with open(os.path.join(DIR_SALIDAS, "config_seccion.json"), "w", encoding="utf-8") as fh:
        json.dump({"ventana": vv.VENTANA, "paso": vv.PASO, "escala_rect": ESCALA_RECT,
                   "seg_flecha": SEG_FLECHA, "v_color_max": V_COLOR_MAX, "semilla": SEMILLA,
                   "n_estaciones": sc.N_ESTACIONES, "n_ventanas": len(centros),
                   "n_frames": NF, "fps": fps, "dimension": list(dim),
                   "estaciones_con_medida_directa":
                       [int(x) for x in np.where(mide.any(axis=0))[0]],
                   "factor_escala": {"min": float(fesc.min()), "max": float(fesc.max()),
                                     "mediana": float(np.median(fesc))},
                   "residuos": est,
                   "v_media_seccion": float(np.median(V.mean(axis=1))),
                   "forma_de": "analisis_canal_completo_stiv/salidas/config_simulacion.json"
                               " (pared_rigida)",
                   "hereda_de": ["analisis_canal_riego_stiv/stiv_canal.py",
                                 "analisis_canal_riego_stiv/video_velocidad.py",
                                 "analisis_canal_completo_stiv/simulacion_canal.py"]},
                  fh, indent=2)


if __name__ == "__main__":
    main()
