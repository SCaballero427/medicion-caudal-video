"""Figuras del filtro adaptado. Lee lo que dejo `filtro_adaptado.py` en `salidas/`.

    python figuras_filtro.py
"""
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "salidas")
V_CASO = 0.0590          # lo que mide el caso principal en el campo cercano


def fig1_curvas():
    """Score contra velocidad candidata, con la envolvente nula, para las tres bandas."""
    bandas = [b for b in ("cerca", "media", "lejos")
              if os.path.exists(os.path.join(DIR, "curva_%s.npy" % b))]
    if not bandas:
        return False
    fig, ax = plt.subplots(1, len(bandas), figsize=(5.2 * len(bandas), 4.4), sharey=False)
    if len(bandas) == 1:
        ax = [ax]
    for k, b in enumerate(bandas):
        vs, real, inv, nulo = np.load(os.path.join(DIR, "curva_%s.npy" % b))
        ax[k].fill_between(vs, 0, nulo, color="0.85",
                           label="techo de la hipotesis nula\n(fotogramas barajados)")
        ax[k].plot(vs, inv, "-", color="#bbbbbb", lw=1.0, label="tiempo invertido")
        ax[k].plot(vs, real, "-", color="#0077b6", lw=1.6, label="real")
        ax[k].axvline(V_CASO, ls="--", color="#c1121f", lw=1.2)
        ax[k].annotate("v del caso\n%.4f" % V_CASO, (V_CASO, ax[k].get_ylim()[1] * 0.93),
                       color="#c1121f", fontsize=8, ha="left")
        i = int(np.argmax(np.where(np.abs(vs) >= 0.012, real, -np.inf)))
        ax[k].plot([vs[i]], [real[i]], "o", color="#023047", ms=7)
        detecta = real[i] > nulo.max()
        ax[k].set_title("%s   pico en %+.4f   %s"
                        % (b, vs[i], "DETECTA" if detecta else "no supera la nula"),
                        fontsize=10, color="#0a7d2e" if detecta else "#c1121f")
        ax[k].set_xlabel("velocidad candidata  (alturas de camara / s)")
        if k == 0:
            ax[k].set_ylabel("score de pico  (max - mediana) / MAD")
            ax[k].legend(fontsize=7.5, loc="upper left")
        ax[k].grid(alpha=0.3)
    fig.suptitle("fig1  Filtro adaptado: se integran los 81 s enteros a lo largo de cada "
                 "trayectoria candidata.\nLa banda gris es lo que sale al destruir la coherencia "
                 "temporal barajando los fotogramas.", fontsize=11, y=1.04)
    fig.savefig(os.path.join(DIR, "fig1_curvas_filtro.png"), dpi=110,
                bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True


def fig2_escalera():
    """Score del pico frente al factor de degradacion del campo cercano."""
    ruta = os.path.join(DIR, "filtro_adaptado.csv")
    if not os.path.exists(ruta):
        return False
    R = [r for r in csv.DictReader(open(ruta, encoding="utf-8"))
         if r["experimento"] == "escalera" and r["estadistico"] == "pico"]
    if not R:
        return False
    f = np.array([float(r["factor"]) for r in R])
    s = np.array([float(r["score"]) for r in R])
    t = np.array([float(r["techo_nulo"]) for r in R])
    v = np.array([float(r["v_pico"]) for r in R])
    o = np.argsort(f)
    f, s, t, v = f[o], s[o], t[o], v[o]
    fig, ax = plt.subplots(1, 2, figsize=(12.5, 4.4))
    ax[0].plot(f, s, "o-", color="#0077b6", lw=2, ms=7, label="score del pico")
    ax[0].plot(f, t, "s--", color="#999999", lw=1.4, ms=5, label="techo de la nula")
    ax[0].axvline(6.5, ls=":", color="#c1121f")
    ax[0].annotate("el campo lejano\nequivale a f = 6.5", (6.5, ax[0].get_ylim()[1] * 0.6),
                   color="#c1121f", fontsize=8, ha="right")
    ax[0].set_xlabel("factor de degradacion  (simula alejar la camara)")
    ax[0].set_ylabel("score de pico")
    ax[0].set_title("Donde muere la deteccion al degradar el campo CERCANO", fontsize=10)
    ax[0].grid(alpha=0.3)
    ax[0].legend(fontsize=8)
    ok = s > t
    ax[1].plot(f[ok], v[ok], "o", color="#0077b6", ms=8, label="detecta")
    ax[1].plot(f[~ok], v[~ok], "x", color="#ff7f0e", ms=9, label="no detecta")
    ax[1].axhline(V_CASO, ls="--", color="#c1121f", label="v del caso %.4f" % V_CASO)
    ax[1].set_xlabel("factor de degradacion")
    ax[1].set_ylabel("velocidad del pico  (alt.cam / s)")
    ax[1].set_title("Mientras detecta, acierta la velocidad", fontsize=10)
    ax[1].grid(alpha=0.3)
    ax[1].legend(fontsize=8)
    fig.suptitle("fig2  Escalera de degradacion: cuanta resolucion haria falta",
                 fontsize=11, y=1.03)
    fig.savefig(os.path.join(DIR, "fig2_escalera.png"), dpi=110,
                bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return True


if __name__ == "__main__":
    a = fig1_curvas()
    b = fig2_escalera()
    print("fig1_curvas_filtro.png" if a else "(faltan curva_*.npy)")
    print("fig2_escalera.png" if b else "(falta la escalera en el CSV)")
