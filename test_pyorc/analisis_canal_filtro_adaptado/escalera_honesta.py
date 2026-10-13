"""La escalera de degradacion, pero pasando de verdad por el codificador.

Por que hace falta
------------------
La escalera de `filtro_adaptado.py` reduce el fotograma **ya descodificado**. Eso simula que la
particula se vea mas pequena, pero **no** simula lo que de verdad la mata: que la particula fuera
pequena *cuando el codificador la vio*. En el video real, un detrito del campo lejano ocupa
menos de un pixel y su realce de unos pocos niveles de gris en una region plana es exactamente lo
que la cuantificacion de H.264 a 661 kb/s pone a cero. La escalera optimista nunca paga ese
precio, porque el codificador ya habia guardado la particula a su tamano grande.

La consecuencia se vio en los resultados: la escalera optimista **sigue detectando hasta f = 6.5**,
que es justo el factor al que equivale el campo lejano -- y sin embargo el campo lejano real no da
nada. Esa contradiccion tiene dos lecturas posibles y hay que separarlas:

    (a) la escalera es optimista y quien mata la senal es el CODIFICADOR, no la geometria;
    (b) en ese tramo del canal sencillamente no pasan detritos.

Aqui se resuelve: para cada factor se **reduce y se vuelve a codificar** con ffmpeg al mismo
numero de bits por pixel que el original (661 kb/s / f^2), se descodifica, se reamplia y se mide.
Si la deteccion muere mucho antes que en la escalera optimista, la culpa es del codificador.

Uso
---
    python escalera_honesta.py                # ~15 min
    python escalera_honesta.py --factores 1 3 6.5
"""
import argparse
import csv
import os
import shutil
import subprocess
import sys

import cv2
import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "analisis_canal_riego_stiv"))
import stiv_canal as sc  # noqa: E402
import filtro_adaptado as fa  # noqa: E402

DIR_CASO = os.path.dirname(os.path.abspath(__file__))
DIR_SALIDAS = os.path.join(DIR_CASO, "salidas")
DIR_TMP = os.path.join(DIR_CASO, "tmp_codificados")

FFMPEG = os.path.join(_RAIZ, "RIVeR-STIV_1.0", "ffmpeg.exe")
if not os.path.exists(FFMPEG):
    FFMPEG = shutil.which("ffmpeg") or ""

# ----------------------------------------------------------------------------------
# >>> AJUSTABLE <<<
# ----------------------------------------------------------------------------------
BITRATE_ORIGINAL = 661            # kb/s, medido sobre el fichero de entrada
BANDA = (0.10, 0.90, 1.60, 2.90, "cerca")
FACTORES = [1.0, 1.5, 2.0, 3.0, 4.5, 6.5]


def recodificar(entrada, salida, factor, w=1024, h=576):
    """Reduce por `factor`, recodifica a los mismos bits por pixel, y **reamplia**.

    Los dos pasos son necesarios y el segundo se me olvido en la primera version, con la
    consecuencia de que toda la escalera dio score 0.00 desde f = 2: la geometria del caso
    muestrea en coordenadas de hasta 1024 px, y sobre un fotograma de 512 eso cae fuera y `remap`
    devuelve ceros. Lo delato el contraste de supervivencia de particulas, que mostraba trazador
    de sobra justo donde el filtro decia no ver nada.

    El reescalado de vuelta va en una segunda pasada de ffmpeg a CRF 12, o sea practicamente sin
    perdida, para que lo unico que degrade sea la primera codificacion -- que es lo que se quiere
    medir.
    """
    nw, nh = int(round(w / factor / 2)) * 2, int(round(h / factor / 2)) * 2
    kb = max(8, int(round(BITRATE_ORIGINAL / (factor ** 2))))
    chico = salida.replace(".mp4", "_chico.mp4")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", entrada,
                    "-vf", "scale=%d:%d:flags=area" % (nw, nh),
                    "-c:v", "libx264", "-preset", "medium", "-profile:v", "baseline",
                    "-b:v", "%dk" % kb, "-maxrate", "%dk" % (kb * 2),
                    "-bufsize", "%dk" % (kb * 4),
                    "-pix_fmt", "yuv420p", "-an", chico], check=True)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", chico,
                    "-vf", "scale=%d:%d:flags=bilinear" % (w, h),
                    "-c:v", "libx264", "-preset", "medium", "-crf", "12",
                    "-pix_fmt", "yuv420p", "-an", salida], check=True)
    return nw, nh, kb


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--video", default=sc.ARCHIVO_VIDEO)
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--factores", type=float, nargs="*", default=None)
    a = ap.parse_args()
    if not FFMPEG:
        raise SystemExit("no se encuentra ffmpeg")
    os.makedirs(DIR_SALIDAS, exist_ok=True)
    os.makedirs(DIR_TMP, exist_ok=True)
    factores = a.factores if a.factores else FACTORES

    cap, ntot, fps = sc.abrir_video(a.video)
    sc.FPS_REAL[0] = fps
    ok, f0 = cap.read()
    cap.release()
    geo = sc.Geometria(cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY))
    NF = ntot if a.frames is None else min(a.frames, ntot)
    rng = np.random.default_rng(fa.SEMILLA)
    vs = np.linspace(fa.V_MIN, fa.V_MAX, fa.N_CAND)

    filas = []
    print("factor  tamano      kb/s   n    pico      score  techo    z      veredicto")
    for fac in factores:
        ruta = os.path.join(DIR_TMP, "f%.1f.mp4" % fac)
        nw, nh, kb = recodificar(a.video, ruta, fac)
        # se lee el recodificado y se reamplia al tamano original, para que toda la geometria
        # del caso valga sin tocar nada
        pl, _, leidos = fa.construir_stis(ruta, geo, [BANDA], NF, verbose=False)
        P = pl[0]
        nv = fa.ventana_residencia(P["y1"] - P["y0"], fps)
        todos = fa.analizar_todo(P["sti"], vs, fps, P["ds"], rng, n_barajados=8, n_ventana=nv)
        ver = fa.veredicto(todos["pico"], vs)
        print("%5.1f  %4dx%-4d %6d %4d  %+.4f  %6.2f %6.2f %+7.1f   %s"
              % (fac, nw, nh, kb, P["n"], ver["v_pico"], ver["score"], ver["techo_nulo"],
                 ver["z"], "DETECTA" if ver["supera_nulo"] else "NO detecta"))
        filas.append(dict(factor=fac, ancho=nw, alto=nh, kbps=kb, n=P["n"],
                          n_frames=leidos, **ver))
    with open(os.path.join(DIR_SALIDAS, "escalera_honesta.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    print("\nescrito: salidas/escalera_honesta.csv")
    print("(los .mp4 intermedios quedan en tmp_codificados/, se pueden borrar)")


if __name__ == "__main__":
    main()
