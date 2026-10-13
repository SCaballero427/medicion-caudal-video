"""Arbitro independiente: rastreo de particulas (PTV) sobre el mismo video.

Para que existe
---------------
En este caso no hay ningun dato de campo -- ni aforo, ni ancho medido, ni velocimetro. Asi que
la unica forma de saber si el numero que da STIV significa algo es medir lo mismo por un camino
que no comparta con STIV nada mas que el video y la geometria. Es la misma disciplina que la
Parte 7 del caso Arrow, donde un PIV de conjunto arbitra el STIV: **el arbitro no usa datos de
validacion, porque no hay; usa otro algoritmo.**

Y aqui el arbitro cae de forma natural, porque el trazador de este video no es una textura
continua sino particulas discretas y brillantes. Eso es exactamente lo que un rastreador de
particulas quiere y lo que un metodo de correlacion sufre. STIV no comparte con esto ni el
tensor, ni la STI, ni el promediado de banda: se detectan manchas, se enlazan entre fotogramas
y se ajusta una recta a cada trayectoria.

Lo que NO se hace
-----------------
No se ajusta ningun parametro de STIV para que se parezca a esto. El resultado de la comparacion
se reporta tal cual sale, sesgo incluido.

Uso
---
    python ptv_arbitro.py                  # video completo (~2 min)
    python ptv_arbitro.py --frames 800     # prueba corta
"""
import argparse
import csv
import json
import os

import cv2
import numpy as np

import stiv_canal as sc

# ----------------------------------------------------------------------------------
# >>> AJUSTABLE <<<
# ----------------------------------------------------------------------------------
# Umbral de deteccion sobre la imagen realzada por top-hat. Mas alto que UMBRAL_PARTICULA
# (que solo cuenta densidad) porque aqui hay que localizar un centroide, no contar.
UMBRAL_DET = 6
# Area admisible de una mancha, en pixeles de imagen. Por debajo de 2 es ruido del codec, por
# encima de 60 es un reflejo o una zona de espuma, no una particula con centroide util.
AREA_MIN, AREA_MAX = 2, 60
# Salto maximo entre fotogramas consecutivos, en alturas de camara. A la velocidad medida el
# desplazamiento real es de 0.0019 por fotograma, asi que 0.010 deja margen de sobra sin permitir
# enlaces entre particulas distintas.
SALTO_MAX = 0.010
# Una pista tiene que durar esto para contar. Es el filtro que separa las particulas de verdad
# del ruido: el ruido no persiste.
DURACION_MIN = 6
# Residuo maximo del ajuste recto, en alturas de camara. Una particula arrastrada por el flujo va
# recta; una deteccion espuria que salta no.
RESIDUO_MAX = 0.004
# Velocidad minima para que la pista cuente como movimiento.
V_MIN = 0.005
# Caja de agua util, como fraccion del ancho desde cada orilla.
MARGEN_ORILLA = 0.04


def detectar(ruta, geo, n_frames=None, verbose=True):
    cap, ntot, fps = sc.abrir_video(ruta)
    NF = ntot if n_frames is None else min(n_frames, ntot)
    ok, f = cap.read()
    g0 = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    mask = np.zeros(g0.shape, np.uint8)
    mask[0:sc.FILA_BORDE_FIN - 40, :] = 255
    cv2.fillPoly(mask, [geo.poligono_agua()], 0)
    p0 = cv2.goodFeaturesToTrack(g0, 600, 0.01, 7, mask=mask)
    det = []
    for i in range(NF):
        if i > 0:
            ok, f = cap.read()
            if not ok:
                break
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        else:
            g = g0
        A, _ = sc.estimar_estabilizacion(g0, g, p0)
        # inversa de la afinidad: del fotograma actual al marco de referencia
        Ai = cv2.invertAffineTransform(A)
        t = sc.realzar(g)
        _, bw = cv2.threshold(t, UMBRAL_DET, 255, cv2.THRESH_BINARY)
        n, lab, stt, cen = cv2.connectedComponentsWithStats(bw.astype(np.uint8), 8)
        pts = [cen[j] for j in range(1, n)
               if AREA_MIN <= stt[j, cv2.CC_STAT_AREA] <= AREA_MAX]
        if pts:
            P = np.array(pts, float)
            det.append(geo.a_suelo(P @ Ai[:, :2].T + Ai[:, 2]))
        else:
            det.append(np.zeros((0, 2)))
        if verbose and (i + 1) % 400 == 0:
            print("   %d/%d fotogramas" % (i + 1, NF), flush=True)
    cap.release()
    return det, fps


def enlazar(det, geo, fps):
    x0 = geo.X_izq + MARGEN_ORILLA * geo.ancho
    x1 = geo.X_der - MARGEN_ORILLA * geo.ancho
    activas, cerradas = [], []
    for i, G in enumerate(det):
        if len(G):
            m = (G[:, 0] > x0) & (G[:, 0] < x1) & (G[:, 1] > sc.Y_MIN) & (G[:, 1] < sc.Y_MAX)
            G = G[m]
        usada = np.zeros(len(G), bool)
        siguientes = []
        for tr in activas:
            f, x, y = tr[-1]
            if i - f > 2:
                if len(tr) >= DURACION_MIN:
                    cerradas.append(tr)
                continue
            if len(G):
                d = np.hypot(G[:, 0] - x, G[:, 1] - y)
                d[usada] = 9e9
                j = int(np.argmin(d))
                if d[j] < SALTO_MAX * (i - f):
                    tr.append((i, G[j, 0], G[j, 1]))
                    usada[j] = True
                    siguientes.append(tr)
                    continue
            siguientes.append(tr)
        for j in range(len(G)):
            if not usada[j]:
                siguientes.append([(i, G[j, 0], G[j, 1])])
        activas = siguientes
    for tr in activas:
        if len(tr) >= DURACION_MIN:
            cerradas.append(tr)
    filas = []
    for tr in cerradas:
        A = np.array(tr, float)
        f, x, y = A[:, 0], A[:, 1], A[:, 2]
        if f[-1] - f[0] < DURACION_MIN - 1:
            continue
        py = np.polyfit(f, y, 1)
        px = np.polyfit(f, x, 1)
        res = float(np.std(y - np.polyval(py, f)))
        filas.append((x.mean(), y.mean(), py[0] * fps, px[0] * fps, len(A), res))
    return np.array(filas)


def perfil(pistas, geo, n_bins=15):
    buenas = pistas[(pistas[:, 5] < RESIDUO_MAX) & (np.abs(pistas[:, 2]) > V_MIN)]
    bordes = np.linspace(geo.X_izq + sc.RETRANQUEO, geo.X_der - sc.RETRANQUEO, n_bins + 1)
    out = []
    for i in range(n_bins):
        m = (buenas[:, 0] >= bordes[i]) & (buenas[:, 0] < bordes[i + 1])
        c = (bordes[i] + bordes[i + 1]) / 2
        if m.sum() >= 20:
            out.append({"X": float(c), "n_pistas": int(m.sum()),
                        "v": float(np.median(buenas[m, 2])),
                        "v_q25": float(np.percentile(buenas[m, 2], 25)),
                        "v_q75": float(np.percentile(buenas[m, 2], 75)),
                        "v_X": float(np.median(buenas[m, 3]))})
        else:
            out.append({"X": float(c), "n_pistas": int(m.sum()), "v": float("nan"),
                        "v_q25": float("nan"), "v_q75": float("nan"), "v_X": float("nan")})
    return out, buenas


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--video", default=sc.ARCHIVO_VIDEO)
    ap.add_argument("--frames", type=int, default=None)
    a = ap.parse_args()
    os.makedirs(sc.DIR_SALIDAS, exist_ok=True)
    cap, ntot, fps = sc.abrir_video(a.video)
    sc.FPS_REAL[0] = fps
    ok, f0 = cap.read()
    cap.release()
    geo = sc.Geometria(cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY))
    print("PTV: detectando particulas...")
    det, fps = detectar(a.video, geo, a.frames)
    tot = sum(len(d) for d in det)
    print("  %d fotogramas, %d detecciones" % (len(det), tot))
    pistas = enlazar(det, geo, fps)
    print("  %d pistas de >= %d fotogramas" % (len(pistas), DURACION_MIN))
    prof, buenas = perfil(pistas, geo)
    print("  %d pistas rectas y con movimiento" % len(buenas))
    print("\n  X        n     v (alt.cam/s)   q25      q75      v_X")
    for r in prof:
        if r["n_pistas"] >= 20:
            print("  %+.3f  %4d   %+.4f      %+.4f  %+.4f  %+.4f" %
                  (r["X"], r["n_pistas"], r["v"], r["v_q25"], r["v_q75"], r["v_X"]))
        else:
            print("  %+.3f  %4d   -- pocas pistas" % (r["X"], r["n_pistas"]))
    vv = np.array([r["v"] for r in prof if r["n_pistas"] >= 20])
    print("\n  mediana de las bandas con datos: %+.4f alt.cam/s  (%d bandas)"
          % (np.median(vv), len(vv)))
    print("  componente transversal mediana: %+.4f  (0 = flujo puramente longitudinal)"
          % np.median(buenas[:, 3]))
    with open(os.path.join(sc.DIR_SALIDAS, "ptv_perfil.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(prof[0].keys()))
        w.writeheader()
        w.writerows(prof)
    np.save(os.path.join(sc.DIR_SALIDAS, "ptv_pistas.npy"), buenas)
    with open(os.path.join(sc.DIR_SALIDAS, "ptv_config.json"), "w", encoding="utf-8") as fh:
        json.dump({"umbral_det": UMBRAL_DET, "area": [AREA_MIN, AREA_MAX],
                   "salto_max": SALTO_MAX, "duracion_min": DURACION_MIN,
                   "residuo_max": RESIDUO_MAX, "v_min": V_MIN,
                   "n_frames": len(det), "n_detecciones": tot,
                   "n_pistas": int(len(pistas)), "n_buenas": int(len(buenas)),
                   "v_mediana_bandas": float(np.median(vv)),
                   "v_X_mediana": float(np.median(buenas[:, 3]))}, fh, indent=2)
    print("\nescrito: salidas/ptv_perfil.csv, salidas/ptv_pistas.npy, salidas/ptv_config.json")


if __name__ == "__main__":
    main()
