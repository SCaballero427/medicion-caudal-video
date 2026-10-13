"""El canal completo: modelo fisico del perfil transversal, anclado en lo que si se ha medido.

El problema
-----------
STIV mide 12 de 29 estaciones, todas en la mitad derecha (X = +0.12 a +0.93 de un canal que va de
-1.15 a +1.10). La izquierda no tiene trazador y `stiv_mejorado.py` lo demuestra midiendo:
ensanchar la banda de lineas no la rescata. **El 64 % del ancho no se puede medir en este video.**

Lo que si se puede hacer es lo que hace la hidraulica cuando falta parte del aforo: poner un
modelo de la distribucion transversal, ajustarlo donde hay datos y extrapolarlo donde no. Eso es
una **simulacion, no una medida**, y va etiquetada como tal en todas partes.

El modelo: Shiono-Knight
------------------------
SKM (Shiono & Knight 1991) es el metodo estandar para la distribucion lateral de velocidad
promediada en vertical en canal prismatico. Sale de promediar en profundidad la ecuacion de
momento y quedarse con tres terminos -- peso, friccion de fondo y tension turbulenta lateral --
y para profundidad constante y paredes verticales se integra a mano:

    U(y) = Umax * sqrt( [1 - cosh(g*y)/cosh(Gamma)] / [1 - 1/cosh(Gamma)] ),   Gamma = g*W

**La forma depende de un solo numero adimensional, Gamma**, y la amplitud de otro. Eso es lo que
lo hace utilizable aqui: no hace falta conocer g, H, S0 ni f por separado -- en unidades afines no
se pueden conocer -- porque todos entran por Gamma y por Umax.

Gamma grande = meseta central y caida concentrada junto a la pared. Gamma pequeno = perfil ancho;
en el limite Gamma -> 0 el modelo tiende a la elipse U = Umax*sqrt(1-(y/W)^2), que es la forma
mas ancha que SKM puede dar. Y Gamma se traduce a relacion de aspecto:

    Gamma = (B/2H) * sqrt(2) * (f/8)^(1/4) / sqrt(lambda)

Con lambda = 0.07 (Knight, canal recto) y f = 0.03 (hormigon liso) sale **B/H ~ 1.51*Gamma**.

Dos parametros de forma, y los dos hacen falta
-----------------------------------------------
1. **Gamma.** Se va al limite inferior: el perfil medido es tan ancho como SKM permite,
   practicamente la elipse. Asi que **el dato no fija Gamma por abajo**, y citar el valor
   ajustado seria citar el tope que se ha puesto en el codigo, no lo que dice la medida. Lo que
   si acota es por arriba, y eso si es util: del perfil de chi2 sale **Gamma <= 4.1 (2 sigma),
   o sea B/H <= 6.2** con lambda 0.07, o <= 12.8 con lambda 0.30. **Un canal ancho y somero
   queda descartado**; uno de proporciones normales, no.
2. **El semiancho efectivo W**, o sea donde se para el agua. No tiene por que coincidir con la
   linea de orilla que ve la camara: en un canal de riego revestido, que suele ser trapecial, el
   talud tiene lamina fina y velocidad practicamente nula. Liberarlo baja el chi2 reducido de
   1.95 a 0.52, y coloca el borde hidraulico 0.14 alturas de camara por dentro de la orilla
   visible -- un 6 % del ancho por lado. Es una afirmacion fisica, no un mando de ajuste. No
   podia bajar de 0.972: ahi esta la estacion medida mas externa.

Lo que NO se puede determinar, y se mide cuanto duele
-----------------------------------------------------
Con datos en un solo lado del eje, **la posicion del eje no esta determinada**: una curva muy
ancha centrada lejos ajusta la caida monotona igual de bien que una centrada. En vez de dejar que
un ajuste con el eje libre se encalle en un tope, se **barre el eje supuesto** y se reporta que el
chi2 apenas se mueve mientras la respuesta si. Esa es la incertidumbre real de esta carpeta, y es
mayor que la del parametro del modelo.

Uso
---
    python simulacion_canal.py                  # ~10 s
    python simulacion_canal.py --gamma 3.0      # fija Gamma en vez de ajustarlo
"""
import argparse
import csv
import json
import os

import numpy as np
from scipy.optimize import least_squares

DIR_CASO = os.path.dirname(os.path.abspath(__file__))
DIR_SALIDAS = os.path.join(DIR_CASO, "salidas")
PTV = os.path.join(os.path.dirname(DIR_CASO), "analisis_canal_riego_stiv", "salidas",
                   "ptv_perfil.csv")

# ----------------------------------------------------------------------------------
# >>> AJUSTABLE <<<
# ----------------------------------------------------------------------------------
# Solo para traducir Gamma a relacion de aspecto. NO entran en el ajuste: el perfil no los
# distingue de la profundidad.
LAMBDA_SKM = 0.07              # Knight, canal recto
F_DARCY = 0.03                 # hormigon liso
GAMMA_LIMITES = (0.05, 12.0)   # 0.05 es ya el limite eliptico; 12 daria B/H 18
GAMMA_BARRIDO = (0.3, 6.0)     # para la banda de incertidumbre
EJE_BARRIDO = (-0.45, 0.45)    # desplazamientos del eje supuesto, para la identificabilidad
N_MALLA = 401


def aspecto(Gamma, lam=LAMBDA_SKM, f=F_DARCY):
    """B/H implicado por Gamma."""
    return 2.0 * Gamma * np.sqrt(lam) / (np.sqrt(2.0) * (f / 8.0) ** 0.25)


def skm(y, centro, Gamma, Umax, WR, WL=None, semi_ref=None):
    """Perfil SKM. Semianchos independientes a cada lado, mismo gamma.

    Los dos lados comparten gamma (misma friccion, misma profundidad, misma turbulencia), valen
    Umax en el eje y cero en su pared, y tienen derivada nula en el eje, asi que el empalme es
    suave. Con WL = WR queda el SKM simetrico de siempre.

    `semi_ref` es el semiancho respecto al que se define Gamma, para que el parametro siga
    significando lo mismo cuando los dos lados no miden igual. Por defecto, WR.
    """
    y = np.atleast_1d(np.asarray(y, float))
    WL = WR if WL is None else WL
    g = Gamma / max(semi_ref if semi_ref else WR, 1e-6)
    out = np.zeros_like(y)
    for W, m in ((WR, y >= centro), (WL, y < centro)):
        if W <= 1e-6:
            continue
        chW = np.cosh(np.clip(g * W, 0, 60))
        ch = np.cosh(np.clip(g * (y[m] - centro), -60, 60))
        Wn = (1.0 - ch / chW) / max(1.0 - 1.0 / chW, 1e-12)
        out[m] = Umax * np.sqrt(np.maximum(Wn, 0.0))
    out[(y > centro + WR) | (y < centro - WL)] = 0.0
    return out


def espejo(y, Xm, Um, centro, semi):
    """Modelo nulo: el semiperfil medido, interpolado y reflejado sobre el eje supuesto."""
    d = np.abs(np.atleast_1d(np.asarray(y, float)) - centro)
    dm = np.abs(np.asarray(Xm) - centro)
    o = np.argsort(dm)
    dd = np.r_[dm[o], semi]        # el cero en la pared, para que no salga plano al extrapolar
    uu = np.r_[np.asarray(Um)[o], 0.0]
    return np.interp(d, dd, uu)


def ajustar(Xm, Um, sig, centro, semi_max, gamma_fijo=None, W_fijo=None):
    """Minimos cuadrados ponderados sobre (Gamma, Umax, W). Simetrico sobre `centro`."""
    def parte(p):
        i = 0
        G = gamma_fijo if gamma_fijo is not None else p[i]
        i += 0 if gamma_fijo is not None else 1
        U = p[i]
        i += 1
        return G, U, (W_fijo if W_fijo is not None else p[i])

    def res(p):
        G, U, W = parte(p)
        return (skm(Xm, centro, G, U, W, semi_ref=semi_max) - Um) / sig

    p0, lo, hi = [], [], []
    if gamma_fijo is None:
        p0.append(3.0)
        lo.append(GAMMA_LIMITES[0])
        hi.append(GAMMA_LIMITES[1])
    p0.append(float(np.max(Um)))
    lo.append(1e-6)
    hi.append(10.0)
    if W_fijo is None:
        # el borde hidraulico no puede quedar por dentro de la estacion medida mas externa (ahi
        # el modelo daria cero y la medida no lo es) ni pasar de la orilla vista
        lo.append(float(np.max(np.abs(Xm - centro))) + 0.02)
        hi.append(max(semi_max, lo[-1] + 1e-3))
        p0.append(float(np.clip(0.9 * semi_max, lo[-1], hi[-1])))
    s = least_squares(res, p0, bounds=(lo, hi))
    G, U, W = parte(s.x)
    npar = len(p0)
    pred = skm(Xm, centro, G, U, W, semi_ref=semi_max)
    return dict(Gamma=float(G), Umax=float(U), W=float(W), centro=float(centro),
                chi2=float(np.sum(s.fun ** 2) / max(len(Xm) - npar, 1)), n_par=npar,
                rms=float(np.sqrt(np.mean((pred - Um) ** 2))),
                en_tope_gamma=bool(abs(G - GAMMA_LIMITES[0]) < 1e-3))


def leer_perfil():
    """Estaciones aceptadas con su incertidumbre.

    La sigma no puede ser solo la dispersion entre ventanas: esa mide **repetibilidad**, sale de
    0.010 y con ella el chi2 reducido se dispara, que es la forma que tiene un ajuste de avisar
    de que la barra de error esta mal, no de que el modelo lo este.

    Falta la parte sistematica, y hay una forma de medirla sin inventar nada: la dispersion entre
    los tres estimadores en esa misma estacion. Tensor, cresta espectral y filtro adaptado ven la
    misma STI y no comparten mas que eso, asi que lo que discrepan es error de metodo.

        sigma = sqrt(sigma_ventanas^2 + sigma_estimadores^2)
    """
    p = os.path.join(DIR_SALIDAS, "perfil_mejorado.csv")
    if not os.path.exists(p):
        raise SystemExit("falta salidas/perfil_mejorado.csv: hay que correr stiv_mejorado.py")
    filas = list(csv.DictReader(open(p, encoding="utf-8")))
    X, U, S, Sv, Se = [], [], [], [], []
    for r in filas:
        if r["aceptada"] not in ("True", "1"):
            continue
        X.append(float(r["X"]))
        if r["v_ventanas"] not in ("", "nan"):
            U.append(float(r["v_ventanas"]))
            sv = (float(r["q95"]) - float(r["q05"])) / 3.29   # q05-q95 = 3.29 sigma si normal
        else:
            U.append(float(r["v"]))
            sv = 0.10 * float(r["v"])
        est = [float(r[k]) for k in ("v", "v_fft", "v_filtro")
               if r[k] not in ("", "nan") and np.isfinite(float(r[k]))]
        se = float(np.std(est)) if len(est) >= 2 else 0.005
        Sv.append(sv)
        Se.append(se)
        S.append(max(np.hypot(sv, se), 0.002))
    return np.array(X), np.array(U), np.array(S), np.array(Sv), np.array(Se), filas


def leer_ptv():
    """El perfil del arbitro PTV del caso original, si esta. Solo para contrastar."""
    if not os.path.exists(PTV):
        return None
    X, U = [], []
    for r in csv.DictReader(open(PTV, encoding="utf-8")):
        try:
            v = float(r["v"])
        except ValueError:
            continue
        if np.isfinite(v) and int(r["n_pistas"]) >= 20:
            X.append(float(r["X"]))
            U.append(v)
    return (np.array(X), np.array(U)) if X else None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gamma", type=float, default=None)
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(DIR_SALIDAS, "config_mejorado.json"), encoding="utf-8"))
    yL, yR = cfg["X_izq"], cfg["X_der"]
    B = yR - yL
    eje = 0.5 * (yL + yR)
    semi = 0.5 * B
    Xm, Um, Sm, Sv, Se, filas = leer_perfil()
    print("anclaje: %d estaciones, X de %+.3f a %+.3f (canal de %+.3f a %+.3f, eje %+.3f)"
          % (len(Xm), Xm.min(), Xm.max(), yL, yR, eje))
    print("cubren el %.0f %% del ancho; el %.0f %% restante es extrapolacion"
          % (100 * (Xm.max() - Xm.min()) / B, 100 * (1 - (Xm.max() - Xm.min()) / B)))
    print("sigma por estacion: %.4f de ventanas (repetibilidad) + %.4f entre estimadores "
          "(sistematica) = %.4f" % (np.median(Sv), np.median(Se), np.median(Sm)))

    rig = ajustar(Xm, Um, Sm, eje, semi, gamma_fijo=a.gamma, W_fijo=semi)
    mA = ajustar(Xm, Um, Sm, eje, semi, gamma_fijo=a.gamma)
    W_min = float(np.max(np.abs(Xm - eje))) + 0.02
    print("\n== el ajuste ==")
    print("%-34s %7s %8s %8s %8s %9s" % ("", "Gamma", "Umax", "W", "rms", "chi2red"))
    print("%-34s %7.2f %8.4f %8.3f %8.4f %9.2f"
          % ("pared en la orilla vista", rig["Gamma"], rig["Umax"], semi, rig["rms"],
             rig["chi2"]))
    print("%-34s %7.2f %8.4f %8.3f %8.4f %9.2f   <- el que se usa"
          % ("semiancho efectivo libre", mA["Gamma"], mA["Umax"], mA["W"], mA["rms"],
             mA["chi2"]))
    print("Liberar W baja el chi2 de %.2f a %.2f y pone el borde del agua %.3f alt.cam por"
          % (rig["chi2"], mA["chi2"], semi - mA["W"]))
    print("dentro de la orilla visible (%.0f %% del ancho por lado). En un canal trapecial eso"
          % (100 * (semi - mA["W"]) / B))
    print("es el talud: lamina fina, velocidad ya nula. W no podia bajar de %.3f, donde esta la"
          % W_min)
    print("estacion medida mas externa.")

    # Gamma se pega al limite inferior, asi que **no esta determinado**: dar su valor y
    # traducirlo a B/H seria citar el tope que yo he puesto, no lo que dice el dato. Lo que el
    # dato si dice es "no mas grande que esto", y eso es una afirmacion util: acota la relacion
    # de aspecto por arriba. Se saca del perfil de chi2, subiendo 4 sobre el minimo (~2 sigma
    # para un parametro).
    Gs = np.linspace(GAMMA_LIMITES[0], GAMMA_LIMITES[1], 60)
    chis_g = [ajustar(Xm, Um, Sm, eje, semi, gamma_fijo=G) for G in Gs]
    gl = len(Xm) - 2
    raw = np.array([m["chi2"] * gl for m in chis_g])
    dentro = Gs[raw <= raw.min() + 4.0]
    G_sup = float(dentro.max())
    print("\n== lo que Gamma dice, y lo que no ==")
    if mA["en_tope_gamma"]:
        print("Gamma se va al limite inferior: **el perfil medido es tan ancho como SKM puede**")
        print("dar, practicamente la elipse. La mezcla lateral domina sobre la friccion de fondo")
        print("en toda la seccion, y el dato NO fija Gamma por abajo.")
    print("Lo que si acota es por arriba: Gamma <= %.2f al 2 sigma, o sea **B/H <= %.1f** con"
          % (G_sup, aspecto(G_sup)))
    print("lambda %.2f y f %.3f, o **B/H <= %.1f** si la mezcla lateral es fuerte (lambda 0.30,"
          % (LAMBDA_SKM, F_DARCY, aspecto(G_sup, lam=0.30)))
    print("corrientes secundarias o una curva aguas arriba). Un canal ancho y somero queda")
    print("descartado; uno de proporciones normales, no.")
    print("La otra lectura de un Gamma tan bajo es que la seccion no sea rectangular: en un")
    print("trapecio el talud alarga la caida, que es justo lo que el semiancho efectivo absorbe.")

    # -- identificabilidad del eje -----------------------------------------------------
    yy = np.linspace(yL, yR, N_MALLA)
    margen = semi - mA["W"]        # el talud muerto que sale del ajuste, se conserva al barrer
    print("\n== la posicion del eje NO esta determinada por los datos ==")
    print("   %8s %8s %9s %13s" % ("eje X", "Gamma", "chi2red", "v media total"))
    ejes, curvas_eje = [], []
    for dx in np.linspace(*EJE_BARRIDO, 7):
        c = eje + dx
        WR, WL = (yR - margen) - c, c - (yL + margen)
        if min(WR, WL) <= np.max(np.abs(Xm - c)) + 0.02:
            continue

        def res(p, c=c, WR=WR, WL=WL):
            return (skm(Xm, c, p[0], p[1], WR, WL, semi_ref=semi) - Um) / Sm
        s = least_squares(res, [3.0, float(np.max(Um))],
                          bounds=([GAMMA_LIMITES[0], 1e-6], [GAMMA_LIMITES[1], 10.0]))
        u = skm(yy, c, s.x[0], s.x[1], WR, WL, semi_ref=semi)
        vt = float(np.trapezoid(u, yy) / B)
        ch = float(np.sum(s.fun ** 2) / max(len(Xm) - 2, 1))
        ejes.append(dict(eje=float(c), Gamma=float(s.x[0]), Umax=float(s.x[1]), chi2=ch,
                         v_media=vt))
        curvas_eje.append(u)
        print("   %+8.3f %8.2f %9.2f %13.4f%s"
              % (c, s.x[0], ch, vt, "   <- eje geometrico" if abs(dx) < 1e-9 else ""))
    chis = [e["chi2"] for e in ejes]
    vms = [e["v_media"] for e in ejes]
    print("   chi2 va de %.2f a %.2f -- el dato no distingue -- y la media total se mueve un "
          "%.0f %%." % (min(chis), max(chis), 100 * (max(vms) / min(vms) - 1)))

    # -- envolvente de hipotesis --------------------------------------------------------
    uA = skm(yy, eje, mA["Gamma"], mA["Umax"], mA["W"], semi_ref=semi)
    uC = espejo(yy, Xm, Um, eje, semi)
    curvas = list(curvas_eje) + [uA, uC]
    for G in np.linspace(*GAMMA_BARRIDO, 8):
        m = ajustar(Xm, Um, Sm, eje, semi, gamma_fijo=G)
        curvas.append(skm(yy, eje, G, m["Umax"], m["W"], semi_ref=semi))
    curvas = np.array(curvas)
    lo, hi = curvas.min(axis=0), curvas.max(axis=0)

    med = (yy >= Xm.min()) & (yy <= Xm.max())
    sinmed = ~med

    def prom(u, m):
        return float(np.trapezoid(u[m], yy[m]) / max(yy[m][-1] - yy[m][0], 1e-9))

    vm_medido, vm_total = prom(uA, med), float(np.trapezoid(uA, yy) / B)
    env = [float(np.trapezoid(lo, yy) / B), float(np.trapezoid(hi, yy) / B)]
    print("\n== para que sirve la simulacion ==")
    print("   v superficial media sobre el tramo MEDIDO   : %.4f alt.cam/s" % vm_medido)
    print("   v superficial media sobre el ancho COMPLETO : %.4f" % vm_total)
    print("   -> quedarse solo con el tercio medido %s la seccion en un %+.0f %%"
          % ("sobrestima" if vm_medido > vm_total else "subestima",
             100 * (vm_medido / vm_total - 1)))
    print("   sobre el tramo que NADIE ha medido:  modelo A %.4f   espejo %.4f"
          % (prom(uA, sinmed), prom(uC, sinmed)))
    print("   envolvente de TODAS las hipotesis, media total: %.4f a %.4f  (%+.0f %%)"
          % (env[0], env[1], 100 * (env[1] / env[0] - 1)))

    ptv = leer_ptv()
    sesgo_ptv = None
    if ptv is not None:
        Xp, Up = ptv
        m = (Xp >= Xm.min() - 0.05) & (Xp <= Xm.max() + 0.05)
        pred = skm(Xp[m], eje, mA["Gamma"], mA["Umax"], mA["W"], semi_ref=semi)
        sesgo_ptv = float(100 * (pred.mean() / Up[m].mean() - 1))
        print("\n== contraste con el PTV del caso original (otro algoritmo, mismo video) ==")
        print("   %8s %10s %10s %9s" % ("X", "PTV", "modelo A", "dif %"))
        for x, u, p in zip(Xp[m], Up[m], pred):
            print("   %+8.3f %10.4f %10.4f %+8.0f" % (x, u, p, 100 * (p / u - 1)))
        print("   sesgo medio del modelo respecto al PTV: %+.1f %%" % sesgo_ptv)
        print("   El PTV sigue particulas y es inmune a la textura estatica de la pared.")

    with open(os.path.join(DIR_SALIDAS, "perfil_simulado.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["X", "X_rel", "u_A_skm", "u_C_espejo", "banda_lo", "banda_hi",
                    "dentro_del_tramo_medido"])
        for i, y in enumerate(yy):
            w.writerow(["%.5f" % y, "%.5f" % ((y - yL) / B), "%.6f" % uA[i], "%.6f" % uC[i],
                        "%.6f" % lo[i], "%.6f" % hi[i], int(med[i])])
    with open(os.path.join(DIR_SALIDAS, "config_simulacion.json"), "w", encoding="utf-8") as fh:
        json.dump({"modelo": "Shiono-Knight, canal prismatico, semiancho efectivo libre",
                   "lambda": LAMBDA_SKM, "f_darcy": F_DARCY, "n_malla": N_MALLA,
                   "gamma_limites": list(GAMMA_LIMITES),
                   "gamma_barrido": list(GAMMA_BARRIDO), "eje_barrido": list(EJE_BARRIDO),
                   "X_izq": yL, "X_der": yR, "ancho": B, "eje_geometrico": eje,
                   "n_estaciones_ancla": len(Xm), "X_ancla_min": float(Xm.min()),
                   "X_ancla_max": float(Xm.max()),
                   "fraccion_medida": float((Xm.max() - Xm.min()) / B),
                   "sigma_ventanas_mediana": float(np.median(Sv)),
                   "sigma_estimadores_mediana": float(np.median(Se)),
                   "pared_rigida": rig, "A": mA, "gamma_cota_superior": G_sup,
                   "aspecto_cota_superior": float(aspecto(G_sup)),
                   "aspecto_cota_superior_lambda030": float(aspecto(G_sup, lam=0.30)),
                   "margen_muerto": float(margen), "barrido_eje": ejes,
                   "v_media_tramo_medido": vm_medido, "v_media_ancho_completo": vm_total,
                   "v_media_sin_medir_A": prom(uA, sinmed),
                   "v_media_sin_medir_C": prom(uC, sinmed),
                   "envolvente_media_total": env, "sesgo_vs_ptv_pct": sesgo_ptv}, fh, indent=2)
    print("\nescrito: salidas/perfil_simulado.csv, config_simulacion.json")


if __name__ == "__main__":
    main()
