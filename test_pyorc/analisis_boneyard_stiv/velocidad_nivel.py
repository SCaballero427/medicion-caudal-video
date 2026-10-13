"""Velocidad por STIV + nivel leido en la mira, sobre el video entero y en tiempo real.

Que a\u00f1ade sobre `stiv_interactivo.py`
-----------------------------------
Es el mismo STIV, con la misma geometria puesta a mano (lee
`salidas/config_stiv_manual.json`), pero con dos cosas nuevas y una salida propia,
`salidas/velocidad_nivel.mp4`, para no tocar el video anterior:

1. **Continuidad temporal de las estaciones.** Cuando una estacion se cae en una
   ventana, se mantiene su ultimo valor valido durante como mucho `HOLD_VENTANAS`
   ventanas y se dibuja con OTRO simbolo (anillo hueco en vez de circulo lleno),
   de modo que el video no parpadea pero tampoco disimula: se ve cuando el numero
   es de ahora y cuando es el ultimo bueno. Pasado ese plazo la estacion se
   declara caida. Medido sobre el video: el 66 % de los huecos duran 5 ventanas o
   menos, y el mayor dura 65 -- ese sigue viendose como caida, que es lo honesto.

2. **Nivel de agua leido en la mira limnimetrica** del muro derecho. Se muestrea
   una linea a lo largo de la chapa y se localiza en cada fotograma el corte con
   el agua. El origen de la medida es la propia mira, no una fila de la imagen:
   se reporta el recorrido a lo largo de la chapa desde su extremo superior, asi
   que un movimiento de la camara no se confundiria con un cambio de nivel.

Sobre las estaciones de muro
----------------------------
Las estaciones 0 y 10 miran al hormigon, no al agua: dan 0,00 m/s con coherencia
alta (0,76 la 10), porque una estructura estatica es una estela de pendiente cero
perfectamente coherente. El criterio de coherencia las aprueba en vez de
rechazarlas -- es la leccion del caso, no un fallo del tensor. Aqui se siguen
dibujando con su 0,00, pero **marcadas como MURO y fuera de los dos agregados**:
no entran en la mediana de la seccion (que pasa de 0,860 a 0,914 m/s) ni en el
rango de la barra de color (que si no arranca en 0,00 y aplasta toda la paleta,
porque el agua real va de 0,63 a 0,98). No afectan a nada mas: cada estacion tiene
su propia STI y su propio tensor, asi que las de agua salen igual esten o no.

Unidades del nivel
------------------
Pixeles a lo largo de la chapa y variacion respecto a la mediana del video. El
release del USGS da un unico `GH` por video (14.45 ft sobre el datum local para
este), interpolado al instante del video, no una serie: sirve de rotulo, no de
escala. Y la rectificacion es del plano del agua, horizontal, asi que no aporta
escala vertical. Se intento sacar el paso de las graduaciones de la chapa por FFT
para poder dar pies: no es fiable, las marcas caen a ~6 px y la perspectiva las
comprime de forma desigual a lo largo de la chapa.

Uso
---
    python velocidad_nivel.py                    # video entero
    python velocidad_nivel.py --frames 200       # prueba corta
"""
import argparse
import csv
import json
import os
import sys
import time

import cv2
import numpy as np

# Se reutiliza la maquinaria del programa interactivo en vez de copiarla: el tensor,
# la homografia y el muestreo son EXACTAMENTE los mismos, y asi no hay dos versiones
# del STIV que puedan separarse.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import escritor_video as ev
import stiv_interactivo as si

DIR_CASO = si.DIR_CASO
RUTA_CONFIG = si.RUTA_CONFIG
RUTA_SALIDA = os.path.join(DIR_CASO, "salidas", "velocidad_nivel.mp4")
# Tabla del release, para el rotulo de GH. Fuera del workspace, ruta absoluta.
RUTA_REGISTROS = r"C:\Users\Sergio\Desktop\Boneyardcreek\boneyardcreek_video_records (2).csv"

# ===========================================================================================
#  >>> AJUSTABLE <<<  Continuidad temporal de las estaciones
# ===========================================================================================
# Ventanas que como mucho se mantiene el ultimo valor valido de una estacion caida.
# 5 ventanas son 15 fotogramas, 0.6 s: cubre el 66 % de los huecos medidos y nunca
# ense\u00f1a un numero de mas de medio segundo de antiguedad.
HOLD_VENTANAS = 5

# Una estacion se declara MURO si su mediana en todo el video no llega a esta fraccion
# de la mediana de la seccion. Es una decision de video entero, no de ventana, para que
# no pueda parpadear. El hueco medido es limpio: los muros dan 0.00 y la estacion de
# agua mas lenta 0.59 m/s, asi que cualquier umbral entre 0.05 y 0.5 da lo mismo.
FRAC_MURO = 0.15

# ===========================================================================================
#  >>> AJUSTABLE <<<  Muestreo del tensor. Sobrescribe lo que traiga el JSON compartido.
# ===========================================================================================
# El JSON que comparte con stiv_interactivo.py trae L = 2.45 m y bloque 48, que sobre una
# ventana de 100 fotogramas dejan una rejilla de 3 filas x 1 columna: TRES bloques por
# medida. La coherencia que decide si la estacion se acepta es la mediana de esos tres
# numeros, asi que basta con que uno se tuerza para tirar la estacion. Y lo que se tiraba
# no eran medidas malas: entre el 80 y el 100 % de las ventanas rechazadas tenian
# coherencia entre 0.30 y 0.40, justo por debajo del corte, y su velocidad se desviaba
# solo un 8.7 % de la mediana de su propia estacion. Medido sobre el video entero:
#   L=2.45  b=48  coh=0.40 ->  3 bloques, 20.2 % de caidas, rugosidad 0.069
#   L=4.00  b=48  coh=0.40 ->  9 bloques, 13.0 % de caidas, rugosidad 0.053
#   L=4.00  b=32  coh=0.40 -> 25 bloques,  9.4 % de caidas, rugosidad 0.044
#   L=4.00  b=32  coh=0.35 -> 25 bloques,  1.9 % de caidas, rugosidad 0.051
#   solo bajar el umbral a 0.30 ->        1.8 % de caidas, rugosidad 0.084  <- peor perfil
# Alargar la STI y achicar el bloque no relaja el criterio: le dan mas informacion sobre la
# que decidir, y por eso mejoran las caidas Y la suavidad del perfil a la vez, mientras que
# bajar el umbral a secas solo deja entrar ruido. El precio es que una STI de 4 m promedia
# el flujo sobre un tramo mas largo del cauce: la medida es menos local.
LARGO_STI = 4.0
BLOQUE = 32
COH_MIN = 0.35

# ===========================================================================================
#  >>> AJUSTABLE <<<  Mira limnimetrica
# ===========================================================================================
# Extremos de la linea de lectura, en pixeles de la imagen ORIGINAL. Van de un punto por
# encima del extremo superior de la chapa a otro por DEBAJO de su extremo inferior, para
# que el corte con el agua caiga siempre dentro. Medidos a mano sobre el fotograma 300 de
# 03337000_bullet_20171118-095500.mp4; si se cambia de encuadre hay que volver a medirlos.
MIRA_SUP = (1216.0, 258.0)
MIRA_INF = (1168.0, 510.0)
MUESTRAS_POR_PX = 2          # submuestreo de la linea; 2 basta para interpolar el cruce

# Tolerancia de la lectura de nivel respecto a la mediana reciente, en px de imagen. La
# oscilacion real medida es de 0.89 px de desviacion tipica, asi que 3 px son ~3.4 sigma:
# solo caza salpicaduras, que llegan a mover el borde 5 px de un fotograma al siguiente.
TOL_NIVEL = 3.0
VENTANA_MEDIANA = 48         # fotogramas sobre los que se toma esa mediana reciente (~2 s)
HOLD_NIVEL = 15              # fotogramas que se mantiene la ultima lectura buena (0.6 s)

# --- Presentacion --------------------------------------------------------------------------
ALTO_PANEL = si.ALTO_PANEL
HUECO = si.HUECO
ALTO_CABECERA = si.ALTO_CABECERA
ALTO_PIE = 114


def gh_del_video(nombre):
    """GH y Q del release para este video. Solo es un rotulo: no entra en ningun calculo."""
    try:
        for fila in csv.DictReader(open(RUTA_REGISTROS, encoding="utf-8")):
            if os.path.basename(fila["filepath"].replace("\\", "/")) == nombre:
                return float(fila["GH"]), float(fila["Q"])
    except Exception:
        pass
    return None, None


# ================================================================================ la mira
def muestrear_mira(video, n):
    """Perfil de brillo a lo largo de la chapa, fotograma a fotograma.

    Devuelve una matriz (fotograma, muestra). La muestra 0 es el extremo superior de la
    linea; el indice crece hacia abajo, asi que un indice mayor significa nivel MAS BAJO.
    """
    A, B = np.array(MIRA_SUP), np.array(MIRA_INF)
    largo = float(np.hypot(*(B - A)))
    n_mu = int(largo * MUESTRAS_POR_PX)
    t = np.linspace(0.0, 1.0, n_mu)
    P = A[None, :] + (B - A)[None, :] * t[:, None]
    mx = P[:, 0].astype(np.float32).reshape(1, -1)
    my = P[:, 1].astype(np.float32).reshape(1, -1)
    cap = cv2.VideoCapture(video)
    S = np.zeros((n, n_mu), np.float32)
    for k in range(n):
        ok, fr = cap.read()
        if not ok:
            S = S[:k]
            break
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        S[k] = cv2.remap(g, mx, my, cv2.INTER_LINEAR)[0]
        if (k + 1) % 200 == 0:
            print(f"  {k+1}/{n} fotogramas")
    cap.release()
    return S, largo / n_mu


def detectar_nivel(S):
    """Posicion del corte agua-chapa en cada fotograma, en muestras.

    La banda de busqueda no se elige a mano: la marca la propia desviacion tipica
    temporal del perfil. En la posicion donde esta el borde, el pixel salta entre chapa
    iluminada y agua oscura, de modo que su desviacion se dispara (24.5 frente a 3-5 en
    el resto de la linea). Alrededor de ese maximo se toma el nivel de gris de la chapa
    seca y el del agua, y el borde es el cruce al 50 % entre los dos, interpolado.
    """
    n_mu = S.shape[1]
    sd = S.std(0)
    mu = S.mean(0)
    borde = int(0.10 * n_mu)                       # los extremos de la linea no cuentan
    i_pico = borde + int(np.argmax(sd[borde:n_mu - borde]))
    sep, anc = int(0.04 * n_mu), int(0.18 * n_mu)
    seca = float(np.median(mu[max(i_pico - anc, 0):max(i_pico - sep, 1)]))
    moja = float(np.median(mu[min(i_pico + sep, n_mu - 2):min(i_pico + anc, n_mu - 1)]))
    umbral = 0.5 * (seca + moja)
    b0 = max(i_pico - int(0.14 * n_mu), 1)
    b1 = min(i_pico + int(0.14 * n_mu), n_mu - 2)

    nucleo = np.ones(9) / 9.0
    pos = np.full(len(S), np.nan)
    for k, perfil in enumerate(S):
        g = np.convolve(perfil, nucleo, mode="same")
        cruces = np.where((g[b0:b1] >= umbral) & (g[b0 + 1:b1 + 1] < umbral))[0]
        if len(cruces):
            i = b0 + int(cruces[-1])               # el ultimo cruce chapa -> agua
            d = (g[i] - umbral) / max(g[i] - g[i + 1], 1e-6)
            pos[k] = i + d
    return pos, dict(i_pico=i_pico, seca=seca, moja=moja, umbral=umbral, sd_pico=float(sd[i_pico]))


def filtrar_nivel(pos, esc_px):
    """Descarta salpicaduras y mantiene la ultima lectura buena, igual que las estaciones.

    Una salpicadura blanquea el agua junto a la chapa y el cruce se va varios pixeles de
    golpe. Se compara cada lectura con la mediana de las ultimas VENTANA_MEDIANA y se
    rechaza la que se aleje mas de TOL_NIVEL px.
    """
    n = len(pos)
    fuera = np.zeros(n, bool)
    salida = np.full(n, np.nan)
    estado = np.zeros(n, np.uint8)                 # 0 caida, 1 medida, 2 sostenida
    hist = []
    ultimo, edad = np.nan, 10 ** 6
    for k in range(n):
        v = pos[k]
        ok = np.isfinite(v)
        if ok and hist:
            ref = np.median(hist[-VENTANA_MEDIANA:])
            if abs(v - ref) * esc_px > TOL_NIVEL:
                ok = False
                fuera[k] = True
        if ok:
            hist.append(v)
            ultimo, edad = v, 0
            salida[k], estado[k] = v, 1
        else:
            edad += 1
            if np.isfinite(ultimo) and edad <= HOLD_NIVEL:
                salida[k], estado[k] = ultimo, 2
    return salida, estado, fuera


# ============================================================================ estaciones
def medir_estaciones(stin, cob, cfg, fps):
    """Velocidad por ventana y estado de cada estacion, con el hold ya aplicado.

    estado: 0 caida, 1 medida, 2 sostenida (ultimo valor valido), 3 muro.
    """
    n_est = cfg["n_est"]
    n = stin.shape[0]
    inicios = np.arange(0, max(n - cfg["ventana"], 0) + 1, cfg["paso"])
    V = np.full((len(inicios), n_est), np.nan)
    E = np.zeros((len(inicios), n_est), np.uint8)
    ultimo = np.full(n_est, np.nan)
    edad = np.full(n_est, 10 ** 6)
    for w, i0 in enumerate(inicios):
        for e in range(n_est):
            if cob[e].mean() < cfg["cobertura_min"]:
                continue
            v, c, _ = si.velocidad(stin[i0:i0 + cfg["ventana"], e, :], cob[e], cfg)
            if np.isfinite(v) and c >= cfg["coh_min"]:
                V[w, e] = abs(v) * fps / cfg["esc"]
                E[w, e] = 1
                ultimo[e], edad[e] = V[w, e], 0
            else:
                edad[e] += 1
                if np.isfinite(ultimo[e]) and edad[e] <= HOLD_VENTANAS:
                    V[w, e], E[w, e] = ultimo[e], 2
    return inicios, V, E


def rellenar_continuo(V, E, agua):
    """Ninguna estacion de agua se queda sin valor en ninguna ventana.

    El hold normal caduca a las HOLD_VENTANAS y despues la estacion se ve caida. Aqui se
    prolonga sin limite: los huecos se rellenan con la ULTIMA MEDIDA REAL anterior (nunca
    con otro relleno), y el hueco inicial, si lo hay, con la primera medida real
    posterior. Si una estacion no llega a medir nunca, se interpola de sus vecinas.

    El estado queda marcado con un 2 en el CSV, de modo que en los datos se distingue
    siempre lo medido de lo rellenado aunque el video ya no lo diga.
    """
    idx_agua = np.where(agua)[0]
    for e in idx_agua:
        reales = np.where(E[:, e] == 1)[0]
        if not len(reales):
            continue
        for w in range(V.shape[0]):
            if E[w, e] == 1:
                continue
            previas = reales[reales < w]
            V[w, e] = V[previas[-1], e] if len(previas) else V[reales[0], e]
            E[w, e] = 2
    # Estacion de agua que no mide nunca: se interpola en el espacio, ventana a ventana,
    # sobre las que si tienen valor. Es el mismo recurso que el caso SMC usa en su seccion.
    sin_nada = [e for e in idx_agua if not (E[:, e] == 1).any()]
    if sin_nada:
        con = np.array([e for e in idx_agua if e not in sin_nada])
        for w in range(V.shape[0]):
            if len(con) >= 2:
                V[w, sin_nada] = np.interp(sin_nada, con, V[w, con])
                E[w, sin_nada] = 2
    return V, E


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", default=si.RUTA_VIDEO)
    ap.add_argument("--salida", default=RUTA_SALIDA)
    ap.add_argument("--config", default=RUTA_CONFIG)
    ap.add_argument("--frames", type=int, default=0, help="0 = todo el video")
    a = ap.parse_args()

    cfg = dict(si.CFG_INICIAL)
    if os.path.exists(a.config):
        cfg.update(json.load(open(a.config, encoding="utf-8")))
        print(f"configuracion cargada de {a.config}")
    if cfg["cuadrilatero"] is None:
        raise SystemExit("La configuracion no tiene cuadrilatero: ajustalo antes con "
                         "stiv_interactivo.py")
    # La geometria (cuadrilatero, seccion, escala) es la del JSON; el muestreo del tensor
    # NO, por lo explicado arriba. Se sobrescribe aqui y no en el JSON para no cambiarle la
    # configuracion al programa interactivo ni al video anterior.
    print(f"muestreo del tensor propio de este programa: STI {LARGO_STI} {cfg['unidad']}, "
          f"bloque {BLOQUE}, coherencia minima {COH_MIN} "
          f"(el JSON traia {cfg['largo_sti']:.2f}, {cfg['bloque']}, {cfg['coh_min']:.2f})")
    cfg.update(largo_sti=LARGO_STI, bloque=BLOQUE, coh_min=COH_MIN)

    cap = cv2.VideoCapture(a.video)
    if not cap.isOpened():
        raise SystemExit(f"No se pudo abrir {a.video}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    ntot = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    n = ntot if a.frames <= 0 else min(a.frames, ntot)
    u = cfg["unidad"]
    GH, Q_ref = gh_del_video(os.path.basename(a.video))

    i2o, ow, oh, caja = si.homografia(cfg)
    o2i = np.linalg.inv(i2o)
    centros, flujo, pts, n_mu = si.geometria_medida(cfg, caja)
    mx_, my_, W_, L_ = caja

    print(f"\n{os.path.basename(a.video)}: {ntot} fotogramas a {fps:.2f} fps "
          f"({ntot/fps:.1f} s); se procesan {n}")
    if GH is not None:
        print(f"referencia del release (solo rotulo): GH {GH:.2f} ft, Q {Q_ref:.0f} cfs")

    # --- pasada 1: STI de las estaciones -----------------------------------------------
    print(f"\nPasada 1/3 - rectificando y muestreando las {cfg['n_est']} estaciones")
    t0 = time.time()
    sti, cob = si.construir_sti(a.video, cfg, 0, n, i2o, ow, oh, caja)
    n = sti.shape[0]
    stin, contraste = si.normalizar(sti)
    print(f"  STI de {n} fotogramas en {time.time()-t0:.1f} s")

    inicios, V, E = medir_estaciones(stin, cob, cfg, fps)
    centros_t = inicios + cfg["ventana"] // 2

    # --- estaciones de muro: se marcan, se dibujan, y se dejan fuera de los agregados ---
    perfil = np.nanmedian(V, axis=0)
    ref = np.nanmedian(perfil)
    muro = np.isfinite(perfil) & (np.abs(perfil) < FRAC_MURO * ref)
    E[:, muro] = 3
    agua = ~muro
    print(f"\nEstaciones: {int(agua.sum())} de agua, {int(muro.sum())} de muro "
          f"({', '.join(str(i) for i in np.where(muro)[0]) or 'ninguna'})")
    for e in range(cfg["n_est"]):
        tipo = "MURO" if muro[e] else "agua"
        print(f"  est {e:2d} [{tipo}]  contraste {contraste[e]:6.2f}  "
              f"v mediana {perfil[e]:6.3f} {u}/s  medida {100*(E[:, e]==1).mean():5.1f} %  "
              f"sostenida {100*(E[:, e]==2).mean():4.1f} %")

    Va = np.where(agua[None, :], V, np.nan)        # solo agua, para los agregados
    vmed = np.nanmedian(Va, axis=1)
    if np.isfinite(Va).any():
        lo, hi = np.nanpercentile(np.abs(Va), [2, 98])
        hi = max(hi, lo + 1e-6)
    else:
        lo, hi = 0.0, 1.0
    print(f"\nVelocidad mediana de la seccion (sin los muros): {np.nanmedian(vmed):.4f} {u}/s")
    print(f"Rango de color: {lo:.3f} - {hi:.3f} {u}/s")
    sost = (E == 2).sum() / max((E > 0).sum(), 1)
    print(f"Valores sostenidos por el hold: {100*sost:.1f} % de los dibujados "
          f"(maximo {HOLD_VENTANAS} ventanas = {HOLD_VENTANAS*cfg['paso']/fps:.2f} s)")

    # --- pasada 2: la mira ---------------------------------------------------------------
    print(f"\nPasada 2/3 - leyendo la mira limnimetrica")
    t0 = time.time()
    S, esc_px = muestrear_mira(a.video, n)
    n = min(n, S.shape[0])
    pos, info = detectar_nivel(S)
    nivel, est_niv, fuera = filtrar_nivel(pos, esc_px)
    ref_niv = np.nanmedian(nivel)
    # Signo: el indice crece hacia abajo por la chapa, asi que restar deja el nivel
    # positivo cuando el agua esta MAS ALTA que la mediana del video.
    niv_px = (ref_niv - nivel) * esc_px
    print(f"  {n} fotogramas en {time.time()-t0:.1f} s")
    print(f"  chapa seca {info['seca']:.1f}, agua {info['moja']:.1f}, umbral "
          f"{info['umbral']:.1f}; desviacion en el borde {info['sd_pico']:.1f}")
    print(f"  detectado en {100*np.isfinite(pos[:n]).mean():.1f} % de los fotogramas; "
          f"{int(fuera[:n].sum())} lecturas descartadas por salpicadura; "
          f"{int((est_niv[:n]==2).sum())} sostenidas, {int((est_niv[:n]==0).sum())} sin valor")
    print(f"  oscilacion del nivel: desviacion tipica {np.nanstd(niv_px[:n]):.2f} px, "
          f"q05-q95 {np.nanpercentile(niv_px[:n],5):+.2f} a "
          f"{np.nanpercentile(niv_px[:n],95):+.2f} px")

    # --- pasada 3: render ------------------------------------------------------------------
    eo = ALTO_PANEL / alto
    er = ALTO_PANEL / oh
    pw_o, pw_r = int(ancho * eo), int(ow * er)
    x_o, x_r = HUECO, HUECO + pw_o + HUECO
    cw = x_r + pw_r + HUECO
    y_pie = ALTO_CABECERA + ALTO_PANEL
    ch = y_pie + ALTO_PIE

    print(f"\nPasada 3/3 - render de {n} fotogramas a {cw}x{ch}, {fps:.2f} fps (tiempo real)")
    os.makedirs(os.path.dirname(a.salida) or ".", exist_ok=True)
    vw = ev.abrir(a.salida, fps, (cw, ch))
    if not vw.isOpened():
        raise SystemExit("No se pudo abrir el escritor de video.")

    ext_r = np.float32([[pts[e, 0], pts[e, -1], centros[e]] for e in range(cfg["n_est"])])
    ext_o = cv2.perspectiveTransform(ext_r.reshape(1, -1, 2), o2i).reshape(-1, 3, 2)
    A_m, B_m = np.array(MIRA_SUP), np.array(MIRA_INF)
    dir_m = (B_m - A_m) / max(np.hypot(*(B_m - A_m)), 1e-9)
    perp_m = np.array([-dir_m[1], dir_m[0]])

    cap = cv2.VideoCapture(a.video)
    t0 = time.time()
    for k in range(n):
        ok, fr = cap.read()
        if not ok:
            break
        rect = cv2.warpPerspective(fr, i2o, (ow, oh), flags=cv2.INTER_LINEAR)
        pano = cv2.resize(fr, (pw_o, ALTO_PANEL), interpolation=cv2.INTER_AREA)
        prec = cv2.resize(rect, (pw_r, ALTO_PANEL), interpolation=cv2.INTER_AREA)
        w = int(np.argmin(np.abs(centros_t - k)))

        for e in range(cfg["n_est"]):
            v, est = V[w, e], E[w, e]
            col = si.color_velocidad(v, lo, hi)
            for panel, esc, p in ((prec, er, ext_r[e]), (pano, eo, ext_o[e])):
                p0 = (int(p[0][0] * esc), int(p[0][1] * esc))
                p1 = (int(p[1][0] * esc), int(p[1][1] * esc))
                if est == 3:
                    for f in np.linspace(0, 1, 10):
                        cv2.circle(panel, (int(p0[0] + (p1[0] - p0[0]) * f),
                                           int(p0[1] + (p1[1] - p0[1]) * f)), 1,
                                   (170, 170, 170), -1)
                else:
                    cv2.line(panel, p0, p1, (255, 255, 255), 1, cv2.LINE_AA)
            if np.isfinite(v) and est != 3:
                punta_r = centros[e] + flujo * (abs(v) / hi) * 0.45 * L_
                punta_o = cv2.perspectiveTransform(
                    punta_r.astype(np.float32).reshape(1, 1, 2), o2i).reshape(2)
                grosor = 3 if est == 1 else 2      # la sostenida, mas fina
                dy = 4 if e % 2 == 0 else -14
                for panel, esc, c0, c1 in ((prec, er, centros[e], punta_r),
                                           (pano, eo, ext_o[e][2], punta_o)):
                    b = (int(c0[0] * esc), int(c0[1] * esc))
                    p = (int(c1[0] * esc), int(c1[1] * esc))
                    cv2.arrowedLine(panel, b, p, col, grosor, cv2.LINE_AA, tipLength=0.18)
                    si.texto(panel, f"{abs(v):.3f}", (p[0] + 7, p[1] + dy), 0.44, col, 1)
            # Simbolos: circulo lleno = medida ahora, anillo hueco = ultimo valor valido,
            # cuadro naranja = caida, cuadro negro = muro (se dibuja su 0 pero no cuenta).
            for panel, esc, c0 in ((prec, er, centros[e]), (pano, eo, ext_o[e][2])):
                q = (int(c0[0] * esc), int(c0[1] * esc))
                if est == 3:
                    cv2.rectangle(panel, (q[0] - 5, q[1] - 5), (q[0] + 5, q[1] + 5),
                                  (30, 30, 30), -1)
                    cv2.rectangle(panel, (q[0] - 5, q[1] - 5), (q[0] + 5, q[1] + 5),
                                  (255, 255, 255), 1)
                    # Su valor se sigue viendo, en gris y sin flecha: esta ahi, es cero,
                    # y no cuenta para la mediana ni para la barra de color.
                    if np.isfinite(v):
                        si.texto(panel, f"{abs(v):.2f}", (q[0] - 12, q[1] - 12), 0.42,
                                 (170, 170, 170), 1)
                elif est == 1:
                    cv2.circle(panel, q, 5, (255, 255, 255), -1)
                    cv2.circle(panel, q, 5, (20, 20, 20), 1)
                elif est == 2:
                    cv2.circle(panel, q, 6, (255, 255, 255), 2)
                    cv2.circle(panel, q, 3, (20, 20, 20), -1)
                else:
                    cv2.rectangle(panel, (q[0] - 6, q[1] - 6), (q[0] + 6, q[1] + 6),
                                  (0, 165, 255), -1)
                    cv2.rectangle(panel, (q[0] - 6, q[1] - 6), (q[0] + 6, q[1] + 6),
                                  (20, 20, 20), 1)

        # --- la mira, solo en la vista original --------------------------------------
        # No se dibuja en la rectificada a proposito: la homografia es del plano del agua,
        # horizontal, y una chapa vertical rectificada con ella no significa nada.
        pa = (int(A_m[0] * eo), int(A_m[1] * eo))
        pb = (int(B_m[0] * eo), int(B_m[1] * eo))
        cv2.line(pano, pa, pb, (255, 220, 120), 1, cv2.LINE_AA)
        if est_niv[k] > 0:
            pm = A_m + dir_m * (nivel[k] * esc_px)
            c1 = (int((pm[0] - perp_m[0] * 9) * eo), int((pm[1] - perp_m[1] * 9) * eo))
            c2 = (int((pm[0] + perp_m[0] * 9) * eo), int((pm[1] + perp_m[1] * 9) * eo))
            col_n = (120, 255, 120) if est_niv[k] == 1 else (0, 200, 255)
            cv2.line(pano, c1, c2, col_n, 2, cv2.LINE_AA)
            si.texto(pano, f"{niv_px[k]:+.2f} px", (c2[0] + 6, c2[1] + 4), 0.45, col_n, 1)

        lienzo = np.zeros((ch, cw, 3), np.uint8)
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ALTO_PANEL, x_o:x_o + pw_o] = pano
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ALTO_PANEL, x_r:x_r + pw_r] = prec
        si.texto(lienzo, "vista original de la camara", (x_o, 24), 0.62, (255, 255, 255), 2)
        si.texto(lienzo, "plano rectificado (aqui se mide)",
                 (x_r, 24), 0.62, (255, 255, 255), 2)
        si.texto(lienzo, f"ventana {cfg['ventana']/fps:.1f} s   DS = {cfg['ds']} px",
                 (x_o + 300, 24), 0.5, (170, 170, 170), 1)

        # La franja con la serie temporal del nivel se quito a proposito: el nivel varia
        # 0.74 px de desviacion tipica en 38 s y la grafica era una linea casi plana que
        # ocupaba 104 px de alto. La serie completa sigue en el CSV, y la lectura del
        # fotograma se ve donde importa: sobre la propia mira y en el pie.
        si.barra_color(lienzo, lo, hi, u, cw - 330, ch - 28)
        vm = vmed[w]
        si.texto(lienzo, f"t = {k/fps:6.2f} s", (x_o, y_pie + 28), 0.66, (255, 255, 255), 2)
        si.texto(lienzo, f"v mediana de la seccion = {vm:.4f} {u}/s"
                 if np.isfinite(vm) else "v mediana = --",
                 (x_o + 180, y_pie + 28), 0.66, (120, 220, 255), 2)
        si.texto(lienzo, f"nivel {niv_px[k]:+.2f} px" if np.isfinite(niv_px[k])
                 else "nivel --", (x_o + 640, y_pie + 28), 0.66, (120, 255, 120), 2)
        si.texto(lienzo, f"medidas {int((E[w]==1).sum())}   sostenidas "
                         f"{int((E[w]==2).sum())}   caidas {int((E[w]==0).sum())}",
                 (x_o + 860, y_pie + 28), 0.6, (150, 255, 150), 2)
        si.texto(lienzo, "circulo lleno = medida en esta ventana   anillo = ultimo valor "
                         "valido (max 0.6 s)   cuadro naranja = caida   cuadro negro = muro, "
                         "su 0 no entra en la mediana",
                 (x_o, y_pie + 54), 0.44, (170, 170, 170), 1)
        si.texto(lienzo, "el nivel se mide sobre la mira, en pixeles a lo largo de la chapa: "
                         "no hay escala vertical, solo variacion relativa",
                 (x_o, y_pie + 76), 0.44, (140, 140, 140), 1)
        if GH is not None:
            # El GH del release es un solo valor por video, interpolado al instante de la
            # grabacion. Se rotula para dar contexto y se dice que no se usa.
            si.texto(lienzo, f"GH {GH:.2f} ft   Q {Q_ref:.0f} cfs   del release, no se usa "
                             f"para nada", (x_o, y_pie + 98), 0.44, (140, 140, 140), 1)
        vw.write(lienzo)
        if (k + 1) % 100 == 0:
            print(f"  {k+1}/{n} fotogramas")
    vw.release()
    cap.release()
    print(f"  render en {time.time()-t0:.1f} s")
    print(f"\nListo: {a.salida} ({os.path.getsize(a.salida)/1e6:.1f} MB, {n/fps:.1f} s)")

    # --- salidas de datos -----------------------------------------------------------------
    base = os.path.splitext(a.salida)[0]
    with open(base + "_ventanas.csv", "w", newline="", encoding="utf-8") as f:
        esc = csv.writer(f)
        esc.writerow(["ventana", "frame_centro", "t_s"]
                     + [f"v{e}_{u}_s" for e in range(cfg["n_est"])]
                     + [f"estado{e}" for e in range(cfg["n_est"])] + [f"v_mediana_{u}_s"])
        for w in range(len(inicios)):
            esc.writerow([w, int(centros_t[w]), round(centros_t[w] / fps, 3)]
                         + [round(float(x), 5) if np.isfinite(x) else "" for x in V[w]]
                         + [int(x) for x in E[w]]
                         + [round(float(vmed[w]), 5) if np.isfinite(vmed[w]) else ""])
    print(f"Velocidades por ventana en: {base}_ventanas.csv "
          f"(estado 0 caida, 1 medida, 2 sostenida, 3 muro)")
    with open(base + "_nivel.csv", "w", newline="", encoding="utf-8") as f:
        esc = csv.writer(f)
        esc.writerow(["frame", "t_s", "pos_mira_px", "nivel_px", "estado", "salpicadura"])
        for k in range(n):
            esc.writerow([k, round(k / fps, 3),
                          round(float(nivel[k] * esc_px), 4) if np.isfinite(nivel[k]) else "",
                          round(float(niv_px[k]), 4) if np.isfinite(niv_px[k]) else "",
                          int(est_niv[k]), int(fuera[k])])
    print(f"Nivel por fotograma en: {base}_nivel.csv")


if __name__ == "__main__":
    main()
