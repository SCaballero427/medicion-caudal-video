"""Solo velocidad por STIV: lo mismo que `velocidad_nivel_curva.py` sin la mira.

Que hace
--------
Identico a `velocidad_nivel_curva.py` en todo lo que toca a la velocidad -- misma
geometria del agua, mismo tensor, mismo hold, mismo tratamiento de las estaciones de
muro, mismo lenguaje visual y tiempo real -- pero **sin nada de nivel**: no se muestrea
la mira, no se rectifica su banda, no hay recuadro en la esquina ni linea sobre la
chapa, y el CSV de nivel no existe.

Sirve para dos cosas: mirar el agua sin nada encima que distraiga, y ahorrarse la
pasada sobre el video que cuesta la mira (unos 9 s de los 110 del total).

Lo que se conserva de las decisiones tomadas
--------------------------------------------
* **Hold de 5 ventanas.** Una estacion caida mantiene su ultimo valor valido hasta
  0.6 s, dibujada con anillo hueco en vez de circulo lleno.
* **Estaciones de muro marcadas y fuera de los agregados.** La 0 y la 10 miran al
  hormigon y dan 0.00 m/s con coherencia alta; se ven con su cero, pero no entran ni en
  la mediana de la seccion ni en el rango de la barra de color.
* **Muestreo del tensor corregido**: STI de 4 m, bloque 32, coherencia 0.35. Con los 3
  bloques que dejaba la configuracion anterior se caia el 20 % de las ventanas.

Uso
---
    python velocidad_sin_nivel.py                 # video entero
    python velocidad_sin_nivel.py --frames 200    # prueba corta
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

RUTA_SALIDA = os.path.join(si.DIR_CASO, "salidas", "velocidad_sin_nivel.mp4")

ALTO_PANEL = si.ALTO_PANEL
HUECO = si.HUECO
ALTO_CABECERA = si.ALTO_CABECERA
ALTO_PIE = 52


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

    # --- pasada 1: velocidad --------------------------------------------------------------
    print(f"\nPasada 1/2 - rectificando el agua y muestreando las {cfg['n_est']} estaciones")
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
    # Ninguna estacion de agua puede verse caida: el hold se prolonga sin limite.
    V, E = vn.rellenar_continuo(V, E, agua)
    Va = np.where(agua[None, :], V, np.nan)
    vmed = np.nanmedian(Va, axis=1)
    lo, hi = np.nanpercentile(np.abs(Va), [2, 98])
    hi = max(hi, lo + 1e-6)
    print(f"\nEstaciones: {int(agua.sum())} de agua, {int(muro.sum())} de muro "
          f"({', '.join(str(i) for i in np.where(muro)[0]) or 'ninguna'})")
    for e in range(cfg["n_est"]):
        print(f"  est {e:2d} [{'MURO' if muro[e] else 'agua'}]  contraste {contraste[e]:6.2f}"
              f"  v mediana {perfil_v[e]:6.3f} {u}/s  medida {100*(E[:, e]==1).mean():5.1f} %"
              f"  sostenida {100*(E[:, e]==2).mean():4.1f} %")
    print(f"\nVelocidad mediana de la seccion (sin los muros): {np.nanmedian(vmed):.4f} {u}/s")
    print(f"Rango de color: {lo:.3f} - {hi:.3f} {u}/s")
    print(f"Estados: medida {100*(E[:, agua]==1).mean():.1f} %, sostenida "
          f"{100*(E[:, agua]==2).mean():.1f} %, caida {100*(E[:, agua]==0).mean():.1f} %")

    # --- pasada 2: render -------------------------------------------------------------------
    eo = ALTO_PANEL / alto_img
    er = ALTO_PANEL / oh
    pw_o, pw_r = int(ancho * eo), int(ow * er)
    x_o, x_r = HUECO, HUECO + pw_o + HUECO
    cw = x_r + pw_r + HUECO
    y_pie = ALTO_CABECERA + ALTO_PANEL
    ch = y_pie + ALTO_PIE
    print(f"\nPasada 2/2 - render de {n} fotogramas a {cw}x{ch}, {fps:.2f} fps (tiempo real)")
    os.makedirs(os.path.dirname(a.salida) or ".", exist_ok=True)
    vw = ev.abrir(a.salida, fps, (cw, ch))
    if not vw.isOpened():
        raise SystemExit("No se pudo abrir el escritor de video.")

    ext_r = np.float32([[pts[e, 0], pts[e, -1], centros[e]] for e in range(cfg["n_est"])])
    ext_o = cv2.perspectiveTransform(ext_r.reshape(1, -1, 2), o2i).reshape(-1, 3, 2)

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
                grosor = 3
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
                else:
                    # Todas las estaciones de agua se dibujan igual: siempre tienen valor,
                    # asi que distinguir el origen del numero solo seria ruido visual.
                    # El CSV conserva el estado para quien quiera separarlo.
                    cv2.circle(panel, q, 5, (255, 255, 255), -1)
                    cv2.circle(panel, q, 5, (20, 20, 20), 1)

        lienzo = np.zeros((ch, cw, 3), np.uint8)
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ALTO_PANEL, x_o:x_o + pw_o] = pano
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ALTO_PANEL, x_r:x_r + pw_r] = prec
        si.texto(lienzo, "vista original de la camara", (x_o, 24), 0.62, (255, 255, 255), 2)
        si.texto(lienzo, "plano rectificado", (x_r, 24), 0.62,
                 (255, 255, 255), 2)
        si.texto(lienzo, f"ventana {cfg['ventana']/fps:.1f} s   DS = {cfg['ds']} px",
                 (x_o + 300, 24), 0.5, (170, 170, 170), 1)
        si.barra_color(lienzo, lo, hi, u, cw - 330, ch - 28)

        vm = vmed[w]
        si.texto(lienzo, f"t = {k/fps:6.2f} s", (x_o, y_pie + 28), 0.66, (255, 255, 255), 2)
        si.texto(lienzo, f"v mediana de la seccion = {vm:.4f} {u}/s"
                 if np.isfinite(vm) else "v mediana = --",
                 (x_o + 180, y_pie + 28), 0.66, (120, 220, 255), 2)
        si.texto(lienzo, f"{int(agua.sum())} verticales de agua",
                 (x_o + 700, y_pie + 28), 0.6, (150, 255, 150), 2)
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
    print(f"Velocidades por ventana en: {base}_ventanas.csv "
          f"(estado 0 caida, 1 medida, 2 sostenida, 3 muro)")


if __name__ == "__main__":
    main()
