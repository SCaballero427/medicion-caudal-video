"""Figuras del caso. Se llaman desde `stiv_canal.py`; no se ejecuta por si solo.

Todas las figuras que muestran el agua van con estirado de contraste, como en el caso Bradano:
el agua de este canal es casi uniforme y sin estirar sale como un rectangulo liso. La diferencia
con Bradano es que aqui no es por oscuridad (el brillo medio es 147/255) sino por falta de
contraste local -- el codec ha aplanado la superficie.
"""
import os

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import stiv_canal as sc

DIR = sc.DIR_SALIDAS


def _estirar(a, lo=1.0, hi=99.0):
    a = a.astype(np.float32)
    p0, p1 = np.percentile(a, [lo, hi])
    return np.clip((a - p0) / max(p1 - p0, 1e-6), 0, 1)


def _guardar(fig, nombre):
    fig.savefig(os.path.join(DIR, nombre), dpi=110, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)


# ----------------------------------------------------------------------------------
def fig1_geometria(gris, geo, filas):
    """Orillas, punto de fuga, estaciones, y la vista rectificada al lado."""
    fig, ax = plt.subplots(1, 2, figsize=(15, 5.0))
    vis = cv2.cvtColor(gris, cv2.COLOR_GRAY2RGB)
    H, W = gris.shape
    ys = np.arange(0, H, 4)
    for a_, b_, col in ((geo.al, geo.bl, (255, 60, 60)), (geo.ar, geo.br, (60, 220, 60))):
        xs = a_ * ys + b_
        for x, y in zip(xs, ys):
            if 0 <= x < W:
                cv2.circle(vis, (int(x), int(y)), 1, col, -1)
    ax[0].imshow(vis)
    ax[0].plot([0, W], [geo.yv, geo.yv], "--", color="magenta", lw=1.2)
    ax[0].plot([geo.xv], [geo.yv], "x", color="magenta", ms=11, mew=2.5)
    ax[0].annotate("punto de fuga (%.0f, %.0f)\nhorizonte con roll nulo" % (geo.xv, geo.yv),
                   (geo.xv, geo.yv), xytext=(geo.xv + 30, geo.yv + 62), color="magenta",
                   fontsize=8, arrowprops=dict(arrowstyle="->", color="magenta", lw=1))
    # lineas de busqueda de cada estacion
    for f in filas:
        P = np.column_stack([np.full(40, f["X"]), np.linspace(sc.Y_MIN, sc.Y_MAX, 40)])
        I = geo.a_imagen(P)
        col = "#00d0ff" if f["aceptada"] else "#ff7f0e"
        ax[0].plot(I[:, 0], I[:, 1], "-", color=col, lw=1.4, alpha=0.9)
    ax[0].set_xlim(0, W); ax[0].set_ylim(H, -70)
    ax[0].set_title("vista de la camara: orillas ajustadas por RANSAC y %d lineas de busqueda\n"
                    "(azul = aceptada, naranja = rechazada)" % len(filas), fontsize=9)
    ax[0].axis("off")

    rst = geo.raster(escala=200)
    mp = geo.mapa_rect(rst)
    rec = cv2.remap(gris, mp[:, :, 0], mp[:, :, 1], cv2.INTER_LINEAR)
    ax[1].imshow(_estirar(rec), cmap="gray")
    for a_, X in ((0, geo.X_izq), (1, geo.X_der)):
        p = geo.rect_a_pix(rst, np.column_stack([np.full(2, X), [sc.Y_MIN, sc.Y_MAX]]))
        ax[1].plot(p[:, 0], p[:, 1], "-", color="#00ff66", lw=1.6)
    for f in filas:
        p = geo.rect_a_pix(rst, np.column_stack([np.full(2, f["X"]), [sc.Y_MIN, sc.Y_MAX]]))
        ax[1].plot(p[:, 0], p[:, 1], "-", lw=1.2,
                   color="#00d0ff" if f["aceptada"] else "#ff7f0e", alpha=0.9)
    ax[1].set_title("plano del agua rectificado. Que las orillas salgan paralelas NO valida la\n"
                    "geometria: es identidad, el punto de fuga ES su interseccion. Lo que la\n"
                    "valida son las estelas rectas de fig2 y fig3.", fontsize=8.5)
    ax[1].axis("off")
    fig.suptitle("fig1  Geometria por punto de fuga, sin ningun punto de control",
                 fontsize=11, y=1.02)
    _guardar(fig, "fig1_geometria.png")


# ----------------------------------------------------------------------------------
def fig2_realce(gris, geo, video):
    """La leccion del caso: sin top-hat la STI es ruido de macrobloques; con top-hat, estelas."""
    cap = cv2.VideoCapture(video)
    N = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    DS = sc.V_ESPERADA / cap.get(cv2.CAP_PROP_FPS)
    n_mues = int((sc.Y_MAX - sc.Y_MIN) / DS)
    Yv = sc.Y_MIN + DS * np.arange(n_mues)
    NF = min(500, N)
    Xst = 0.42
    I = geo.a_imagen(np.column_stack([np.full(n_mues, Xst), Yv]))
    mx = I[:, 0].astype(np.float32).reshape(1, -1)
    my = I[:, 1].astype(np.float32).reshape(1, -1)
    crudo = np.empty((NF, n_mues), np.float32)
    real = np.empty((NF, n_mues), np.float32)
    f0 = None
    for i in range(NF):
        ok, f = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        if f0 is None:
            f0 = g
        crudo[i] = cv2.remap(g.astype(np.float32), mx, my, cv2.INTER_LINEAR)[0]
        real[i] = cv2.remap(sc.realzar(g), mx, my, cv2.INTER_LINEAR)[0]
    cap.release()
    crudo = crudo[:i]; real = real[:i]
    crudo = crudo - crudo.mean(0)
    real = real - real.mean(0)

    fig = plt.figure(figsize=(15, 6.4))
    gs = fig.add_gridspec(2, 3, width_ratios=[1.0, 1.25, 1.25], hspace=0.28, wspace=0.16)
    # recorte del agua en crudo y realzado
    y0, y1, x0, x1 = 300, 470, 560, 900
    a0 = fig.add_subplot(gs[0, 0])
    a0.imshow(_estirar(f0[y0:y1, x0:x1], 2, 98), cmap="gray")
    a0.set_title("agua en crudo (estirada)\nbrillo medio 147/255", fontsize=8)
    a0.axis("off")
    a1 = fig.add_subplot(gs[1, 0])
    a1.imshow(np.clip(sc.realzar(f0)[y0:y1, x0:x1] / 12.0, 0, 1), cmap="gray")
    a1.set_title("tras el top-hat: solo los detritos", fontsize=8)
    a1.axis("off")
    a2 = fig.add_subplot(gs[:, 1])
    a2.imshow(_estirar(crudo, 1, 99), cmap="gray", aspect="auto")
    a2.set_title("STI SIN realce: macrobloques de H.264.\nla correlacion de conjunto da 0.95 con"
                 " el pico clavado en cero", fontsize=8.5)
    a2.set_xlabel("posicion a lo largo del canal ->"); a2.set_ylabel("tiempo ->")
    a3 = fig.add_subplot(gs[:, 2])
    a3.imshow(np.clip(real / 6.0, 0, 1), cmap="gray", aspect="auto")
    a3.set_title("STI CON top-hat: estelas rectas.\nrectas porque el plano esta rectificado",
                 fontsize=8.5)
    a3.set_xlabel("posicion a lo largo del canal ->")
    fig.suptitle("fig2  El realce top-hat es lo que hace medible este video (estacion X = %+.2f)"
                 % Xst, fontsize=11, y=0.99)
    _guardar(fig, "fig2_realce.png")


# ----------------------------------------------------------------------------------
def fig3_sti(sti, filas, info):
    """STI de varias estaciones con la pendiente medida dibujada encima."""
    sel = [f for f in filas if f["aceptada"]]
    if len(sel) < 2:
        sel = sorted(filas, key=lambda f: -f["densidad"])[:4]
    sel = sel[:4]
    otras = [f for f in filas if not f["aceptada"] and f["densidad"] < sc.DENSIDAD_MIN]
    muestra = sel + otras[len(otras) // 2:len(otras) // 2 + 2]
    n = len(muestra)
    fig, ax = plt.subplots(1, n, figsize=(3.1 * n, 5.2))
    if n == 1:
        ax = [ax]
    DS = info["DS"]; fps = info["fps"]
    for k, f in enumerate(muestra):
        im = sti[f["estacion"]]
        ax[k].imshow(np.clip(im / 6.0, 0, 1), cmap="gray", aspect="auto")
        if f["aceptada"]:
            pend = f["v"] / (DS * fps)
            h, w = im.shape
            t0 = h * 0.08
            for x0 in (w * 0.06, w * 0.40):
                t1 = min(h * 0.95, t0 + (w * 0.30) / max(pend, 1e-6))
                ax[k].plot([x0, x0 + pend * (t1 - t0)], [t0, t1], "-",
                           color="#ff2d55", lw=1.6, alpha=0.95)
        ax[k].set_title("est %d   X=%+.2f\ndens %.4f  coh %.2f\n%s" %
                        (f["estacion"], f["X"], f["densidad"], f["coherencia"],
                         ("v = %+.4f alt.cam/s" % f["v"]) if f["aceptada"]
                         else ("RECHAZADA: " + f["motivo"])),
                        fontsize=8, color="black" if f["aceptada"] else "#c1121f")
        ax[k].set_xticks([]); ax[k].set_yticks([])
        if k == 0:
            ax[k].set_ylabel("tiempo ->", fontsize=8)
    fig.suptitle("fig3  Imagenes espacio-temporales. La linea roja es la pendiente que mide el "
                 "tensor.\nLas estaciones sin trazador no son ruidosas: estan vacias.",
                 fontsize=10.5, y=1.03)
    _guardar(fig, "fig3_sti.png")


# ----------------------------------------------------------------------------------
def fig4_control_calidad(filas):
    """Densidad (dos umbrales) y coherencia por estacion."""
    X = np.array([f["X"] for f in filas])
    d = np.array([f["densidad"] for f in filas])
    c = np.array([f["coherencia"] for f in filas])
    ok = np.array([f["aceptada"] for f in filas])
    fig, ax = plt.subplots(1, 2, figsize=(13.5, 4.4))
    ax[0].semilogy(X[~ok], np.maximum(d[~ok], 1e-6), "o", color="#ff7f0e", label="rechazada")
    ax[0].semilogy(X[ok], np.maximum(d[ok], 1e-6), "o", color="#0077b6", label="aceptada")
    ax[0].axhline(sc.DENSIDAD_MIN, ls="--", color="#c1121f")
    ax[0].axhline(sc.DENSIDAD_MAX, ls="--", color="#6a4c93")
    ax[0].annotate("DENSIDAD_MIN = %.3f" % sc.DENSIDAD_MIN, (X.min(), sc.DENSIDAD_MIN * 1.25),
                   color="#c1121f", fontsize=8)
    ax[0].annotate("DENSIDAD_MAX = %.2f  (orilla)" % sc.DENSIDAD_MAX,
                   (X.min(), sc.DENSIDAD_MAX * 1.25), color="#6a4c93", fontsize=8)
    ax[0].set_xlabel("X  (transversal, alturas de camara)")
    ax[0].set_ylabel("densidad de particulas")
    ax[0].set_title("Densidad de trazador: tres poblaciones, dos huecos de factor 10",
                    fontsize=9.5)
    ax[0].grid(alpha=0.3, which="both"); ax[0].legend(fontsize=8)
    ax[1].plot(X[~ok], c[~ok], "o", color="#ff7f0e", label="rechazada")
    ax[1].plot(X[ok], c[ok], "o", color="#0077b6", label="aceptada")
    ax[1].axhline(sc.COH_MIN, ls="--", color="#c1121f")
    ax[1].annotate("COH_MIN = %.2f" % sc.COH_MIN, (X.min(), sc.COH_MIN + 0.015),
                   color="#c1121f", fontsize=8)
    ax[1].set_xlabel("X  (transversal, alturas de camara)")
    ax[1].set_ylabel("coherencia sobre los bloques con senal")
    ax[1].set_title("La coherencia sola no basta: la estacion pegada a la orilla derecha\n"
                    "la pasa con 0.67 y solo la para el filtro de densidad", fontsize=9.5)
    ax[1].set_ylim(0, 1); ax[1].grid(alpha=0.3); ax[1].legend(fontsize=8)
    fig.suptitle("fig4  Control de calidad", fontsize=11, y=1.02)
    _guardar(fig, "fig4_control_calidad.png")


# ----------------------------------------------------------------------------------
def fig5_perfil(filas, res, geo):
    X = np.array([f["X"] for f in filas])
    v = np.array([f["v"] for f in filas])
    ok = np.array([f["aceptada"] for f in filas])
    fig, ax = plt.subplots(figsize=(10.5, 5.0))
    ax.axvspan(geo.X_izq, geo.X_izq + sc.RETRANQUEO, color="0.85")
    ax.axvspan(geo.X_der - sc.RETRANQUEO, geo.X_der, color="0.85")
    ax.plot(X[ok], v[ok], "o-", color="#0077b6", lw=2, ms=7, label="STIV aceptada")
    vtop = float(np.nanmax(v[ok])) * 1.18 if ok.any() else 0.08
    ax.plot(X[~ok], np.clip(v[~ok], -0.005, vtop), "x", color="#ff7f0e", ms=8,
            label="rechazada (valor sin sentido; recortado al margen)")
    ax.axhline(res["v_mediana"], ls="--", color="#023047",
               label="mediana %.4f alt.cam/s" % res["v_mediana"])
    ax.axhspan(res["v_q05"], res["v_q95"], color="#0077b6", alpha=0.12,
               label="q05-q95")
    ax.axvline(geo.X_izq, color="k", lw=1.2)
    ax.axvline(geo.X_der, color="k", lw=1.2)
    ax.annotate("no hay ni un trazador en esta mitad:\ndensidad 0.00000 - 0.00113",
                (geo.X_izq + 0.15, 0.062), fontsize=9, color="#c1121f")
    ax.annotate("banda de detritos que caen\nde la vegetacion de la orilla derecha",
                (0.10, 0.006), fontsize=9, color="#0077b6")
    ax.set_xlabel("X  transversal  (alturas de camara; 0 = eje del canal)")
    ax.set_ylabel("velocidad superficial  (alturas de camara / s)")
    ax.set_title("fig5  Perfil transversal: %d de %d estaciones medidas.\n"
                 "Las rechazadas NO se rellenan -- no hay seccion que integrar."
                 % (res["n_aceptadas"], res["n_estaciones"]), fontsize=10.5)
    ax.grid(alpha=0.3); ax.legend(fontsize=8, loc="upper left")
    _guardar(fig, "fig5_perfil.png")


# ----------------------------------------------------------------------------------
def fig6_arbitro(filas):
    """STIV contra el arbitro PTV, si `ptv_arbitro.py` ya se ha ejecutado."""
    ruta = os.path.join(DIR, "ptv_perfil.csv")
    if not os.path.exists(ruta):
        return False
    import csv as _csv
    P = list(_csv.DictReader(open(ruta, encoding="utf-8")))
    pX = np.array([float(r["X"]) for r in P])
    pV = np.array([float(r["v"]) for r in P])
    pN = np.array([int(r["n_pistas"]) for r in P])
    ac = [f for f in filas if f["aceptada"]]
    sX = np.array([f["X"] for f in ac]); sV = np.array([f["v"] for f in ac])
    sF = np.array([f.get("v_fft", np.nan) for f in ac], float)
    fig, ax = plt.subplots(1, 2, figsize=(13.5, 4.6))
    ax[0].plot(pX, pV, "s--", color="#6a4c93", ms=6, label="PTV (arbitro independiente)")
    mF = np.isfinite(sF) & (sF > 0)
    if mF.any():
        ax[0].plot(sX[mF], sF[mF], "^:", color="#e07a5f", ms=6,
                   label="STIV, cresta FFT (2o estimador)")
    ax[0].plot(sX, sV, "o-", color="#0077b6", ms=7, lw=2, label="STIV, tensor (el que manda)")
    ax[0].set_xlabel("X transversal (alturas de camara)")
    ax[0].set_ylabel("velocidad (alturas de camara / s)")
    ax[0].set_title("Perfil: dos metodos que no comparten codigo", fontsize=9.5)
    ax[0].grid(alpha=0.3); ax[0].legend(fontsize=8)
    par = []
    for x, vv in zip(sX, sV):
        j = np.argmin(np.abs(pX - x))
        if abs(pX[j] - x) < 0.08 and pN[j] >= 20:
            par.append((pV[j], vv))
    if par:
        par = np.array(par)
        ax[1].plot(par[:, 0], par[:, 1], "o", color="#0077b6", ms=8)
        lim = [0, max(par.max(), 0.07) * 1.15]
        ax[1].plot(lim, lim, "k--", lw=1, label="1:1")
        r = np.corrcoef(par[:, 0], par[:, 1])[0, 1]
        sesgo = np.median(par[:, 1] / par[:, 0] - 1) * 100
        rmse = float(np.sqrt(np.mean((par[:, 1] - par[:, 0]) ** 2)))
        ax[1].set_xlim(lim); ax[1].set_ylim(lim)
        ax[1].set_xlabel("PTV  (alt.cam/s)"); ax[1].set_ylabel("STIV  (alt.cam/s)")
        ax[1].set_title("r = %+.3f    sesgo %+.1f %%    RMSE %.4f\n(n = %d estaciones)"
                        % (r, sesgo, rmse, len(par)), fontsize=9.5)
        ax[1].grid(alpha=0.3); ax[1].legend(fontsize=8)
    fig.suptitle("fig6  STIV contra rastreo de particulas: el arbitro no usa ningun dato de "
                 "campo,\nsolo el mismo video por otro camino", fontsize=10.5, y=1.03)
    _guardar(fig, "fig6_arbitro.png")
    return True


# ----------------------------------------------------------------------------------
def todas(gris, geo, sti, Yv, info, filas, res, video):
    fig1_geometria(gris, geo, filas)
    fig2_realce(gris, geo, video)
    fig3_sti(sti, filas, info)
    fig4_control_calidad(filas)
    fig5_perfil(filas, res, geo)
    if not fig6_arbitro(filas):
        print("   (fig6 pendiente: ejecuta ptv_arbitro.py y vuelve a lanzar)")
