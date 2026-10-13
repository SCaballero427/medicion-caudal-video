"""STIV con interfaz: se configura a mano la rectificacion, la seccion y las STI.

Por que existe
--------------
`video_velocidad.py` construye la rectificacion a partir del punto de fuga de las
hiladas de mamposteria y de una focal supuesta. Ese camino es automatico pero
fragil: si el punto de fuga esta mal, TODO lo que viene detras esta mal, y el
error no se ve en ningun sitio hasta que el plano rectificado sale torcido. Aqui
la geometria se pone a mano y se ve mientras se pone.

Va por pasos, y en cada uno el video corre en vivo en las dos vistas -- sobre una
imagen congelada no se ve si la rectificacion deforma el movimiento del agua, que
es justo lo que se va a medir. TAB avanza, RETROCESO vuelve, BARRA pausa.

1. **La rectificacion.** Se arrastran en la imagen original las cuatro esquinas de
   un cuadrilatero que en el mundo real sea un RECTANGULO sobre la superficie del
   agua: dos puntos aguas arriba (margen izquierda y derecha) y dos aguas abajo. No
   hace falta ningun punto de fuga ni ninguna focal. El panel derecho muestra el
   resultado mientras se arrastra, y el recuadro amarillo tiene que salir
   rectangular: esa es la comprobacion.

   Aqui se dan tambien las **dimensiones reales** del rectangulo. El ancho del cauce
   en Boneyard Creek es de unos **6 m**, que es el valor de partida, y con el el
   resultado sale en m/s de verdad. El largo hay que estimarlo aunque no se conozca,
   porque es el que fija la escala EN LA DIRECCION DEL FLUJO, o sea la que mide la
   velocidad; con `u` se declara que no hay medidas y todo vuelve a unidades afines.

2. **La linea de seccion.** Los dos extremos del transecto, arrastrados sobre la
   vista ya rectificada. El flujo se supone perpendicular a ella, y `a`/`A` lo
   desvia si el cauce no cruza de frente.

3. **Las estaciones y las STI.** Cuantas estaciones se reparten por la linea --
   cada una se dibuja numerada en las dos vistas, para saber cual es cual -- y
   cuanto se prolonga su linea de busqueda a lo largo del flujo, junto con el paso
   de muestreo DS, los fotogramas por ventana y los umbrales del control de calidad.

La tecla `p` mide UNA ventana con la configuracion actual y dibuja las flechas
encima, de modo que se puede juzgar antes de gastar los minutos del video entero.
Tambien imprime el angulo medio de las trazas: ese es el numero con el que se
ajusta DS, porque STIV pierde precision lejos de los 45 grados.

Todo lo configurado se guarda en un JSON y se puede recuperar con `--config`, asi
que una vez ajustada la geometria no hay que volver a tocarla.

Uso
---
Sin argumentos toma el video de mayor caudal diurno de Boneyard Creek y la ultima
configuracion guardada, si la hay. Se ejecuta desde la carpeta del caso.

    python stiv_interactivo.py
    python stiv_interactivo.py --video OTRO.mp4 --config salidas/config_stiv_manual.json
    python stiv_interactivo.py --ancho 6.0 --largo 4.2      # dimensiones reales, en m
    python stiv_interactivo.py --sin-interfaz               # reprocesa sin abrir ventana
"""
import argparse
import csv
import json
import os
import time

import cv2
import numpy as np

import escritor_video as ev

# --- valores de partida. Todos se cambian desde la interfaz; esto es solo el punto
# --- desde el que se empieza a arrastrar.
CFG_INICIAL = {
    "cuadrilatero": None,     # 4 puntos en la imagen: AA-izq, AA-der, AB-der, AB-izq
    # 6 m es el ancho aproximado del cauce en Boneyard Creek, dado a mano: es el unico
    # dato metrico del caso y es lo que convierte el resultado en m/s. El largo NO es
    # opcional aunque no se conozca -- fija la escala EN LA DIRECCION DEL FLUJO, que es
    # justo la que mide la velocidad. Si se ignora, se estima cuadrando la vista
    # rectificada hasta que las cosas se vean con su proporcion.
    "ancho_real": 6.0,        # ancho real del cuadrilatero (transversal al flujo)
    "largo_real": 6.0,        # largo real del cuadrilatero (a lo largo del flujo)
    "unidad": "m",            # pasa a "alturas" si se declara que no hay medidas reales
    "esc": 150.0,             # px de la vista rectificada por unidad real
    "margen": 0.35,           # margen alrededor del cuadrilatero, en fracciones de el
    "seccion": [[-0.02, 0.50], [1.02, 0.50]],   # extremos en coordenadas del rectangulo
    "n_est": 21,              # estaciones repartidas por la linea de seccion
    "largo_sti": 3.0,         # longitud de cada linea de busqueda, en unidades reales
    "ds": 6,                  # paso de muestreo de la STI, px de la vista rectificada
    "angulo_flujo": 0.0,      # grados respecto a la normal de la linea de seccion
    "ventana": 96,            # fotogramas por medida
    "paso": 3,                # fotogramas entre medidas
    "bloque": 48,             # lado del bloque del tensor de estructura
    "coh_min": 0.40,          # coherencia minima para aceptar una estacion
    "contraste_min": 1.5,     # desviacion temporal minima: descarta estructuras estaticas
    "cobertura_min": 0.60,    # fraccion de la linea que la camara ve de verdad
}

# Video por defecto. Los videos no estan en el workspace (4.7 GB), viven donde se
# descomprimieron, asi que la ruta es absoluta a proposito.
#
# Este sale de medir los 50 videos utilizables del release con ESTA misma geometria y
# quedarse con el que da el perfil transversal mas coherente. El criterio no fue el
# brillo ni la nitidez del triaje, sino dos numeros que son justo la queja de "resultados
# raros entre estaciones": la rugosidad transversal (mediana de |segunda diferencia| del
# perfil, dividida por la velocidad mediana) y la dispersion temporal de cada estacion.
#   20171118-095500  GH 14.45 ft, Q 326 cfs, 24.20 fps   rugosidad 0.031  temporal 0.027
# Su perfil sube de 0.80 a 0.99 m/s hacia el centro y cae a 0.59 junto a la otra orilla,
# sin saltos entre estaciones vecinas. El siguiente mejor, 20171118-100000, es el MISMO
# episodio cinco minutos despues y da casi lo mismo, que es la comprobacion de que no es
# casualidad de una ventana. Otras opciones medidas:
#   20180610-144500  GH 14.57, Q 338, la de mas estaciones aceptadas (0.87), rugosidad 0.125
#   20180610-082000  GH 14.88, Q 368, el mayor caudal diurno, rugosidad 0.211
#   20170719-063500  rugosidad 0.180 y solo 44 % de aceptacion
# Los nocturnos (11 del release, entre ellos 20180611-050500) estan en infrarrojo, sin
# textura que medir: el triaje los marca no utilizables y el STIV lo confirma.
DIR_VIDEOS = r"C:\Users\Sergio\Desktop\Boneyardcreek\boneyardcreek_video"
RUTA_VIDEO = os.path.join(DIR_VIDEOS, "03337000_bullet_20171118-095500.mp4")

# Todo lo que se escribe cuelga de la carpeta del caso, no del directorio desde el que
# se lanza el comando: si no, lanzarlo desde la raiz del workspace dejaba el video en
# un `salidas/` recien creado alli, lejos del resto de las salidas del caso.
DIR_CASO = os.path.dirname(os.path.abspath(__file__))
# Configuracion por defecto: la ultima guardada, si existe. Asi la geometria se ajusta
# una vez y las siguientes ejecuciones arrancan ya con ella puesta.
RUTA_CONFIG = os.path.join(DIR_CASO, "salidas", "config_stiv_manual.json")
RUTA_SALIDA = os.path.join(DIR_CASO, "salidas", "velocidad_manual.mp4")

ALTO_PANEL = 500
# Margen negro alrededor de la vista original, en fraccion de la altura del panel. Existe
# para que las esquinas del rectangulo se puedan sacar FUERA del cuadro del video: la
# orilla opuesta suele quedarse justo en el borde, o detras de el, y sin margen no habria
# donde soltarlas. La homografia no exige que las esquinas caigan dentro de la imagen.
PAD = 0.16
HUECO = 18
ALTO_CABECERA = 34
ALTO_AYUDA = 210
PALETA = cv2.applyColorMap(np.arange(256, dtype=np.uint8).reshape(-1, 1),
                           cv2.COLORMAP_TURBO).reshape(-1, 3)


# =========================================================================== geometria
def homografia(cfg):
    """Imagen original -> vista rectificada, a partir de las cuatro esquinas.

    El cuadrilatero marcado es, por hipotesis del usuario, un rectangulo real sobre
    el agua. Mandarlo a un rectangulo de px es exactamente la rectificacion: no hace
    falta focal ni punto de fuga, y si el cuadrilatero esta mal el canal sale torcido
    en la vista de al lado, que es la comprobacion.
    """
    q = np.float32(cfg["cuadrilatero"])
    W = cfg["ancho_real"] * cfg["esc"]
    L = cfg["largo_real"] * cfg["esc"]
    mx, my = cfg["margen"] * W, cfg["margen"] * L
    dst = np.float32([[mx, my], [mx + W, my], [mx + W, my + L], [mx, my + L]])
    i2o = cv2.getPerspectiveTransform(q, dst)
    return i2o, int(round(W + 2 * mx)), int(round(L + 2 * my)), (mx, my, W, L)


def a_rect(cfg, uv, caja):
    """Coordenada normalizada del rectangulo (u a lo ancho, v a lo largo) -> px."""
    mx, my, W, L = caja
    return np.array([mx + uv[0] * W, my + uv[1] * L], np.float32)


def geometria_medida(cfg, caja):
    """Centros de estacion, direccion del flujo y mapa de muestreo, en px rectificados.

    Devuelve tambien el numero de muestras por STI, que es lo que fija la longitud de
    la ventana espacial del tensor.
    """
    p0 = a_rect(cfg, cfg["seccion"][0], caja)
    p1 = a_rect(cfg, cfg["seccion"][1], caja)
    n = cfg["n_est"]
    t = np.linspace(0.0, 1.0, n)
    centros = p0[None, :] + (p1 - p0)[None, :] * t[:, None]

    # Direccion del flujo: la normal a la linea de seccion, girada lo que diga
    # angulo_flujo. STIV no mide la direccion, la recibe: por eso es ajustable.
    d = p1 - p0
    d = d / max(np.hypot(*d), 1e-9)
    normal = np.array([d[1], -d[0]], np.float32)
    a = np.radians(cfg["angulo_flujo"])
    flujo = np.array([normal[0] * np.cos(a) - normal[1] * np.sin(a),
                      normal[0] * np.sin(a) + normal[1] * np.cos(a)], np.float32)

    largo_px = cfg["largo_sti"] * cfg["esc"]
    n_mu = max(int(largo_px / cfg["ds"]), 8)
    s = (np.arange(n_mu) - (n_mu - 1) / 2.0) * cfg["ds"]
    pts = centros[:, None, :] + flujo[None, None, :] * s[None, :, None]
    return centros, flujo, pts.astype(np.float32), n_mu


# ================================================================== tensor de estructura
def velocidad(sti, cobertura, cfg):
    """Velocidad (px rectificados por fotograma), coherencia y angulo de las trazas.

    Bloques solapados combinados con mediana ponderada por coherencia: un tensor
    global dejaria que un parche brillante dictara la respuesta.

    Convenio: fila = fotograma, columna = muestra cada DS px a lo largo del flujo.
    Una particula a v px/fotograma avanza v/DS columnas por fila, luego el angulo
    theta de la traza desde el eje de columnas cumple tan(theta) = DS/v.
    """
    b = cfg["bloque"]
    if sti.shape[0] < b or sti.shape[1] < b:
        return np.nan, 0.0, np.nan
    img = sti.astype(np.float32)
    gy, gx = np.gradient(img)
    k = (b, b)
    jxx = cv2.boxFilter(gx * gx, -1, k, normalize=False)
    jyy = cv2.boxFilter(gy * gy, -1, k, normalize=False)
    jxy = cv2.boxFilter(gx * gy, -1, k, normalize=False)
    h = b // 2
    fi = np.arange(h, img.shape[0] - h, h)          # 50 % de solape
    co = np.arange(h, img.shape[1] - h, h)
    if not len(fi) or not len(co):
        return np.nan, 0.0, np.nan
    ii, jj = np.meshgrid(fi, co, indexing="ij")
    a, bb, c = jxx[ii, jj], jyy[ii, jj], jxy[ii, jj]
    ok = cobertura[jj] > 0.99
    tr = a + bb
    val = ok & (tr > 1e-9)
    if val.sum() < 2:
        return np.nan, 0.0, np.nan
    a, bb, c, tr = a[val], bb[val], c[val], tr[val]
    dif = np.sqrt(np.maximum((a - bb) ** 2 + 4 * c * c, 0.0))
    coh = (dif / tr) ** 2
    ang = 0.5 * np.arctan2(2 * c, a - bb) + np.pi / 2
    o = np.argsort(ang)
    ang, coh = ang[o], coh[o]
    ac = np.cumsum(coh)
    th = ang[np.searchsorted(ac, ac[-1] / 2)]
    tn = np.tan(th)
    v = cfg["ds"] / tn if abs(tn) > 1e-6 else np.nan
    return float(v), float(np.median(coh)), float(np.degrees(th))


# ============================================================================== dibujo
def texto(img, s, org, escala=0.5, col=(255, 255, 255), grosor=1):
    """Texto con reborde negro: sobre el agua el blanco solo no se lee."""
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, escala, (0, 0, 0), grosor + 2,
                cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, escala, col, grosor, cv2.LINE_AA)


def color_velocidad(v, lo, hi):
    """Color BGR. Gris si no hay medida. El rango es el de los datos, no [0, vmax]:
    el abanico de velocidades de una seccion es estrecho."""
    if not np.isfinite(v):
        return (120, 120, 120)
    i = int(np.clip((abs(v) - lo) / max(hi - lo, 1e-9), 0, 1) * 255)
    return tuple(int(x) for x in PALETA[i])


def barra_color(lienzo, lo, hi, unidad, x, y, ancho=220, alto=14):
    for j in range(ancho):
        c = PALETA[int(255 * j / (ancho - 1))]
        cv2.line(lienzo, (x + j, y), (x + j, y + alto), tuple(int(v) for v in c), 1)
    cv2.rectangle(lienzo, (x, y), (x + ancho, y + alto), (90, 90, 90), 1)
    texto(lienzo, f"{lo:.2f}", (x - 46, y + 12), 0.45, (170, 170, 170), 1)
    texto(lienzo, f"{hi:.2f} {unidad}/s", (x + ancho + 8, y + 12), 0.45, (170, 170, 170), 1)


# ============================================================================== editor
# El editor va por pasos, y cada paso solo deja tocar lo suyo. El motivo es que los
# tres ajustes estan encadenados: la seccion se dibuja sobre el plano rectificado, y
# las estaciones sobre la seccion. Mezclarlos en una sola pantalla invita a mover el
# cuadrilatero cuando lo que estaba mal era una estacion.
PASOS = [
    ("1/3  RECTIFICACION",
     "arrastra las 4 esquinas hasta encerrar un RECTANGULO real del agua. "
     "El video de la derecha es el resultado en vivo: el cauce debe salir recto y de "
     "ancho constante."),
    ("2/3  LINEA DE SECCION",
     "arrastra los dos extremos verdes hasta cruzar el cauce de margen a margen. "
     "Es el transecto donde se mide; el flujo se supone perpendicular a el."),
    ("3/3  ESTACIONES Y STI",
     "reparte las estaciones sobre la linea y fija cuanto se prolonga cada STI a lo "
     "largo del flujo. Pulsa p para medir una ventana aqui mismo."),
]

AYUDA = [
    [("raton", "arrastrar las 4 esquinas numeradas; pueden salirse del cuadro del video"),
     ("z / Z", "mas / menos margen negro alrededor del video, para sacarlas mas lejos"),
     ("w / h", "ancho / largo REALES del rectangulo, en metros"),
     ("- / +", "margen alrededor del rectangulo    e / E  px por metro -/+"),
     ("u", "declarar que no hay medidas reales (resultado en unidades afines)")],
    [("raton", "arrastrar los dos extremos verdes de la seccion"),
     ("a / A", "girar la direccion del flujo -/+ 1 grado respecto a la normal")],
    [("n / N", "numero de estaciones -/+       l / L  longitud de la STI -/+"),
     ("d / D", "paso de muestreo DS -/+        v / V  fotogramas por ventana -/+"),
     ("b / B", "bloque del tensor -/+          c / C  coherencia minima -/+"),
     ("p", "PROBAR: mide una ventana aqui y dibuja las flechas y sus valores")],
]

COMUNES = [
    ("TAB", "paso siguiente        RETROCESO  paso anterior        BARRA  pausar el video"),
    ("s", "guardar la configuracion    INTRO  procesar el video entero    ESC  salir"),
]


class Editor:
    def __init__(self, video, cfg, salida):
        self.video, self.cfg, self.salida = video, cfg, salida
        self.cap = cv2.VideoCapture(video)
        if not self.cap.isOpened():
            raise SystemExit(f"No se pudo abrir {video}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.ntot = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.ancho_img = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.alto_img = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.paso = 0             # 0 rectificacion, 1 seccion, 2 estaciones
        self.reproduciendo = True  # el video corre en vivo en las dos vistas: sobre una
                                   # imagen congelada no se ve si la rectificacion deforma
                                   # el movimiento del agua, que es lo que se va a medir
        self.frame0 = 0
        ok, self.base = self.cap.read()
        if not ok:
            raise SystemExit(f"No se pudo leer ningun fotograma de {video}")
        if cfg["cuadrilatero"] is None:
            # Cuadrilatero de partida: un trapecio centrado, con la perspectiva tipica
            # de una camara oblicua. No pretende ser correcto, solo estar a mano.
            w, h = self.ancho_img, self.alto_img
            cfg["cuadrilatero"] = [[0.32 * w, 0.42 * h], [0.68 * w, 0.42 * h],
                                   [0.92 * w, 0.88 * h], [0.08 * w, 0.88 * h]]
        self.arrastrando = None
        self.previa = None          # resultado de la ultima prueba, para dibujarlo
        self.mensaje = ""
        self.pad_frac = PAD         # cuanto margen hay alrededor del video; z / Z lo cambia

    # ------------------------------------------------------------------------- pintado
    def a_orig(self, p):
        """Punto en pixeles del video -> pixel del panel original (con su margen)."""
        return (int(round(p[0] * self.eo)) + self.pad,
                int(round(p[1] * self.eo)) + self.pad)

    def componer(self):
        cfg = self.cfg
        i2o, ow, oh, caja = homografia(cfg)
        self.i2o, self.o2i, self.caja = i2o, np.linalg.inv(i2o), caja
        self.ow, self.oh = ow, oh
        rect = cv2.warpPerspective(self.base, i2o, (ow, oh), flags=cv2.INTER_LINEAR)

        # La vista original se dibuja encogida dentro de un panel con margen negro, de
        # modo que hay sitio fisico donde soltar una esquina que caiga fuera del video.
        self.pad = int(ALTO_PANEL * self.pad_frac)
        self.eo = (ALTO_PANEL - 2 * self.pad) / self.alto_img
        self.er = ALTO_PANEL / oh
        pw_o = int(self.ancho_img * self.eo) + 2 * self.pad
        pw_r = int(ow * self.er)
        pano = np.zeros((ALTO_PANEL, pw_o, 3), np.uint8)
        vista = cv2.resize(self.base, (pw_o - 2 * self.pad, ALTO_PANEL - 2 * self.pad),
                           interpolation=cv2.INTER_AREA)
        pano[self.pad:ALTO_PANEL - self.pad, self.pad:pw_o - self.pad] = vista
        cv2.rectangle(pano, (self.pad, self.pad), (pw_o - self.pad, ALTO_PANEL - self.pad),
                      (70, 70, 70), 1)      # el borde real del video, para saber donde esta
        prec = cv2.resize(rect, (pw_r, ALTO_PANEL), interpolation=cv2.INTER_AREA)
        self.x_o, self.x_r = HUECO, HUECO + pw_o + HUECO
        self.pw_o, self.pw_r = pw_o, pw_r
        cw = self.x_r + pw_r + HUECO
        ch = ALTO_CABECERA + ALTO_PANEL + ALTO_AYUDA

        centros, flujo, pts, n_mu = geometria_medida(cfg, caja)

        # --- el cuadrilatero, sobre la original -------------------------------------
        q = np.float32(cfg["cuadrilatero"])
        etiquetas = ["1 aguas arriba izq", "2 aguas arriba der",
                     "3 aguas abajo der", "4 aguas abajo izq"]
        for i in range(4):
            cv2.line(pano, self.a_orig(q[i]), self.a_orig(q[(i + 1) % 4]),
                     (0, 220, 255), 2, cv2.LINE_AA)
        for i in range(4):
            a = self.a_orig(q[i])
            r = 8 if self.paso == 0 else 4
            cv2.circle(pano, a, r, (0, 220, 255), -1)
            cv2.circle(pano, a, r, (20, 20, 20), 2)
            if self.paso == 0:
                texto(pano, etiquetas[i], (a[0] + 12, a[1] + 5), 0.45, (0, 220, 255), 1)
        # El mismo cuadrilatero en la rectificada tiene que salir como un rectangulo
        # perfecto: es la comprobacion visual de que la homografia es la que se cree.
        mx, my, W, L = caja
        cv2.rectangle(prec, (int(mx * self.er), int(my * self.er)),
                      (int((mx + W) * self.er), int((my + L) * self.er)),
                      (0, 220, 255), 2)

        # --- la seccion y las lineas de busqueda, en las dos vistas ------------------
        # En el paso 1 no se dibujan: alli lo unico que se juzga es si el agua sale
        # rectificada, y las lineas encima solo estorban.
        lo = hi = None
        if self.previa is not None:
            lo, hi = self.previa["lo"], self.previa["hi"]
        if self.paso >= 1:
            pr = np.float32([a_rect(cfg, cfg["seccion"][0], caja),
                             a_rect(cfg, cfg["seccion"][1], caja)])
            po = cv2.perspectiveTransform(pr.reshape(1, 2, 2), self.o2i).reshape(2, 2)
            cv2.line(prec, tuple((pr[0] * self.er).astype(int)),
                     tuple((pr[1] * self.er).astype(int)), (120, 255, 120), 2, cv2.LINE_AA)
            cv2.line(pano, self.a_orig(po[0]), self.a_orig(po[1]),
                     (120, 255, 120), 2, cv2.LINE_AA)
        for e in range(cfg["n_est"] if self.paso >= 2 else 0):
            v = np.nan
            if self.previa is not None:
                v = self.previa["v"][e]
            col = color_velocidad(v, lo, hi) if self.previa is not None else (255, 255, 255)
            pr = np.float32([pts[e, 0], pts[e, -1]])
            po = cv2.perspectiveTransform(pr.reshape(1, 2, 2), self.o2i).reshape(2, 2)
            cv2.line(prec, tuple((pr[0] * self.er).astype(int)),
                     tuple((pr[1] * self.er).astype(int)), (255, 255, 255), 1, cv2.LINE_AA)
            cv2.line(pano, self.a_orig(po[0]), self.a_orig(po[1]),
                     (255, 255, 255), 1, cv2.LINE_AA)
            cr = centros[e]
            co_ = cv2.perspectiveTransform(cr.reshape(1, 1, 2), self.o2i).reshape(2)
            if self.previa is not None and np.isfinite(v):
                punta = cr + flujo * (abs(v) / max(hi, 1e-9)) * 0.45 * L * np.sign(v)
                pu = cv2.perspectiveTransform(
                    punta.astype(np.float32).reshape(1, 1, 2), self.o2i).reshape(2)
                cv2.arrowedLine(prec, tuple((cr * self.er).astype(int)),
                                tuple((punta * self.er).astype(int)), col, 3,
                                cv2.LINE_AA, tipLength=0.18)
                cv2.arrowedLine(pano, self.a_orig(co_), self.a_orig(pu), col, 3,
                                cv2.LINE_AA, tipLength=0.18)
                dy = 4 if e % 2 == 0 else -14
                for panel, p in ((prec, tuple((punta * self.er).astype(int))),
                                 (pano, self.a_orig(pu))):
                    texto(panel, f"{abs(v):.3f}", (p[0] + 7, p[1] + dy), 0.44, col, 1)
            for panel, q_ in ((prec, tuple((cr * self.er).astype(int))),
                              (pano, self.a_orig(co_))):
                if self.previa is not None and self.previa["medida"][e]:
                    cv2.circle(panel, q_, 5, (255, 255, 255), -1)
                    cv2.circle(panel, q_, 5, (20, 20, 20), 1)
                else:
                    cv2.rectangle(panel, (q_[0] - 5, q_[1] - 5), (q_[0] + 5, q_[1] + 5),
                                  (0, 165, 255) if self.previa is not None else (200, 200, 200), -1)
                    cv2.rectangle(panel, (q_[0] - 5, q_[1] - 5), (q_[0] + 5, q_[1] + 5),
                                  (20, 20, 20), 1)
                # El numero de cada estacion: es la unica forma de saber cual falla
                # cuando la prueba rechaza una, y de leer el CSV despues.
                texto(panel, str(e), (q_[0] - 4, q_[1] - 12), 0.4, (230, 230, 230), 1)
        # extremos arrastrables de la seccion
        if self.paso >= 1:
            for i in (0, 1):
                p = a_rect(cfg, cfg["seccion"][i], caja) * self.er
                r = 9 if self.paso == 1 else 5
                cv2.circle(prec, (int(p[0]), int(p[1])), r, (120, 255, 120), -1)
                cv2.circle(prec, (int(p[0]), int(p[1])), r, (20, 20, 20), 2)

        lienzo = np.zeros((ch, cw, 3), np.uint8)
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ALTO_PANEL, self.x_o:self.x_o + pw_o] = pano
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ALTO_PANEL, self.x_r:self.x_r + pw_r] = prec
        titulo, instruccion = PASOS[self.paso]
        texto(lienzo, titulo, (self.x_o, 24), 0.66, (0, 255, 255), 2)
        texto(lienzo, instruccion, (self.x_o + 260, 24), 0.5, (230, 230, 230), 1)
        texto(lienzo, "vista original", (self.x_o, ALTO_CABECERA + 22), 0.55,
              (255, 255, 255), 2)
        texto(lienzo, "vista rectificada - el recuadro amarillo debe salir rectangular",
              (self.x_r, ALTO_CABECERA + 22), 0.55, (255, 255, 255), 2)

        # --- panel de ayuda y estado -------------------------------------------------
        y = ALTO_CABECERA + ALTO_PANEL + 24
        u = cfg["unidad"]
        estado = (f"{cfg['n_est']} estaciones   STI {cfg['largo_sti']:.2f} {u} "
                  f"({n_mu} muestras de DS={cfg['ds']} px)   ventana {cfg['ventana']} "
                  f"fot ({cfg['ventana']/self.fps:.1f} s)   bloque {cfg['bloque']}   "
                  f"coh>={cfg['coh_min']:.2f}   angulo {cfg['angulo_flujo']:+.1f} deg")
        texto(lienzo, estado, (self.x_o, y), 0.52, (120, 220, 255), 1)
        texto(lienzo, f"rectangulo {cfg['ancho_real']:.3f} x {cfg['largo_real']:.3f} {u}"
                      f"   escala {cfg['esc']:.0f} px/{u}   vista {ow}x{oh} px"
                      f"   fotograma de referencia {self.frame0} de {self.ntot}",
              (self.x_o, y + 22), 0.52, (200, 200, 200), 1)
        if cfg["unidad"] == "alturas":
            aviso, col = ("sin medidas reales: el resultado es afin, correcto salvo una "
                          "constante global. Pulsa w y h para dar metros.", (0, 165, 255))
        elif n_mu < cfg["bloque"]:
            aviso, col = (f"la STI tiene {n_mu} muestras y el bloque del tensor pide "
                          f"{cfg['bloque']}: alarga la STI (L) o baja DS (d) o el bloque (b)",
                          (0, 100, 255))
        else:
            aviso, col = (f"resultado en m/s: el rectangulo mide "
                          f"{cfg['ancho_real']:.2f} x {cfg['largo_real']:.2f} m. "
                          f"El LARGO fija la escala en la direccion del flujo, que es la "
                          f"que mide la velocidad.", (150, 255, 150))
        texto(lienzo, aviso, (self.x_o, y + 44), 0.5, col, 1)
        for i, (k, d) in enumerate(AYUDA[self.paso] + COMUNES):
            yy = y + 72 + i * 16
            texto(lienzo, f"{k:>7s}", (self.x_o, yy), 0.42, (255, 255, 120), 1)
            texto(lienzo, d, (self.x_o + 70, yy), 0.42, (170, 170, 170), 1)
        if self.mensaje:
            texto(lienzo, self.mensaje, (self.x_o + 760, y + 72), 0.55, (150, 255, 150), 1)
        if self.previa is not None:
            barra_color(lienzo, lo, hi, u, cw - 330, ch - 26)
        return lienzo

    # ---------------------------------------------------------------------- interaccion
    def raton(self, evento, x, y, flags, _):
        yy = y - ALTO_CABECERA
        if evento == cv2.EVENT_LBUTTONDOWN:
            # Cada paso solo deja mover lo suyo: en el 2 y el 3 el cuadrilatero queda
            # fijo, para no deshacer sin querer la rectificacion ya ajustada.
            if (self.paso == 0 and self.x_o <= x < self.x_o + self.pw_o
                    and 0 <= yy < ALTO_PANEL):
                p = np.array([(x - self.x_o - self.pad) / self.eo,
                              (yy - self.pad) / self.eo])
                d = [np.hypot(*(np.array(q) - p)) for q in self.cfg["cuadrilatero"]]
                if min(d) < 60 / self.eo:
                    self.arrastrando = ("q", int(np.argmin(d)))
            elif (self.paso >= 1 and self.x_r <= x < self.x_r + self.pw_r
                    and 0 <= yy < ALTO_PANEL):
                p = np.array([(x - self.x_r) / self.er, yy / self.er])
                ext = [a_rect(self.cfg, s, self.caja) for s in self.cfg["seccion"]]
                d = [np.hypot(*(e - p)) for e in ext]
                if min(d) < 40 / self.er:
                    self.arrastrando = ("s", int(np.argmin(d)))
        elif evento == cv2.EVENT_MOUSEMOVE and self.arrastrando:
            tipo, i = self.arrastrando
            # Se limita al panel, no a la imagen: fuera del panel el punto ya no seria
            # visible ni se podria volver a agarrar.
            x = int(np.clip(x, self.x_o, self.x_o + self.pw_o + self.pw_r + HUECO))
            yy = int(np.clip(yy, 0, ALTO_PANEL))
            if tipo == "q":
                # Sin recortar a la imagen: una esquina puede quedar fuera del cuadro,
                # y de hecho suele hacer falta cuando la orilla opuesta no se ve entera.
                self.cfg["cuadrilatero"][i] = [(x - self.x_o - self.pad) / self.eo,
                                               (yy - self.pad) / self.eo]
            else:
                mx, my, W, L = self.caja
                self.cfg["seccion"][i] = [((x - self.x_r) / self.er - mx) / W,
                                          (yy / self.er - my) / L]
            self.previa = None       # la medida anterior ya no corresponde a esta geometria
        elif evento == cv2.EVENT_LBUTTONUP:
            self.arrastrando = None

    def pedir_numero(self, titulo, actual):
        """Entrada de un numero por teclado, dibujada sobre el propio lienzo."""
        s = ""
        while True:
            img = self.componer()
            texto(img, f"{titulo} (ahora {actual}): {s}_    INTRO acepta, ESC cancela",
                  (self.x_o, ALTO_CABECERA + ALTO_PANEL + 90), 0.7, (0, 255, 255), 2)
            cv2.imshow(self.win, img)
            k = cv2.waitKey(0) & 0xFF
            if k == 13:
                try:
                    return float(s)
                except ValueError:
                    return actual
            if k == 27:
                return actual
            if k == 8:
                s = s[:-1]
            elif chr(k) in "0123456789.":
                s += chr(k)

    # --------------------------------------------------------------------------- prueba
    def probar(self):
        """Mide UNA ventana empezando en el fotograma de referencia y guarda el
        resultado para dibujarlo. Es el bucle corto: ver el efecto de un cambio sin
        pagar el video entero."""
        cfg = self.cfg
        t0 = time.time()
        # La prueba mide donde este parado el video. Se pausa sola: si siguiera
        # corriendo, las flechas dibujadas dejarian de corresponder a lo que se ve.
        self.reproduciendo = False
        self.frame0 = min(self.frame0, max(self.ntot - cfg["ventana"] - 1, 0))
        sti, cob = construir_sti(self.video, cfg, self.frame0, cfg["ventana"],
                                 self.i2o, self.ow, self.oh, self.caja)
        v, coh, ang, med = medir_ventana(sti, cob, cfg)
        vg = v * self.fps / cfg["esc"]
        vg[~med] = np.nan
        if np.isfinite(vg).any():
            lo, hi = np.nanpercentile(np.abs(vg), [2, 98])
            hi = max(hi, lo + 1e-6)
        else:
            lo, hi = 0.0, 1.0
        self.previa = {"v": vg, "lo": lo, "hi": hi, "medida": med}
        ang_med = np.nanmedian(ang[med]) if med.any() else np.nan
        self.mensaje = (f"{int(med.sum())}/{cfg['n_est']} estaciones, "
                        f"mediana {np.nanmedian(np.abs(vg)):.4f} {cfg['unidad']}/s")
        print(f"\nprueba en el fotograma {self.frame0} ({time.time()-t0:.1f} s): "
              f"{int(med.sum())} de {cfg['n_est']} estaciones aceptadas")
        print(f"  velocidad mediana {np.nanmedian(np.abs(vg)):.4f} {cfg['unidad']}/s")
        print(f"  angulo medio de las trazas {ang_med:.1f} deg  "
              f"(lo ideal son 45; sube DS si pasa de 60, bajalo si baja de 30)")

    # ----------------------------------------------------------------------------- bucle
    def correr(self):
        self.win = "STIV interactivo"
        cv2.namedWindow(self.win, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(self.win, self.raton)
        cfg = self.cfg
        procesar = False
        espera = max(int(1000 / max(self.fps, 1)), 1)
        while True:
            # El video corre solo. Al llegar al final vuelve a empezar, de modo que se
            # puede dejar puesto mientras se arrastra un punto y ver el efecto sobre
            # agua en movimiento, no sobre una foto.
            if self.reproduciendo and self.arrastrando is None:
                ok, fr = self.cap.read()
                if not ok:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok, fr = self.cap.read()
                if ok:
                    self.base = fr
                    self.frame0 = max(int(self.cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1, 0)
            cv2.imshow(self.win, self.componer())
            k = cv2.waitKey(espera if self.reproduciendo else 20) & 0xFF
            if k == 255:
                continue
            self.mensaje = ""
            if k == 27:
                break
            elif k == 13:
                if self.paso < 2:
                    self.paso += 1      # INTRO tambien avanza mientras queden pasos
                    continue
                procesar = True
                break
            elif k == 9:                                     # TAB
                self.paso = min(2, self.paso + 1)
                continue
            elif k == 8:                                     # RETROCESO
                self.paso = max(0, self.paso - 1)
                continue
            elif k == 32:                                    # BARRA
                self.reproduciendo = not self.reproduciendo
                continue
            elif k == ord("z"):
                self.pad_frac = min(0.40, self.pad_frac + 0.04)
            elif k == ord("Z"):
                self.pad_frac = max(0.02, self.pad_frac - 0.04)
            elif k == ord("u"):
                cfg["unidad"] = "alturas"
                cfg["ancho_real"] = cfg["largo_real"] = 1.0
            elif k == ord("n"):
                cfg["n_est"] = max(3, cfg["n_est"] - 1)
            elif k == ord("N"):
                cfg["n_est"] += 1
            elif k == ord("l"):
                cfg["largo_sti"] = max(0.05, cfg["largo_sti"] - 0.05)
            elif k == ord("L"):
                cfg["largo_sti"] += 0.05
            elif k == ord("d"):
                cfg["ds"] = max(1, cfg["ds"] - 1)
            elif k == ord("D"):
                cfg["ds"] += 1
            elif k == ord("v"):
                cfg["ventana"] = max(cfg["bloque"] + 4, cfg["ventana"] - 6)
            elif k == ord("V"):
                cfg["ventana"] += 6
            elif k == ord("b"):
                cfg["bloque"] = max(8, cfg["bloque"] - 8)
            elif k == ord("B"):
                cfg["bloque"] += 8
            elif k == ord("c"):
                cfg["coh_min"] = max(0.0, cfg["coh_min"] - 0.05)
            elif k == ord("C"):
                cfg["coh_min"] = min(1.0, cfg["coh_min"] + 0.05)
            elif k == ord("a"):
                cfg["angulo_flujo"] -= 1.0
            elif k == ord("A"):
                cfg["angulo_flujo"] += 1.0
            elif k in (ord("-"), ord("_")):
                cfg["margen"] = max(0.0, cfg["margen"] - 0.05)
            elif k in (ord("+"), ord("=")):
                cfg["margen"] += 0.05
            elif k == ord("e"):
                cfg["esc"] = max(20.0, cfg["esc"] - 20.0)
            elif k == ord("E"):
                cfg["esc"] += 20.0
            elif k == ord("w"):
                cfg["ancho_real"] = self.pedir_numero("ancho REAL del rectangulo",
                                                      cfg["ancho_real"])
                cfg["unidad"] = "m"
            elif k == ord("h"):
                cfg["largo_real"] = self.pedir_numero("largo REAL del rectangulo",
                                                      cfg["largo_real"])
                cfg["unidad"] = "m"
            elif k == ord("p"):
                self.probar()
            elif k == ord("s"):
                guardar_config(cfg, self.salida)
                self.mensaje = "configuracion guardada"
            if k not in (ord("p"), ord("s")):
                self.previa = None      # cualquier cambio invalida la medida dibujada
        cv2.destroyAllWindows()
        self.cap.release()
        return procesar


# ================================================================= medida sobre el video
def construir_sti(video, cfg, inicio, n, i2o, ow, oh, caja):
    """STI de n fotogramas: (fotograma, estacion, muestra) y la cobertura por muestra."""
    _, _, pts, n_mu = geometria_medida(cfg, caja)
    mapx = np.ascontiguousarray(pts[:, :, 0])
    mapy = np.ascontiguousarray(pts[:, :, 1])
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(inicio))
    ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    blanco = cv2.warpPerspective(np.full((alto, ancho), 255, np.uint8), i2o, (ow, oh))
    cobertura = (cv2.remap(blanco, mapx, mapy, cv2.INTER_NEAREST) > 128).astype(np.float32)
    sti = np.zeros((n, cfg["n_est"], n_mu), np.float32)
    for k in range(n):
        ok, fr = cap.read()
        if not ok:
            sti = sti[:k]
            break
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        r = cv2.warpPerspective(g, i2o, (ow, oh), flags=cv2.INTER_LINEAR)
        # Antialias ANTES de muestrear cada DS px: sin esto el submuestreo inventa
        # orientaciones. Es isotropo a proposito.
        r = cv2.GaussianBlur(r, (0, 0), max(cfg["ds"] / 2.0, 0.6))
        sti[k] = cv2.remap(r, mapx, mapy, cv2.INTER_LINEAR)
        if n > 200 and (k + 1) % 100 == 0:
            print(f"  {k+1}/{n} fotogramas")
    cap.release()
    return sti, cobertura


def normalizar(sti):
    """Normalizacion temporal por posicion: el reflejo especular es estatico en el
    espacio, restarlo posicion a posicion lo elimina sin ningun parametro. Devuelve
    tambien el contraste temporal, que es el filtro que descarta los muros."""
    mu, sd = sti.mean(0), sti.std(0)
    contraste = np.median(sd, axis=1)
    stin = (sti - mu) / np.maximum(sd, 1e-3)
    stin[:, sd < 1.0] = 0.0
    return stin, contraste


def medir_ventana(sti, cobertura, cfg):
    """Velocidad, coherencia, angulo y aceptacion de cada estacion en una ventana."""
    stin, contraste = normalizar(sti)
    n = cfg["n_est"]
    v = np.full(n, np.nan)
    coh = np.zeros(n)
    ang = np.full(n, np.nan)
    for e in range(n):
        v[e], coh[e], ang[e] = velocidad(stin[:, e, :], cobertura[e], cfg)
    med = ((cobertura.mean(1) >= cfg["cobertura_min"]) & (contraste >= cfg["contraste_min"])
           & (coh >= cfg["coh_min"]) & np.isfinite(v))
    return v, coh, ang, med


def guardar_config(cfg, salida):
    ruta = os.path.join(os.path.dirname(salida) or ".", "config_stiv_manual.json")
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print(f"configuracion guardada en {ruta}")
    return ruta


# ==================================================================== proceso del video
def procesar(video, cfg, salida, n_max=0):
    """Mide en ventanas deslizantes sobre el video entero y renderiza el resultado.

    Mismo lenguaje visual que `video_velocidad.py`: dos vistas con el mismo dibujo
    encima, un fotograma de salida por fotograma de entrada (tiempo real) y cada uno
    con la medida de la ventana cuyo centro le queda mas cerca.
    """
    i2o, ow, oh, caja = homografia(cfg)
    o2i = np.linalg.inv(i2o)
    centros, flujo, pts, n_mu = geometria_medida(cfg, caja)
    mx, my, W, L = caja

    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    ntot = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    n = ntot if n_max <= 0 else min(n_max, ntot)
    u = cfg["unidad"]

    print(f"\n{os.path.basename(video)}: {ntot} fotogramas a {fps:.2f} fps "
          f"({ntot/fps:.1f} s); se procesan {n}")
    print(f"vista rectificada {ow}x{oh} px, {cfg['n_est']} estaciones, "
          f"STI de {n_mu} muestras cada {cfg['ds']} px")

    print(f"\nPasada 1/2 - rectificando y muestreando {n} fotogramas")
    t0 = time.time()
    sti, cobertura = construir_sti(video, cfg, 0, n, i2o, ow, oh, caja)
    n = sti.shape[0]
    print(f"  STI de {n} fotogramas en {time.time()-t0:.1f} s")

    stin, contraste = normalizar(sti)
    admisible = (cobertura.mean(1) >= cfg["cobertura_min"]) & (contraste >= cfg["contraste_min"])
    print(f"\nEstaciones admisibles por cobertura y contraste: {admisible.sum()} "
          f"de {cfg['n_est']}")
    for e in range(cfg["n_est"]):
        motivo = []
        if cobertura[e].mean() < cfg["cobertura_min"]:
            motivo.append("fuera de campo")
        if contraste[e] < cfg["contraste_min"]:
            motivo.append("estructura estatica")
        print(f"  {e:3d}  cobertura {cobertura[e].mean():.2f}  contraste {contraste[e]:7.2f}"
              f"  {'OK' if admisible[e] else 'RECHAZADA: ' + ', '.join(motivo)}")

    inicios = np.arange(0, max(n - cfg["ventana"], 0) + 1, cfg["paso"])
    centros_t = inicios + cfg["ventana"] // 2
    V = np.full((len(inicios), cfg["n_est"]), np.nan)
    MED = np.zeros((len(inicios), cfg["n_est"]), bool)
    print(f"\nMidiendo {len(inicios)} ventanas x {cfg['n_est']} estaciones")
    t0 = time.time()
    for w, i0 in enumerate(inicios):
        for e in range(cfg["n_est"]):
            if not admisible[e]:
                continue
            v, c, _ = velocidad(stin[i0:i0 + cfg["ventana"], e, :], cobertura[e], cfg)
            if np.isfinite(v) and c >= cfg["coh_min"]:
                V[w, e] = v
                MED[w, e] = True
    print(f"  {len(inicios)} ventanas en {time.time()-t0:.1f} s")

    # px rectificados por fotograma -> unidades reales por segundo
    Vg = V * fps / cfg["esc"]
    if np.isfinite(Vg).any():
        lo, hi = np.nanpercentile(np.abs(Vg), [2, 98])
        hi = max(hi, lo + 1e-6)
    else:
        lo, hi = 0.0, 1.0
    vmed = np.nanmedian(np.abs(Vg), axis=1)
    print(f"\nEstaciones medidas por ventana: mediana {np.median(MED.sum(1)):.0f} "
          f"de las {admisible.sum()} admisibles")
    print(f"Velocidad mediana de la seccion: {np.nanmedian(vmed):.4f} {u}/s "
          f"(rango {np.nanmin(vmed):.4f} - {np.nanmax(vmed):.4f})")

    # --- render -----------------------------------------------------------------------
    eo = ALTO_PANEL / alto
    er = ALTO_PANEL / oh
    pw_o, pw_r = int(ancho * eo), int(ow * er)
    x_o, x_r = HUECO, HUECO + pw_o + HUECO
    cw = x_r + pw_r + HUECO
    ch = ALTO_CABECERA + ALTO_PANEL + 96

    print(f"\nPasada 2/2 - render de {n} fotogramas a {cw}x{ch}, {fps:.2f} fps (tiempo real)")
    os.makedirs(os.path.dirname(salida) or ".", exist_ok=True)
    vw = ev.abrir(salida, fps, (cw, ch))
    if not vw.isOpened():
        raise SystemExit("No se pudo abrir el escritor de video.")

    # Extremos de cada linea de busqueda y centro de cada estacion, en las dos vistas.
    # En la original se proyectan con o2i, de modo que la perspectiva los inclina sola.
    ext_r = np.float32([[pts[e, 0], pts[e, -1], centros[e]] for e in range(cfg["n_est"])])
    ext_o = cv2.perspectiveTransform(ext_r.reshape(1, -1, 2), o2i).reshape(-1, 3, 2)

    cap = cv2.VideoCapture(video)
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
            v = Vg[w, e]
            col = color_velocidad(v, lo, hi)
            for panel, esc, p in ((prec, er, ext_r[e]), (pano, eo, ext_o[e])):
                a = (int(p[0][0] * esc), int(p[0][1] * esc))
                b = (int(p[1][0] * esc), int(p[1][1] * esc))
                if admisible[e]:
                    cv2.line(panel, a, b, (255, 255, 255), 1, cv2.LINE_AA)
                else:
                    for f in np.linspace(0, 1, 10):
                        cv2.circle(panel, (int(a[0] + (b[0] - a[0]) * f),
                                           int(a[1] + (b[1] - a[1]) * f)), 1,
                                   (170, 170, 170), -1)
            if np.isfinite(v):
                punta_r = centros[e] + flujo * (abs(v) / hi) * 0.45 * L * np.sign(v)
                punta_o = cv2.perspectiveTransform(
                    punta_r.astype(np.float32).reshape(1, 1, 2), o2i).reshape(2)
                dy = 4 if e % 2 == 0 else -14
                for panel, esc, c0, c1 in ((prec, er, centros[e], punta_r),
                                           (pano, eo, ext_o[e][2], punta_o)):
                    a = (int(c0[0] * esc), int(c0[1] * esc))
                    b = (int(c1[0] * esc), int(c1[1] * esc))
                    cv2.arrowedLine(panel, a, b, col, 3, cv2.LINE_AA, tipLength=0.18)
                    texto(panel, f"{abs(v):.3f}", (b[0] + 7, b[1] + dy), 0.44, col, 1)
            for panel, esc, c0 in ((prec, er, centros[e]), (pano, eo, ext_o[e][2])):
                q_ = (int(c0[0] * esc), int(c0[1] * esc))
                if not admisible[e]:
                    cv2.rectangle(panel, (q_[0] - 5, q_[1] - 5), (q_[0] + 5, q_[1] + 5),
                                  (30, 30, 30), -1)
                    cv2.rectangle(panel, (q_[0] - 5, q_[1] - 5), (q_[0] + 5, q_[1] + 5),
                                  (255, 255, 255), 1)
                elif MED[w, e]:
                    cv2.circle(panel, q_, 5, (255, 255, 255), -1)
                    cv2.circle(panel, q_, 5, (20, 20, 20), 1)
                else:
                    cv2.rectangle(panel, (q_[0] - 6, q_[1] - 6), (q_[0] + 6, q_[1] + 6),
                                  (0, 165, 255), -1)
                    cv2.rectangle(panel, (q_[0] - 6, q_[1] - 6), (q_[0] + 6, q_[1] + 6),
                                  (20, 20, 20), 1)

        lienzo = np.zeros((ch, cw, 3), np.uint8)
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ALTO_PANEL, x_o:x_o + pw_o] = pano
        lienzo[ALTO_CABECERA:ALTO_CABECERA + ALTO_PANEL, x_r:x_r + pw_r] = prec
        texto(lienzo, "vista original de la camara", (x_o, 24), 0.62, (255, 255, 255), 2)
        texto(lienzo, "plano de agua rectificado (aqui se mide)", (x_r, 24), 0.62,
              (255, 255, 255), 2)
        texto(lienzo, f"ventana {cfg['ventana']/fps:.1f} s   DS = {cfg['ds']} px   "
                      f"coherencia min = {cfg['coh_min']:.2f}",
              (x_o + 400, 24), 0.5, (170, 170, 170), 1)
        barra_color(lienzo, lo, hi, u, cw - 330, ch - 30)

        y = ALTO_CABECERA + ALTO_PANEL
        texto(lienzo, f"t = {k/fps:6.2f} s", (x_o, y + 30), 0.68, (255, 255, 255), 2)
        texto(lienzo, f"v mediana de la seccion = {vmed[w]:.4f} {u}/s"
              if np.isfinite(vmed[w]) else "v mediana = --",
              (x_o + 190, y + 30), 0.68, (120, 220, 255), 2)
        texto(lienzo, f"estaciones medidas: {int(MED[w].sum())} de {cfg['n_est']}",
              (x_o + 760, y + 30), 0.68, (150, 255, 150), 2)
        texto(lienzo, "circulo = medida   cuadro naranja = sin coherencia en esta ventana"
                      "   cuadro negro = rechazada (estructura estatica o fuera de campo)",
              (x_o, y + 58), 0.46, (170, 170, 170), 1)
        leyenda = ("geometria puesta a mano sobre 4 esquinas; la direccion de las flechas "
                   "no se mide, es la normal a la seccion")
        if u == "alturas":
            leyenda += ".  Unidades afines: correctas salvo una constante global."
        texto(lienzo, leyenda, (x_o, y + 80), 0.46, (140, 140, 140), 1)
        vw.write(lienzo)
        if (k + 1) % 100 == 0:
            print(f"  {k+1}/{n} fotogramas")
    vw.release()
    cap.release()
    print(f"  render en {time.time()-t0:.1f} s")
    print(f"\nListo: {salida} ({os.path.getsize(salida)/1e6:.1f} MB, {n/fps:.1f} s)")

    # El CSV toma el nombre del video, no uno fijo: con un nombre fijo, un render de
    # prueba en la misma carpeta pisaba las series de la corrida buena.
    csv_out = os.path.splitext(salida)[0] + "_ventanas.csv"
    with open(csv_out, "w", newline="", encoding="utf-8") as f:
        esc = csv.writer(f)
        esc.writerow(["ventana", "frame_centro", "t_s"]
                     + [f"v{e}_{u}_s" for e in range(cfg["n_est"])]
                     + [f"medida{e}" for e in range(cfg["n_est"])] + [f"v_mediana_{u}_s"])
        for w in range(len(inicios)):
            esc.writerow([w, int(centros_t[w]), round(centros_t[w] / fps, 3)]
                         + [round(float(x), 5) if np.isfinite(x) else "" for x in Vg[w]]
                         + [int(x) for x in MED[w]]
                         + [round(float(vmed[w]), 5) if np.isfinite(vmed[w]) else ""])
    print(f"Series por ventana en: {csv_out}")
    guardar_config(cfg, salida)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", default=RUTA_VIDEO,
                    help="por defecto, el video de mayor caudal diurno de Boneyard Creek")
    ap.add_argument("--salida", default=RUTA_SALIDA,
                    help=f"por defecto {RUTA_SALIDA}, dentro de la carpeta del caso")
    ap.add_argument("--config", default=None,
                    help=f"JSON de una sesion anterior; por defecto {RUTA_CONFIG} si existe")
    ap.add_argument("--ancho", type=float, default=None, help="ancho real del rectangulo")
    ap.add_argument("--largo", type=float, default=None, help="largo real del rectangulo")
    ap.add_argument("--frames", type=int, default=0, help="0 = todo el video")
    ap.add_argument("--sin-interfaz", action="store_true",
                    help="procesa directamente con el --config dado, sin abrir la ventana")
    a = ap.parse_args()

    cfg = dict(CFG_INICIAL)
    ruta_cfg = a.config or (RUTA_CONFIG if os.path.exists(RUTA_CONFIG) else None)
    if ruta_cfg:
        with open(ruta_cfg, encoding="utf-8") as f:
            cfg.update(json.load(f))
        print(f"configuracion cargada de {ruta_cfg}")
    if not os.path.exists(a.video):
        raise SystemExit(f"No existe el video {a.video}.\n"
                         f"Pasa otro con --video RUTA.mp4")
    if a.ancho:
        cfg["ancho_real"], cfg["unidad"] = a.ancho, "m"
    if a.largo:
        cfg["largo_real"], cfg["unidad"] = a.largo, "m"

    if a.sin_interfaz:
        if cfg["cuadrilatero"] is None:
            raise SystemExit("--sin-interfaz necesita un --config con el cuadrilatero.")
        procesar(a.video, cfg, a.salida, a.frames)
        return

    ed = Editor(a.video, cfg, a.salida)
    if ed.correr():
        procesar(a.video, ed.cfg, a.salida, a.frames)
    else:
        print("salida sin procesar el video.")


if __name__ == "__main__":
    main()
