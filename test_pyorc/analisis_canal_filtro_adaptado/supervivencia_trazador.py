"""Cuanto trazador sobrevive al codificador segun los bits por pixel.

Que mide y por que importa
--------------------------
Es la medida mas directa de todo este experimento, y no depende del filtro adaptado ni de STIV ni
de ningun estimador: se cuenta, sin mas, **cuantos detritos quedan en la imagen** despues de
recodificar el video a resoluciones y bitrates decrecientes.

Sirve para separar las dos explicaciones posibles de que el campo lejano no sea medible:

    (a) la geometria -- alli el agua avanza 0.04 px por fotograma;
    (b) el codificador -- alli la particula ocupa menos de un pixel cuando el codificador la ve,
        y un realce de pocos niveles de gris en una region plana es lo primero que se cuantifica
        a cero.

Se mide sobre la region del campo CERCANO, donde se sabe que hay trazador de sobra, asi que
cualquier perdida es atribuible al codec y no a la falta de particulas.

Ademas fue esta medida la que delato un error en `escalera_honesta.py`: mostraba trazador
abundante justo donde el filtro decia score 0.00, lo que era imposible y llevo a encontrar que
alli faltaba reamplificar el fotograma recodificado a su tamano original.

Uso
---
    python supervivencia_trazador.py           # usa tmp_codificados/ si existe
"""
import csv
import os
import sys

import cv2
import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "analisis_canal_riego_stiv"))
import stiv_canal as sc  # noqa: E402
import escalera_honesta as eh  # noqa: E402

DIR_CASO = os.path.dirname(os.path.abspath(__file__))
DIR_SALIDAS = os.path.join(DIR_CASO, "salidas")

# ventana de imagen sobre agua con trazador abundante, en el campo cercano
REGION = (250, 450, 560, 920)      # y0, y1, x0, x1
N_FRAMES = 300


def medir(ruta, w=1024, h=576):
    cap = cv2.VideoCapture(ruta)
    y0, y1, x0, x1 = REGION
    n = c4 = c8 = tot = 0
    energia = 0.0
    mx = 0.0
    while n < N_FRAMES:
        ok, f = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        if g.shape[1] != w:
            g = cv2.resize(g, (w, h), interpolation=cv2.INTER_LINEAR)
        t = sc.realzar(g)[y0:y1, x0:x1]
        c4 += int((t > 4).sum())
        c8 += int((t > 8).sum())
        energia += float(t.sum())
        mx = max(mx, float(t.max()))
        tot += t.size
        n += 1
    cap.release()
    return dict(n_frames=n, frac_4=c4 / max(tot, 1), frac_8=c8 / max(tot, 1),
                energia=energia / max(n, 1), maximo=mx)


def main():
    os.makedirs(DIR_SALIDAS, exist_ok=True)
    filas = []
    print("supervivencia de trazador en la region de agua del campo cercano (%d fotogramas)"
          % N_FRAMES)
    print(" factor   kb/s   px>4      px>8     energia    max")
    for fac in eh.FACTORES:
        ruta = os.path.join(eh.DIR_TMP, "f%.1f.mp4" % fac)
        if not os.path.exists(ruta):
            print("  (falta %s: ejecuta antes escalera_honesta.py)" % ruta)
            continue
        kb = max(8, int(round(eh.BITRATE_ORIGINAL / (fac ** 2))))
        r = medir(ruta)
        print(" %5.1f  %5d  %.5f  %.5f  %9.1f  %5.1f"
              % (fac, kb, r["frac_4"], r["frac_8"], r["energia"], r["maximo"]))
        filas.append(dict(factor=fac, kbps=kb, **r))
    if filas:
        base = filas[0]
        print("\n  caida respecto al original: px>4 x%.0f, energia x%.1f, maximo x%.1f"
              % (base["frac_4"] / max(filas[-1]["frac_4"], 1e-9),
                 base["energia"] / max(filas[-1]["energia"], 1e-9),
                 base["maximo"] / max(filas[-1]["maximo"], 1e-9)))
        with open(os.path.join(DIR_SALIDAS, "supervivencia_trazador.csv"), "w", newline="",
                  encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
            w.writeheader()
            w.writerows(filas)
        print("escrito: salidas/supervivencia_trazador.csv")


if __name__ == "__main__":
    main()
