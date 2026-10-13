"""El filtro adaptado en video: el barrido de velocidades candidatas, banda a banda.

Que produce
-----------
`salidas/video_filtro.mp4` (H.264). No es un video del rio: es el **barrido** del detector, un
fotograma por candidata, con una pausa final en el veredicto.

Por que este video y no uno del agua
------------------------------------
Los otros videos del workspace ensenan agua con flechas encima. Aqui no serviria de nada: el
resultado de esta carpeta es que **en el campo lejano no hay nada que ensenar**, y un panel de
agua quieta sin flechas no distingue "no hay senal" de "el programa no dibuja". Lo que si se
puede ver es el detector trabajando, que es donde esta el argumento.

Lo que hace el filtro adaptado es integrar a lo largo de una trayectoria: para cada velocidad
candidata recorre `s(t) = s0 + v*t` sobre la STI y suma. Si la candidata acierta, cada particula
se apila consigo misma y la proyeccion saca un pico; si no, suma ruido. Eso es exactamente lo
que se ve aqui, columna a columna:

- **izquierda**: la STI de la banda con la familia de trayectorias de la candidata actual
  dibujada encima. Cuando la inclinacion de las rectas coincide con la de las estelas, se nota.
- **centro**: la proyeccion resultante en una ventana fija. Es donde aparece el pico.
- **derecha**: la puntuacion (max - mediana)/MAD frente a la velocidad candidata, rellenandose,
  contra el techo de la hipotesis nula (fotogramas barajados) y con la zona muerta marcada.

Cuatro filas, y la primera es la que da derecho a creerse las otras tres
------------------------------------------------------------------------
La fila de arriba es un **control positivo sintetico**: estelas de velocidad conocida (+0.059)
metidas en ruido, con la misma escasez de trazador que el video real. Si el detector no la
encontrara, nada de lo que dijera sobre el campo lejano valdria. Debajo van las tres bandas
reales. Un negativo solo significa algo cuando el mismo codigo, en el mismo fotograma, da
positivo en un caso conocido.

NO duplica constantes
---------------------
Bandas, rango de candidatas, ventana de residencia, barajados, zona muerta y el propio filtro se
importan de `filtro_adaptado.py`; la geometria y el realce, de
`analisis_canal_riego_stiv/stiv_canal.py`. Lo unico propio de aqui es el lenguaje visual.

Uso
---
    python video_filtro.py                 # ~4 min (casi todo el precalculo)
    python video_filtro.py --frames 900    # prueba corta
"""
import argparse
import json
import os
import sys
import time

import cv2
import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "analisis_canal_riego_stiv"))
import escritor_video as ev      # noqa: E402
import stiv_canal as sc          # noqa: E402

import filtro_adaptado as fa     # noqa: E402

DIR_CASO = os.path.dirname(os.path.abspath(__file__))
DIR_SALIDAS = os.path.join(DIR_CASO, "salidas")

# ----------------------------------------------------------------------------------
# >>> AJUSTABLE <<<  solo lo propio del video
# ----------------------------------------------------------------------------------
FPS_SALIDA = 30.0
CUADROS_POR_CANDIDATA = 3      # 121 candidatas x 3 = 12 s de barrido
CUADROS_FINAL = 120            # 4 s parado en el veredicto
W_STI, W_PROY, W_CURVA, ALTO_FILA = 420, 300, 620, 190
HUECO_FILA = 40                # sitio bajo cada fila para su veredicto
CLIP_STI = 6.0
N_TRAYECTORIAS = 9             # cuantas rectas de la familia se dibujan sobre la STI
COLOR_FILA = {"sintetico": (150, 230, 250), "cerca": (90, 210, 120),
              "media": (70, 190, 235), "lejos": (90, 110, 245)}


def texto(img, s, org, esc=0.5, col=(255, 255, 255), gr=1):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, esc, (0, 0, 0), gr + 2, cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, esc, col, gr, cv2.LINE_AA)


def lienzo_panel(w, h, fondo=(20, 18, 17)):
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = fondo
    return img


def a_px(xs, ys, xlim, ylim, w, h, m=(34, 8, 8, 20)):
    """(x, y) de datos -> pixel, con margenes (izq, der, arr, aba)."""
    ml, mr, ma, mb = m
    x = ml + (np.asarray(xs, float) - xlim[0]) / (xlim[1] - xlim[0]) * (w - ml - mr)
    y = ma + (ylim[1] - np.asarray(ys, float)) / (ylim[1] - ylim[0]) * (h - ma - mb)
    return np.column_stack([x, y])


# ==================================================================================
# los tres paneles de una fila
# ==================================================================================
def panel_sti(sti, v, fps, ds, w=W_STI, h=ALTO_FILA):
    """La STI con la familia de trayectorias de la candidata actual encima."""
    a = np.clip(sti / CLIP_STI, 0, 1)
    img = cv2.cvtColor((a * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    NF, n = sti.shape
    img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
    # pendiente en muestras/fotograma -> px de pantalla, con las dos escalas del resize
    m = (v / (fps * ds)) * (w / float(n)) / (h / float(NF))
    for k in range(N_TRAYECTORIAS):
        x0 = (k + 0.5) / N_TRAYECTORIAS * w
        cv2.line(img, (int(x0), 0), (int(x0 + m * h), h), (60, 210, 255), 1, cv2.LINE_AA)
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), (85, 85, 85), 1)
    return img


def panel_proy(P, C, iv, w=W_PROY, h=ALTO_FILA, ylim=None):
    """La proyeccion de una ventana fija para la candidata actual, con su pico marcado."""
    img = lienzo_panel(w, h)
    p, c = P[iv], C[iv]
    ok = c >= 0.8 * c.max()
    if ok.sum() < 8:
        texto(img, "sin cobertura", (10, h // 2), 0.44, (150, 150, 150), 1)
        cv2.rectangle(img, (0, 0), (w - 1, h - 1), (85, 85, 85), 1)
        return img
    q = p - p[ok].mean()
    idx = np.where(ok)[0]
    pts = a_px(idx, q[ok], (0, len(p) - 1), ylim, w, h)
    cv2.polylines(img, [np.int32(pts)], False, (210, 210, 210), 1, cv2.LINE_AA)
    j = idx[int(np.argmax(q[ok]))]
    pk = a_px([j], [q[j]], (0, len(p) - 1), ylim, w, h)[0]
    cv2.circle(img, tuple(np.int32(pk)), 4, (60, 210, 255), -1, cv2.LINE_AA)
    y0 = a_px([0], [0], (0, len(p) - 1), ylim, w, h)[0][1]
    cv2.line(img, (34, int(y0)), (w - 8, int(y0)), (70, 70, 70), 1)
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), (85, 85, 85), 1)
    return img


def fondo_curva(vs, techo, ylim, w=W_CURVA, h=ALTO_FILA):
    """Ejes, techo de la nula y zona muerta. Se monta una vez por banda."""
    img = lienzo_panel(w, h)
    xlim = (vs[0], vs[-1])
    # zona muerta: alrededor de v = 0 la nula por barajado no discrimina (ver filtro_adaptado)
    zm = a_px([-fa.ZONA_MUERTA, fa.ZONA_MUERTA], [ylim[1], ylim[1]], xlim, ylim, w, h)
    cv2.rectangle(img, (int(zm[0][0]), 8), (int(zm[1][0]), h - 20), (44, 40, 38), -1)
    texto(img, "zona muerta", (int(zm[0][0]) - 30, h - 24), 0.32, (110, 110, 110), 1)
    paso = max(1.0, round((ylim[1] - ylim[0]) / 6.0))
    for yy in np.arange(np.ceil(ylim[0] / paso) * paso, ylim[1] + 0.01, paso):
        p = a_px([xlim[0], xlim[1]], [yy, yy], xlim, ylim, w, h)
        cv2.line(img, tuple(np.int32(p[0])), tuple(np.int32(p[1])), (48, 46, 44), 1)
        texto(img, "%.0f" % yy, (4, int(p[0][1]) + 4), 0.32, (120, 120, 120), 1)
    pt = a_px(vs, techo, xlim, ylim, w, h)
    cv2.polylines(img, [np.int32(pt)], False, (110, 110, 200), 1, cv2.LINE_AA)
    texto(img, "techo de la nula (fotogramas barajados)", (46, 34), 0.34, (140, 140, 210), 1)
    for xx in (-0.15, -0.075, 0.0, 0.075, 0.15):
        p = a_px([xx], [ylim[0]], xlim, ylim, w, h)[0]
        cv2.line(img, (int(p[0]), int(p[1])), (int(p[0]), int(p[1]) + 4), (120, 120, 120), 1)
        # la ultima marca se sale por la derecha si se centra como las demas
        texto(img, "%+.2f" % xx, (int(p[0]) - (34 if xx == 0.15 else 16), h - 6), 0.34,
              (150, 150, 150), 1)
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), (85, 85, 85), 1)
    return img


def panel_curva(fondo, vs, real, inv, i, ylim, col, mostrar_inv, w=W_CURVA, h=ALTO_FILA,
                i_pico=None):
    img = fondo.copy()
    xlim = (vs[0], vs[-1])
    if mostrar_inv:
        # el tiempo invertido es el control de simetria: una adveccion real cambia de signo y
        # conserva el modulo; un artefacto no guarda ninguna relacion con su espejo
        pi = a_px(vs, inv, xlim, ylim, w, h)
        cv2.polylines(img, [np.int32(pi)], False, (120, 120, 120), 1, cv2.LINE_AA)
        texto(img, "tiempo invertido", (w - 150, 34), 0.34, (150, 150, 150), 1)
    k = min(i + 1, len(vs))
    if k > 1:
        pr = a_px(vs[:k], real[:k], xlim, ylim, w, h)
        cv2.polylines(img, [np.int32(pr)], False, col, 2, cv2.LINE_AA)
    if i_pico is None:
        p = a_px([vs[i]], [ylim[0]], xlim, ylim, w, h)[0]
        cv2.line(img, (int(p[0]), 8), (int(p[0]), h - 20), (200, 200, 200), 1)
    else:
        p = a_px([vs[i_pico]], [real[i_pico]], xlim, ylim, w, h)[0]
        cv2.circle(img, tuple(np.int32(p)), 5, (60, 210, 255), 2, cv2.LINE_AA)
    return img


# ==================================================================================
def preparar(a):
    """STI de cada banda + control sintetico, y el barrido completo del filtro."""
    rng = np.random.default_rng(fa.SEMILLA)
    vs = np.linspace(fa.V_MIN, fa.V_MAX, fa.N_CAND)
    cap, ntot, fps = sc.abrir_video(a.video)
    sc.FPS_REAL[0] = fps
    ok, f0 = cap.read()
    cap.release()
    geo = sc.Geometria(cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY))
    NF = ntot if a.frames is None else min(a.frames, ntot)
    print("estabilizacion...")
    afines = fa.afines_del_original(a.video, geo, NF)
    print("STI de las tres bandas...")
    planes, fps, leidos = fa.construir_stis(a.video, geo, fa.BANDAS, NF, afines=afines)

    filas = []
    # control positivo primero: si esta fila fallara, el resto del video no probaria nada
    ds0 = planes[0]["ds"]
    sti_s = fa.sintetico(vs, fps, ds0, rng, NF=leidos)
    filas.append(dict(et="sintetico", sti=sti_s, ds=ds0, ancho=ds0 * (sti_s.shape[1] - 1),
                      nota="estelas de +0.059 metidas en ruido"))
    for P in planes:
        filas.append(dict(et=P["et"], sti=P["sti"], ds=P["ds"], ancho=P["y1"] - P["y0"],
                          nota="Y %.1f a %.1f alturas de camara" % (P["y0"], P["y1"])))

    for F in filas:
        nv = fa.ventana_residencia(F["ancho"], fps)
        print("  %-10s %4d x %3d  ventana %d fotogramas"
              % (F["et"], F["sti"].shape[0], F["sti"].shape[1], nv))
        F["P"], F["C"] = fa.proyecciones(F["sti"], vs, fps, F["ds"], nv)
        r = fa.analizar_todo(F["sti"], vs, fps, F["ds"], rng, n_ventana=nv)["pico"]
        F["real"], F["inv"] = r["real"], r["invertido"]
        F["techo"] = r["nulo_max"]
        F["z"] = (r["real"] - r["nulo_med"]) / np.maximum(r["nulo_std"], 1e-12)
        F["ver"] = fa.veredicto(r, vs)
        F["iv"] = F["P"].shape[0] // 2          # ventana fija que se dibuja, ni elegida ni optima
        F["i_pico"] = int(np.argmin(np.abs(vs - F["ver"]["v_pico"])))
        F["nv"] = nv
        lo = min(F["real"].min(), F["techo"].min(), F["inv"].min())
        hi = max(F["real"].max(), F["techo"].max(), F["inv"].max())
        F["ylim"] = (lo - 0.05 * (hi - lo), hi + 0.18 * (hi - lo))
        # escala vertical del panel de proyeccion: fija para todo el barrido, o el pico de la
        # candidata buena no se distinguiria del ruido de las demas al reescalarse cada cuadro
        q = F["P"][F["iv"]]
        m = F["C"][F["iv"]] >= 0.8 * F["C"][F["iv"]].max(axis=-1, keepdims=True)
        d = np.where(m, q - np.nanmean(np.where(m, q, np.nan), axis=-1, keepdims=True), 0.0)
        F["ylim_p"] = (float(np.nanmin(d)) * 1.1, float(np.nanmax(d)) * 1.15)
        v = F["ver"]
        print("     pico %+.4f  score %.2f  techo %.2f  z %+.1f  invertido %+.4f  -> %s"
              % (v["v_pico"], v["score"], v["techo_nulo"], v["z"], v["v_pico_invertido"],
                 "DETECTA" if v["supera_nulo"] else "no detecta"))
    return filas, vs, fps, leidos


def render(filas, vs, salida, verbose=True):
    W = 12 + W_STI + 12 + W_PROY + 12 + W_CURVA + 12
    CAB, PIE = 46, 74
    H = CAB + len(filas) * (ALTO_FILA + HUECO_FILA) + PIE
    vw = ev.abrir(salida, FPS_SALIDA, (W, H))
    for F in filas:
        F["fondo"] = fondo_curva(vs, F["techo"], F["ylim"])
    total = fa.N_CAND * CUADROS_POR_CANDIDATA + CUADROS_FINAL
    t0 = time.time()
    for k in range(total):
        i = min(k // CUADROS_POR_CANDIDATA, fa.N_CAND - 1)
        final = k >= fa.N_CAND * CUADROS_POR_CANDIDATA
        lienzo = lienzo_panel(W, H, (26, 22, 20))
        texto(lienzo, "Filtro adaptado: integrar a lo largo de la trayectoria",
              (12, 28), 0.62, (255, 255, 255), 1)
        if not final:
            texto(lienzo, "candidata  v = %+.4f   (%d de %d)" % (vs[i], i + 1, fa.N_CAND),
                  (W - 400, 28), 0.54, (60, 210, 255), 1)
        else:
            texto(lienzo, "barrido terminado - cada fila, en su pico",
                  (W - 400, 28), 0.50, (200, 200, 200), 1)
        for b, F in enumerate(filas):
            y = CAB + b * (ALTO_FILA + HUECO_FILA)
            col = COLOR_FILA[F["et"]]
            texto(lienzo, "%s  -  %s" % (F["et"], F["nota"]), (12, y + 15), 0.44, col, 1)
            # en la pausa final cada fila se para en SU pico. Con la ultima candidata (+0.15)
            # la cobertura deja casi sin puntos la proyeccion, y ese era justo el fotograma que
            # quedaba congelado al terminar.
            ic = F["i_pico"] if final else i
            x = 12
            lienzo[y + 20:y + 20 + ALTO_FILA, x:x + W_STI] = \
                panel_sti(F["sti"], vs[ic], F["fps"], F["ds"])
            if b == 0:
                texto(lienzo, "STI + trayectorias", (x + 8, y + 36), 0.36, (185, 185, 185), 1)
            x += W_STI + 12
            lienzo[y + 20:y + 20 + ALTO_FILA, x:x + W_PROY] = \
                panel_proy(F["P"][:, ic], F["C"][:, ic], F["iv"], ylim=F["ylim_p"])
            if b == 0:
                texto(lienzo, "proyeccion (ventana %d de %d)" % (F["iv"] + 1, F["P"].shape[0]),
                      (x + 8, y + 36), 0.36, (185, 185, 185), 1)
            x += W_PROY + 12
            lienzo[y + 20:y + 20 + ALTO_FILA, x:x + W_CURVA] = \
                panel_curva(F["fondo"], vs, F["real"], F["inv"], i, F["ylim"], col, final,
                            i_pico=F["i_pico"] if final else None)
            if b == 0:
                texto(lienzo, "puntuacion (max - mediana)/MAD", (x + 46, y + 36), 0.36,
                      (185, 185, 185), 1)
            v = F["ver"]
            if final:
                ok = v["supera_nulo"]
                espejo = abs(v["v_pico_invertido"] + v["v_pico"]) < 0.006
                s = ("DETECTA  v = %+.4f   score %.2f > techo %.2f   z %+.0f"
                     % (v["v_pico"], v["score"], v["techo_nulo"], v["z"])) if ok else \
                    ("no detecta   pico %.2f, techo %.2f" % (v["score"], v["techo_nulo"]))
                s += "   |   espejo temporal %+.4f %s" % (
                    v["v_pico_invertido"], "(coincide)" if espejo else "(no coincide)")
                # el veredicto va bajo la STI, a la izquierda: pegado al panel de la curva
                # pisaba las marcas de su eje X
                texto(lienzo, s, (12, y + ALTO_FILA + 34), 0.42,
                      col if ok else (140, 140, 140), 1)
            else:
                texto(lienzo, "score %.2f   techo de la nula %.2f"
                      % (F["real"][i], F["techo"][i]), (12, y + ALTO_FILA + 34), 0.40,
                      (170, 170, 170), 1)
        yb = CAB + len(filas) * (ALTO_FILA + HUECO_FILA)
        texto(lienzo, "si la candidata acierta, cada particula se apila consigo misma y la "
                      "proyeccion saca un pico; si no, suma ruido",
              (12, yb + 20), 0.44, (200, 200, 200), 1)
        texto(lienzo, "la fila de arriba es un control positivo de velocidad conocida: sin ella, "
                      "un negativo en las de abajo no probaria nada",
              (12, yb + 40), 0.42, (165, 165, 165), 1)
        texto(lienzo, "la zona muerta se excluye porque ahi la nula por barajado no discrimina: "
                      "sumar a v = 0 es la media temporal, que no depende del orden",
              (12, yb + 58), 0.40, (145, 145, 145), 1)
        vw.write(lienzo)
        if verbose and (k + 1) % 100 == 0:
            print("   %d/%d (%.1fs)" % (k + 1, total, time.time() - t0), flush=True)
    vw.release()
    return total, (W, H)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--video", default=sc.ARCHIVO_VIDEO)
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--salida", default=os.path.join(DIR_SALIDAS, "video_filtro.mp4"))
    a = ap.parse_args()
    os.makedirs(DIR_SALIDAS, exist_ok=True)
    filas, vs, fps, NF = preparar(a)
    for F in filas:
        F["fps"] = fps
    print("dibujando el barrido...")
    n, dim = render(filas, vs, a.salida)
    print("escrito: %s  (%dx%d, %d fotogramas)" % (a.salida, dim[0], dim[1], n))
    with open(os.path.join(DIR_SALIDAS, "config_video_filtro.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"fps_salida": FPS_SALIDA, "cuadros_por_candidata": CUADROS_POR_CANDIDATA,
                   "cuadros_final": CUADROS_FINAL, "n_candidatas": fa.N_CAND,
                   "n_frames_video": NF, "fps_video": fps, "dimension": list(dim),
                   "veredictos": {F["et"]: F["ver"] for F in filas},
                   "hereda_de": ["analisis_canal_riego_stiv/stiv_canal.py",
                                 "filtro_adaptado.py"]}, fh, indent=2, default=float)


if __name__ == "__main__":
    main()
