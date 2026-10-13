"""STIV tal cual, sin nada modelado: las flechas, y la STI de la que sale cada una.

Que produce
-----------
`salidas/stiv_puro.mp4` (H.264, tiempo real: un fotograma de salida por cada uno de entrada) y
`salidas/perfil_ventanas.csv`.

Que es y que no es
------------------
`analisis_canal_completo_stiv/` termina en una **simulacion**: un modelo hidraulico que rellena el
64 % del ancho donde no hay trazador. Es util y esta bien etiquetado, pero es facil quedarse con la
imagen de un canal entero en movimiento y olvidar que dos tercios de esa imagen los pone un modelo.

Este video es lo contrario y por eso existe aparte: **todo lo que se ve aqui esta medido**. No hay
particulas virtuales, no hay perfil extrapolado, no hay relleno de las estaciones rechazadas, no
hay curva ajustada. Donde STIV no mide, no se dibuja nada. La imagen que sale es mas pobre -- el
canal aparece medido solo en su tercio derecho -- y esa pobreza **es el resultado honesto** de este
video de movil.

Que se ve
---------
- **Las lineas de busqueda de las 15 estaciones**, tenues las rechazadas y en color las aceptadas.
- **Una flecha por estacion aceptada**, cuyo largo es el recorrido en 10 s, o sea que su longitud
  *es* la velocidad. Sobre la vista de camara la punta se proyecta con la misma homografia, asi
  que la perspectiva la escorza sola: no es una copia girada.
- **La STI de la estacion resaltada, abajo, con la recta que el tensor ha encontrado dibujada
  encima.** Es lo que convierte esto en STIV y no en "flechas sobre agua": se ven las estelas del
  detrito, se ve la pendiente que se les ajusta, y se ve la flecha que esa pendiente produce. La
  estacion resaltada va rotando cada pocos segundos.
- **El perfil transversal medido**, solo con los puntos que hay. Los huecos se quedan huecos.

NO duplica nada
---------------
La medida es literalmente la del caso original: `pasada_sti` y `medir_ventanas` se importan de
`analisis_canal_riego_stiv/video_velocidad.py`, y la geometria, el realce, el tensor y el control
de calidad de `stiv_canal.py`. Este fichero solo dibuja.

Uso
---
    python video_stiv_puro.py                 # ~7 min
    python video_stiv_puro.py --frames 600    # prueba corta
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
import escritor_video as ev      # noqa: E402
import stiv_canal as sc          # noqa: E402
import video_velocidad as vv     # noqa: E402

DIR_CASO = os.path.dirname(os.path.abspath(__file__))
DIR_SALIDAS = os.path.join(DIR_CASO, "salidas")

# ----------------------------------------------------------------------------------
# >>> AJUSTABLE <<<  solo lo propio del video
# ----------------------------------------------------------------------------------
ESCALA_RECT = 320.0            # px por altura de camara en el panel rectificado
MARGEN_RECT = 0.06
SEG_FLECHA = 10.0              # la flecha es el recorrido en 10 s: su largo ES la velocidad
V_COLOR_MAX = 0.075
ALTO_STI, ALTO_PERFIL = 210, 210
CLIP_STI = 3.5                 # tope de gris de la STI. Mas bajo que en otros paneles del
                               # workspace a proposito: aqui la STI no es un adorno, es la prueba,
                               # y con 6.0 las estelas del detrito se quedaban al borde de verse.
CICLO_SEG = 4.0                # cada cuanto pasa el foco a la siguiente estacion aceptada
UMBRAL_DIBUJO = 6.0
COLOR_PARTICULA = (60, 255, 255)
COLOR_RECHAZO = (120, 120, 120)
COLOR_FOCO = (255, 255, 255)

_LUT = cv2.applyColorMap(np.arange(256, dtype=np.uint8).reshape(1, -1),
                         cv2.COLORMAP_TURBO)[0]
_LUT_T = [tuple(int(x) for x in _LUT[i]) for i in range(256)]


def color_v(v):
    if not np.isfinite(v):
        return COLOR_RECHAZO
    return _LUT_T[int(np.clip(v / V_COLOR_MAX, 0, 1) * 255)]


def texto(img, s, org, esc=0.5, col=(255, 255, 255), gr=1):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, esc, (0, 0, 0), gr + 2, cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, esc, col, gr, cv2.LINE_AA)


def stretch_bgr(g, lo, hi):
    a = np.clip((g.astype(np.float32) - lo) / max(hi - lo, 1e-6), 0, 1)
    return cv2.cvtColor((a * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


def panel_sti(im, pend, w, h, etiqueta, col):
    """La STI de una estacion con la pendiente que el tensor le ha encontrado.

    Filas = tiempo hacia abajo, columnas = espacio a lo largo de la linea. Una particula que baja
    por el canal a velocidad constante deja una raya inclinada; la pendiente de esa raya es la
    velocidad, y es literalmente lo unico que mide STIV.
    """
    a = np.clip(im / CLIP_STI, 0, 1)
    img = cv2.cvtColor((a * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    nt, ns = im.shape
    img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
    if np.isfinite(pend):
        # pendiente en muestras/fotograma -> px de pantalla, con las dos escalas del resize
        m = pend * (w / float(ns)) / (h / float(nt))
        cx, cy, dy = w * 0.5, h * 0.5, h * 0.44
        cv2.line(img, (int(cx - m * dy), int(cy - dy)), (int(cx + m * dy), int(cy + dy)),
                 col, 2, cv2.LINE_AA)
    texto(img, etiqueta, (8, 20), 0.46, col, 1)
    texto(img, "tiempo v", (8, h - 8), 0.36, (170, 170, 170), 1)
    texto(img, "espacio, a lo largo de la linea ->", (w - 250, h - 8), 0.36, (170, 170, 170), 1)
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), (85, 85, 85), 1)
    return img


def panel_perfil(fila, Xs, envol, rst, w, h, foco):
    """El perfil transversal de la ventana actual. Solo lo medido; los huecos se quedan huecos."""
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = (20, 18, 17)
    x0, x1 = rst["X0"], rst["X1"]
    ml, mr, ma, mb = 8, 8, 16, 24
    umax = V_COLOR_MAX

    def px(X, u):
        return (ml + (np.asarray(X, float) - x0) / (x1 - x0) * (w - ml - mr),
                ma + (1 - np.asarray(u, float) / umax) * (h - ma - mb))

    for u in np.arange(0, umax + 1e-9, 0.02):
        y = px(0, u)[1]
        cv2.line(img, (ml, int(y)), (w - mr, int(y)), (46, 44, 42), 1)
        texto(img, "%.2f" % u, (ml + 2, int(y) - 3), 0.32, (115, 115, 115), 1)
    # recorrido de cada estacion sobre TODO el video (min-max de las ventanas): tambien medido
    for a, (lo, hi) in envol.items():
        if not np.isfinite(lo):
            continue
        cx = px(Xs[a], 0)[0]
        _, y0 = px(0, lo)
        _, y1 = px(0, hi)
        cv2.line(img, (int(cx), int(y0)), (int(cx), int(y1)), (70, 66, 62), 3, cv2.LINE_AA)
    pts = []
    for a in range(sc.N_ESTACIONES):
        v, coh, dens, ok = fila[a]
        cx, cy = px(Xs[a], v if np.isfinite(v) else 0)
        if ok:
            pts.append((a, int(cx), int(cy)))
            cv2.circle(img, (int(cx), int(cy)), 4, color_v(v), -1, cv2.LINE_AA)
            if a == foco:
                cv2.circle(img, (int(cx), int(cy)), 8, COLOR_FOCO, 1, cv2.LINE_AA)
        else:
            yb = px(0, 0)[1]
            cv2.drawMarker(img, (int(cx), int(yb) - 8), COLOR_RECHAZO,
                           cv2.MARKER_TILTED_CROSS, 8, 1, cv2.LINE_AA)
    # Se unen dos puntos SOLO si son estaciones contiguas. Saltar por encima de una que no mide
    # dibujaria una recta que nadie ha medido, que es exactamente lo que esta carpeta no hace --
    # y es un detalle facil de pasar por alto, porque la lista de aceptadas ya viene sin huecos.
    for (a0, x0p, y0p), (a1, x1p, y1p) in zip(pts, pts[1:]):
        if a1 == a0 + 1:
            cv2.line(img, (x0p, y0p), (x1p, y1p), (150, 150, 150), 1, cv2.LINE_AA)
    texto(img, "perfil transversal medido, ventana actual", (ml + 2, ma - 4), 0.38,
          (215, 215, 215), 1)
    texto(img, "x gris = estacion sin medida. No se rellena.", (ml + 2, h - 8), 0.36,
          COLOR_RECHAZO, 1)
    texto(img, "gris vertical = recorrido de esa estacion en los 81 s",
          (w - 330, h - 8), 0.36, (130, 130, 130), 1)
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), (85, 85, 85), 1)
    return img


def render(ruta, geo, centros, res, afines, sti, DS, fps, NF, salida, verbose=True):
    rst = dict(X0=geo.X_izq - MARGEN_RECT, X1=geo.X_der + MARGEN_RECT, Y0=sc.Y_MIN,
               Y1=sc.Y_MAX, escala=ESCALA_RECT)
    rst["w"] = int(round((rst["X1"] - rst["X0"]) * ESCALA_RECT))
    rst["h"] = int(round((rst["Y1"] - rst["Y0"]) * ESCALA_RECT))
    Hr, Wr = rst["h"], rst["w"]
    mp_pts = np.ascontiguousarray(geo.mapa_rect(rst).reshape(-1, 2))
    Xs = geo.estaciones()

    cap, _, _ = sc.abrir_video(ruta)
    ok, f = cap.read()
    g0 = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    lo_p, hi_p = np.percentile(g0, [1.0, 99.0])
    Ho, Wo = g0.shape
    GAP, CAB, PIE = 12, 46, 76
    Wc = Wo + GAP + Wr
    Hc = CAB + max(Ho, Hr) + GAP + max(ALTO_STI, ALTO_PERFIL) + PIE
    vw = ev.abrir(salida, fps, (Wc, Hc))

    # estaciones que se aceptan alguna vez: son las que puede visitar el foco
    acept_alguna = [a for a in range(sc.N_ESTACIONES)
                    if any(res[k][a][3] for k in range(len(res)))]
    # recorrido de cada estacion sobre todo el video, para el fondo del perfil
    envol = {}
    for a in range(sc.N_ESTACIONES):
        vs = [res[k][a][0] for k in range(len(res)) if res[k][a][3]]
        envol[a] = (min(vs), max(vs)) if vs else (np.nan, np.nan)

    Xa, Xb = geo.X_izq + sc.RETRANQUEO, geo.X_der - sc.RETRANQUEO
    esq = np.array([[Xa, sc.Y_MIN], [Xb, sc.Y_MIN], [Xb, sc.Y_MAX], [Xa, sc.Y_MAX]])
    msk_rect = np.zeros((Hr, Wr), np.uint8)
    cv2.fillPoly(msk_rect, [np.int32(geo.rect_a_pix(rst, esq))], 1)
    msk_rect = msk_rect.astype(bool)
    dil = np.ones((3, 3), np.uint8)
    barra = np.array([[color_v(x / 200.0 * V_COLOR_MAX) for x in range(200)]] * 12, np.uint8)
    t0, serie = time.time(), []
    for i in range(NF):
        if i > 0:
            ok, f = cap.read()
            if not ok:
                break
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        else:
            g = g0
        A = afines[i]
        k = int(np.argmin(np.abs(centros - i)))
        fila = res[k]
        foco = acept_alguna[int(i / (CICLO_SEG * fps)) % len(acept_alguna)] \
            if acept_alguna else -1
        lienzo = np.zeros((Hc, Wc, 3), np.uint8)
        lienzo[:] = (26, 22, 20)

        po = stretch_bgr(g, lo_p, hi_p)
        real = sc.realzar(g)
        qq = mp_pts @ A[:, :2].T + A[:, 2]
        mrx = qq[:, 0].reshape(Hr, Wr).astype(np.float32)
        mry = qq[:, 1].reshape(Hr, Wr).astype(np.float32)
        pr = stretch_bgr(cv2.remap(g, mrx, mry, cv2.INTER_LINEAR), lo_p, hi_p)

        # el detrito detectado: es el dato en bruto del que sale todo, asi que se ve
        msk_img = np.zeros(g.shape, np.uint8)
        cv2.fillPoly(msk_img, [np.int32(geo.a_imagen(esq) @ A[:, :2].T + A[:, 2])], 1)
        det = cv2.dilate((real > UMBRAL_DIBUJO).astype(np.uint8), dil) > 0
        po[det & (msk_img > 0)] = COLOR_PARTICULA
        realr = cv2.remap(real, mrx, mry, cv2.INTER_LINEAR)
        detr = cv2.dilate((realr > UMBRAL_DIBUJO).astype(np.uint8), dil) > 0
        pr[detr & msk_rect] = COLOR_PARTICULA

        acept = [fila[a][0] for a in range(sc.N_ESTACIONES) if fila[a][3]]
        Ym = (sc.Y_MIN + sc.Y_MAX) / 2
        for a in range(sc.N_ESTACIONES):
            v, coh, dens, okk = fila[a]
            X = Xs[a]
            col = color_v(v) if okk else COLOR_RECHAZO
            gr = 2 if okk else 1
            Q = np.column_stack([np.full(20, X), np.linspace(sc.Y_MIN, sc.Y_MAX, 20)])
            Io = geo.a_imagen(Q) @ A[:, :2].T + A[:, 2]
            Ir = geo.rect_a_pix(rst, Q)
            if a == foco:
                cv2.polylines(po, [np.int32(Io)], False, COLOR_FOCO, gr + 2, cv2.LINE_AA)
                cv2.polylines(pr, [np.int32(Ir)], False, COLOR_FOCO, gr + 2, cv2.LINE_AA)
            cv2.polylines(po, [np.int32(Io)], False, col, gr, cv2.LINE_AA)
            cv2.polylines(pr, [np.int32(Ir)], False, col, gr, cv2.LINE_AA)
            b0 = geo.rect_a_pix(rst, [[X, Ym]])[0]
            if not okk:
                cv2.drawMarker(pr, tuple(np.int32(b0)), COLOR_RECHAZO,
                               cv2.MARKER_TILTED_CROSS, 10, 1, cv2.LINE_AA)
                continue
            # la flecha: recorrido en SEG_FLECHA segundos, longitud real sobre el plano del agua
            Yb = min(sc.Y_MAX - 0.02, Ym + v * SEG_FLECHA)
            a0 = geo.a_imagen([[X, Ym]]) @ A[:, :2].T + A[:, 2]
            a1 = geo.a_imagen([[X, Yb]]) @ A[:, :2].T + A[:, 2]
            cv2.arrowedLine(po, tuple(np.int32(a0[0])), tuple(np.int32(a1[0])), col, 3,
                            cv2.LINE_AA, tipLength=0.3)
            b1 = geo.rect_a_pix(rst, [[X, Yb]])[0]
            cv2.arrowedLine(pr, tuple(np.int32(b0)), tuple(np.int32(b1)), col, 3,
                            cv2.LINE_AA, tipLength=0.3)
            dy = 22 * (a % 3)
            texto(pr, "%.3f" % v, (int(b0[0]) - 22, int(b0[1]) + 32 + dy), 0.46, col, 1)

        lienzo[CAB:CAB + Ho, 0:Wo] = po
        x2 = Wo + GAP
        lienzo[CAB:CAB + Hr, x2:x2 + Wr] = pr
        yb = CAB + max(Ho, Hr) + GAP

        w0v = max(0, min(i - vv.VENTANA // 2, NF - vv.VENTANA))
        if foco >= 0:
            im = sti[foco, w0v:w0v + vv.VENTANA]
            im = im - im.mean(axis=0, keepdims=True)
            v, coh, dens, okk = fila[foco]
            pend = v / (DS * fps) if np.isfinite(v) else np.nan
            et = ("estacion %d   X %+.3f   v %+.4f alt.cam/s   coherencia %.2f"
                  % (foco, Xs[foco], v, coh)) if okk else \
                 ("estacion %d   X %+.3f   sin medida en esta ventana" % (foco, Xs[foco]))
            lienzo[yb:yb + ALTO_STI, 0:Wo] = panel_sti(im, pend, Wo, ALTO_STI, et,
                                                       color_v(v) if okk else COLOR_RECHAZO)
        lienzo[yb:yb + ALTO_PERFIL, x2:x2 + Wr] = panel_perfil(fila, Xs, envol, rst, Wr,
                                                               ALTO_PERFIL, foco)

        texto(lienzo, "STIV tal cual: solo lo que el algoritmo mide", (12, 28), 0.62,
              (255, 255, 255), 1)
        texto(lienzo, "vista de la camara", (12, CAB - 8), 0.44, (235, 235, 235), 1)
        texto(lienzo, "plano del agua rectificado  (aqui se mide)", (x2, CAB - 8), 0.44,
              (170, 255, 190), 1)
        yf = yb + max(ALTO_STI, ALTO_PERFIL)
        med = float(np.median(acept)) if acept else float("nan")
        texto(lienzo, "t = %5.1f s" % (i / fps), (12, yf + 26), 0.56, (255, 255, 255), 1)
        if acept:
            texto(lienzo, "mediana de la seccion: %.4f alturas de camara/s   (%d de %d "
                          "estaciones con medida)" % (med, len(acept), sc.N_ESTACIONES),
                  (150, yf + 26), 0.54, (120, 230, 255), 1)
        else:
            texto(lienzo, "ninguna estacion mide en esta ventana", (150, yf + 26), 0.54,
                  (120, 120, 200), 1)
        texto(lienzo, "la flecha es el recorrido en %.0f s, asi que su largo ES la velocidad.  "
                      "amarillo = detrito real detectado, que es lo unico que se mide."
              % SEG_FLECHA, (12, yf + 48), 0.44, (185, 185, 185), 1)
        texto(lienzo, "Sin modelo, sin relleno, sin extrapolacion: donde STIV no mide, no se "
                      "dibuja nada. Unidades afines (alturas de camara).",
              (12, yf + 68), 0.44, (150, 200, 150), 1)
        bx, by, bw_, bh_ = Wc - 250, yf + 34, 200, 12
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
    ap.add_argument("--salida", default=os.path.join(DIR_SALIDAS, "stiv_puro.mp4"))
    a = ap.parse_args()
    os.makedirs(DIR_SALIDAS, exist_ok=True)
    cap, ntot, fps = sc.abrir_video(a.video)
    sc.FPS_REAL[0] = fps
    ok, f0 = cap.read()
    cap.release()
    geo = sc.Geometria(cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY))
    print("geometria: fuga (%.1f, %.1f), ancho %.4f alt.cam" % (geo.xv, geo.yv, geo.ancho))
    print("pasada 1: STI de las %d estaciones (funcion del caso original)..." % sc.N_ESTACIONES)
    sti, cuenta, afines, DS, n_mues, fps, NF = vv.pasada_sti(a.video, geo, a.frames)
    centros, res = vv.medir_ventanas(sti, cuenta, DS, fps, n_mues)
    tot = sum(1 for f in res for e in f if e[3])
    print("  %d fotogramas, %d ventanas, %d de %d parejas estacion-ventana con medida"
          % (NF, len(centros), tot, len(res) * sc.N_ESTACIONES))
    meds = [np.median([e[0] for e in f if e[3]]) for f in res if any(e[3] for e in f)]
    if meds:
        print("  mediana de la seccion: %.4f  (q05-q95 %.4f - %.4f)"
              % (np.median(meds), np.percentile(meds, 5), np.percentile(meds, 95)))
    with open(os.path.join(DIR_SALIDAS, "perfil_ventanas.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ventana", "centro_frame", "t_s", "estacion", "X", "v", "coherencia",
                    "densidad", "con_medida"])
        Xs = geo.estaciones()
        for kk, c in enumerate(centros):
            for aa in range(sc.N_ESTACIONES):
                v, coh, dens, okk = res[kk][aa]
                w.writerow([kk, int(c), "%.3f" % (c / fps), aa, "%.4f" % Xs[aa],
                            "%.6f" % v if np.isfinite(v) else "", "%.4f" % coh,
                            "%.6f" % dens, int(okk)])
    print("pasada 2: dibujando...")
    serie, dim = render(a.video, geo, centros, res, afines, sti, DS, fps, NF, a.salida)
    print("escrito: %s  (%dx%d, %d fotogramas)" % (a.salida, dim[0], dim[1], len(serie)))
    with open(os.path.join(DIR_SALIDAS, "config_stiv_puro.json"), "w", encoding="utf-8") as fh:
        json.dump({"ventana": vv.VENTANA, "paso": vv.PASO, "escala_rect": ESCALA_RECT,
                   "seg_flecha": SEG_FLECHA, "ciclo_seg": CICLO_SEG,
                   "v_color_max": V_COLOR_MAX, "n_estaciones": sc.N_ESTACIONES,
                   "n_ventanas": len(centros), "n_frames": NF, "fps": fps,
                   "v_mediana_video": float(np.median(meds)) if meds else None,
                   "dimension": list(dim),
                   "hereda_de": ["analisis_canal_riego_stiv/stiv_canal.py",
                                 "analisis_canal_riego_stiv/video_velocidad.py"]}, fh, indent=2)


if __name__ == "__main__":
    main()
