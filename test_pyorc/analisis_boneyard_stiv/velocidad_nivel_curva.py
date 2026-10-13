"""Igual que `velocidad_nivel_chapa.py`, pero con la mira definida A MANO y con lados CURVOS.

Por que
-------
La camara es un ojo de pez y la chapa de la mira sale curvada en la imagen. Un
cuadrilatero de cuatro esquinas tiene los lados rectos por construccion, asi que
por bien que se coloquen las esquinas, el centro de la chapa se sale de la banda:
el rectificado mete muro por un lado y pierde chapa por el otro, y las
graduaciones salen inclinadas en vez de horizontales.

Aqui la banda de la mira la defines tu, y sus dos lados largos son **curvas**. Cada
lado es una parabola que pasa por tres puntos que se arrastran: los dos extremos y
**un tirador en el centro**, que es el que dobla la curva para seguir la
deformacion del objetivo. Seis tiradores en total. Si se dejan los centros sobre la
recta, la banda es exactamente el cuadrilatero de antes.

El muestreo ya no es una homografia: para cada fila `t` a lo largo de la chapa y
cada columna `s` a lo ancho, el punto es `(1-s)*Izq(t) + s*Der(t)`, una mezcla de
las dos curvas, y se lee con `cv2.remap`. Eso endereza la chapa aunque este curva.

Como se comprueba que esta bien: en el panel derecho, en vivo, **las graduaciones
tienen que salir horizontales** y la chapa llenar la banda de lado a lado. Con `g`
se superponen unas guias horizontales para juzgarlo.

El resto es identico a `velocidad_nivel_chapa.py`: el nivel sale del cruce al 50 %
entre el gris de la chapa seca y el del agua, interpolado, no de contar marcas (la
cuenta fluctua diez veces mas que la oscilacion real; se guarda en el CSV como
diagnostico). El periodo de las graduaciones da la escala interna y el nivel se
reporta tambien en graduaciones.

Uso
---
    python velocidad_nivel_curva.py                 # abre el ajuste y luego procesa
    python velocidad_nivel_curva.py --sin-interfaz  # reprocesa con lo ya guardado
"""
import argparse
import csv
import json
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import escritor_video as ev
import stiv_interactivo as si
import velocidad_nivel as vn
import velocidad_nivel_chapa as vc

RUTA_SALIDA = os.path.join(si.DIR_CASO, "salidas", "velocidad_nivel_curva.mp4")
RUTA_MIRA = os.path.join(si.DIR_CASO, "salidas", "config_mira_curva.json")

# ===========================================================================================
#  >>> AJUSTABLE <<<  Punto de partida de la banda de la mira
# ===========================================================================================
# Seis puntos: los dos extremos y el centro de cada lado largo. El centro es un punto POR EL
# QUE PASA la curva, no un control de Bezier suelto, para que arrastrarlo haga lo que uno
# espera. De partida estan sobre la recta, o sea la banda arranca como el cuadrilatero de
# `velocidad_nivel_chapa.py`, prolongado hacia abajo para que el agua caiga dentro.
MIRA_INICIAL = {
    "izq": [[1205.0, 266.0], [1188.5, 373.5], [1169.0, 496.0]],   # arriba, centro, abajo
    "der": [[1228.0, 269.0], [1210.0, 373.5], [1189.0, 499.0]],
}
BANDA_W, BANDA_H = 60, 460        # tamaño del rectificado de la banda
# Franja de columnas que se promedia. Con la banda bien puesta ya no hace falta recortar
# tanto como en la version de cuadrilatero recto, pero se dejan unos margenes por si un
# lado roza el muro.
FRANJA_COL = (0.15, 0.90)

ALTO_PANEL = si.ALTO_PANEL
HUECO = si.HUECO
ALTO_CABECERA = si.ALTO_CABECERA
ALTO_PIE = 52
INSET_W, INSET_H = 46, 322


# =================================================================== la banda curva
def curva(p3, t):
    """Parabola que pasa por p3[0] en t=0, p3[1] en t=0.5 y p3[2] en t=1.

    Se usa la forma de Bezier cuadratica con el control despejado a partir del punto
    medio: asi el tirador del centro esta SOBRE la curva y arrastrarlo la lleva consigo.
    """
    p0, pm, p1 = np.array(p3[0]), np.array(p3[1]), np.array(p3[2])
    pc = 2.0 * pm - 0.5 * (p0 + p1)
    t = t[:, None]
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * pc + t ** 2 * p1


def mapa_banda(mira, w=BANDA_W, h=BANDA_H):
    """Mapa de muestreo de la banda curva y su longitud media en px de imagen.

    Para cada fila t y columna s el punto es (1-s)*Izq(t) + s*Der(t): una mezcla lineal
    de las dos curvas. No es una homografia, asi que endereza la chapa aunque este curva.
    """
    t = np.linspace(0.0, 1.0, h)
    Lz, Dr = curva(mira["izq"], t), curva(mira["der"], t)
    s = np.linspace(0.0, 1.0, w)[None, :, None]
    P = (1 - s) * Lz[:, None, :] + s * Dr[:, None, :]
    largo = 0.5 * (np.hypot(*np.diff(Lz, axis=0).T).sum() + np.hypot(*np.diff(Dr, axis=0).T).sum())
    return (np.ascontiguousarray(P[:, :, 0], np.float32),
            np.ascontiguousarray(P[:, :, 1], np.float32), float(largo))


def eje_banda(mira, h=BANDA_H):
    """Puntos del eje de la banda en la imagen, para dibujar la marca del nivel."""
    t = np.linspace(0.0, 1.0, h)
    return 0.5 * (curva(mira["izq"], t) + curva(mira["der"], t))


def perfiles_banda(video, n, mapx, mapy):
    """Brillo medio de cada fila de la banda rectificada, fotograma a fotograma."""
    c0 = int(FRANJA_COL[0] * mapx.shape[1])
    c1 = int(FRANJA_COL[1] * mapx.shape[1])
    cap = cv2.VideoCapture(video)
    P = np.zeros((n, mapx.shape[0]), np.float32)
    for k in range(n):
        ok, fr = cap.read()
        if not ok:
            P = P[:k]
            break
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        P[k] = cv2.remap(g, mapx, mapy, cv2.INTER_LINEAR).astype(np.float32)[:, c0:c1].mean(1)
    cap.release()
    return P


# ========================================================================== el ajuste
AYUDA_MIRA = [
    ("raton", "arrastrar los 6 tiradores: extremos y CENTRO de cada lado largo"),
    ("", "el centro es el que dobla la curva para seguir el ojo de pez"),
    ("g", "guias horizontales    z / Z  acercar / alejar    r  recentrar la vista"),
    ("BARRA", "pausar el video    s  guardar    INTRO  procesar    ESC  salir"),
]


class EditorMira:
    """Ajuste de la banda con el video corriendo en las dos vistas.

    El video no se congela a proposito: sobre una foto no se ve si la banda sigue a la
    chapa cuando el agua salpica, y ademas el nivel se mueve.
    """

    def __init__(self, video, mira):
        self.video, self.mira = video, mira
        self.cap = cv2.VideoCapture(video)
        if not self.cap.isOpened():
            raise SystemExit(f"No se pudo abrir {video}")
        ok, self.base = self.cap.read()
        if not ok:
            raise SystemExit("No se pudo leer ningun fotograma")
        self.guias = True
        self.reproduciendo = True
        self.arrastrando = None
        self.mensaje = ""
        self.pw = 560
        self.recentrar()

    def puntos(self):
        return [("izq", i) for i in range(3)] + [("der", i) for i in range(3)]

    def recentrar(self):
        """Centra y ajusta el zoom para que la banda entera quepa con margen.

        Con un zoom fijo los extremos se salian del panel y no habia forma de agarrarlos.
        """
        p = np.array(self.mira["izq"] + self.mira["der"])
        c = p.mean(0)
        self.cx, self.cy = float(c[0]), float(c[1])
        ancho = max(p[:, 0].max() - p[:, 0].min(), 20.0) + 60.0
        alto = max(p[:, 1].max() - p[:, 1].min(), 20.0) + 60.0
        self.zoom = float(np.clip(min(self.pw / ancho, ALTO_PANEL / alto), 1.0, 8.0))

    def a_panel(self, p):
        return (int((p[0] - self.cx) * self.zoom + self.pw / 2),
                int((p[1] - self.cy) * self.zoom + ALTO_PANEL / 2))

    def a_imagen(self, x, y):
        return ((x - self.pw / 2) / self.zoom + self.cx,
                (y - ALTO_PANEL / 2) / self.zoom + self.cy)

    def componer(self):
        alto, ancho = self.base.shape[:2]
        self.pw = 560
        # recorte ampliado alrededor del centro
        M = np.float32([[self.zoom, 0, self.pw / 2 - self.cx * self.zoom],
                        [0, self.zoom, ALTO_PANEL / 2 - self.cy * self.zoom]])
        vista = cv2.warpAffine(self.base, M, (self.pw, ALTO_PANEL), flags=cv2.INTER_NEAREST)

        t = np.linspace(0, 1, 120)
        for lado, col in (("izq", (255, 220, 120)), ("der", (255, 220, 120))):
            c = curva(self.mira[lado], t)
            for i in range(len(c) - 1):
                cv2.line(vista, self.a_panel(c[i]), self.a_panel(c[i + 1]), col, 1, cv2.LINE_AA)
        for lado in ("izq", "der"):
            for i, p in enumerate(self.mira[lado]):
                q = self.a_panel(p)
                r = 8 if i == 1 else 6
                col = (120, 255, 120) if i == 1 else (255, 220, 120)
                cv2.circle(vista, q, r, col, -1)
                cv2.circle(vista, q, r, (20, 20, 20), 2)
        si.texto(vista, "centro: dobla la curva", (12, ALTO_PANEL - 14), 0.45,
                 (120, 255, 120), 1)

        # --- la banda rectificada, en vivo -------------------------------------------
        mapx, mapy, largo = mapa_banda(self.mira)
        banda = cv2.remap(self.base, mapx, mapy, cv2.INTER_LINEAR)
        # Se estira a lo ancho a proposito: a su proporcion real la banda sale de 65 px y
        # las graduaciones no se pueden juzgar. Aqui solo se mira si salen horizontales.
        bw = 170
        ban = cv2.resize(banda, (bw, ALTO_PANEL), interpolation=cv2.INTER_LINEAR)
        if self.guias:
            # Las graduaciones tienen que quedar paralelas a estas guias: es la unica
            # forma de ver si la curvatura esta bien compensada.
            for y in range(0, ALTO_PANEL, 24):
                cv2.line(ban, (0, y), (bw, y), (0, 120, 255), 1)
        c0 = int(FRANJA_COL[0] * bw)
        c1 = int(FRANJA_COL[1] * bw)
        cv2.rectangle(ban, (c0, 0), (c1, ALTO_PANEL - 1), (120, 255, 120), 1)

        cw = HUECO + self.pw + HUECO + bw + HUECO + 560
        ch = ALTO_CABECERA + ALTO_PANEL + 40
        lienzo = np.zeros((ch, cw, 3), np.uint8)
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ALTO_PANEL, HUECO:HUECO + self.pw] = vista
        x2 = HUECO + self.pw + HUECO
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ALTO_PANEL, x2:x2 + bw] = ban
        self.x1, self.x2, self.bw = HUECO, x2, bw

        si.texto(lienzo, "AJUSTE DE LA MIRA", (HUECO, 24), 0.66, (0, 255, 255), 2)
        si.texto(lienzo, "arrastra los 6 tiradores hasta que la banda siga la chapa",
                 (HUECO + 240, 24), 0.5, (230, 230, 230), 1)
        x3 = x2 + bw + HUECO
        si.texto(lienzo, "las graduaciones deben salir HORIZONTALES", (x3, 24), 0.5,
                 (255, 255, 255), 1)
        for i, (k, d) in enumerate(AYUDA_MIRA):
            y = ALTO_CABECERA + 40 + i * 22
            si.texto(lienzo, f"{k:>6s}", (x3, y), 0.45, (255, 255, 120), 1)
            si.texto(lienzo, d, (x3 + 60, y), 0.44, (170, 170, 170), 1)
        si.texto(lienzo, f"zoom x{self.zoom:.1f}   banda {BANDA_W}x{BANDA_H} px para "
                         f"{largo:.0f} px de imagen", (x3, ALTO_CABECERA + 150), 0.45,
                 (150, 150, 150), 1)
        si.texto(lienzo, "el recuadro verde de la banda es la franja de columnas",
                 (x3, ALTO_CABECERA + 174), 0.44, (120, 255, 120), 1)
        si.texto(lienzo, "que se promedia para leer el nivel",
                 (x3, ALTO_CABECERA + 194), 0.44, (120, 255, 120), 1)
        if self.mensaje:
            si.texto(lienzo, self.mensaje, (x3, ALTO_CABECERA + 240), 0.55, (150, 255, 150), 1)
        return lienzo

    def raton(self, evento, x, y, flags, _):
        yy = y - ALTO_CABECERA
        if evento == cv2.EVENT_LBUTTONDOWN:
            if self.x1 <= x < self.x1 + self.pw and 0 <= yy < ALTO_PANEL:
                p = np.array(self.a_imagen(x - self.x1, yy))
                d = [np.hypot(*(np.array(self.mira[l][i]) - p)) for l, i in self.puntos()]
                if min(d) < 30 / self.zoom:
                    self.arrastrando = self.puntos()[int(np.argmin(d))]
        elif evento == cv2.EVENT_MOUSEMOVE and self.arrastrando:
            l, i = self.arrastrando
            px, py = self.a_imagen(np.clip(x - self.x1, 0, self.pw),
                                   np.clip(yy, 0, ALTO_PANEL))
            self.mira[l][i] = [float(px), float(py)]
        elif evento == cv2.EVENT_LBUTTONUP:
            self.arrastrando = None

    def correr(self):
        win = "Ajuste de la mira"
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(win, self.raton)
        fps = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
        espera = max(int(1000 / fps), 1)
        procesar = False
        while True:
            if self.reproduciendo and self.arrastrando is None:
                ok, fr = self.cap.read()
                if not ok:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok, fr = self.cap.read()
                if ok:
                    self.base = fr
            cv2.imshow(win, self.componer())
            k = cv2.waitKey(espera if self.reproduciendo else 20) & 0xFF
            if k == 255:
                continue
            self.mensaje = ""
            if k == 27:
                break
            elif k == 13:
                procesar = True
                break
            elif k == 32:
                self.reproduciendo = not self.reproduciendo
            elif k == ord("g"):
                self.guias = not self.guias
            elif k == ord("z"):
                self.zoom = min(8.0, self.zoom + 0.5)
            elif k == ord("Z"):
                self.zoom = max(1.0, self.zoom - 0.5)
            elif k == ord("r"):
                self.recentrar()
            elif k == ord("s"):
                guardar_mira(self.mira)
                self.mensaje = "mira guardada"
        cv2.destroyAllWindows()
        self.cap.release()
        return procesar


def guardar_mira(mira):
    os.makedirs(os.path.dirname(RUTA_MIRA), exist_ok=True)
    with open(RUTA_MIRA, "w", encoding="utf-8") as f:
        json.dump(mira, f, indent=2)
    print(f"mira guardada en {RUTA_MIRA}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", default=si.RUTA_VIDEO)
    ap.add_argument("--salida", default=RUTA_SALIDA)
    ap.add_argument("--config", default=si.RUTA_CONFIG)
    ap.add_argument("--mira", default=RUTA_MIRA)
    ap.add_argument("--frames", type=int, default=0, help="0 = todo el video")
    ap.add_argument("--sin-interfaz", action="store_true",
                    help="no abre la ventana de ajuste: usa la mira ya guardada")
    a = ap.parse_args()

    mira = json.loads(json.dumps(MIRA_INICIAL))
    if os.path.exists(a.mira):
        mira = json.load(open(a.mira, encoding="utf-8"))
        print(f"mira cargada de {a.mira}")
    if not a.sin_interfaz:
        ed = EditorMira(a.video, mira)
        if not ed.correr():
            print("salida sin procesar el video.")
            return
        mira = ed.mira
        guardar_mira(mira)

    cfg = dict(si.CFG_INICIAL)
    if os.path.exists(a.config):
        cfg.update(json.load(open(a.config, encoding="utf-8")))
        print(f"configuracion del agua cargada de {a.config}")
    if cfg["cuadrilatero"] is None:
        raise SystemExit("La configuracion no tiene cuadrilatero: ajustalo con "
                         "stiv_interactivo.py")
    print(f"muestreo del tensor: STI {vn.LARGO_STI} {cfg['unidad']}, bloque {vn.BLOQUE}, "
          f"coherencia minima {vn.COH_MIN}")
    cfg.update(largo_sti=vn.LARGO_STI, bloque=vn.BLOQUE, coh_min=vn.COH_MIN)

    cap = cv2.VideoCapture(a.video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    ntot = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto_img = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    n = ntot if a.frames <= 0 else min(a.frames, ntot)
    u = cfg["unidad"]
    GH, Q_ref = vn.gh_del_video(os.path.basename(a.video))

    i2o, ow, oh, caja = si.homografia(cfg)
    o2i = np.linalg.inv(i2o)
    centros, flujo, pts, n_mu = si.geometria_medida(cfg, caja)
    _, _, _, L_ = caja

    print(f"\n{os.path.basename(a.video)}: {ntot} fotogramas a {fps:.2f} fps "
          f"({ntot/fps:.1f} s); se procesan {n}")

    # --- pasada 1: velocidad ------------------------------------------------------------
    print(f"\nPasada 1/3 - rectificando el agua y muestreando las {cfg['n_est']} estaciones")
    t0 = time.time()
    sti, cob = si.construir_sti(a.video, cfg, 0, n, i2o, ow, oh, caja)
    n = sti.shape[0]
    stin, contraste = si.normalizar(sti)
    print(f"  STI de {n} fotogramas en {time.time()-t0:.1f} s")
    inicios, V, E = vn.medir_estaciones(stin, cob, cfg, fps)
    centros_t = inicios + cfg["ventana"] // 2
    perfil_v = np.nanmedian(V, axis=0)
    muro = np.isfinite(perfil_v) & (np.abs(perfil_v) < vn.FRAC_MURO * np.nanmedian(perfil_v))
    E[:, muro] = 3
    agua = ~muro
    # Ninguna estacion de agua puede verse caida: el hold se prolonga sin limite.
    V, E = vn.rellenar_continuo(V, E, agua)
    Va = np.where(agua[None, :], V, np.nan)
    vmed = np.nanmedian(Va, axis=1)
    lo, hi = np.nanpercentile(np.abs(Va), [2, 98])
    hi = max(hi, lo + 1e-6)
    print(f"Estaciones: {int(agua.sum())} de agua, {int(muro.sum())} de muro")
    print(f"Velocidad mediana de la seccion (sin los muros): {np.nanmedian(vmed):.4f} {u}/s")
    print(f"Estados: medida {100*(E[:, agua]==1).mean():.1f} %, sostenida "
          f"{100*(E[:, agua]==2).mean():.1f} %, caida {100*(E[:, agua]==0).mean():.1f} %")

    # --- pasada 2: la banda curva de la mira ---------------------------------------------
    print(f"\nPasada 2/3 - rectificando la banda curva de la mira")
    t0 = time.time()
    mapx, mapy, largo_img = mapa_banda(mira)
    px_por_fila = largo_img / BANDA_H
    P = perfiles_banda(a.video, n, mapx, mapy)
    n = min(n, P.shape[0])
    pos, info = vc.detectar_nivel_chapa(P)
    periodo = vc.periodo_marcas(P.mean(0), info["i_pico"])
    periodo_px = periodo * px_por_fila
    nivel, est_niv, fuera = vn.filtrar_nivel(pos, px_por_fila)
    ref_niv = np.nanmedian(nivel)
    niv_px = (ref_niv - nivel) * px_por_fila
    niv_gr = niv_px / periodo_px
    marcas = np.array([vc.contar_marcas(P[k], nivel[k] if np.isfinite(nivel[k])
                                        else info["i_pico"], periodo) for k in range(n)])
    eje = eje_banda(mira)
    print(f"  {n} fotogramas en {time.time()-t0:.1f} s")
    print(f"  banda {BANDA_W}x{BANDA_H} px para {largo_img:.0f} px de imagen "
          f"-> {px_por_fila:.4f} px de imagen por fila")
    print(f"  chapa seca {info['seca']:.1f}, agua {info['moja']:.1f}, umbral "
          f"{info['umbral']:.1f}; desviacion en el borde {info['sd_pico']:.1f}")
    print(f"  periodo de las graduaciones: {periodo} filas = {periodo_px:.2f} px de imagen")
    print(f"  detectado en {100*np.isfinite(pos[:n]).mean():.1f} % de los fotogramas; "
          f"{int(fuera[:n].sum())} salpicaduras descartadas, "
          f"{int((est_niv[:n]==2).sum())} sostenidas")
    print(f"  nivel: desviacion tipica {np.nanstd(niv_px[:n]):.2f} px = "
          f"{np.nanstd(niv_gr[:n]):.3f} graduaciones; q05-q95 "
          f"{np.nanpercentile(niv_px[:n],5):+.2f} a {np.nanpercentile(niv_px[:n],95):+.2f} px")
    print(f"  DIAGNOSTICO (no se usa) cuenta de marcas: mediana {np.median(marcas):.0f}, "
          f"rango {marcas.min()}-{marcas.max()}, desviacion {marcas.std():.2f} marcas")

    # --- pasada 3: render ------------------------------------------------------------------
    eo = ALTO_PANEL / alto_img
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
    t_c = np.linspace(0, 1, 80)
    c_izq, c_der = curva(mira["izq"], t_c), curva(mira["der"], t_c)
    ix, iy = 14, 22

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
                grosor = 3
                dy = 4 if e % 2 == 0 else -14
                for panel, esc, c0, c1 in ((prec, er, centros[e], punta_r),
                                           (pano, eo, ext_o[e][2], punta_o)):
                    b = (int(c0[0] * esc), int(c0[1] * esc))
                    p = (int(c1[0] * esc), int(c1[1] * esc))
                    cv2.arrowedLine(panel, b, p, col, grosor, cv2.LINE_AA, tipLength=0.18)
                    si.texto(panel, f"{abs(v):.3f}", (p[0] + 7, p[1] + dy), 0.44, col, 1)
            for panel, esc, c0 in ((prec, er, centros[e]), (pano, eo, ext_o[e][2])):
                q = (int(c0[0] * esc), int(c0[1] * esc))
                if est == 3:
                    cv2.rectangle(panel, (q[0] - 5, q[1] - 5), (q[0] + 5, q[1] + 5),
                                  (30, 30, 30), -1)
                    cv2.rectangle(panel, (q[0] - 5, q[1] - 5), (q[0] + 5, q[1] + 5),
                                  (255, 255, 255), 1)
                    if np.isfinite(v):
                        si.texto(panel, f"{abs(v):.2f}", (q[0] - 12, q[1] - 12), 0.42,
                                 (170, 170, 170), 1)
                else:
                    # Todas las estaciones de agua se dibujan igual: siempre tienen valor,
                    # asi que distinguir el origen del numero solo seria ruido visual.
                    # El CSV conserva el estado para quien quiera separarlo.
                    cv2.circle(panel, q, 5, (255, 255, 255), -1)
                    cv2.circle(panel, q, 5, (20, 20, 20), 1)

        # --- la mira: banda curva, marca del nivel y recuadro rectificado -------------
        for c in (c_izq, c_der):
            for i in range(len(c) - 1):
                cv2.line(pano, (int(c[i][0] * eo), int(c[i][1] * eo)),
                         (int(c[i + 1][0] * eo), int(c[i + 1][1] * eo)),
                         (255, 220, 120), 1, cv2.LINE_AA)
        col_n = (120, 255, 120) if est_niv[k] == 1 else (0, 200, 255)
        if est_niv[k] > 0:
            j = int(np.clip(round(nivel[k]), 0, BANDA_H - 1))
            pl = 0.5 * (curva(mira["izq"], np.array([j / (BANDA_H - 1)]))[0]
                        + curva(mira["der"], np.array([j / (BANDA_H - 1)]))[0])
            d = np.array(mira["der"][1]) - np.array(mira["izq"][1])
            d = d / max(np.hypot(*d), 1e-9)
            c1 = (int((pl[0] - d[0] * 16) * eo), int((pl[1] - d[1] * 16) * eo))
            c2 = (int((pl[0] + d[0] * 16) * eo), int((pl[1] + d[1] * 16) * eo))
            cv2.line(pano, c1, c2, col_n, 2, cv2.LINE_AA)

        banda = cv2.remap(fr, mapx, mapy, cv2.INTER_LINEAR)
        ins = cv2.resize(banda, (INSET_W, INSET_H), interpolation=cv2.INTER_LINEAR)
        pano[iy:iy + INSET_H, ix:ix + INSET_W] = ins
        cv2.rectangle(pano, (ix - 1, iy - 1), (ix + INSET_W, iy + INSET_H),
                      (255, 220, 120), 1)
        # Sin cifras: el nivel se ENSEÑA como la linea sobre la chapa, no como un numero.
        # La serie completa, en px y en graduaciones, sigue yendo al CSV.
        if est_niv[k] > 0:
            yl = iy + int(INSET_H * nivel[k] / BANDA_H)
            cv2.line(pano, (ix - 6, yl), (ix + INSET_W + 6, yl), col_n, 2, cv2.LINE_AA)
        si.texto(pano, "mira rectificada", (ix - 4, iy - 6), 0.42, (255, 220, 120), 1)

        lienzo = np.zeros((ch, cw, 3), np.uint8)
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ALTO_PANEL, x_o:x_o + pw_o] = pano
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ALTO_PANEL, x_r:x_r + pw_r] = prec
        si.texto(lienzo, "vista original de la camara", (x_o, 24), 0.62, (255, 255, 255), 2)
        si.texto(lienzo, "plano rectificado", (x_r, 24), 0.62,
                 (255, 255, 255), 2)
        si.texto(lienzo, f"ventana {cfg['ventana']/fps:.1f} s   DS = {cfg['ds']} px",
                 (x_o + 300, 24), 0.5, (170, 170, 170), 1)
        si.barra_color(lienzo, lo, hi, u, cw - 330, ch - 28)

        vm = vmed[w]
        si.texto(lienzo, f"t = {k/fps:6.2f} s", (x_o, y_pie + 28), 0.66, (255, 255, 255), 2)
        si.texto(lienzo, f"v mediana de la seccion = {vm:.4f} {u}/s"
                 if np.isfinite(vm) else "v mediana = --",
                 (x_o + 180, y_pie + 28), 0.66, (120, 220, 255), 2)
        vw.write(lienzo)
        if (k + 1) % 100 == 0:
            print(f"  {k+1}/{n} fotogramas")
    vw.release()
    cap.release()
    print(f"  render en {time.time()-t0:.1f} s")
    print(f"\nListo: {a.salida} ({os.path.getsize(a.salida)/1e6:.1f} MB, {n/fps:.1f} s)")

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
    print(f"Velocidades por ventana en: {base}_ventanas.csv")
    with open(base + "_nivel.csv", "w", newline="", encoding="utf-8") as f:
        esc = csv.writer(f)
        esc.writerow(["frame", "t_s", "fila_banda", "nivel_px", "nivel_graduaciones",
                      "estado", "salpicadura", "marcas_visibles"])
        for k in range(n):
            esc.writerow([k, round(k / fps, 3),
                          round(float(nivel[k]), 3) if np.isfinite(nivel[k]) else "",
                          round(float(niv_px[k]), 4) if np.isfinite(niv_px[k]) else "",
                          round(float(niv_gr[k]), 5) if np.isfinite(niv_gr[k]) else "",
                          int(est_niv[k]), int(fuera[k]), int(marcas[k])])
    print(f"Nivel por fotograma en: {base}_nivel.csv")


if __name__ == "__main__":
    main()
