"""El mismo STIV en ventanas deslizantes sobre los 81 s, dibujado sobre las dos vistas.

Que produce
-----------
`salidas/velocidad_tiempo_real.mp4` (H.264, reproduccion a tiempo real: un fotograma de salida
por cada fotograma de entrada) y `salidas/velocidad_ventanas.csv` con la serie por ventana.

Dos paneles, como en Boneyard y Hommerich y a diferencia de SMC y Bradano: la camara es oblicua,
asi que la medida ocurre en el panel rectificado y el original es lo que permite juzgar que las
estaciones caen donde uno cree. Los dos llevan el mismo dibujo; la flecha del panel original no
es una copia girada, su punta se proyecta con la misma homografia, asi que la perspectiva la
inclina y la acorta sola.

NO duplica las constantes
-------------------------
Esta es la diferencia deliberada con los otros cinco casos del workspace, donde el
`video_velocidad.py` copia las constantes del notebook y hay que cambiarlas en dos sitios. Aqui
todo se importa de `stiv_canal.py`: geometria, realce, tensor y umbrales de calidad son
literalmente los mismos objetos. Lo unico propio de este fichero es lo que solo tiene sentido en
un video -- el tamano de ventana, el paso y el lenguaje visual.

Coste
-----
Una sola pasada construye la STI completa; el tensor sobre las ventanas es despues casi gratis
(la misma asimetria medida en todos los casos STIV del workspace). La segunda pasada es solo para
dibujar.

Uso
---
    python video_velocidad.py                 # video entero
    python video_velocidad.py --frames 600    # prueba corta
"""
import argparse
import csv
import json
import os
import time

import cv2
import numpy as np

import escritor_video as ev
import stiv_canal as sc

# ----------------------------------------------------------------------------------
# >>> AJUSTABLE <<<  solo lo que es propio del video
# ----------------------------------------------------------------------------------
# Ventana de medida, en fotogramas. 360 = 12 s. Medido: con ventanas de 400 fotogramas alguna
# estacion devuelve valores absurdos (0.21 y 0.10 alt.cam/s) que la cota fisica atrapa; con
# ventanas mas cortas pasa mas a menudo, porque hay menos particulas dentro.
VENTANA = 360
PASO = 15                      # media ventana nueva cada 0.5 s
ESCALA_RECT = 320.0            # px por altura de camara en el panel rectificado
SEG_FLECHA = 10.0              # la flecha es el recorrido en 10 s (1 s seria invisible aqui)
V_COLOR_MAX = 0.075            # tope de la paleta, en alturas de camara/s
# Los detritos detectados se pintan encima de los dos paneles. Es lo que hace el video
# autoexplicativo -- se ve la particula y se ve la flecha que produce -- y evita el truco de
# estirar el contraste sobre el agua, que en este video quema las dos orillas (30 % de pixeles
# saturados) y aun asi deja el agua plana.
UMBRAL_DIBUJO = 6.0
COLOR_PARTICULA = (60, 255, 255)


def stretch_bgr(g, lo, hi):
    a = np.clip((g.astype(np.float32) - lo) / max(hi - lo, 1e-6), 0, 1)
    return cv2.cvtColor((a * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


# Paleta precalculada. `cv2.applyColorMap` sobre un array de 1x1 cuesta 1.9 ms por la
# sobrecarga de montar la LUT, y aqui se pedia un color 205 veces por fotograma: eran 23 de los
# 31 s del bucle de dibujo. Con la tabla hecha una vez, el dibujo baja de 0.52 a 0.13 s por
# fotograma.
_LUT = cv2.applyColorMap(np.arange(256, dtype=np.uint8).reshape(1, -1),
                         cv2.COLORMAP_TURBO)[0]
_LUT_T = [tuple(int(x) for x in _LUT[i]) for i in range(256)]


def color_v(v):
    if not np.isfinite(v):
        return (120, 120, 120)
    return _LUT_T[int(np.clip(v / V_COLOR_MAX, 0, 1) * 255)]


def texto(img, s, org, esc=0.5, col=(255, 255, 255), gr=1):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, esc, (0, 0, 0), gr + 2, cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, esc, col, gr, cv2.LINE_AA)


# ==================================================================================
# pasada 1: STI completa + conteo de particulas por fotograma
# ==================================================================================
def pasada_sti(ruta, geo, n_frames, verbose=True):
    DS = sc.V_ESPERADA / sc.FPS_REAL[0]
    n_mues = int((sc.Y_MAX - sc.Y_MIN) / DS)
    Yv = sc.Y_MIN + DS * np.arange(n_mues)
    Xs = geo.estaciones()
    offs = np.linspace(-sc.BANDA / 2, sc.BANDA / 2, sc.N_LINEAS)
    mapas = np.empty((sc.N_ESTACIONES, sc.N_LINEAS, n_mues, 2), np.float32)
    for a, X in enumerate(Xs):
        for b, o in enumerate(offs):
            mapas[a, b] = geo.a_imagen(np.column_stack([np.full(n_mues, X + o), Yv]))
    pts = mapas.reshape(-1, 2)
    nr = sc.N_ESTACIONES * sc.N_LINEAS

    cap, ntot, fps = sc.abrir_video(ruta)
    NF = ntot if n_frames is None else min(n_frames, ntot)
    ok, f = cap.read()
    g0 = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    mask = np.zeros(g0.shape, np.uint8)
    mask[0:sc.FILA_BORDE_FIN - 40, :] = 255
    cv2.fillPoly(mask, [geo.poligono_agua()], 0)
    p0 = cv2.goodFeaturesToTrack(g0, 600, 0.01, 7, mask=mask)

    sti = np.zeros((sc.N_ESTACIONES, NF, n_mues), np.float32)
    cuenta = np.zeros((sc.N_ESTACIONES, NF), np.int32)
    afines = np.zeros((NF, 2, 3), np.float32)
    t0 = time.time()
    leidos = 0
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
        afines[i] = A
        t = sc.realzar(g)
        xy = pts @ A[:, :2].T + A[:, 2]
        v = cv2.remap(t, xy[:, 0].reshape(nr, n_mues).astype(np.float32),
                      xy[:, 1].reshape(nr, n_mues).astype(np.float32), cv2.INTER_LINEAR)
        v = v.reshape(sc.N_ESTACIONES, sc.N_LINEAS, n_mues)
        sti[:, i, :] = v.mean(axis=1)
        cuenta[:, i] = (v.max(axis=1) > sc.UMBRAL_PARTICULA).sum(axis=1)
        if verbose and (i + 1) % 300 == 0:
            print("   STI %d/%d (%.1fs)" % (i + 1, NF, time.time() - t0), flush=True)
    cap.release()
    NF = leidos
    return sti[:, :NF], cuenta[:, :NF], afines[:NF], DS, n_mues, fps, NF


# ==================================================================================
# ventanas
# ==================================================================================
def medir_ventanas(sti, cuenta, DS, fps, n_mues):
    NF = sti.shape[1]
    centros, res = [], []
    for w0 in range(0, max(1, NF - VENTANA + 1), PASO):
        w1 = w0 + VENTANA
        centros.append((w0 + w1) // 2)
        fila = []
        for a in range(sc.N_ESTACIONES):
            im = sti[a, w0:w1]
            im = im - im.mean(axis=0, keepdims=True)     # media temporal de ESTA ventana
            dens = float(cuenta[a, w0:w1].sum()) / (VENTANA * n_mues)
            pend, coh, nsel, ntot = sc.tensor_seleccion(im)
            v = pend * DS * fps if np.isfinite(pend) else np.nan
            # mismo control de calidad que la medida sobre el video entero, misma funcion
            ok = not sc.motivos_rechazo(dens, v, coh)
            fila.append((v, coh, dens, ok))
        res.append(fila)
    return np.array(centros), res


# ==================================================================================
# pasada 2: dibujo
# ==================================================================================
def render(ruta, geo, centros, res, NF, fps, salida, verbose=True):
    rst = geo.raster(escala=ESCALA_RECT, margen=0.06)
    mp = geo.mapa_rect(rst)
    Xs = geo.estaciones()
    cap, ntot, _ = sc.abrir_video(ruta)
    ok, f = cap.read()
    g0 = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    lo, hi = np.percentile(g0, [1.0, 99.0])
    cap.release()

    Ho, Wo = g0.shape
    Hr, Wr = rst["h"], rst["w"]
    esc_o = Hr / float(Ho) if Hr < Ho else 1.0
    Wo2, Ho2 = int(Wo * esc_o), int(Ho * esc_o)
    GAP, CAB, PIE = 14, 44, 82
    Wc = Wo2 + GAP + Wr
    Hc = CAB + max(Ho2, Hr) + PIE
    vw = ev.abrir(salida, fps, (Wc, Hc))

    cap, _, _ = sc.abrir_video(ruta)
    ok, f = cap.read()
    g0 = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    mask = np.zeros(g0.shape, np.uint8)
    mask[0:sc.FILA_BORDE_FIN - 40, :] = 255
    cv2.fillPoly(mask, [geo.poligono_agua()], 0)
    p0 = cv2.goodFeaturesToTrack(g0, 600, 0.01, 7, mask=mask)
    barra = np.array([[color_v(xx / 200.0 * V_COLOR_MAX) for xx in range(200)]] * 12,
                     np.uint8)
    # el mapa rectificado como dos planos contiguos, para no rehacer el dstack cada fotograma
    mp_pts = np.ascontiguousarray(mp.reshape(-1, 2))

    # Mascara del agua medida. Hace falta porque el top-hat responde MUCHO mas a la grava y la
    # vegetacion de las orillas que al agua -- tienen mucha mas estructura fina -- y si se pintan
    # los detritos sin recortar, las dos orillas salen en amarillo macizo y los pocos detritos
    # reales no se ven. Se recorta al mismo tramo que se mide: entre los dos retranqueos y entre
    # Y_MIN e Y_MAX.
    Xa, Xb = geo.X_izq + sc.RETRANQUEO, geo.X_der - sc.RETRANQUEO
    esquinas = np.array([[Xa, sc.Y_MIN], [Xb, sc.Y_MIN], [Xb, sc.Y_MAX], [Xa, sc.Y_MAX]])
    esq_img0 = geo.a_imagen(esquinas)
    msk_rect = np.zeros((Hr, Wr), np.uint8)
    cv2.fillPoly(msk_rect, [np.int32(geo.rect_a_pix(rst, esquinas))], 1)
    msk_rect = msk_rect.astype(bool)
    dil = np.ones((3, 3), np.uint8)
    t0 = time.time()
    serie = []
    for i in range(NF):
        if i > 0:
            ok, f = cap.read()
            if not ok:
                break
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        else:
            g = g0
        A, _ = sc.estimar_estabilizacion(g0, g, p0)
        k = int(np.argmin(np.abs(centros - i)))
        fila = res[k]
        lienzo = np.zeros((Hc, Wc, 3), np.uint8)
        lienzo[:] = (26, 22, 20)

        # -- panel original --------------------------------------------------------
        po = stretch_bgr(g, lo, hi)
        real = sc.realzar(g)
        # -- panel rectificado (del fotograma actual, con la deriva compuesta) ------
        qq = mp_pts @ A[:, :2].T + A[:, 2]
        mrx = qq[:, 0].reshape(Hr, Wr).astype(np.float32)
        mry = qq[:, 1].reshape(Hr, Wr).astype(np.float32)
        pr = cv2.remap(g, mrx, mry, cv2.INTER_LINEAR)
        pr = stretch_bgr(pr, lo, hi)
        # los detritos, en los dos paneles, dilatados 1 px para que se vean a esta escala y
        # recortados al agua medida (ver la nota de msk_rect)
        msk_img = np.zeros(g.shape, np.uint8)
        cv2.fillPoly(msk_img, [np.int32(esq_img0 @ A[:, :2].T + A[:, 2])], 1)
        det_o = cv2.dilate((real > UMBRAL_DIBUJO).astype(np.uint8), dil) > 0
        po[det_o & (msk_img > 0)] = COLOR_PARTICULA
        realr = cv2.remap(real, mrx, mry, cv2.INTER_LINEAR)
        det_r = cv2.dilate((realr > UMBRAL_DIBUJO).astype(np.uint8), dil) > 0
        pr[det_r & msk_rect] = COLOR_PARTICULA

        acept = [fila[a][0] for a in range(sc.N_ESTACIONES) if fila[a][3]]
        med = float(np.median(acept)) if acept else float("nan")

        for a in range(sc.N_ESTACIONES):
            v, coh, dens, okk = fila[a]
            X = Xs[a]
            col = color_v(v) if okk else (120, 120, 120)
            # linea de busqueda
            P = np.column_stack([np.full(24, X), np.linspace(sc.Y_MIN, sc.Y_MAX, 24)])
            Io = geo.a_imagen(P) @ A[:, :2].T + A[:, 2]
            for j in range(len(Io) - 1):
                cv2.line(po, tuple(np.int32(Io[j])), tuple(np.int32(Io[j + 1])), col,
                         2 if okk else 1, cv2.LINE_AA)
            Ir = geo.rect_a_pix(rst, P)
            for j in range(len(Ir) - 1):
                cv2.line(pr, tuple(np.int32(Ir[j])), tuple(np.int32(Ir[j + 1])), col,
                         2 if okk else 1, cv2.LINE_AA)
            Ym = (sc.Y_MIN + sc.Y_MAX) / 2
            if okk:
                # flecha = recorrido en SEG_FLECHA segundos, longitud real
                Yb = min(sc.Y_MAX - 0.02, Ym + v * SEG_FLECHA)
                a0 = geo.a_imagen([[X, Ym]]) @ A[:, :2].T + A[:, 2]
                a1 = geo.a_imagen([[X, Yb]]) @ A[:, :2].T + A[:, 2]
                cv2.arrowedLine(po, tuple(np.int32(a0[0])), tuple(np.int32(a1[0])), col, 2,
                                cv2.LINE_AA, tipLength=0.28)
                b0 = geo.rect_a_pix(rst, [[X, Ym]])[0]
                b1 = geo.rect_a_pix(rst, [[X, Yb]])[0]
                cv2.arrowedLine(pr, tuple(np.int32(b0)), tuple(np.int32(b1)), col, 2,
                                cv2.LINE_AA, tipLength=0.28)
                # las etiquetas se escalonan: a este paso entre estaciones, en una sola fila
                # se solapan y no se lee ninguna
                dy = 22 * (a % 3)
                texto(pr, "%.3f" % v, (int(b0[0]) - 20, int(b0[1]) + 30 + dy), 0.42, col, 1)
            else:
                b0 = geo.rect_a_pix(rst, [[X, Ym]])[0]
                cv2.drawMarker(pr, tuple(np.int32(b0)), (110, 110, 110), cv2.MARKER_TILTED_CROSS,
                               9, 1, cv2.LINE_AA)
        if esc_o != 1.0:
            po = cv2.resize(po, (Wo2, Ho2), interpolation=cv2.INTER_AREA)
        lienzo[CAB:CAB + Ho2, 0:Wo2] = po
        lienzo[CAB:CAB + Hr, Wo2 + GAP:Wo2 + GAP + Wr] = pr

        texto(lienzo, "STIV desde cero sobre video de movil - canal de riego sin datos de campo",
              (12, 26), 0.62, (255, 255, 255), 1)
        texto(lienzo, "vista de la camara", (12, CAB - 8), 0.44, (235, 235, 235), 1)
        texto(lienzo, "plano del agua rectificado  (aqui se mide)",
              (Wo2 + GAP + 8, CAB - 8), 0.44, (170, 255, 190), 1)
        yb = CAB + max(Ho2, Hr)
        texto(lienzo, "t = %5.1f s" % (i / fps), (12, yb + 24), 0.54, (255, 255, 255), 1)
        if acept:
            texto(lienzo, "mediana de la seccion: %.4f alturas de camara/s   (%d de %d "
                          "estaciones)" % (med, len(acept), sc.N_ESTACIONES),
                  (150, yb + 24), 0.54, (120, 230, 255), 1)
        else:
            texto(lienzo, "sin estaciones validas en esta ventana", (150, yb + 24), 0.54,
                  (120, 120, 200), 1)
        texto(lienzo, "amarillo = detrito flotante detectado (lo que se mide).   x gris = "
                      "estacion rechazada: por ahi no pasa ninguno",
              (12, yb + 46), 0.44, (180, 180, 180), 1)
        texto(lienzo, "sin escala real: unidades afines (alturas de camara). la flecha es el "
                      "recorrido en %.0f s" % SEG_FLECHA,
              (12, yb + 64), 0.42, (165, 165, 165), 1)
        texto(lienzo, "ventana %d fotogramas (%.1f s) | video preprocesado, no en directo"
              % (VENTANA, VENTANA / fps), (Wc - 640, yb + 64), 0.40, (140, 140, 140), 1)
        # barra de color (el degradado se monta una sola vez, fuera del bucle)
        bx, by, bw_, bh_ = Wc - 250, yb + 30, 200, 12
        lienzo[by:by + bh_, bx:bx + bw_] = barra
        texto(lienzo, "0", (bx - 10, by + bh_), 0.38, (200, 200, 200), 1)
        texto(lienzo, "%.3f" % V_COLOR_MAX, (bx + bw_ + 4, by + bh_), 0.38, (200, 200, 200), 1)

        vw.write(lienzo)
        serie.append((i, i / fps, med, len(acept)))
        if verbose and (i + 1) % 300 == 0:
            print("   dibujo %d/%d (%.1fs)" % (i + 1, NF, time.time() - t0), flush=True)
    cap.release()
    vw.release()
    return serie, (Wc, Hc)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--video", default=sc.ARCHIVO_VIDEO)
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--salida", default=os.path.join(sc.DIR_SALIDAS,
                                                     "velocidad_tiempo_real.mp4"))
    a = ap.parse_args()
    os.makedirs(sc.DIR_SALIDAS, exist_ok=True)
    cap, ntot, fps = sc.abrir_video(a.video)
    sc.FPS_REAL[0] = fps
    ok, f0 = cap.read()
    cap.release()
    geo = sc.Geometria(cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY))
    print("geometria: fuga (%.1f, %.1f), inclinacion %.2f deg, ancho %.4f alt.cam"
          % (geo.xv, geo.yv, np.degrees(geo.inclinacion), geo.ancho))
    print("pasada 1: construyendo la STI completa...")
    sti, cuenta, afines, DS, n_mues, fps, NF = pasada_sti(a.video, geo, a.frames)
    print("  %d fotogramas, %d muestras" % (NF, n_mues))
    centros, res = medir_ventanas(sti, cuenta, DS, fps, n_mues)
    print("  %d ventanas de %d fotogramas" % (len(centros), VENTANA))
    tot = sum(1 for f in res for e in f if e[3])
    print("  aceptadas %d de %d parejas estacion-ventana"
          % (tot, len(res) * sc.N_ESTACIONES))
    meds = []
    for fila in res:
        ac = [e[0] for e in fila if e[3]]
        if ac:
            meds.append(np.median(ac))
    meds = np.array(meds)
    if len(meds):
        print("  mediana de la seccion: %.4f  (q05-q95 %.4f - %.4f, rango %.4f - %.4f)"
              % (np.median(meds), np.percentile(meds, 5), np.percentile(meds, 95),
                 meds.min(), meds.max()))
    with open(os.path.join(sc.DIR_SALIDAS, "velocidad_ventanas.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ventana", "centro_frame", "t_s", "estacion", "X", "v", "coherencia",
                    "densidad", "aceptada"])
        Xs = geo.estaciones()
        for k, c in enumerate(centros):
            for aa in range(sc.N_ESTACIONES):
                v, coh, dens, okk = res[k][aa]
                w.writerow([k, int(c), "%.3f" % (c / fps), aa, "%.4f" % Xs[aa],
                            "%.6f" % v if np.isfinite(v) else "", "%.4f" % coh,
                            "%.6f" % dens, int(okk)])
    print("pasada 2: dibujando...")
    serie, dim = render(a.video, geo, centros, res, NF, fps, a.salida)
    print("escrito: %s  (%dx%d, %d fotogramas)" % (a.salida, dim[0], dim[1], len(serie)))
    with open(os.path.join(sc.DIR_SALIDAS, "config_video_velocidad.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"ventana": VENTANA, "paso": PASO, "escala_rect": ESCALA_RECT,
                   "seg_flecha": SEG_FLECHA, "v_color_max": V_COLOR_MAX,
                   "n_ventanas": len(centros), "n_frames": NF, "fps": fps,
                   "v_mediana_video": float(np.median(meds)) if len(meds) else None,
                   "dimension": list(dim)}, fh, indent=2)


if __name__ == "__main__":
    main()
