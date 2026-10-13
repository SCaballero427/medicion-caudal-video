"""STIV en ventana movil sobre los dos videos del River Arrow, y video comparativo.

Que hace
--------
Repite el STIV del notebook `Arrow_STIV_pipeline.ipynb` en **ventanas deslizantes** sobre los dos
videos a la vez -- el sin sembrar y el sembrado -- y los renderiza **lado a lado**, con exactamente
el mismo tratamiento, la misma configuracion y la misma escala de color en los dos.

Por que dos paneles, y por que aqui no son redundantes
------------------------------------------------------
En el caso del rio Bradano el video lleva un solo panel: la vista es cenital, no hay nada que
rectificar y el segundo panel no ensenaria nada nuevo. En Boneyard Creek y en Hommerich hay dos
porque la rectificacion es una afirmacion que conviene poder comprobar a ojo.

Aqui los dos paneles son **los dos videos del experimento**. El caso no es una medida sino una
comparacion, y el objeto de la comparacion es precisamente lo que se ve al poner los dos juntos:
la misma agua, el mismo encuadre, el mismo algoritmo, y flechas en uno solo. Verlo en movimiento
anade algo que las figuras del notebook no pueden dar -- que el video sin sembrar **no esta roto**:
el agua se mueve, se ve moverse, y aun asi no hay nada que un correlador pueda seguir.

Duplica las constantes del notebook
-----------------------------------
Igual que las herramientas equivalentes de los otros casos, este script **repite** las constantes
`>>> AJUSTABLE <<<` del notebook en lugar de importarlas. Si se cambia una alli, hay que cambiarla
aqui. Las propias de la herramienta (tamano de ventana, paso y escala de dibujo) estan marcadas.

Uso
---
    cd analisis_arrow_stiv
    python video_velocidad.py
"""

import argparse
import csv
import json
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

import escritor_video

# ---------------------------------------------------------------------------------------
#  Rutas
# ---------------------------------------------------------------------------------------
DIR_DATOS = Path(r"C:\Users\Sergio\Desktop\datasets vision velocimetria\data\RiverArrow")
DIR_STAB = DIR_DATOS / "Stabilised"
VIDEOS = {
    "sin sembrar": DIR_STAB / "GoPro_Stable_trans_Unseeded" / "Video" / "Arrow_GoPro_Unseeded_Stabilised.avi",
    "sembrado":    DIR_STAB / "GoPro_stable_trans_seeded" / "Video" / "Arrow_GoPro_Seeded_Stabilised.avi",
}
ARCHIVO_VALIDACION = DIR_DATOS / "Reference" / "Validation_Data_Arrow_GoPro.xlsx"
DIR_SALIDA = Path("salidas")

# ---------------------------------------------------------------------------------------
#  >>> AJUSTABLE <<<  Geometria (duplicado del notebook, Parte 2)
# ---------------------------------------------------------------------------------------
ESCALA = 0.0174               # m/px, declarada por el Readme.txt del dataset
COBERTURA_MIN = 0.50          # fraccion minima de la linea dentro del fotograma
MARGEN_BORDE = 5              # px

# ---------------------------------------------------------------------------------------
#  >>> AJUSTABLE <<<  Muestreo de la STI (duplicado del notebook, Parte 3)
# ---------------------------------------------------------------------------------------
V_ESPERADA = 0.45             # m/s
LARGO_STI = 48                # muestras por linea
ANCHO_BANDA = 6               # px
PASO_BANDA = 3                # px

# ---------------------------------------------------------------------------------------
#  >>> AJUSTABLE <<<  Estimador y QC (duplicado del notebook, Partes 4 y 4b)
# ---------------------------------------------------------------------------------------
LADO_BLOQUE = 24
COH_MIN_BLOQUE = 0.45
SIGMA_DERIVADA = 1.2
COH_MIN_ESTACION = 0.70
CONTRASTE_MIN = 2.0

# ---------------------------------------------------------------------------------------
#  >>> AJUSTABLE <<<  Propias de esta herramienta (no existen en el notebook)
# ---------------------------------------------------------------------------------------
# Longitud de la ventana de medida, en fotogramas. 48 a 5 fps son 9.6 s, y dejan tres
# bloques de tensor en el eje del tiempo. Menos que eso y la mediana ponderada se queda sin
# nada sobre lo que hacer mediana: este video solo tiene 99 fotogramas en total.
VENTANA = 48
# Cada cuantos fotogramas se abre una ventana nueva.
PASO_VENTANA = 2
# Cota fisica de velocidad, como en la herramienta del Sile Main Canal: en ventanas cortas
# una onda estacionaria puede dar una estela coherente con pendiente absurda. Sale de la
# estimacion a priori, no de ninguna referencia.
V_MAX_FISICA = 3 * V_ESPERADA        # m/s
# Velocidad a la que satura la paleta de color.
V_COLOR_MAX = 0.8                    # m/s
# Aumento de cada panel. El fotograma original mide 464x505 px, que es ilegible con
# flechas y numeros encima.
ZOOM = 2
# Pixeles de flecha (ya en el panel ampliado) por cada m/s.
PX_POR_MS = 210
# ---------------------------------------------------------------------------------------

ALTO_CABECERA = 46
ALTO_PIE = 104
SEPARACION = 18


# ------------------------------------------------------------------------------ geometria
def leer_verticales(ruta):
    """Sistema de verticales de aforo del fichero de validacion: SOLO las coordenadas."""
    val = pd.read_excel(ruta, header=None)
    filas, seccion = [], None
    for _, r in val.iloc[11:].iterrows():
        etiqueta = str(r[0])
        if etiqueta.startswith("XS"):
            seccion = etiqueta
        elif seccion is not None and etiqueta.replace(".", "").isdigit():
            filas.append((seccion, float(r[0]), float(r[1])))
    v = pd.DataFrame(filas, columns=["seccion", "x", "y"])
    # La direccion del flujo de cada seccion es su normal, de los extremos.
    angulos = {}
    for sec in dict.fromkeys(v.seccion):
        p = v[v.seccion == sec][["x", "y"]].to_numpy()
        d = p[-1] - p[0]
        n = np.array([d[1], -d[0]]) / np.linalg.norm(d)
        angulos[sec] = float(np.degrees(np.arctan2(n[1], n[0])))
    v["angulo"] = v.seccion.map(angulos)
    return v, angulos


def geometria_lineas(verticales, ds, largo, offsets, ancho, alto, margen):
    """Coordenadas de muestreo de la banda de cada vertical, y su cobertura."""
    s = (np.arange(largo) - largo / 2) * ds
    salida = []
    for r in verticales.itertuples():
        ang = np.radians(r.angulo)
        ux, uy = np.cos(ang), np.sin(ang)
        px, py = -uy, ux
        X, Y = r.x + s * ux, r.y + s * uy
        dentro = ((X >= margen) & (X < ancho - margen)
                  & (Y >= margen) & (Y < alto - margen))
        salida.append(dict(
            mapx=np.array([X[dentro] + o * px for o in offsets], np.float32),
            mapy=np.array([Y[dentro] + o * py for o in offsets], np.float32),
            cobertura=float(dentro.mean()), ux=ux, uy=uy))
    return salida


# ------------------------------------------------------------------------------ STIV
def tensor_estructura(bloque, sigma=SIGMA_DERIVADA):
    """Pendiente m (muestras/fotograma) y coherencia C de un trozo de STI."""
    g = cv2.GaussianBlur(bloque, (0, 0), sigma)
    It = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)[2:-2, 2:-2]
    Ix = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)[2:-2, 2:-2]
    Jxx = float((Ix * Ix).sum())
    Jtt = float((It * It).sum())
    Jxt = float((Ix * It).sum())
    if Jxx + Jtt <= 0:
        return np.nan, 0.0
    _, vec = np.linalg.eigh(np.array([[Jxx, Jxt], [Jxt, Jtt]]))
    ex, et = vec[:, 0]
    if et < 0:
        ex, et = -ex, -et
    m = ex / et if et != 0 else np.nan
    return m, float(np.sqrt((Jxx - Jtt) ** 2 + 4 * Jxt ** 2) / (Jxx + Jtt))


def mediana_ponderada(valores, pesos):
    orden = np.argsort(valores)
    v, w = np.asarray(valores)[orden], np.asarray(pesos)[orden]
    return float(v[np.searchsorted(np.cumsum(w), 0.5 * w.sum())])


def medir_sti(sti_p, lado=LADO_BLOQUE, coh_min=COH_MIN_BLOQUE):
    nt, nx = sti_p.shape
    if nt < lado or nx < lado:
        return np.nan, 0.0
    paso = lado // 2
    ms, cs = [], []
    for t0 in range(0, nt - lado + 1, paso):
        for x0 in range(0, nx - lado + 1, paso):
            m, c = tensor_estructura(sti_p[t0:t0 + lado, x0:x0 + lado])
            if np.isfinite(m):
                ms.append(m); cs.append(c)
    if not ms:
        return np.nan, 0.0
    ms, cs = np.array(ms), np.array(cs)
    coh = float(np.median(cs))
    usables = cs >= coh_min
    if usables.sum() == 0:
        return np.nan, coh
    return mediana_ponderada(ms[usables], cs[usables]), coh


def preparar_sti(sti):
    a = sti - sti.mean(axis=0, keepdims=True)
    a = a - a.mean(axis=1, keepdims=True)
    d = a.std()
    return a / d if d > 0 else a


def mediana_por_ventana(v):
    """Mediana de cada ventana ignorando los NaN, sin quejarse de las filas enteras vacias.

    Una ventana sin ninguna vertical valida es el caso normal del video sin sembrar, no un
    error: `np.nanmedian` lo resolveria bien pero avisando, y ese aviso repetido 25 veces
    esconde los mensajes que si importan.
    """
    salida = np.full(v.shape[0], np.nan)
    hay = np.isfinite(v).any(axis=1)
    if hay.any():
        salida[hay] = np.nanmedian(v[hay], axis=1)
    return salida


# ------------------------------------------------------------------------------ dibujo
PALETA = cv2.applyColorMap(np.arange(256, dtype=np.uint8).reshape(-1, 1),
                           cv2.COLORMAP_TURBO).reshape(-1, 3)


def color_velocidad(v):
    if not np.isfinite(v):
        return (120, 120, 120)
    return tuple(int(x) for x in PALETA[int(np.clip(v / V_COLOR_MAX, 0, 1) * 255)])


def texto(img, s, org, escala=0.5, col=(255, 255, 255), grosor=1):
    """Texto con reborde negro: sobre el agua el blanco solo no se lee."""
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, escala, (0, 0, 0), grosor + 2,
                cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, escala, col, grosor, cv2.LINE_AA)


def cargar(ruta):
    cap = cv2.VideoCapture(str(ruta))
    fs = []
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        fs.append(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY).astype(np.float32))
    cap.release()
    return np.stack(fs)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salida", default=None, help="ruta del mp4 de salida")
    args = ap.parse_args()

    DIR_SALIDA.mkdir(exist_ok=True)
    salida = Path(args.salida) if args.salida else DIR_SALIDA / "velocidad_tiempo_real.mp4"

    cap = cv2.VideoCapture(str(VIDEOS["sin sembrar"]))
    fps = cap.get(cv2.CAP_PROP_FPS)
    ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    dt = 1.0 / fps

    ds = int(round(V_ESPERADA * dt / ESCALA))
    sigma_antialias = 0.5 * ds
    offsets = np.arange(-ANCHO_BANDA / 2, ANCHO_BANDA / 2 + 1e-9, PASO_BANDA)

    verticales, angulos = leer_verticales(ARCHIVO_VALIDACION)
    lineas = geometria_lineas(verticales, ds, LARGO_STI, offsets, ancho, alto, MARGEN_BORDE)
    verticales["cobertura"] = [l["cobertura"] for l in lineas]
    n_est = len(verticales)

    print(f"Videos : {ancho}x{alto}, {fps:.2f} fps")
    print(f"STIV   : DS = {ds} px, {n_est} verticales en {len(angulos)} secciones")
    print(f"Ventana: {VENTANA} fotogramas ({VENTANA/fps:.1f} s), paso {PASO_VENTANA}")

    # --- Pasada de medida: STI completa de cada video, y luego las ventanas -------------
    pilas, stis, contraste = {}, {}, {}
    for etq, ruta in VIDEOS.items():
        t0 = time.perf_counter()
        pilas[etq] = cargar(ruta)
        suaves = [cv2.GaussianBlur(f, (0, 0), sigma_antialias) for f in pilas[etq]]
        banda_por_est, con = [], []
        for l in lineas:
            banda = np.stack([
                np.stack([cv2.remap(f, l["mapx"][b:b + 1], l["mapy"][b:b + 1],
                                    cv2.INTER_LINEAR)[0] for f in suaves])
                for b in range(l["mapx"].shape[0])
            ])                                    # (banda, t, muestras)
            banda_por_est.append(banda)
            con.append(float(banda.mean(axis=0).std(axis=0).mean()))
        stis[etq] = banda_por_est
        contraste[etq] = np.array(con)
        print(f"  [{etq:11s}] {len(pilas[etq])} fotogramas leidos en "
              f"{time.perf_counter()-t0:.1f} s, contraste mediano "
              f"{np.median(contraste[etq]):.2f}")

    n = min(len(p) for p in pilas.values())
    centros = list(range(VENTANA // 2, n - VENTANA // 2, PASO_VENTANA))
    if not centros:
        raise SystemExit("Los videos son mas cortos que la ventana de medida.")
    n_v = len(centros)

    V, COH = {}, {}
    n_cota = {}
    for etq in VIDEOS:
        v = np.full((n_v, n_est), np.nan)
        c = np.zeros((n_v, n_est))
        cota = 0
        t0 = time.perf_counter()
        for w, kc in enumerate(centros):
            k0 = kc - VENTANA // 2
            for i in range(n_est):
                if verticales.cobertura[i] < COBERTURA_MIN or contraste[etq][i] < CONTRASTE_MIN:
                    continue
                banda = stis[etq][i][:, k0:k0 + VENTANA, :]
                sp = np.mean([preparar_sti(banda[b]) for b in range(banda.shape[0])], axis=0)
                m, ci = medir_sti(sp)
                c[w, i] = ci
                if not np.isfinite(m) or ci < COH_MIN_ESTACION:
                    continue
                vel = abs(m) * ds * ESCALA / dt
                if vel > V_MAX_FISICA:
                    cota += 1
                    continue
                v[w, i] = vel
        V[etq], COH[etq], n_cota[etq] = v, c, cota
        print(f"  [{etq:11s}] {n_v} ventanas en {time.perf_counter()-t0:.1f} s   "
              f"aceptadas {np.isfinite(v).sum()}/{n_v*n_est}   "
              f"descartes por cota fisica {cota}")

    for etq in VIDEOS:
        med = mediana_por_ventana(V[etq])
        if np.isfinite(med).any():
            print(f"\n  [{etq}] mediana de la seccion: {np.nanmedian(med):.4f} m/s   "
                  f"q05-q95 {np.nanquantile(med, 0.05):.4f}-{np.nanquantile(med, 0.95):.4f}")
        else:
            print(f"\n  [{etq}] ninguna ventana con medida valida en ninguna vertical")

    # --- Render: un fotograma de salida por fotograma de entrada, a los fps originales ---
    pw, ph = ancho * ZOOM, alto * ZOOM
    cw = 2 * pw + SEPARACION
    ch = ALTO_CABECERA + ph + ALTO_PIE
    vw = escritor_video.abrir(str(salida), fps, (cw, ch))

    t0 = time.perf_counter()
    for k in range(n):
        w = int(np.clip(round((k - centros[0]) / PASO_VENTANA), 0, n_v - 1))
        lienzo = np.zeros((ch, cw, 3), np.uint8)

        for j, etq in enumerate(VIDEOS):
            gris = pilas[etq][k].astype(np.uint8)
            panel = cv2.cvtColor(cv2.resize(gris, (pw, ph), interpolation=cv2.INTER_LINEAR),
                                 cv2.COLOR_GRAY2BGR)

            # Las cinco secciones de aforo, tenues.
            for sec in angulos:
                p = verticales[verticales.seccion == sec][["x", "y"]].to_numpy() * ZOOM
                cv2.polylines(panel, [p.astype(np.int32)], False, (70, 70, 200), 1, cv2.LINE_AA)

            for i, l in enumerate(lineas):
                x, y = verticales.x[i] * ZOOM, verticales.y[i] * ZOOM
                v = V[etq][w, i]
                col = color_velocidad(v)
                # La linea de busqueda entera, tenue.
                mx, my = l["mapx"][l["mapx"].shape[0] // 2], l["mapy"][l["mapy"].shape[0] // 2]
                if len(mx) > 1:
                    cv2.line(panel, (int(mx[0] * ZOOM), int(my[0] * ZOOM)),
                             (int(mx[-1] * ZOOM), int(my[-1] * ZOOM)),
                             col if np.isfinite(v) else (85, 85, 85), 1, cv2.LINE_AA)
                if np.isfinite(v):
                    lx = int(v * PX_POR_MS * l["ux"])
                    ly = int(v * PX_POR_MS * l["uy"])
                    cv2.arrowedLine(panel, (int(x), int(y)), (int(x + lx), int(y + ly)),
                                    col, 2, cv2.LINE_AA, tipLength=0.25)
                    cv2.circle(panel, (int(x), int(y)), 4, (255, 255, 255), -1, cv2.LINE_AA)
                    cv2.circle(panel, (int(x), int(y)), 4, (0, 0, 0), 1, cv2.LINE_AA)
                else:
                    cv2.drawMarker(panel, (int(x), int(y)), (60, 60, 220),
                                   cv2.MARKER_SQUARE, 8, 2)

            n_ok = int(np.isfinite(V[etq][w]).sum())
            texto(panel, etq.upper(), (14, 30), 0.85, (255, 255, 255), 2)
            texto(panel, f"{n_ok} de {n_est} verticales medidas",
                  (14, 58), 0.6, (120, 220, 255) if n_ok else (110, 110, 255), 2)
            if n_ok == 0:
                texto(panel, "sin senal: ninguna supera el control de calidad",
                      (14, 84), 0.55, (110, 110, 255), 1)
            else:
                med = np.nanmedian(V[etq][w])
                texto(panel, f"v mediana = {med:.3f} m/s", (14, 84), 0.6, (150, 255, 150), 2)

            x0 = j * (pw + SEPARACION)
            lienzo[ALTO_CABECERA:ALTO_CABECERA + ph, x0:x0 + pw] = panel

        texto(lienzo, "River Arrow - el mismo STIV sobre los dos videos del experimento de "
                      "sembrado", (16, 32), 0.78, (255, 255, 255), 2)
        texto(lienzo, f"ventana {VENTANA/fps:.1f} s   escala {ESCALA*1000:.1f} mm/px   "
                      f"coherencia min {COH_MIN_ESTACION}   contraste min {CONTRASTE_MIN}",
              (cw - 700, 32), 0.55, (170, 170, 170), 1)

        bx, by, bw_, bh_ = cw - 400, ch - 34, 260, 14
        for jj in range(bw_):
            c_ = PALETA[int(255 * jj / (bw_ - 1))]
            cv2.line(lienzo, (bx + jj, by), (bx + jj, by + bh_), tuple(int(x) for x in c_), 1)
        cv2.rectangle(lienzo, (bx, by), (bx + bw_, by + bh_), (90, 90, 90), 1)
        texto(lienzo, "0", (bx - 14, by + 12), 0.45, (170, 170, 170), 1)
        texto(lienzo, f"{V_COLOR_MAX:.1f} m/s", (bx + bw_ + 8, by + 12), 0.45,
              (170, 170, 170), 1)

        y_pie = ALTO_CABECERA + ph
        texto(lienzo, f"t = {k/fps:5.2f} s", (16, y_pie + 34), 0.72, (255, 255, 255), 2)
        texto(lienzo, "misma configuracion, mismo encuadre, misma escala: lo unico que "
                      "cambia entre los dos paneles es el sembrado",
              (16, y_pie + 64), 0.5, (200, 200, 200), 1)
        texto(lienzo, "circulo = vertical medida   cuadro rojo = rechazada por coherencia, "
                      "contraste o cobertura; no se rellenan",
              (16, y_pie + 88), 0.48, (150, 150, 150), 1)
        vw.write(lienzo)

    vw.release()
    print(f"\n  render en {time.perf_counter()-t0:.1f} s")
    print(f"Listo: {salida} ({salida.stat().st_size/1e6:.1f} MB, {n/fps:.1f} s, {cw}x{ch})")

    # --- Series por ventana --------------------------------------------------------------
    csv_out = DIR_SALIDA / "velocidad_ventanas.csv"
    with open(csv_out, "w", newline="", encoding="utf-8") as f:
        esc = csv.writer(f)
        esc.writerow(["video", "ventana", "frame_centro", "t_s", "v_mediana_ms",
                      "n_verticales"] + [f"v_{r.seccion}_{i}" for i, r in
                                         enumerate(verticales.itertuples())])
        for etq in VIDEOS:
            med = mediana_por_ventana(V[etq])
            for w, kc in enumerate(centros):
                esc.writerow([etq, w, kc, round(kc / fps, 3),
                              "" if not np.isfinite(med[w]) else round(float(med[w]), 4),
                              int(np.isfinite(V[etq][w]).sum())]
                             + ["" if not np.isfinite(V[etq][w, i]) else
                                round(float(V[etq][w, i]), 4) for i in range(n_est)])
    print(f"Series por ventana: {csv_out}")

    cfg = DIR_SALIDA / "config_video_velocidad.json"
    cfg.write_text(json.dumps(dict(
        videos={k: str(v) for k, v in VIDEOS.items()}, n_frames=n, fps=round(fps, 4),
        escala_m_px=ESCALA, n_estaciones=n_est,
        angulos_seccion_grados={k: round(v, 3) for k, v in angulos.items()},
        v_esperada_ms=V_ESPERADA, ds_px=ds, largo_sti=LARGO_STI,
        ancho_banda_px=ANCHO_BANDA, paso_banda_px=PASO_BANDA,
        cobertura_min=COBERTURA_MIN, lado_bloque=LADO_BLOQUE,
        coh_min_bloque=COH_MIN_BLOQUE, sigma_derivada=SIGMA_DERIVADA,
        coh_min_estacion=COH_MIN_ESTACION, contraste_min=CONTRASTE_MIN,
        ventana=VENTANA, paso_ventana=PASO_VENTANA, v_max_fisica_ms=V_MAX_FISICA,
        n_ventanas=n_v,
        aceptadas={k: int(np.isfinite(V[k]).sum()) for k in VIDEOS},
        v_mediana_global_ms={
            k: (None if not np.isfinite(mediana_por_ventana(V[k])).any()
                else round(float(np.nanmedian(mediana_por_ventana(V[k]))), 6))
            for k in VIDEOS},
        descartes_cota_fisica=n_cota,
    ), indent=2), encoding="utf-8")
    print(f"Configuracion:      {cfg}")


if __name__ == "__main__":
    main()
