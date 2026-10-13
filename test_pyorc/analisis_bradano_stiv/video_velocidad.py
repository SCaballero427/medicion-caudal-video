"""STIV en ventana movil sobre el video completo del rio Bradano, y video de resultados.

Que hace
--------
Repite exactamente el STIV del notebook `Bradano_STIV_pipeline.ipynb`, pero en lugar de medir
una sola vez sobre los 600 fotogramas lo hace en **ventanas deslizantes**, y renderiza un video
en tiempo real con las lineas de busqueda, una flecha por estacion y su valor en m/s.

Sirve para dos cosas. La primera es ver si la medida del notebook es una casualidad de esa
ventana concreta: si la mediana de la seccion se mantiene a lo largo de los 25 s, la ventana no
era afortunada. La segunda es mirar el rio moverse con los numeros encima, que es la unica forma
de darse cuenta de ciertas cosas -- por ejemplo, que la mitad derecha del cauce esta practicamente
parada, o que las particulas trazadoras llegan a rachas.

Por que un solo panel
---------------------
El video del Bradano viene **ya ortorrectificado** del dataset: la vista es cenital y el fotograma
*es* el plano del agua. No hay nada que rectificar, asi que no hay un segundo panel que ensenar,
igual que en el caso del Sile Main Canal. En Boneyard Creek y en Hommerich si hay dos paneles,
porque alli la rectificacion es una afirmacion que hay que poder comprobar a ojo.

El realce de contraste no es cosmetico
--------------------------------------
El agua del Bradano sale con un brillo medio de 0.12 sobre 255. Sin estirar el contraste, el video
es un rectangulo negro con unas flechas encima y no se ve ni una particula trazadora, que es
justamente lo que hay que poder ver para creerse la medida. El estirado usa percentiles **fijos**,
calculados una vez sobre el primer fotograma: si se recalcularan por fotograma, el fondo
parpadearia y las particulas cambiarian de brillo sin que el agua hiciera nada.

Duplica las constantes del notebook
-----------------------------------
Igual que las herramientas equivalentes de los casos del Sile Main Canal y de Boneyard Creek,
este script **repite** las constantes `>>> AJUSTABLE <<<` del notebook en lugar de importarlas.
Si se cambia una alli, hay que cambiarla aqui. Las que son propias de la herramienta (el tamano
de la ventana, su paso y la cota fisica de velocidad) estan marcadas como tales.

Uso
---
    cd analisis_bradano_stiv
    python video_velocidad.py                    # todo el video
    python video_velocidad.py --fin 300          # solo los primeros 300 fotogramas
"""

import argparse
import csv
import json
import time
from pathlib import Path

import cv2
import numpy as np

import escritor_video

# ---------------------------------------------------------------------------------------
#  Rutas
# ---------------------------------------------------------------------------------------
DIR_DATOS = Path(r"C:\Users\Sergio\Desktop\datasets vision velocimetria\data\RiverBradano")
ARCHIVO_VIDEO = DIR_DATOS / "Stabilised" / "Video" / "RiverBradano_24_fps_Stabilised.avi"
DIR_SALIDA = Path("salidas")

# ---------------------------------------------------------------------------------------
#  >>> AJUSTABLE <<<  Geometria (duplicado del notebook, Parte 2)
# ---------------------------------------------------------------------------------------
ESCALA = 0.009                # m/px, declarada por el Readme.txt del dataset
FILA_SECCION = 706            # fila de la seccion de aforo
COLUMNA_AGUA_IZQ = 383        # orilla izquierda en esa fila
COLUMNA_AGUA_DER = 1353       # orilla derecha
COLUMNA_ESTACION_0 = 456      # primera estacion (primera vertical de validacion)
PASO_ESTACION_PX = 111        # 1 m a la escala del dataset
N_ESTACIONES = 9
ANGULO_FLUJO = -90.0          # grados desde +x; el rio va hacia arriba en la imagen

# ---------------------------------------------------------------------------------------
#  >>> AJUSTABLE <<<  Muestreo de la STI (duplicado del notebook, Parte 3)
# ---------------------------------------------------------------------------------------
V_ESPERADA = 0.9              # m/s, estimacion a priori de la que sale DS
LARGO_STI = 128               # muestras por linea
ANCHO_BANDA = 24              # px; sin banda el trazador disperso del Bradano no da estelas
PASO_BANDA = 4                # px entre lineas paralelas de la banda

# ---------------------------------------------------------------------------------------
#  >>> AJUSTABLE <<<  Estimador y control de calidad (duplicado del notebook, Partes 4 y 4b)
# ---------------------------------------------------------------------------------------
LADO_BLOQUE = 64
COH_MIN_BLOQUE = 0.50
SIGMA_DERIVADA = 1.5
COH_MIN_ESTACION = 0.70
BRILLO_MAX_AGUA = 5.0

# ---------------------------------------------------------------------------------------
#  >>> AJUSTABLE <<<  Propias de esta herramienta (no existen en el notebook)
# ---------------------------------------------------------------------------------------
# Longitud de la ventana de medida, en fotogramas. 150 a 24 fps son 6.25 s. Mas corta
# responde antes a los cambios y tiene menos estelas de las que fiarse; el notebook usa los
# 600 de golpe, que es el otro extremo.
VENTANA = 150
# Cada cuantos fotogramas se abre una ventana nueva. 5 da 91 ventanas sobre el video.
PASO_VENTANA = 5
# Cota fisica de velocidad, como en la herramienta del Sile Main Canal. Midiendo en ventanas
# cortas en vez de en una larga, una onda estacionaria puede dar una estela perfectamente
# coherente con una pendiente absurda, y la coherencia no puede distinguirla de un trazador.
# El limite sale de la estimacion a priori, no de ninguna referencia.
V_MAX_FISICA = 3 * V_ESPERADA        # m/s
# Velocidad a la que satura la paleta de color de las flechas.
V_COLOR_MAX = 1.5                    # m/s
# Pixeles de flecha por cada m/s. Solo afecta al dibujo.
PX_POR_MS = 190
# Filas de la imagen que entran en el panel. El resto es orilla y no aporta nada.
FILA_PANEL_0, FILA_PANEL_1 = 380, 1010
# Percentiles del realce de contraste, fijos para todo el video.
PCT_REALCE = (1.0, 99.5)
# ---------------------------------------------------------------------------------------

ALTO_CABECERA = 44
ALTO_PIE = 96


# ------------------------------------------------------------------------------ STIV
def mapa_banda(columnas, fila, angulo_deg, ds, largo, offsets):
    """Coordenadas de muestreo de todas las lineas de todas las estaciones.

    Devuelve mapx, mapy de forma (n_estaciones * n_banda, largo): un solo `cv2.remap` por
    fotograma resuelve la banda entera.
    """
    ang = np.radians(angulo_deg)
    ux, uy = np.cos(ang), np.sin(ang)        # a lo largo de la linea (direccion del flujo)
    px, py = -uy, ux                         # perpendicular (a traves de la seccion)
    s = (np.arange(largo) - largo / 2) * ds

    mx, my = [], []
    for c in columnas:
        for off in offsets:
            mx.append(c + off * px + s * ux)
            my.append(fila + off * py + s * uy)
    return np.array(mx, np.float32), np.array(my, np.float32)


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
    """Pendiente robusta de una STI completa, por bloques con solape."""
    nt, nx = sti_p.shape
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
    """Quita el fondo estatico y el parpadeo global, y normaliza."""
    a = sti - sti.mean(axis=0, keepdims=True)
    a = a - a.mean(axis=1, keepdims=True)
    d = a.std()
    return a / d if d > 0 else a


# ------------------------------------------------------------------------------ dibujo
PALETA = cv2.applyColorMap(np.arange(256, dtype=np.uint8).reshape(-1, 1),
                           cv2.COLORMAP_TURBO).reshape(-1, 3)


def color_velocidad(v):
    """Color BGR de una velocidad. Gris si no hay medida."""
    if not np.isfinite(v):
        return (120, 120, 120)
    return tuple(int(x) for x in PALETA[int(np.clip(v / V_COLOR_MAX, 0, 1) * 255)])


def texto(img, s, org, escala=0.5, col=(255, 255, 255), grosor=1):
    """Texto con reborde negro: sobre el agua el blanco solo no se lee."""
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, escala, (0, 0, 0), grosor + 2,
                cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, escala, col, grosor, cv2.LINE_AA)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fin", type=int, default=None,
                    help="ultimo fotograma a procesar (indice, inclusive)")
    ap.add_argument("--salida", default=None, help="ruta del mp4 de salida")
    args = ap.parse_args()

    DIR_SALIDA.mkdir(exist_ok=True)
    salida = Path(args.salida) if args.salida else DIR_SALIDA / "velocidad_tiempo_real.mp4"

    cap = cv2.VideoCapture(str(ARCHIVO_VIDEO))
    if not cap.isOpened():
        raise SystemExit(f"No se pudo abrir {ARCHIVO_VIDEO}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    cap.release()

    n = n_total if args.fin is None else min(args.fin + 1, n_total)
    dt = 1.0 / fps
    ds = int(round(V_ESPERADA * dt / ESCALA))
    sigma_antialias = 0.5 * ds
    offsets = np.arange(-ANCHO_BANDA / 2, ANCHO_BANDA / 2 + 1e-9, PASO_BANDA)
    n_banda = len(offsets)
    columnas = COLUMNA_ESTACION_0 + PASO_ESTACION_PX * np.arange(N_ESTACIONES)
    s_estaciones = (columnas - COLUMNA_AGUA_IZQ) * ESCALA

    print(f"Video : {ARCHIVO_VIDEO.name}  {ancho}x{int(FILA_PANEL_1-FILA_PANEL_0)} util, "
          f"{fps:.2f} fps, {n} fotogramas ({n/fps:.1f} s)")
    print(f"STIV  : DS = {ds} px, banda de {n_banda} lineas, {N_ESTACIONES} estaciones")
    print(f"Ventana: {VENTANA} fotogramas ({VENTANA/fps:.2f} s), paso {PASO_VENTANA}")

    mapx, mapy = mapa_banda(columnas, FILA_SECCION, ANGULO_FLUJO, ds, LARGO_STI, offsets)

    # --- Pasada 1: construir la STI del video entero, una sola vez ----------------------
    # Las ventanas se recortan luego de esta STI. Volver a leer el video por ventana
    # costaria 91 pasadas para no obtener nada nuevo.
    t0 = time.perf_counter()
    cap = cv2.VideoCapture(str(ARCHIVO_VIDEO))
    filas = []
    for k in range(n):
        ok, fr = cap.read()
        if not ok:
            break
        gris = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        suave = cv2.GaussianBlur(gris, (0, 0), sigma_antialias)
        filas.append(cv2.remap(suave, mapx, mapy, cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_REPLICATE))
        if (k + 1) % 200 == 0:
            print(f"  STI {k+1}/{n}")
    cap.release()
    n = len(filas)
    sti = np.stack(filas).reshape(n, N_ESTACIONES, n_banda, LARGO_STI)
    print(f"  STI construida en {time.perf_counter()-t0:.1f} s  ({sti.nbytes/1e6:.0f} MB)")

    # El brillo por estacion decide que estaciones miran al agua. Se calcula sobre todo el
    # video, no por ventana: que una estacion este sobre grava no cambia con el tiempo.
    brillo = sti.mean(axis=(0, 2, 3))
    sobre_agua = brillo <= BRILLO_MAX_AGUA
    print(f"  estaciones sobre agua: {int(sobre_agua.sum())}/{N_ESTACIONES} "
          f"(brillo {np.round(brillo, 2).tolist()})")

    # --- Medida por ventanas ------------------------------------------------------------
    centros = list(range(VENTANA // 2, n - VENTANA // 2, PASO_VENTANA))
    if not centros:
        raise SystemExit("El video es mas corto que la ventana de medida.")
    n_v = len(centros)
    V = np.full((n_v, N_ESTACIONES), np.nan)
    COH = np.zeros((n_v, N_ESTACIONES))
    n_cota = 0

    t0 = time.perf_counter()
    for w, kc in enumerate(centros):
        k0 = kc - VENTANA // 2
        bloque = sti[k0:k0 + VENTANA]
        for i in range(N_ESTACIONES):
            if not sobre_agua[i]:
                continue
            sp = np.mean([preparar_sti(bloque[:, i, b, :]) for b in range(n_banda)], axis=0)
            m, c = medir_sti(sp)
            COH[w, i] = c
            if not np.isfinite(m) or c < COH_MIN_ESTACION:
                continue
            v = abs(m) * ds * ESCALA / dt
            if v > V_MAX_FISICA:
                n_cota += 1
                continue
            V[w, i] = v
        if (w + 1) % 20 == 0:
            print(f"  ventana {w+1}/{n_v}")
    print(f"  {n_v} ventanas medidas en {time.perf_counter()-t0:.1f} s")

    v_mediana = np.nanmedian(V, axis=1)
    aceptadas = np.isfinite(V).sum(axis=1)
    tot_posibles = n_v * int(sobre_agua.sum())
    print(f"\n  descartes por la cota fisica de {V_MAX_FISICA:.2f} m/s: "
          f"{n_cota} de {tot_posibles} estacion-ventana")
    print(f"  mediana de la seccion: {np.nanmedian(v_mediana):.4f} m/s   "
          f"q05-q95 {np.nanquantile(v_mediana, 0.05):.4f}-{np.nanquantile(v_mediana, 0.95):.4f}")
    print("  aceptacion por estacion:")
    for i in range(N_ESTACIONES):
        motivo = "" if sobre_agua[i] else "  (orilla: no se mide)"
        print(f"    est {i} (x={columnas[i]}, s={s_estaciones[i]:.2f} m): "
              f"{np.isfinite(V[:, i]).sum():3d}/{n_v} ventanas{motivo}")

    # --- Pasada 2: render ---------------------------------------------------------------
    # Un fotograma de salida por fotograma de entrada, a los fps originales: el video se ve
    # a la velocidad real del agua. Cada uno toma la medida de la ventana cuyo centro le
    # queda mas cerca.
    ph = FILA_PANEL_1 - FILA_PANEL_0
    cw, ch = ancho, ALTO_CABECERA + ph + ALTO_PIE
    vw = escritor_video.abrir(str(salida), fps, (cw, ch))

    ang = np.radians(ANGULO_FLUJO)
    ux, uy = np.cos(ang), np.sin(ang)
    dxl, dyl = 0.5 * LARGO_STI * ds * ux, 0.5 * LARGO_STI * ds * uy

    cap = cv2.VideoCapture(str(ARCHIVO_VIDEO))
    lo = hi = None
    t0 = time.perf_counter()
    for k in range(n):
        ok, fr = cap.read()
        if not ok:
            break
        gris = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)[FILA_PANEL_0:FILA_PANEL_1]
        if lo is None:
            # Percentiles fijos, calculados una sola vez: recalcularlos por fotograma haria
            # parpadear el fondo y cambiar el brillo de las particulas sin motivo.
            lo, hi = np.percentile(gris, PCT_REALCE)
        realce = np.clip((gris.astype(np.float32) - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)
        panel = cv2.cvtColor(realce, cv2.COLOR_GRAY2BGR)

        w = int(np.clip(round((k - centros[0]) / PASO_VENTANA), 0, n_v - 1))
        yf = FILA_SECCION - FILA_PANEL_0

        # Las lineas de agua, para situar el cauce.
        for c in (COLUMNA_AGUA_IZQ, COLUMNA_AGUA_DER):
            cv2.line(panel, (c, 0), (c, ph - 1), (60, 200, 60), 1, cv2.LINE_AA)

        for i, c in enumerate(columnas):
            v = V[w, i]
            col = color_velocidad(v)
            # La linea de busqueda entera, tenue: la flecha sale de aqui.
            cv2.line(panel, (int(c - dxl), int(yf - dyl)), (int(c + dxl), int(yf + dyl)),
                     col if np.isfinite(v) else (90, 90, 90), 1, cv2.LINE_AA)
            if np.isfinite(v):
                lx, ly = int(v * PX_POR_MS * ux), int(v * PX_POR_MS * uy)
                cv2.arrowedLine(panel, (int(c), yf), (int(c + lx), int(yf + ly)),
                                col, 3, cv2.LINE_AA, tipLength=0.18)
                cv2.circle(panel, (int(c), yf), 5, (255, 255, 255), -1, cv2.LINE_AA)
                cv2.circle(panel, (int(c), yf), 5, (0, 0, 0), 1, cv2.LINE_AA)
                texto(panel, f"{v:.2f}", (int(c) + 8, yf + 26), 0.55, (255, 255, 255), 1)
            else:
                cv2.drawMarker(panel, (int(c), yf), (60, 60, 220), cv2.MARKER_SQUARE, 11, 2)
            texto(panel, f"{i}", (int(c) - 6, yf + 60), 0.5, (230, 230, 230), 1)

        lienzo = np.zeros((ch, cw, 3), np.uint8)
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ph] = panel

        texto(lienzo, "Rio Bradano - STIV en ventana movil sobre el video completo",
              (16, 30), 0.72, (255, 255, 255), 2)
        texto(lienzo, f"ventana {VENTANA/fps:.2f} s   escala {ESCALA*1000:.1f} mm/px   "
                      f"banda {ANCHO_BANDA} px   contraste realzado",
              (cw - 640, 30), 0.55, (170, 170, 170), 1)

        # Barra de color: sin ella los colores de las flechas no significan nada.
        bx, by, bw_, bh_ = cw - 400, ch - 34, 260, 14
        for j in range(bw_):
            c_ = PALETA[int(255 * j / (bw_ - 1))]
            cv2.line(lienzo, (bx + j, by), (bx + j, by + bh_), tuple(int(x) for x in c_), 1)
        cv2.rectangle(lienzo, (bx, by), (bx + bw_, by + bh_), (90, 90, 90), 1)
        texto(lienzo, "0", (bx - 14, by + 12), 0.45, (170, 170, 170), 1)
        texto(lienzo, f"{V_COLOR_MAX:.1f} m/s", (bx + bw_ + 8, by + 12), 0.45, (170, 170, 170), 1)

        y_pie = ALTO_CABECERA + ph
        vm = v_mediana[w]
        texto(lienzo, f"t = {k/fps:5.2f} s", (16, y_pie + 32), 0.7, (255, 255, 255), 2)
        texto(lienzo, f"v superficial mediana = {vm:.3f} m/s" if np.isfinite(vm)
              else "v superficial mediana = --", (210, y_pie + 32), 0.7, (120, 220, 255), 2)
        texto(lienzo, f"estaciones medidas = {aceptadas[w]}/{int(sobre_agua.sum())}",
              (700, y_pie + 32), 0.7, (150, 255, 150), 2)
        texto(lienzo, "circulo = estacion medida   cuadro rojo = rechazada (coherencia baja "
                      "o cota fisica); las rechazadas no se rellenan",
              (16, y_pie + 62), 0.48, (170, 170, 170), 1)
        texto(lienzo, "la direccion de las flechas no se mide: es el ANGULO_FLUJO que STIV "
                      "recibe como configuracion. El sentido si sale del tensor",
              (16, y_pie + 84), 0.48, (140, 140, 140), 1)
        vw.write(lienzo)
        if (k + 1) % 100 == 0:
            print(f"  render {k+1}/{n}")

    vw.release()
    cap.release()
    print(f"  render en {time.perf_counter()-t0:.1f} s")
    print(f"\nListo: {salida} ({salida.stat().st_size/1e6:.1f} MB, {n/fps:.1f} s)")

    # --- Series por ventana, para rehacer cualquier grafica sin volver a medir -----------
    csv_out = DIR_SALIDA / "velocidad_ventanas.csv"
    with open(csv_out, "w", newline="", encoding="utf-8") as f:
        esc = csv.writer(f)
        esc.writerow(["ventana", "frame_centro", "t_s", "v_mediana_ms", "n_estaciones"]
                     + [f"v_est{i}" for i in range(N_ESTACIONES)])
        for w, kc in enumerate(centros):
            esc.writerow([w, kc, round(kc / fps, 3),
                          "" if not np.isfinite(v_mediana[w]) else round(float(v_mediana[w]), 4),
                          int(aceptadas[w])]
                         + ["" if not np.isfinite(V[w, i]) else round(float(V[w, i]), 4)
                            for i in range(N_ESTACIONES)])
    print(f"Series por ventana: {csv_out}")

    cfg = DIR_SALIDA / "config_video_velocidad.json"
    cfg.write_text(json.dumps(dict(
        video=str(ARCHIVO_VIDEO), n_frames=n, fps=round(fps, 4), escala_m_px=ESCALA,
        fila_seccion=FILA_SECCION, columnas=columnas.tolist(),
        angulo_flujo_grados=ANGULO_FLUJO, v_esperada_ms=V_ESPERADA, ds_px=ds,
        largo_sti=LARGO_STI, ancho_banda_px=ANCHO_BANDA, paso_banda_px=PASO_BANDA,
        lado_bloque=LADO_BLOQUE, coh_min_bloque=COH_MIN_BLOQUE,
        sigma_derivada=SIGMA_DERIVADA, coh_min_estacion=COH_MIN_ESTACION,
        brillo_max_agua=BRILLO_MAX_AGUA, ventana=VENTANA, paso_ventana=PASO_VENTANA,
        v_max_fisica_ms=V_MAX_FISICA, n_ventanas=n_v,
        v_mediana_global_ms=round(float(np.nanmedian(v_mediana)), 6),
        q05=round(float(np.nanquantile(v_mediana, 0.05)), 6),
        q95=round(float(np.nanquantile(v_mediana, 0.95)), 6),
        descartes_cota_fisica=n_cota,
    ), indent=2), encoding="utf-8")
    print(f"Configuracion:      {cfg}")


if __name__ == "__main__":
    main()
