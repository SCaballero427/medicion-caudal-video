"""STIV sobre el video original con todo lo aprendido en las tres carpetas anteriores.

Que hace de mas que `analisis_canal_riego_stiv/stiv_canal.py`
-------------------------------------------------------------
El caso original da **un numero por estacion y ninguna barra de error**, y decide con un solo
estimador. Aqui se anaden cuatro cosas, todas medidas, ninguna nueva en el metodo:

1. **Barra de error por estacion.** La medida se repite en ventanas deslizantes de 360 fotogramas
   sobre los 81 s y se reporta mediana, q05-q95 y en cuantas ventanas la estacion se acepta. Sin
   esto no hay forma de saber si una estacion vale 0.059 +- 0.002 o +- 0.02, y la simulacion que
   se ajusta despues necesita pesos.
2. **Tres estimadores independientes por estacion**, no uno: el tensor de estructura por bloques
   con seleccion por senal (el del caso), la cresta espectral `cresta_fft` (que no comparte con el
   tensor mas que la STI) y el **filtro adaptado** de `analisis_canal_filtro_adaptado/`, que
   integra a lo largo de la trayectoria y trae su propia hipotesis nula. En el caso original el
   filtro solo se habia aplicado a bandas anchas de X; por estacion es nuevo, y es lo que permite
   decir que una velocidad esta en el dato y no en el estimador.
3. **Resolucion transversal doble**: 29 estaciones en vez de 15. Las bandas se solapan, asi que
   las estaciones vecinas NO son independientes -- eso se dice y no se disimula -- pero el perfil
   queda muestreado lo bastante fino para ajustarle un modelo.
4. **La prueba de la banda ancha en la mitad izquierda**, que es la que cierra la puerta. Ver
   abajo.

Lo que NO se puede mejorar, y esta medido aqui en vez de supuesto
-----------------------------------------------------------------
La mitad izquierda del canal no tiene trazador: densidades de 1e-5 a 4e-4 frente a 6e-3 a 3e-2 en
la derecha. La tentacion es ensanchar la banda de lineas para recoger mas senal, que es el truco
que rescato el caso Bradano. Aqui no puede funcionar y la aritmetica ya lo dice -- triplicar el
ancho sube la densidad x3 como mucho, o sea a 1.2e-3, todavia por debajo del umbral 0.004 -- pero
la aritmetica supone que la densidad escala linealmente con el ancho, asi que se **mide**: cuatro
estaciones de la izquierda con 61 lineas sobre una banda de 0.30, el triple de la del caso.

Y la medida devuelve algo que la aritmetica no anticipaba: en X = 0.00 la banda ancha **si** pasa
el umbral, x42, porque una banda de 0.30 centrada ahi llega hasta X = +0.15 y se mete en el agua
con trazador. Mide la densidad de sus vecinas, no la suya, y luego devuelve v = +0.004 con
coherencia 0.85 -- un cero confiado. Ensanchar la banda hacia agua vacia no es inutil, es
peligroso.

El resultado de este fichero es `salidas/perfil_mejorado.csv`, que es lo que
`simulacion_canal.py` toma como anclaje.

Uso
---
    python stiv_mejorado.py                 # ~9 min (1 de pasada, 8 de estimadores)
    python stiv_mejorado.py --frames 900    # prueba corta
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
sys.path.insert(0, os.path.join(_RAIZ, "analisis_canal_filtro_adaptado"))
import stiv_canal as sc          # noqa: E402
import filtro_adaptado as fa     # noqa: E402

DIR_CASO = os.path.dirname(os.path.abspath(__file__))
DIR_SALIDAS = os.path.join(DIR_CASO, "salidas")

# ----------------------------------------------------------------------------------
# >>> AJUSTABLE <<<  todo lo demas se importa del caso original
# ----------------------------------------------------------------------------------
N_ESTACIONES = 29              # el doble que el caso; las bandas se solapan (ver docstring)
VENTANA = 360                  # 12 s, la misma que el video del caso
PASO = 15
# Filtro adaptado por estacion. Malla mas gruesa que la de `filtro_adaptado.py` (61 en vez de
# 121) porque aqui es un contraste, no el estimador principal: 0.005 alt.cam/s es un 8 % sobre
# las velocidades del caso, suficiente para decir si coincide.
FILTRO_N_CAND = 61
FILTRO_N_NULOS = 12            # los mismos que filtro_adaptado.py, para comparar igual
FILTRO_DECIMA = 4              # la STI del caso esta sobremuestreada 4.3x respecto al pixel
# Prueba de banda ancha en la mitad izquierda.
IZQ_X = [-0.90, -0.60, -0.30, 0.00]
IZQ_LINEAS, IZQ_BANDA = 61, 0.30


def estaciones(geo, n=N_ESTACIONES):
    return np.linspace(geo.X_izq + sc.RETRANQUEO, geo.X_der - sc.RETRANQUEO, n)


# ==================================================================================
# una pasada: STI fina de las 29 estaciones + STI de banda ancha de 4 de la izquierda
# ==================================================================================
def pasada(ruta, geo, n_frames, verbose=True):
    cap, ntot, fps = sc.abrir_video(ruta)
    NF = ntot if n_frames is None else min(n_frames, ntot)
    ok, f = cap.read()
    g0 = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    mask = np.zeros(g0.shape, np.uint8)
    mask[0:sc.FILA_BORDE_FIN - 40, :] = 255
    cv2.fillPoly(mask, [geo.poligono_agua()], 0)
    p0 = cv2.goodFeaturesToTrack(g0, 600, 0.01, 7, mask=mask)

    DS = sc.V_ESPERADA / fps
    nmu = int((sc.Y_MAX - sc.Y_MIN) / DS)
    Yv = sc.Y_MIN + DS * np.arange(nmu)
    Xs = estaciones(geo)
    offs = np.linspace(-sc.BANDA / 2, sc.BANDA / 2, sc.N_LINEAS)
    M = np.empty((N_ESTACIONES, sc.N_LINEAS, nmu, 2), np.float32)
    for a, X in enumerate(Xs):
        for b, o in enumerate(offs):
            M[a, b] = geo.a_imagen(np.column_stack([np.full(nmu, X + o), Yv]))
    pts = M.reshape(-1, 2)
    nr = N_ESTACIONES * sc.N_LINEAS

    # banda ancha en la izquierda, a resolucion nativa: aqui solo se cuentan particulas
    res_nativa = abs(geo.a_suelo([[0.0, geo.a_imagen([[0, 2.3]])[0][1] + 1]])[0][1] - 2.3)
    nmw = max(32, int((sc.Y_MAX - sc.Y_MIN) / res_nativa))
    Yw = np.linspace(sc.Y_MIN, sc.Y_MAX, nmw)
    offw = np.linspace(-IZQ_BANDA / 2, IZQ_BANDA / 2, IZQ_LINEAS)
    Mw = np.empty((len(IZQ_X), IZQ_LINEAS, nmw, 2), np.float32)
    for a, X in enumerate(IZQ_X):
        for b, o in enumerate(offw):
            Mw[a, b] = geo.a_imagen(np.column_stack([np.full(nmw, X + o), Yw]))
    ptsw = Mw.reshape(-1, 2)
    nrw = len(IZQ_X) * IZQ_LINEAS

    sti = np.zeros((N_ESTACIONES, NF, nmu), np.float32)
    cnt = np.zeros((N_ESTACIONES, NF), np.int32)
    stiw = np.zeros((len(IZQ_X), NF, nmw), np.float32)
    cntw = np.zeros((len(IZQ_X), NF), np.int32)
    t0, leidos = time.time(), 0
    for i in range(NF):
        if i > 0:
            ok, f = cap.read()
            if not ok:
                break
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        else:
            g = g0
        leidos = i + 1
        A, _ = sc.estimar_estabilizacion(g0, g, p0)
        t = sc.realzar(g)
        xy = pts @ A[:, :2].T + A[:, 2]
        v = cv2.remap(t, np.ascontiguousarray(xy[:, 0].reshape(nr, nmu), np.float32),
                      np.ascontiguousarray(xy[:, 1].reshape(nr, nmu), np.float32),
                      cv2.INTER_LINEAR).reshape(N_ESTACIONES, sc.N_LINEAS, nmu)
        sti[:, i, :] = v.mean(axis=1)
        # el conteo va sobre el maximo entre lineas ANTES de promediar
        cnt[:, i] = (v.max(axis=1) > sc.UMBRAL_PARTICULA).sum(axis=1)
        xw = ptsw @ A[:, :2].T + A[:, 2]
        w = cv2.remap(t, np.ascontiguousarray(xw[:, 0].reshape(nrw, nmw), np.float32),
                      np.ascontiguousarray(xw[:, 1].reshape(nrw, nmw), np.float32),
                      cv2.INTER_LINEAR).reshape(len(IZQ_X), IZQ_LINEAS, nmw)
        stiw[:, i, :] = w.mean(axis=1)
        cntw[:, i] = (w.max(axis=1) > sc.UMBRAL_PARTICULA).sum(axis=1)
        if verbose and (i + 1) % 300 == 0:
            print("   %d/%d (%.1fs)" % (i + 1, NF, time.time() - t0), flush=True)
    cap.release()
    return (sti[:, :leidos], cnt[:, :leidos], stiw[:, :leidos], cntw[:, :leidos],
            DS, nmu, nmw, fps, leidos, Xs)


# ==================================================================================
# los tres estimadores
# ==================================================================================
def filtro_por_estacion(im, DS, fps, rng):
    """Filtro adaptado sobre la STI de una estacion. Devuelve (v_pico, score, techo).

    La STI del caso esta muestreada a DS = 0.23 px de imagen, o sea sobremuestreada 4.3 veces.
    Para el filtro se decima 4:1 con un promedio previo -- sin el, decimar aliasea -- porque el
    coste del barrido va con el numero de posiciones y a resolucion nativa no se pierde nada.
    """
    a = cv2.blur(im, (FILTRO_DECIMA, 1))[:, ::FILTRO_DECIMA]
    a = np.ascontiguousarray(a - a.mean(axis=0, keepdims=True))
    ds = DS * FILTRO_DECIMA
    vs = np.linspace(fa.V_MIN, fa.V_MAX, FILTRO_N_CAND)
    nv = fa.ventana_residencia(ds * (a.shape[1] - 1), fps)
    r = fa.analizar_todo(a, vs, fps, ds, rng, n_barajados=FILTRO_N_NULOS, n_ventana=nv)["pico"]
    ver = fa.veredicto(r, vs)
    return ver["v_pico"], ver["score"], ver["techo_nulo"], ver["supera_nulo"]


def medir_estacion(im, cuenta, DS, fps, nmu, rng):
    """Los tres estimadores sobre la STI completa de una estacion."""
    st = im - im.mean(axis=0, keepdims=True)
    dens = float(cuenta.sum()) / (im.shape[0] * nmu)
    pend, coh, nsel, ntot = sc.tensor_seleccion(st)
    v = pend * DS * fps if np.isfinite(pend) else np.nan
    pf, agu = sc.cresta_fft(st)
    vf = pf * DS * fps if np.isfinite(pf) else np.nan
    vfil, sco, tech, det = filtro_por_estacion(st, DS, fps, rng)
    return dict(densidad=dens, v=v, coherencia=coh, v_fft=vf, agudeza_fft=agu,
                v_filtro=vfil, filtro_score=sco, filtro_techo=tech, filtro_detecta=det,
                motivos=sc.motivos_rechazo(dens, v, coh))


def medir_ventanas(im, cuenta, DS, fps, nmu):
    """Mediana, q05-q95 y tasa de aceptacion sobre las ventanas deslizantes."""
    NF = im.shape[0]
    vs, acc = [], 0
    n = 0
    for w0 in range(0, max(1, NF - VENTANA + 1), PASO):
        n += 1
        b = im[w0:w0 + VENTANA]
        b = b - b.mean(axis=0, keepdims=True)
        d = float(cuenta[w0:w0 + VENTANA].sum()) / (VENTANA * nmu)
        p, c, _, _ = sc.tensor_seleccion(b)
        v = p * DS * fps if np.isfinite(p) else np.nan
        if not sc.motivos_rechazo(d, v, c):
            vs.append(v)
            acc += 1
    if not vs:
        return dict(v_ventanas=np.nan, q05=np.nan, q95=np.nan, n_aceptadas=0, n_ventanas=n)
    vs = np.array(vs)
    return dict(v_ventanas=float(np.median(vs)), q05=float(np.percentile(vs, 5)),
                q95=float(np.percentile(vs, 95)), n_aceptadas=acc, n_ventanas=n)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--video", default=sc.ARCHIVO_VIDEO)
    ap.add_argument("--frames", type=int, default=None)
    a = ap.parse_args()
    os.makedirs(DIR_SALIDAS, exist_ok=True)
    rng = np.random.default_rng(fa.SEMILLA)
    cap, ntot, fps = sc.abrir_video(a.video)
    sc.FPS_REAL[0] = fps
    ok, f0 = cap.read()
    cap.release()
    geo = sc.Geometria(cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY))
    print("geometria: fuga (%.1f, %.1f), ancho %.4f alt.cam, focal %s"
          % (geo.xv, geo.yv, geo.ancho, geo.focal))
    print("pasada unica sobre el video...")
    sti, cnt, stiw, cntw, DS, nmu, nmw, fps, NF, Xs = pasada(a.video, geo, a.frames)
    print("  %d fotogramas, %d estaciones, %d muestras por STI" % (NF, N_ESTACIONES, nmu))

    filas = []
    t0 = time.time()
    for i in range(N_ESTACIONES):
        r = medir_estacion(sti[i], cnt[i], DS, fps, nmu, rng)
        r.update(medir_ventanas(sti[i], cnt[i], DS, fps, nmu))
        r.update(estacion=i, X=float(Xs[i]),
                 X_rel=float((Xs[i] - geo.X_izq) / (geo.X_der - geo.X_izq)),
                 aceptada=not r["motivos"])
        filas.append(r)
        print("  est %2d  X %+.3f  dens %.5f  v %+.4f coh %.2f | fft %+.4f | filtro %+.4f "
              "%s | ventanas %s  %s"
              % (i, Xs[i], r["densidad"], r["v"], r["coherencia"], r["v_fft"], r["v_filtro"],
                 "det" if r["filtro_detecta"] else "no ",
                 ("%+.4f [%+.4f %+.4f] %d/%d" % (r["v_ventanas"], r["q05"], r["q95"],
                                                 r["n_aceptadas"], r["n_ventanas"]))
                 if r["n_aceptadas"] else "--",
                 "ACEPTADA" if r["aceptada"] else ";".join(r["motivos"])), flush=True)
    print("  (%.1f s de estimadores)" % (time.time() - t0))

    print("\n== prueba de banda ancha en la mitad izquierda ==")
    print("   banda %.2f con %d lineas, o sea %.0fx la del caso" %
          (IZQ_BANDA, IZQ_LINEAS, IZQ_BANDA / sc.BANDA))
    izq = []
    for a2, X in enumerate(IZQ_X):
        d = float(cntw[a2].sum()) / (NF * nmw)
        st = stiw[a2] - stiw[a2].mean(axis=0, keepdims=True)
        p, c, _, _ = sc.tensor_seleccion(st)
        res_n = (sc.Y_MAX - sc.Y_MIN) / (nmw - 1)
        v = p * res_n * fps if np.isfinite(p) else np.nan
        # la estacion del muestreo normal mas cercana, para comparar densidades
        j = int(np.argmin(np.abs(Xs - X)))
        izq.append(dict(X=X, densidad_ancha=d, densidad_caso=filas[j]["densidad"],
                        razon=d / max(filas[j]["densidad"], 1e-12), v=v, coherencia=c,
                        pasa_densidad=d >= sc.DENSIDAD_MIN))
        # el alcance importa: una banda de 0.30 centrada en X = 0 llega hasta +0.15, o sea
        # DENTRO del agua con trazador, y entonces la densidad que mide no es la de X = 0
        izq[-1]["alcance"] = "%+.2f a %+.2f" % (X - IZQ_BANDA / 2, X + IZQ_BANDA / 2)
        print("   X %+.2f  (banda %s)  densidad %.6f (con la banda del caso %.6f, x%.1f)  "
              "v %+.4f coh %.2f  -> %s"
              % (X, izq[-1]["alcance"], d, filas[j]["densidad"], izq[-1]["razon"], v, c,
                 "pasa el umbral" if izq[-1]["pasa_densidad"] else "sigue sin trazador"))

    ac = [f for f in filas if f["aceptada"]]
    print("\naceptadas %d de %d" % (len(ac), N_ESTACIONES))
    if ac:
        print("mediana de la seccion medida: %+.4f alt.cam/s" % np.median([f["v"] for f in ac]))
        d = [abs(f["v"] - f["v_fft"]) for f in ac if np.isfinite(f["v_fft"])]
        print("acuerdo tensor-fft en las aceptadas: %.4f mediana, %.4f maximo"
              % (np.median(d), max(d)))
        d2 = [abs(f["v"] - f["v_filtro"]) for f in ac if f["filtro_detecta"]]
        nd = sum(1 for f in ac if f["filtro_detecta"])
        print("filtro adaptado: detecta en %d de %d aceptadas%s"
              % (nd, len(ac), (", |v_tensor - v_filtro| mediana %.4f" % np.median(d2))
                 if d2 else ""))
        # Falsos positivos del filtro: es lo que decide si puede usarse como criterio de
        # aceptacion o solo como corroborador. En las estaciones sin trazador NO hay nada que
        # detectar, asi que cada deteccion ahi es un falso positivo por construccion.
        vac = [f for f in filas if not f["aceptada"] and "sin_trazador" in f["motivos"]]
        fp = sum(1 for f in vac if f["filtro_detecta"])
        print("filtro adaptado: %d falsos positivos en las %d estaciones sin trazador "
              "-> corrobora, NO sirve de criterio de aceptacion" % (fp, len(vac)))

    campos = ["estacion", "X", "X_rel", "densidad", "v", "coherencia", "v_fft", "agudeza_fft",
              "v_filtro", "filtro_score", "filtro_techo", "filtro_detecta", "v_ventanas",
              "q05", "q95", "n_aceptadas", "n_ventanas", "aceptada"]
    with open(os.path.join(DIR_SALIDAS, "perfil_mejorado.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos + ["motivo"], extrasaction="ignore")
        w.writeheader()
        for f in filas:
            f["motivo"] = ";".join(f["motivos"])
            w.writerow(f)
    with open(os.path.join(DIR_SALIDAS, "banda_ancha_izquierda.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(izq[0].keys()))
        w.writeheader()
        w.writerows(izq)
    with open(os.path.join(DIR_SALIDAS, "config_mejorado.json"), "w", encoding="utf-8") as fh:
        json.dump({"n_estaciones": N_ESTACIONES, "ventana": VENTANA, "paso": PASO,
                   "filtro_n_cand": FILTRO_N_CAND, "filtro_n_nulos": FILTRO_N_NULOS,
                   "filtro_decima": FILTRO_DECIMA, "izq_x": IZQ_X,
                   "izq_lineas": IZQ_LINEAS, "izq_banda": IZQ_BANDA,
                   "n_frames": NF, "fps": fps, "DS": DS, "n_muestras": nmu,
                   "focal": geo.focal, "ancho_canal": geo.ancho,
                   "X_izq": geo.X_izq, "X_der": geo.X_der,
                   "hereda_de": ["analisis_canal_riego_stiv/stiv_canal.py",
                                 "analisis_canal_filtro_adaptado/filtro_adaptado.py"]},
                  fh, indent=2)
    print("\nescrito: salidas/perfil_mejorado.csv, banda_ancha_izquierda.csv, "
          "config_mejorado.json")


if __name__ == "__main__":
    main()
