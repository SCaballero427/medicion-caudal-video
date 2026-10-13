"""Hasta donde alcanza STIV canal arriba, y por que el campo lejano miente con coherencia 0.98.

Que es esto
-----------
NO es un caso nuevo. Es un experimento controlado sobre `analisis_canal_riego_stiv/`, que mide
solo entre Y = 1.40 y Y = 3.20 alturas de camara. Ese limite se puso **heredando el criterio de
Boneyard** ("cerca del horizonte un pixel cubre tanto suelo que la textura no sobrevive al
remuestreo"), sin medirlo en este video. Aqui se mide.

Todo se importa de `analisis_canal_riego_stiv/stiv_canal.py` -- geometria, realce, tensor,
umbrales. Este fichero no redefine ni un solo parametro del metodo: lo unico que cambia entre
casos es **que trozo del canal se mira y con que paso temporal**. Nada de la carpeta original se
toca; las salidas van a la de aqui.

La pregunta y como se responde
------------------------------
Es la misma agua a 2 y a 6 alturas de camara, asi que **tiene que dar la misma velocidad**. Esa
es toda la prueba, y no necesita ningun dato de campo.

Las tres partes:

1. **Tres bandas de distancia con la configuracion del caso.** Cerca (la actual), media y lejos.
2. **Diezmado temporal.** El campo lejano falla con coherencia 0.98, que es un sintoma raro: si
   fuera senal fisica -- por ejemplo celeridad de onda del rizado, que en un canal de 1 m de
   calado seria unas 20 veces la corriente, justo la razon observada -- el resultado NO deberia
   depender del muestreo. Tomando 1 de cada N fotogramas se separan las dos hipotesis.
3. **Partir la banda actual en dos mitades**, porque si el aliasing empieza donde parece, el
   extremo lejano de la AOI que ya se usa esta en zona dudosa y habria que recortarla.

Uso
---
    python experimento_alcance.py                # las tres partes (~8 min)
    python experimento_alcance.py --frames 1200  # mas corto
"""
import argparse
import csv
import json
import os
import sys

import cv2
import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "analisis_canal_riego_stiv"))
import stiv_canal as sc  # noqa: E402

DIR_CASO = os.path.dirname(os.path.abspath(__file__))
DIR_SALIDAS = os.path.join(DIR_CASO, "salidas")

# ----------------------------------------------------------------------------------
# >>> AJUSTABLE <<<
# ----------------------------------------------------------------------------------
# Bandas de distancia a comparar, en alturas de camara. La primera es la AOI del caso.
BANDAS = [(1.40, 3.20, "cerca"), (3.20, 5.00, "media"), (5.00, 8.00, "lejos")]
# Diezmados a probar en cada banda. 1 = todos los fotogramas.
DIEZMADOS = {"cerca": [1], "media": [1, 8], "lejos": [1, 20, 40]}
# Mitades en que se parte la banda actual.
MITADES = [(1.40, 2.30, "mitad cercana"), (2.30, 3.20, "mitad lejana")]
# Estaciones que se miran: las que el caso acepta.
ESTACIONES = [8, 9, 10, 11, 12, 13]


def resolucion(geo, Y):
    """Cuanto suelo cubre un pixel de imagen a la distancia Y, en alturas de camara."""
    p = geo.a_imagen([[0, Y]])[0]
    q = geo.a_suelo([[p[0], p[1] + 1]])[0]
    return abs(q[1] - Y)


def preparar(geo, y0, y1, N, fps, ests):
    """Mapa de muestreo de una banda con paso temporal N. DS mantiene los 45 grados."""
    DS = N * sc.V_ESPERADA / fps
    nmu = int((y1 - y0) / DS)
    Yv = y0 + DS * np.arange(nmu)
    Xs = geo.estaciones()
    offs = np.linspace(-sc.BANDA / 2, sc.BANDA / 2, sc.N_LINEAS)
    M = np.empty((len(ests), sc.N_LINEAS, nmu, 2), np.float32)
    for a, e in enumerate(ests):
        for b, o in enumerate(offs):
            M[a, b] = geo.a_imagen(np.column_stack([np.full(nmu, Xs[e] + o), Yv]))
    return dict(DS=DS, nmu=nmu, N=N, pts=M.reshape(-1, 2), y0=y0, y1=y1)


def recorrer(video, geo, planes, NF, verbose=True):
    """Una sola pasada por el video alimentando todos los planes a la vez."""
    cap, ntot, fps = sc.abrir_video(video)
    NF = min(NF, ntot)
    ok, f = cap.read()
    g0 = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    mask = np.zeros(g0.shape, np.uint8)
    mask[0:sc.FILA_BORDE_FIN - 40, :] = 255
    cv2.fillPoly(mask, [geo.poligono_agua()], 0)
    p0 = cv2.goodFeaturesToTrack(g0, 600, 0.01, 7, mask=mask)
    ne = len(ESTACIONES)
    for P in planes:
        P["ntemp"] = NF // P["N"]
        P["sti"] = np.zeros((ne, P["ntemp"], P["nmu"]), np.float32)
        P["cnt"] = np.zeros((ne, P["ntemp"]), np.int32)
    leidos = 0
    for i in range(NF):
        if i > 0:
            ok, f = cap.read()
            if not ok:
                break
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        else:
            g = g0
        usa = [P for P in planes if i % P["N"] == 0 and i // P["N"] < P["ntemp"]]
        if usa:
            A, _ = sc.estimar_estabilizacion(g0, g, p0)
            t = sc.realzar(g)
            for P in usa:
                xy = P["pts"] @ A[:, :2].T + A[:, 2]
                nr = ne * sc.N_LINEAS
                v = cv2.remap(t, xy[:, 0].reshape(nr, P["nmu"]).astype(np.float32),
                              xy[:, 1].reshape(nr, P["nmu"]).astype(np.float32),
                              cv2.INTER_LINEAR).reshape(ne, sc.N_LINEAS, P["nmu"])
                P["sti"][:, i // P["N"], :] = v.mean(axis=1)
                P["cnt"][:, i // P["N"]] = (v.max(axis=1) > sc.UMBRAL_PARTICULA).sum(axis=1)
        leidos = i + 1
        if verbose and (i + 1) % 400 == 0:
            print("   %d/%d" % (i + 1, NF), flush=True)
    cap.release()
    return leidos, fps


def guardar_sti(P, geo, nombre, est=11):
    """La STI de una estacion, para poder ver el artefacto en vez de solo leerlo."""
    if est not in ESTACIONES:
        return
    a = ESTACIONES.index(est)
    st = P["sti"][a] - P["sti"][a].mean(axis=0, keepdims=True)
    im = np.clip(st / 6.0, 0, 1)
    cv2.imwrite(os.path.join(DIR_SALIDAS, nombre), (im * 255).astype(np.uint8))


def medir_plan(P, fps, geo):
    """Mide cada estacion del plan. fps efectivo = fps/N."""
    filas = []
    Xs = geo.estaciones()
    st = P["sti"] - P["sti"].mean(axis=1, keepdims=True)
    blk = sc.LADO_BLOQUE if P["ntemp"] >= 200 else 24
    for a, e in enumerate(ESTACIONES):
        dens = float(P["cnt"][a].sum()) / max(P["ntemp"] * P["nmu"], 1)
        p, coh, ns, nt = sc.tensor_seleccion(st[a], blk=blk)
        v = p * P["DS"] * (fps / P["N"]) if np.isfinite(p) else float("nan")
        filas.append(dict(estacion=e, X=float(Xs[e]), densidad=dens, coherencia=coh,
                          v=v, n_bloques=ns, n_bloques_total=nt,
                          aceptada=not sc.motivos_rechazo(dens, v, coh)))
    return filas


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--video", default=sc.ARCHIVO_VIDEO)
    ap.add_argument("--frames", type=int, default=None)
    a = ap.parse_args()
    os.makedirs(DIR_SALIDAS, exist_ok=True)
    cap, ntot, fps = sc.abrir_video(a.video)
    sc.FPS_REAL[0] = fps
    ok, f0 = cap.read()
    cap.release()
    geo = sc.Geometria(cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY))
    NF = ntot if a.frames is None else min(a.frames, ntot)
    DS0 = sc.V_ESPERADA / fps

    print("== resolucion de imagen a lo largo del canal ==")
    print("   Y      fila   1 px = ? alt.cam   DS/px  (DS = %.5f)" % DS0)
    for Y in (1.6, 2.0, 2.5, 3.0, 3.2, 4.0, 5.0, 6.5, 8.0):
        r = resolucion(geo, Y)
        print("  %4.1f   %4.0f      %.5f          %.2f"
              % (Y, geo.a_imagen([[0, Y]])[0, 1], r, DS0 / r))
    print()

    planes = []
    for (y0, y1, nm) in BANDAS:
        for N in DIEZMADOS[nm]:
            P = preparar(geo, y0, y1, N, fps, ESTACIONES)
            P["etiqueta"] = "%s N=%d" % (nm, N)
            P["px"] = P["DS"] / resolucion(geo, (y0 + y1) / 2)
            planes.append(P)
    for (y0, y1, nm) in MITADES:
        P = preparar(geo, y0, y1, 1, fps, ESTACIONES)
        P["etiqueta"] = nm
        P["px"] = P["DS"] / resolucion(geo, (y0 + y1) / 2)
        planes.append(P)
    for P in planes:
        print("%-16s Y %.2f-%.2f  N=%-3d DS=%.5f  %5d muestras  DS = %.2f px"
              % (P["etiqueta"], P["y0"], P["y1"], P["N"], P["DS"], P["nmu"], P["px"]))
    print("\nrecorriendo el video (%d fotogramas)..." % NF)
    leidos, fps = recorrer(a.video, geo, planes, NF)
    print("%d fotogramas leidos\n" % leidos)

    todo = []
    medidas = [(P, medir_plan(P, fps, geo)) for P in planes]   # el tensor, una sola vez
    print("== velocidad (alt.cam/s; la referencia del caso es +0.0590) ==")
    print("%-16s %6s   %s" % ("caso", "DS_px", "  ".join("est%-2d" % e for e in ESTACIONES)))
    for P, filas in medidas:
        for fl in filas:
            fl.update(caso=P["etiqueta"], N=P["N"], DS=P["DS"], DS_px=P["px"],
                      Y0=P["y0"], Y1=P["y1"])
            todo.append(fl)
        cel = ["%+7.4f" % fl["v"] if np.isfinite(fl["v"]) else "    nan" for fl in filas]
        acc = [fl["v"] for fl in filas if fl["aceptada"]]
        print("%-16s %6.2f   %s   | acept %d/%d  mediana %s"
              % (P["etiqueta"], P["px"], " ".join(cel), len(acc), len(filas),
                 ("%+.4f" % np.median(acc)) if acc else "--"))
    print("\n== coherencia (la misma tabla) ==")
    print("%-16s %6s   %s" % ("caso", "DS_px", "  ".join("est%-2d" % e for e in ESTACIONES)))
    for P, filas in medidas:
        print("%-16s %6.2f   %s" % (P["etiqueta"], P["px"],
                                    " ".join("%7.3f" % fl["coherencia"] for fl in filas)))

    for P in planes:
        guardar_sti(P, geo, "sti_%s.png" % P["etiqueta"].replace(" ", "_").replace("=", ""))
    with open(os.path.join(DIR_SALIDAS, "alcance.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(todo[0].keys()))
        w.writeheader()
        w.writerows(todo)
    with open(os.path.join(DIR_SALIDAS, "config_alcance.json"), "w", encoding="utf-8") as fh:
        json.dump({"bandas": BANDAS, "diezmados": DIEZMADOS, "mitades": MITADES,
                   "estaciones": ESTACIONES, "n_frames": leidos, "fps": fps,
                   "DS_base": DS0, "focal": geo.focal,
                   "hereda_de": "analisis_canal_riego_stiv/stiv_canal.py"}, fh, indent=2)
    print("\nescrito: salidas/alcance.csv, salidas/config_alcance.json")


if __name__ == "__main__":
    main()
