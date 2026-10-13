"""Las figuras de la carpeta. Se lanzan despues de `stiv_mejorado.py` y `simulacion_canal.py`.

    python figuras.py
"""
import csv
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
import numpy as np                # noqa: E402

import simulacion_canal as sim    # noqa: E402

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "salidas")
plt.rcParams.update({"figure.dpi": 130, "font.size": 9, "axes.grid": True,
                     "grid.alpha": 0.25})


def leer(nombre):
    return list(csv.DictReader(open(os.path.join(DIR, nombre), encoding="utf-8")))


def f(r, k, d=np.nan):
    v = r.get(k, "")
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def fig1(cfg, per, simu):
    """El perfil: lo medido, los tres modelos y la banda."""
    yL, yR = cfg["X_izq"], cfg["X_der"]
    X = np.array([f(r, "X") for r in simu])
    uA = np.array([f(r, "u_A_skm") for r in simu])
    uC = np.array([f(r, "u_C_espejo") for r in simu])
    lo = np.array([f(r, "banda_lo") for r in simu])
    hi = np.array([f(r, "banda_hi") for r in simu])
    ac = [r for r in per if r["aceptada"] in ("True", "1") and r["v_ventanas"] not in ("", "nan")]
    Xm = np.array([f(r, "X") for r in ac])
    Um = np.array([f(r, "v_ventanas") for r in ac])
    q5 = np.array([f(r, "q05") for r in ac])
    q95 = np.array([f(r, "q95") for r in ac])

    fig, ax = plt.subplots(figsize=(9.2, 4.4))
    ax.axvspan(yL, Xm.min(), color="#3a3450", alpha=0.35, lw=0)
    ax.axvspan(Xm.max(), yR, color="#3a3450", alpha=0.35, lw=0,
               label="sin medir (no hay trazador)")
    ax.fill_between(X, lo, hi, color="#7b78c0", alpha=0.30,
                    label="envolvente de todas las hipotesis (Gamma y posicion del eje)")
    ax.plot(X, uA, "-", color="#4f6fd0", lw=2,
            label="SKM ajustado  (W efectivo %.2f, B/H <= %.1f)"
                  % (cfg["A"]["W"], cfg["aspecto_cota_superior"]))
    ax.plot(X, uC, ":", color="#888888", lw=1.8,
            label="espejo de lo medido (hipotesis alternativa, sin fisica)")
    ax.errorbar(Xm, Um, yerr=[Um - q5, q95 - Um], fmt="o", ms=4.5, color="#1f9d55",
                ecolor="#1f9d55", capsize=2.5, lw=1.2, label="STIV medido (q05-q95)", zorder=5)
    ax.axvline(0.5 * (yL + yR), color="#aaaaaa", lw=0.8, ls="-.")
    ax.text(0.5 * (yL + yR), ax.get_ylim()[1] * 0.02, " eje geometrico", fontsize=7.5,
            color="#aaaaaa")
    ax.set_xlim(yL, yR)
    ax.set_ylim(0, None)
    ax.set_xlabel("X, transversal (alturas de camara; 0 = eje del canal)")
    ax.set_ylabel("velocidad superficial (alt.cam/s)")
    ax.set_title("Perfil transversal: %.0f %% medido, %.0f %% simulado"
                 % (100 * cfg["fraccion_medida"], 100 * (1 - cfg["fraccion_medida"])))
    ax.legend(fontsize=7.2, loc="upper left", framealpha=0.9)
    fig.tight_layout()
    fig.savefig(os.path.join(DIR, "fig1_perfil_completo.png"))
    plt.close(fig)


def fig2(cfg, per):
    """Barrido de Gamma: cuanto depende la extrapolacion de la profundidad, que no se conoce."""
    yL, yR = cfg["X_izq"], cfg["X_der"]
    ac = [r for r in per if r["aceptada"] in ("True", "1") and r["v_ventanas"] not in ("", "nan")]
    Xm = np.array([f(r, "X") for r in ac])
    Um = np.array([f(r, "v_ventanas") for r in ac])
    Sm = np.maximum((np.array([f(r, "q95") for r in ac])
                     - np.array([f(r, "q05") for r in ac])) / 3.29, 0.002)
    yy = np.linspace(yL, yR, 401)
    fig, ax = plt.subplots(figsize=(9.2, 4.0))
    cm = plt.get_cmap("viridis")
    Gs = np.linspace(*cfg["gamma_barrido"], 8)
    eje, semi = cfg["eje_geometrico"], 0.5 * cfg["ancho"]
    for i, G in enumerate(Gs):
        m = sim.ajustar(Xm, Um, Sm, eje, semi, gamma_fijo=G)
        ax.plot(yy, sim.skm(yy, eje, G, m["Umax"], m["W"], semi_ref=semi),
                color=cm(i / (len(Gs) - 1)), lw=1.6,
                label="Gamma %.1f  (B/H %.1f)" % (G, sim.aspecto(G)))
    ax.errorbar(Xm, Um, yerr=Sm, fmt="ko", ms=4, capsize=2, lw=1, zorder=5, label="medido")
    ax.axvspan(yL, Xm.min(), color="#dddddd", alpha=0.55, lw=0)
    ax.axvspan(Xm.max(), yR, color="#dddddd", alpha=0.55, lw=0)
    ax.set_xlim(yL, yR)
    ax.set_ylim(0, None)
    ax.set_xlabel("X (alturas de camara)")
    ax.set_ylabel("velocidad superficial (alt.cam/s)")
    ax.set_title("Gamma cambia la meseta central, que es justo donde no hay datos")
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(os.path.join(DIR, "fig2_barrido_gamma.png"))
    plt.close(fig)


def fig3(per):
    """Los tres estimadores, estacion a estacion."""
    X = np.array([f(r, "X") for r in per])
    ok = np.array([r["aceptada"] in ("True", "1") for r in per])
    v = np.array([f(r, "v") for r in per])
    vf = np.array([f(r, "v_fft") for r in per])
    vm = np.array([f(r, "v_filtro") for r in per])
    det = np.array([r["filtro_detecta"] in ("True", "1") for r in per])
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9.2, 5.6), sharex=True,
                                 gridspec_kw=dict(height_ratios=[2, 1]))
    a1.plot(X[ok], v[ok], "o-", ms=4, color="#1f9d55", label="tensor de estructura (el que manda)")
    a1.plot(X[ok], vf[ok], "s--", ms=4, color="#4f6fd0", label="cresta espectral FFT")
    a1.plot(X[ok], vm[ok], "^:", ms=4, color="#d06f4f", label="filtro adaptado")
    a1.plot(X[~ok], v[~ok], "x", ms=5, color="#bbbbbb", label="estacion rechazada")
    a1.plot(X[~ok & det], vm[~ok & det], "^", ms=5, mfc="none", color="#d06f4f",
            label="filtro: falso positivo (no hay trazador ahi)")
    a1.set_ylabel("v (alt.cam/s)")
    a1.set_title("Tres estimadores independientes sobre la misma STI")
    a1.legend(fontsize=7)
    a1.set_ylim(-0.05, 0.12)
    d = np.array([f(r, "densidad") for r in per])
    a2.semilogy(X, np.maximum(d, 1e-6), "o-", ms=3.5, color="#555555")
    a2.axhline(0.004, color="#cc4444", lw=1.2, ls="--", label="umbral de trazador (0.004)")
    a2.axhline(0.05, color="#cc4444", lw=1.2, ls=":", label="umbral de orilla (0.05)")
    a2.set_xlabel("X (alturas de camara)")
    a2.set_ylabel("densidad de trazador")
    a2.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(DIR, "fig3_estimadores.png"))
    plt.close(fig)


def fig4(anch, per):
    """La prueba de la banda ancha: por que no rescata la izquierda."""
    X = np.array([f(r, "X") for r in anch])
    da = np.array([f(r, "densidad_ancha") for r in anch])
    dc = np.array([f(r, "densidad_caso") for r in anch])
    fig, ax = plt.subplots(figsize=(7.6, 3.8))
    w = 0.10
    ax.bar(X - w / 2, np.maximum(dc, 1e-7), w, color="#888888", label="banda del caso (0.10)")
    ax.bar(X + w / 2, np.maximum(da, 1e-7), w, color="#4f6fd0",
           label="banda ancha (0.30, 61 lineas)")
    ax.axhline(0.004, color="#cc4444", lw=1.3, ls="--", label="umbral de trazador")
    ax.set_yscale("log")
    ax.set_xlabel("X (alturas de camara)")
    ax.set_ylabel("densidad de trazador")
    ax.set_title("Ensanchar la banda no crea trazador donde no lo hay")
    for x, d in zip(X, da):
        if d >= 0.004:
            # el texto va a la izquierda y hacia abajo: encima de la barra se comia el titulo
            ax.annotate("pasa el umbral, pero la banda\nllega a X=%+.2f, ya dentro del\nagua con "
                        "trazador: mide a sus vecinas" % (x + 0.15), (x - w / 2, d),
                        textcoords="offset points", xytext=(-16, -6), fontsize=6.8,
                        color="#cc4444", ha="right", va="top",
                        arrowprops=dict(arrowstyle="->", color="#cc4444", lw=0.8))
    ax.legend(fontsize=7.5, loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(DIR, "fig4_banda_ancha.png"))
    plt.close(fig)


def main():
    cfg = json.load(open(os.path.join(DIR, "config_simulacion.json"), encoding="utf-8"))
    per = leer("perfil_mejorado.csv")
    simu = leer("perfil_simulado.csv")
    anch = leer("banda_ancha_izquierda.csv")
    fig1(cfg, per, simu)
    fig2(cfg, per)
    fig3(per)
    fig4(anch, per)
    print("escritas: fig1_perfil_completo.png, fig2_barrido_gamma.png, fig3_estimadores.png, "
          "fig4_banda_ancha.png")


if __name__ == "__main__":
    main()
