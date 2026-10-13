"""STIV en tiempo real sobre directos de YouTube de camaras de vigilancia de rios de Tokio.

Camaras preparadas (`--camara`, por defecto myoshoji):
    myoshoji  rio Myoshoji en Kamitakada (Nakano)          youtube.com/watch?v=huAp4q7lxiQ
    kurome    rio Kurome en el puente Koma (Higashikurume) youtube.com/watch?v=loW9744B-Co

Al arrancar resuelve el flujo HLS del directo con yt-dlp, lo abre con OpenCV y empieza a medir
inmediatamente: cada fotograma se muestrea a lo largo de las lineas de busqueda, las filas se apilan
en un STI deslizante por estacion y cada PASO_MEDIDA segundos se recalcula la velocidad superficial
con el tensor de estructura. pyorc no se importa en ningun momento.

    python stiv_directo.py                    # directo, con ventana
    python stiv_directo.py --camara kurome    # la otra camara
    python stiv_directo.py --sin-ventana --duracion 120     # directo, solo CSV
    python stiv_directo.py --archivo clip.mp4 # mismo algoritmo sobre un video grabado
    python stiv_directo.py --camara sitio1 --fuente rtsp://usuario:clave@IP:554/Streaming/Channels/101
                                              # camara propia (RTSP, p. ej. Hikvision): nombre nuevo,
                                              # su config y sus salidas van a salidas/sitio1/

En una Raspberry Pi (sin pantalla): --sin-ventana, y --vista-cada 30 para tener la imagen anotada
al dia en salidas/<camara>/ultima_vista.png. Ver raspberry/LEEME.md.

Teclas en la ventana: q salir | e editar el cuadrilatero (arrastrar esquinas) | g guardar config |
r vaciar el buffer | espacio congelar la imagen (la medida sigue) | f pantalla completa |
+ / - agrandar / achicar | p ocultar/mostrar el panel de STI (mas sitio para el video). La ventana abre al ~90 % de la pantalla y se redimensiona con el raton.

LA ESCALA ES UN SUPUESTO mientras `escala_verificada` sea false en la config: las dimensiones del
cuadrilatero no vienen de ningun levantamiento, y la pantalla lo dice. La forma del perfil y la
coherencia no dependen de ellas; los m/s si, linealmente en el sentido del flujo.
"""
import argparse
import csv
import json
import os
import queue
import sys
import threading
import time
from collections import deque
from datetime import datetime


def _asegurar_librerias():
    """Si este Python no tiene las librerias (p. ej. el interprete que elige el IDE), relanza el
    script con el .venv de la carpeta en vez de fallar mas tarde al resolver el directo."""
    import importlib.util
    faltan = [m for m in ("cv2", "numpy", "yt_dlp") if importlib.util.find_spec(m) is None]
    if not faltan:
        return
    import subprocess
    carpeta = os.path.dirname(os.path.abspath(__file__))
    py = os.path.join(carpeta, ".venv", "Scripts" if os.name == "nt" else "bin",
                      "python.exe" if os.name == "nt" else "python")
    if os.path.exists(py) and os.path.normcase(os.path.abspath(sys.executable)) != os.path.normcase(py):
        print(f"faltan {', '.join(faltan)} en {sys.executable}; relanzando con {py}", file=sys.stderr)
        sys.exit(subprocess.call([py, os.path.abspath(__file__), *sys.argv[1:]]))
    sys.exit(f"faltan librerias: {', '.join(faltan)}. Instalar con:\n"
             f'  "{sys.executable}" -m pip install -r "{os.path.join(carpeta, "requirements.txt")}"')


_asegurar_librerias()

import cv2  # noqa: E402 - despues de comprobar que existe
import numpy as np  # noqa: E402

# ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
# │ >>> AJUSTABLE <<<  por camara                                                                  │
# └──────────────────────────────────────────────────────────────────────────────────────────────┘
# cuadrilatero: 4 esquinas en la imagen de un rectangulo real de largo x ancho m sobre el agua, en el
#   orden [aguas arriba-orilla A, aguas abajo-orilla A, aguas abajo-orilla B, aguas arriba-orilla B].
#   Trazado a ojo sobre el borde del agua; largo y ancho son un SUPUESTO en las dos camaras (no hay
#   ancho publicado de ninguno de los dos cauces en esos puntos; se busco).
# v_esperada: solo fija DS (estelas a 45 grados); sale de una correlacion de conjunto en el directo.
# ancho_banda_m: ~2/3 del espaciado entre estaciones.
CAMARAS = {
    "myoshoji": {
        "url": "https://www.youtube.com/watch?v=huAp4q7lxiQ",
        "etiqueta": "Rio Myoshoji, Kamitakada (Nakano) - directo Tokyo Suibou",
        # la camara mira a lo largo del cauce y el agua se ALEJA (sube en la imagen): correlacion
        # de conjunto -1 px por fotograma real en las tres zonas bajas. Aguas arriba = abajo en la
        # imagen; orilla A = muro izquierdo (vertical en la imagen), B = muro derecho. El borde
        # lejano se queda bajo el salto (y~365): el agua blanca es estacionaria y da 0 coherente.
        "cuadrilatero": [[360, 700], [360, 385], [697, 385], [1010, 700]],
        "largo_m": 10.0, "ancho_m": 8.0,
        "v_esperada": 0.30, "largo_linea_m": 6.0, "centro_linea": 0.50, "ancho_banda_m": 0.60,
        "fps_camara": 15.0,
    },
    "kurome": {
        "url": "https://www.youtube.com/watch?v=loW9744B-Co",
        "etiqueta": "Rio Kurome, puente Koma (Higashikurume) - directo Tokyo Suibou",
        # el agua avanza hacia la DERECHA: +8 px, -1 px en 4 fotogramas reales en el rapido
        "cuadrilatero": [[100, 500], [1100, 360], [1100, 500], [100, 680]],
        "largo_m": 15.0, "ancho_m": 6.0,
        "v_esperada": 0.40, "largo_linea_m": 8.0, "centro_linea": 0.50, "ancho_banda_m": 0.30,
        "fps_camara": 15.0,
    },
}
# Plantilla para una camara que no esta en la lista (--camara <nombre nuevo>). El cuadrilatero es un
# rectangulo centrado en una imagen 1280x720 que HAY que arrastrar sobre el agua (tecla e, en el PC);
# todo se guarda en salidas/<nombre>/config_stiv_directo.json y desde ahi manda el JSON.
# fps_camara None = la camara entrega fotogramas reales al ritmo del flujo (RTSP directo, sin
# duplicados como los de YouTube).
CAMARA_NUEVA = {
    "url": None, "etiqueta": None,
    "cuadrilatero": [[340, 620], [340, 260], [940, 260], [940, 620]],
    "largo_m": 10.0, "ancho_m": 6.0,
    "v_esperada": 0.50, "largo_linea_m": 6.0, "centro_linea": 0.50, "ancho_banda_m": 0.40,
    "fps_camara": None,
}
CAMARA_POR_DEFECTO = "myoshoji"
ALTURA_MAX = 720            # mejor formato de estos directos; 1080 no existe en este canal

# -- metodo, comun a todas las camaras --
N_ESTACIONES = 9
MARGEN_ORILLA = 0.06        # fraccion del ancho que se deja sin estacion junto a cada borde
LINEAS_BANDA = 7            # lineas paralelas por estacion (normalizadas y promediadas)

VENTANA_S = 10.0            # longitud temporal del STI
PASO_MEDIDA_S = 1.0         # cada cuanto se recalcula
LADO_BLOQUE = 48            # bloques del tensor, 50 % de solape

# FPS_CAMARA (por camara, ver elegir_camara): en los directos de YouTube la camara emite 15 fps y
# YouTube duplica cada fotograma (patron 2,2,2... medido en 150 de 150 cambios). La actividad de un
# bloque se mide entre fotogramas REALES, no entre duplicados. None = sin duplicados.
# Mediana de |I(t + 1/15 s) - I(t)| en el bloque, en niveles de gris. El agua que el codificador
# congela (bloques "skip") da EXACTAMENTE 0.00 aunque sea una estela vertical perfectamente
# coherente; el agua con textura da 0.7-5.6. Medido de noche sobre 300 filas x 9 estaciones.
ACTIVIDAD_MIN = 0.5
N_BLOQUES_MIN = 6           # bloques activos necesarios para que una estacion cuente
# 0.40 como en Boneyard (textura fina). Con la mascara de actividad la coherencia ya no es la que
# frena la trampa del cero; el STI nocturno del rapido da 0.3-0.55 con estelas claras a simple vista,
# y un STI sintetico con duplicados da 0.99 y pendiente exacta, asi que lo bajo es la textura.
COH_MIN = 0.40


def elegir_camara(nombre, fuente=None):
    """Fija las constantes de la camara elegida; sus salidas van a salidas/<camara>/.

    Las camaras de CAMARAS toman sus valores del codigo. Una camara nueva parte de CAMARA_NUEVA y,
    si ya tiene config guardada, toma de ella la URL y los parametros por camara (asi se configura
    una Raspberry editando solo el JSON). `fuente` sustituye la URL en cualquier caso.
    """
    global CAMARA, URL_FUENTE, ETIQUETA, CUADRILATERO_SEMILLA, LARGO_SEMILLA_M, ANCHO_SEMILLA_M
    global V_ESPERADA, LARGO_LINEA_M, CENTRO_LINEA, ANCHO_BANDA_M, V_MAX_FISICA, FPS_CAMARA
    global CARPETA_SALIDAS, ARCHIVO_CONFIG, ARCHIVO_CSV, ARCHIVO_VISTA
    CARPETA_SALIDAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "salidas", nombre)
    ARCHIVO_CONFIG = os.path.join(CARPETA_SALIDAS, "config_stiv_directo.json")
    ARCHIVO_CSV = os.path.join(CARPETA_SALIDAS, "medidas_directo.csv")
    ARCHIVO_VISTA = os.path.join(CARPETA_SALIDAS, "ultima_vista.png")
    c = dict(CAMARAS.get(nombre, CAMARA_NUEVA))
    if nombre not in CAMARAS and os.path.exists(ARCHIVO_CONFIG):
        with open(ARCHIVO_CONFIG, encoding="utf-8") as f:
            guardada = json.load(f)
        par = guardada.get("parametros", {})
        c["url"] = guardada.get("url") or c["url"]
        c["etiqueta"] = guardada.get("etiqueta") or c["etiqueta"]
        for clave, global_ in (("v_esperada", "V_ESPERADA"), ("largo_linea_m", "LARGO_LINEA_M"),
                               ("centro_linea", "CENTRO_LINEA"), ("ancho_banda_m", "ANCHO_BANDA_M"),
                               ("fps_camara", "FPS_CAMARA")):
            if global_ in par:
                c[clave] = par[global_]
    if fuente:
        c["url"] = fuente
    CAMARA, URL_FUENTE = nombre, c["url"]
    ETIQUETA = c["etiqueta"] or f"Camara {nombre}"    # putText no dibuja japones
    CUADRILATERO_SEMILLA = [list(p) for p in c["cuadrilatero"]]
    LARGO_SEMILLA_M, ANCHO_SEMILLA_M = c["largo_m"], c["ancho_m"]
    V_ESPERADA, LARGO_LINEA_M = c["v_esperada"], c["largo_linea_m"]
    CENTRO_LINEA, ANCHO_BANDA_M = c["centro_linea"], c["ancho_banda_m"]
    FPS_CAMARA = c["fps_camara"]
    V_MAX_FISICA = 3 * V_ESPERADA


elegir_camara(CAMARA_POR_DEFECTO)


# ───────────────────────────────────────── configuracion ─────────────────────────────────────────
def cargar_config():
    if os.path.exists(ARCHIVO_CONFIG):
        with open(ARCHIVO_CONFIG, encoding="utf-8") as f:
            return json.load(f)
    return {"camara": CAMARA, "url": URL_FUENTE, "etiqueta": ETIQUETA, "cuadrilatero_px": CUADRILATERO_SEMILLA, "largo_m": LARGO_SEMILLA_M,
            "ancho_m": ANCHO_SEMILLA_M, "escala_verificada": False}


def guardar_config(cfg):
    os.makedirs(CARPETA_SALIDAS, exist_ok=True)
    salida = dict(cfg)
    salida["parametros"] = {k: globals()[k] for k in (
        "V_ESPERADA", "N_ESTACIONES", "MARGEN_ORILLA", "LARGO_LINEA_M", "CENTRO_LINEA",
        "LINEAS_BANDA", "ANCHO_BANDA_M", "VENTANA_S", "PASO_MEDIDA_S", "LADO_BLOQUE", "FPS_CAMARA",
        "ACTIVIDAD_MIN", "N_BLOQUES_MIN", "COH_MIN", "V_MAX_FISICA")}
    with open(ARCHIVO_CONFIG, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────── geometria ───────────────────────────────────────────
class Geometria:
    """Rectangulo del mundo (x aguas abajo, y desde la orilla lejana, en m) <-> imagen."""

    def __init__(self, cfg, fps):
        self.cuad = np.float32(cfg["cuadrilatero_px"])
        self.L, self.W = float(cfg["largo_m"]), float(cfg["ancho_m"])
        mundo = np.float32([[0, 0], [self.L, 0], [self.L, self.W], [0, self.W]])
        self.H = cv2.getPerspectiveTransform(mundo, self.cuad)          # mundo -> imagen
        self.dt = 1.0 / fps
        # DS = V.dt pone las estelas a 45 grados, donde el error angular pesa menos
        self.ds = V_ESPERADA * self.dt
        x0 = self.L * CENTRO_LINEA - LARGO_LINEA_M / 2
        self.xs = x0 + self.ds * np.arange(int(round(LARGO_LINEA_M / self.ds)))
        m = MARGEN_ORILLA * self.W
        self.ys = np.linspace(m, self.W - m, N_ESTACIONES)
        offs = np.linspace(-ANCHO_BANDA_M / 2, ANCHO_BANDA_M / 2, LINEAS_BANDA)
        yy = (self.ys[:, None] + offs[None, :]).reshape(-1)               # (N_EST*NB,)
        X, Y = np.meshgrid(self.xs, yy)
        p = self.a_imagen(np.stack([X.ravel(), Y.ravel()], 1))
        # remap no admite mapas de mas de SHRT_MAX de largo: se deja en 2D (filas = lineas)
        self.map_x = p[:, 0].reshape(X.shape).astype(np.float32)
        self.map_y = p[:, 1].reshape(X.shape).astype(np.float32)
        # pixeles de imagen por muestra (para el aviso de submuestreo y el suavizado antialias)
        paso = np.hypot(np.diff(self.map_x, axis=1), np.diff(self.map_y, axis=1))
        self.px_por_muestra = float(np.median(paso))

    def a_imagen(self, pts):
        return cv2.perspectiveTransform(np.float32(pts).reshape(-1, 1, 2), self.H).reshape(-1, 2)

    def muestrear(self, gris):
        # fuera del fotograma la muestra vale 0: con desviacion temporal nula su z es 0 y no pesa
        return cv2.remap(gris, self.map_x, self.map_y, cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    def procesar(self, frame):
        """Fotograma BGR -> fila de muestras. Igual que gris + suavizado + muestrear, pero solo
        sobre el recuadro que tocan las lineas: en una Raspberry Pi el suavizado del fotograma
        entero era la mayor parte del coste por fotograma."""
        if getattr(self, "_forma", None) != frame.shape:
            self._preparar_recorte(frame.shape)
        y0, y1, x0, x1 = self._recorte
        gris = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(np.float32)
        # antialias isotropo antes de muestrear: sigma ~ medio paso de muestreo, nunca < 0.7 px
        gris = cv2.GaussianBlur(gris, (0, 0), self.sigma)
        return cv2.remap(gris, self._mx, self._my, cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    def _preparar_recorte(self, forma):
        alto, ancho = forma[:2]
        self.sigma = max(0.7, self.px_por_muestra / 2)
        # el margen cubre el nucleo del suavizado: dentro del recuadro el resultado es el mismo
        # que suavizando el fotograma entero
        m = int(np.ceil(4 * self.sigma)) + 2
        x0 = max(int(np.floor(self.map_x.min())) - m, 0)
        x1 = min(int(np.ceil(self.map_x.max())) + m + 1, ancho)
        y0 = max(int(np.floor(self.map_y.min())) - m, 0)
        y1 = min(int(np.ceil(self.map_y.max())) + m + 1, alto)
        if x0 >= x1 or y0 >= y1:          # lineas fuera del fotograma: se usa entero
            x0, x1, y0, y1 = 0, ancho, 0, alto
        self._recorte = (y0, y1, x0, x1)
        self._mx, self._my = self.map_x - x0, self.map_y - y0
        self._forma = forma

    def cobertura(self, alto, ancho):
        """Fraccion de cada estacion que cae dentro del fotograma (depende solo de la geometria)."""
        dentro = ((self.map_x >= 0) & (self.map_x <= ancho - 1) &
                  (self.map_y >= 0) & (self.map_y <= alto - 1))
        return dentro.reshape(N_ESTACIONES, -1).mean(axis=1)


# ─────────────────────────────────────────── el metodo ───────────────────────────────────────────
def pendiente_tensor(sti, actividad):
    """Pendiente (muestras/fila) por tensor de estructura en bloques, mediana ponderada por coherencia.

    Solo cuentan los bloques activos: sin esa seleccion, el agua congelada por el codificador es una
    estela vertical de coherencia ~0.9 y la mediana devuelve 0.00 con toda confianza. Bloques de
    LADO_BLOQUE con 50 % de solape, sumados por celdas de medio bloque (sin bucle Python por bloque).
    """
    gs = cv2.Scharr(sti, cv2.CV_32F, 1, 0)
    gt = cv2.Scharr(sti, cv2.CV_32F, 0, 1)
    # mascara por pixel: el codificador congela parches DENTRO del agua activa, y esos parches son
    # rayas verticales que arrastran la pendiente hacia 0 y hunden la coherencia
    m = (cv2.blur(actividad, (5, 5)) >= ACTIVIDAD_MIN).astype(np.float32)
    T, K = sti.shape
    c = max(min(LADO_BLOQUE, T, K) // 2, 1)
    nt, nk = T // c, K // c
    if nt < 2 or nk < 2:
        return np.nan, 0.0, 0

    def bloques(img):
        celdas = img[:nt * c, :nk * c].reshape(nt, c, nk, c).sum(axis=(1, 3), dtype=np.float64)
        return celdas[:-1, :-1] + celdas[1:, :-1] + celdas[:-1, 1:] + celdas[1:, 1:]

    activos = bloques(m) / (4 * c * c) >= 0.5
    jss, jtt, jst = bloques(m * gs * gs)[activos], bloques(m * gt * gt)[activos], bloques(m * gs * gt)[activos]
    n_activos = int(activos.sum())
    tr = jss + jtt
    ok = tr > 1e-9
    jss, jtt, jst, tr = jss[ok], jtt[ok], jst[ok], tr[ok]
    if tr.size == 0:
        return np.nan, 0.0, n_activos
    l1 = 0.5 * (tr + np.hypot(jss - jtt, 2 * jst))
    coh = ((2 * l1 - tr) / tr) ** 2
    # I(s,t) = f(s - v t)  =>  (Gs, Gt) ~ (1, -v): el gradiente va segun el autovector MAYOR
    # (jst, l1 - jss), o (l1 - jtt, jst) si el primero degenera; v = -ey/ex
    ex, ey = jst.copy(), l1 - jss
    deg = (np.abs(ex) < 1e-12) & (np.abs(ey) < 1e-12)
    ex[deg], ey[deg] = (l1 - jtt)[deg], jst[deg]
    ok = np.abs(ex) >= 1e-12
    if not ok.any():
        return np.nan, 0.0, n_activos
    vs, cs = -ey[ok] / ex[ok], coh[ok]
    o = np.argsort(vs)
    acum = np.cumsum(cs[o])
    if acum[-1] <= 0:
        return np.nan, 0.0, n_activos
    v = vs[o][np.searchsorted(acum, acum[-1] / 2)]
    return float(v), float(np.average(cs, weights=cs)), n_activos


def construir_stis(buffer, lag):
    """buffer: (T, N_EST*NB, K) muestras crudas -> STIs normalizados y actividades, (N_EST, T, K)."""
    T, R, K = buffer.shape
    # normalizacion temporal por posicion: quita lo estatico (piedras, reflejos fijos, la vegetacion
    # que invade la banda) sin parametros, y deja a todas las lineas el mismo peso
    m = buffer.mean(axis=0)
    s = buffer.std(axis=0)
    z = (buffer - m) / np.where(s > 1e-3, s, np.inf)
    sti = z.reshape(T, N_ESTACIONES, LINEAS_BANDA, K).mean(axis=2).transpose(1, 0, 2)
    crudo = buffer.reshape(T, N_ESTACIONES, LINEAS_BANDA, K).mean(axis=2).transpose(1, 0, 2)
    # actividad entre fotogramas REALES (lag = 2 filas a 30 fps): un parche congelado da 0 exacto
    actividad = np.empty_like(crudo)
    actividad[:, lag:] = np.abs(crudo[:, lag:] - crudo[:, :-lag])
    actividad[:, :lag] = actividad[:, lag:2 * lag]
    # la camara emite 15 fps y YouTube duplica cada fotograma: suavizar 1 fila convierte los
    # escalones en estelas continuas sin cambiar su pendiente media (verificado en un STI sintetico)
    sti = np.stack([cv2.GaussianBlur(np.ascontiguousarray(x, np.float32), (0, 0), 1.0, sigmaY=1.0)
                    for x in sti])
    return sti, np.ascontiguousarray(actividad, np.float32)


def medir(buffer, geom, cobertura):
    """buffer: (T, N_EST*NB, K). Devuelve lista de dicts, una por estacion."""
    lag = max(1, int(round(1.0 / (FPS_CAMARA * geom.dt)))) if FPS_CAMARA else 1
    stis, actividades = construir_stis(buffer, lag)
    res = []
    for i in range(N_ESTACIONES):
        pend, coh, n_act = pendiente_tensor(stis[i], actividades[i])
        v = pend * geom.ds / geom.dt if np.isfinite(pend) else np.nan
        motivos = []
        if cobertura[i] < 0.8:
            motivos.append("fuera_de_campo")
        if n_act < N_BLOQUES_MIN:
            motivos.append("sin_textura")
        elif coh < COH_MIN:
            motivos.append("coherencia")
        if np.isfinite(v) and abs(v) > V_MAX_FISICA:
            motivos.append("v_max")
        elif not np.isfinite(v) and not motivos:
            motivos.append("sin_medida")
        res.append({"estacion": i, "y_m": float(geom.ys[i]), "v": v, "pendiente": pend,
                    "coherencia": coh, "bloques_activos": n_act, "cobertura": float(cobertura[i]),
                    "aceptada": not motivos, "motivos": "+".join(motivos), "sti": stis[i]})
    return res


# ───────────────────────────────────────── lectura del directo ───────────────────────────────────
def resolver_url(url_pagina):
    import yt_dlp
    opciones = {"quiet": True, "no_warnings": True,
                "format": f"bestvideo[height<={ALTURA_MAX}]/best[height<={ALTURA_MAX}]"}
    # YouTube a veces bloquea una conexion ("Sign in to confirm you're not a bot"); con las cookies
    # de un navegador donde se haya iniciado sesion (archivo cookies.txt) vuelve a dejar pasar
    if os.environ.get("STIV_COOKIES"):
        opciones["cookiefile"] = os.environ["STIV_COOKIES"]
    with yt_dlp.YoutubeDL(opciones) as y:
        info = y.extract_info(url_pagina, download=False)
    return info["url"], info.get("title", ""), info.get("live_status")


class Lector(threading.Thread):
    """Lee el flujo en un hilo aparte y entrega (pts_s, fotograma). Reconecta si se corta."""

    def __init__(self, origen, es_archivo):
        super().__init__(daemon=True)
        self.origen, self.es_archivo = origen, es_archivo
        # YouTube se resuelve con yt-dlp; cualquier otra URL (rtsp://, http://...m3u8) se abre tal cual
        self.es_youtube = not es_archivo and ("youtube.com" in origen or "youtu.be" in origen)
        # 150 fotogramas = 5 s a 30 fps, ~415 MB a 1280x720. Con 600 el pico de memoria llego a 1.3 GB
        # al procesar un archivo (la lectura va por delante): demasiado para una Raspberry de 4 GB.
        # Si se llena, el lector espera; no se pierde la sincronia del STI.
        self.cola = queue.Queue(maxsize=150)
        self.parar = threading.Event()
        self.fps = 30.0
        self.titulo = ""
        self.listo = threading.Event()
        self.error = None
        self.abierto = False

    def abrir(self):
        if self.es_youtube:
            fuente, self.titulo, estado = resolver_url(self.origen)
            if estado != "is_live":
                print(f"aviso: el video no esta en directo (live_status={estado})", file=sys.stderr)
        else:
            fuente = self.origen
        if self.es_archivo:
            cap = cv2.VideoCapture(fuente, cv2.CAP_FFMPEG)
        else:
            # sin tiempos de espera, una camara que se cuelga deja read() bloqueado para siempre y
            # nunca se llega a reconectar
            cap = cv2.VideoCapture(fuente, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 15000,
                                                            cv2.CAP_PROP_READ_TIMEOUT_MSEC, 15000])
        if not cap.isOpened():
            raise RuntimeError("OpenCV no pudo abrir el flujo")
        f = cap.get(cv2.CAP_PROP_FPS)
        self.fps = f if f and 1 < f < 121 else 30.0
        return cap

    def run(self):
        intentos = 0
        while not self.parar.is_set():
            try:
                cap = self.abrir()
            except Exception as e:  # noqa: BLE001 - se reintenta, el directo es inestable
                self.error = e
                intentos += 1
                if intentos > 5 or self.es_archivo:
                    self.listo.set()
                    self.cola.put(None)
                    return
                time.sleep(3)
                continue
            intentos = 0
            self.abierto = True
            self.listo.set()
            while not self.parar.is_set():
                ok, frame = cap.read()
                if not ok:
                    break
                pts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                self.cola.put((pts, frame))
            cap.release()
            if self.es_archivo:
                self.cola.put(None)
                return
            print("flujo cortado, reconectando...", file=sys.stderr)
            self.cola.put("corte")


class Medidor(threading.Thread):
    """Mide en un hilo aparte: la medida cuesta ~140 ms y el directo entrega un fotograma cada 33."""

    def __init__(self):
        super().__init__(daemon=True)
        self.entrada = queue.Queue(maxsize=1)
        self.salida = queue.Queue()
        self.n, self.segundos = 0, 0.0     # para el resumen: cuanto cuesta cada medida

    def libre(self):
        return self.entrada.empty() and self.salida.empty()

    def run(self):
        while True:
            gen, t, filas, geom, cobertura = self.entrada.get()
            c0 = time.perf_counter()
            res = medir(np.stack(filas), geom, cobertura)
            self.n, self.segundos = self.n + 1, self.segundos + time.perf_counter() - c0
            self.salida.put((gen, t, res))


# ──────────────────────────────────────────── ventana ────────────────────────────────────────────
FRACCION_PANTALLA = 0.90    # tamano inicial de la ventana respecto a la pantalla


def tamano_pantalla():
    """Resolucion de la pantalla principal en pixeles fisicos."""
    try:
        import ctypes
        u32 = ctypes.windll.user32
        # sin esto Windows reescala la ventana por DPI (borrosa) y GetSystemMetrics miente
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:  # noqa: BLE001 - Windows antiguo
            u32.SetProcessDPIAware()
        return u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
    except Exception:  # noqa: BLE001 - no es Windows
        return 1920, 1080


def ajustar_ventana(ventana, alto_img, ancho_img, escala=None):
    """Da a la ventana el mayor tamano que cabe en FRACCION_PANTALLA sin deformar la imagen
    (o `escala` veces ese tamano) y la centra. Devuelve la escala base usada."""
    sw, sh = tamano_pantalla()
    base = min(FRACCION_PANTALLA * sw / ancho_img, FRACCION_PANTALLA * sh / alto_img)
    f = base if escala is None else escala
    w, h = int(ancho_img * f), int(alto_img * f)
    cv2.resizeWindow(ventana, w, h)
    cv2.moveWindow(ventana, max((sw - w) // 2, 0), max((sh - h) // 2 - 20, 0))
    return f


# ──────────────────────────────────────────── dibujo ─────────────────────────────────────────────
ALTO_PANEL = 210


def dibujar(frame, geom, res, estado, editando, con_panel=True):
    img = frame.copy()
    cv2.polylines(img, [geom.cuad.astype(np.int32)], True, (0, 200, 255) if editando else (90, 90, 90),
                  2 if editando else 1, cv2.LINE_AA)
    if editando:
        for p in geom.cuad.astype(int):
            cv2.circle(img, tuple(p), 9, (0, 200, 255), 2, cv2.LINE_AA)
    for i, y in enumerate(geom.ys):
        a, b = geom.a_imagen([[geom.xs[0], y], [geom.xs[-1], y]])
        r = res[i] if res else None
        color = (120, 120, 120)
        if r is not None:
            color = (80, 220, 80) if r["aceptada"] else (60, 60, 200)
        cv2.line(img, tuple(a.astype(int)), tuple(b.astype(int)), color, 1, cv2.LINE_AA)
        cv2.putText(img, str(i), tuple((a + [-18, 5]).astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    color, 1, cv2.LINE_AA)
        if r is not None and r["aceptada"]:
            # flecha = 2 s de recorrido en el mundo; la punta se proyecta, asi la perspectiva la acorta
            xc = (geom.xs[0] + geom.xs[-1]) / 2
            p0, p1 = geom.a_imagen([[xc, y], [xc + 2.0 * r["v"], y]])
            cv2.arrowedLine(img, tuple(p0.astype(int)), tuple(p1.astype(int)), (0, 255, 255), 2,
                            cv2.LINE_AA, tipLength=0.25)
            cv2.putText(img, f"{r['v']:.2f}", tuple((p1 + [6, -6]).astype(int)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
    # cabecera
    lineas = [estado["titulo"][:70],
              f"STIV en directo | t={estado['t']:.1f}s | buffer {estado['llenado']:.0%} | "
              f"retraso {estado['retraso']:.1f}s | {estado['px_muestra']:.2f} px/muestra"]
    if res:
        ac = [r["v"] for r in res if r["aceptada"]]
        med = f"{np.median(ac):.3f} m/s" if ac else "sin estaciones validas"
        lineas.append(f"mediana seccion: {med}  ({len(ac)}/{len(res)} estaciones)")
    if not estado["verificada"]:
        lineas.append("ESCALA SUPUESTA: m/s sin verificar (ver config)")
    y0 = 22
    capa = img.copy()
    cv2.rectangle(capa, (0, 0), (560, 10 + 20 * len(lineas)), (0, 0, 0), -1)
    img = cv2.addWeighted(capa, 0.65, img, 0.35, 0)
    for j, t in enumerate(lineas):
        col = (0, 140, 255) if t.startswith("ESCALA") else (255, 255, 255)
        cv2.putText(img, t, (10, y0 + 20 * j), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(img, t, (10, y0 + 20 * j), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1, cv2.LINE_AA)
    if editando:
        cv2.putText(img, "EDITANDO: arrastra las esquinas, 'e' para terminar, 'g' para guardar",
                    (10, img.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 2,
                    cv2.LINE_AA)
    if not con_panel:
        return img
    # panel inferior: el STI de cada estacion con la pendiente ajustada, para auditar cada flecha
    panel = np.zeros((ALTO_PANEL, img.shape[1], 3), np.uint8)
    w = img.shape[1] // N_ESTACIONES
    for i in range(N_ESTACIONES):
        x0 = i * w
        if res:
            r = res[i]
            s = r["sti"]
            s8 = np.clip(127 + 40 * s, 0, 255).astype(np.uint8)
            hh = ALTO_PANEL - 20
            th = cv2.resize(s8, (w - 4, hh), interpolation=cv2.INTER_AREA)
            panel[18:18 + hh, x0 + 2:x0 + w - 2] = th[..., None]
            if np.isfinite(r["pendiente"]):
                # pendiente en muestras/fila -> en pixeles del recuadro
                kx = (w - 4) / s.shape[1]
                ky = hh / s.shape[0]
                cx = x0 + w / 2
                dx = r["pendiente"] * kx * (hh / 2) / ky
                col = (80, 220, 80) if r["aceptada"] else (60, 60, 200)
                ok, q0, q1 = cv2.clipLine((x0 + 2, 18, w - 4, hh), (int(cx - dx), 18),
                                          (int(cx + dx), 18 + hh))
                if ok:
                    cv2.line(panel, q0, q1, col, 1, cv2.LINE_AA)
            et = f"{i}: c{r['coherencia']:.2f} b{r['bloques_activos']}"
            col = (80, 220, 80) if r["aceptada"] else (60, 60, 200)
        else:
            et, col = f"{i}: llenando", (150, 150, 150)
        cv2.putText(panel, et, (x0 + 4, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.38, col, 1, cv2.LINE_AA)
    return np.vstack([img, panel])


def ocultar_clave(url):
    """rtsp://usuario:clave@host -> rtsp://usuario:***@host, para no imprimir contrasenas."""
    if "://" in url and "@" in url.split("://", 1)[1]:
        esquema, resto = url.split("://", 1)
        cred, host = resto.split("@", 1)
        if ":" in cred:
            return f"{esquema}://{cred.split(':', 1)[0]}:***@{host}"
    return url


def guardar_vista(frame, geom, res, cfg, t, llenado, args):
    """Imagen anotada a disco. Se escribe en un temporal y se renombra, para que quien la lea desde
    otro equipo (p. ej. el PC mirando la Raspberry) nunca vea una imagen a medio escribir."""
    estado = {"titulo": os.path.basename(args.archivo) if args.archivo else ETIQUETA,
              "t": t, "llenado": llenado, "retraso": 0.0,
              "px_muestra": geom.px_por_muestra, "verificada": bool(cfg.get("escala_verificada"))}
    os.makedirs(CARPETA_SALIDAS, exist_ok=True)
    tmp = ARCHIVO_VISTA[:-4] + ".tmp.png"
    cv2.imwrite(tmp, dibujar(frame, geom, res, estado, False))
    os.replace(tmp, ARCHIVO_VISTA)


# ─────────────────────────────────────────── bucle ───────────────────────────────────────────────
def main():
    global PASO_MEDIDA_S
    # el titulo del directo es japones y la consola de Windows es cp1252
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--camara", default=CAMARA_POR_DEFECTO,
                    help=f"camara: {', '.join(sorted(CAMARAS))} o un nombre nuevo para una propia "
                         f"(por defecto {CAMARA_POR_DEFECTO})")
    ap.add_argument("--fuente", help="URL del video en directo (rtsp://..., http://...); sustituye "
                                     "a la de la camara y queda guardada en su config")
    ap.add_argument("--archivo", help="procesar un video grabado en vez del directo")
    ap.add_argument("--sin-ventana", action="store_true", help="sin interfaz, solo CSV")
    ap.add_argument("--duracion", type=float, default=0, help="segundos de flujo a procesar (0 = sin fin)")
    ap.add_argument("--paso-medida", type=float, default=PASO_MEDIDA_S,
                    help=f"segundos entre medidas (por defecto {PASO_MEDIDA_S:g})")
    ap.add_argument("--vista-cada", type=float, default=0,
                    help="sin ventana: guardar la imagen anotada cada N s de flujo (0 = solo al salir)")
    args = ap.parse_args()
    if not args.camara.replace("_", "").replace("-", "").isalnum():
        ap.error("--camara: solo letras, numeros, '_' y '-' (es el nombre de su carpeta)")
    PASO_MEDIDA_S = args.paso_medida
    elegir_camara(args.camara, args.fuente)
    if not args.archivo and not URL_FUENTE:
        ap.error(f"la camara '{args.camara}' es nueva y no tiene URL: pasa --fuente rtsp://...")

    cfg = cargar_config()
    if args.fuente and cfg.get("url") != args.fuente:
        cfg["url"] = args.fuente
        guardar_config(cfg)
    if not os.path.exists(ARCHIVO_CONFIG):
        guardar_config(cfg)
    if not args.archivo and URL_FUENTE.startswith("rtsp"):
        # por TCP: por UDP se pierden paquetes en cuanto la red titubea y salen fotogramas rotos
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
    lector = Lector(args.archivo or URL_FUENTE, bool(args.archivo))
    print(f"abriendo {args.archivo}" if args.archivo else
          "resolviendo el flujo..." if lector.es_youtube else f"conectando a {ocultar_clave(URL_FUENTE)}")
    lector.start()
    lector.listo.wait()
    if not lector.abierto:
        sys.exit(f"no se pudo abrir el flujo: {lector.error}")
    geom = Geometria(cfg, lector.fps)
    T = int(round(VENTANA_S * lector.fps))
    print(f"{lector.titulo}\nfps {lector.fps:g} | DS {geom.ds * 1000:.1f} mm = {geom.px_por_muestra:.2f} px "
          f"| {len(geom.xs)} muestras/linea | STI de {T} filas")
    if geom.px_por_muestra < 0.2:
        print("aviso: DS < 0.2 px de imagen, el STI estaria submuestreado (aliasing)", file=sys.stderr)

    os.makedirs(CARPETA_SALIDAS, exist_ok=True)
    nuevo = not os.path.exists(ARCHIVO_CSV)
    fcsv = open(ARCHIVO_CSV, "a", newline="", encoding="utf-8")
    wcsv = csv.writer(fcsv)
    if nuevo:
        wcsv.writerow(["hora_local", "t_flujo_s", "estacion", "y_m", "v_m_s", "coherencia", "bloques_activos",
                       "aceptada", "motivos", "escala_verificada"])

    filas = deque(maxlen=T)
    medidor = Medidor()
    medidor.start()
    gen = 0                 # cambia cada vez que el buffer deja de ser continuo; descarta medidas viejas
    pts_prev, t_ult_medida, res = None, -1e9, None
    t_ini_flujo, reloj_ini, t = None, None, 0.0
    reanclar = False        # tras una discontinuidad, el reloj del flujo se re-ancla para que t siga creciendo
    n_fotogramas, coste_proceso = 0, 0.0
    t_ult_vista, reloj_arranque = 0.0, time.time()
    editando, congelado, arrastre, ultimo = False, False, None, None
    ventana = f"STIV directo - {CAMARA}"
    escala_ventana, pantalla_completa = None, False   # la escala se fija con el primer fotograma
    con_panel = True

    if not args.sin_ventana:
        # WINDOW_NORMAL: redimensionable con el raton; KEEPRATIO: sin deformar la imagen. Con ella
        # OpenCV devuelve el raton en coordenadas de la imagen, asi que editar sigue funcionando
        cv2.namedWindow(ventana, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)

        def raton(evento, x, y, flags, _):
            nonlocal arrastre, geom, res, gen
            if not editando:
                return
            if evento == cv2.EVENT_LBUTTONDOWN:
                d = np.hypot(*(geom.cuad - [x, y]).T)
                arrastre = int(np.argmin(d)) if d.min() < 30 else None
            elif evento == cv2.EVENT_MOUSEMOVE and arrastre is not None:
                cfg["cuadrilatero_px"][arrastre] = [int(x), int(y)]
                geom = Geometria(cfg, lector.fps)
                filas.clear(); res = None; gen += 1
            elif evento == cv2.EVENT_LBUTTONUP and arrastre is not None:
                arrastre = None
                filas.clear(); res = None; gen += 1
        cv2.setMouseCallback(ventana, raton)

    try:
        while True:
            item = lector.cola.get()
            if item is None:
                break
            if item == "corte":
                filas.clear(); pts_prev = None; reanclar = True; gen += 1
                continue
            pts, frame = item
            c0 = time.perf_counter()
            n_fotogramas += 1
            if t_ini_flujo is None:
                t_ini_flujo, reloj_ini = pts, time.time()
            fila = geom.procesar(frame)
            # el STI exige filas equiespaciadas en tiempo: un hueco de PTS se rellena repitiendo la
            # ultima fila (lo mismo que hace YouTube con los duplicados). Un salto de mas de 1 s o un
            # PTS que RETROCEDE (camara o emisor reiniciado: el tiempo vuelve a empezar en 0, medido
            # con un servidor RTSP de prueba) es una discontinuidad: STI vacio y reloj re-anclado.
            # Sin re-anclar, t volvia atras y no se media hasta superar el t de antes del corte.
            if pts_prev is not None:
                pasos = (pts - pts_prev) * lector.fps
                if pasos < -0.5 or pasos > lector.fps + 1:
                    filas.clear(); gen += 1; reanclar = True
                else:
                    for _ in range(int(round(pasos)) - 1):
                        if filas:
                            filas.append(filas[-1])
            if reanclar:
                t_ini_flujo = pts - (t + 1.0 / lector.fps)
                reloj_ini = time.time() - (t + 1.0 / lector.fps)
                reanclar = False
            filas.append(fila)
            pts_prev = pts
            t = pts - t_ini_flujo

            if len(filas) == T and t - t_ult_medida >= PASO_MEDIDA_S and medidor.libre():
                # la deque guarda referencias: la copia de la lista es barata y el hilo apila
                medidor.entrada.put((gen, t, list(filas), geom, geom.cobertura(*frame.shape[:2])))
                t_ult_medida = t
            while not medidor.salida.empty():
                g_m, t_m, res_m = medidor.salida.get()
                if g_m != gen:
                    continue
                res = res_m
                hora = datetime.now().isoformat(timespec="seconds")
                for r in res:
                    wcsv.writerow([hora, f"{t_m:.2f}", r["estacion"], f"{r['y_m']:.3f}", f"{r['v']:.4f}",
                                   f"{r['coherencia']:.3f}", r["bloques_activos"], int(r["aceptada"]),
                                   r["motivos"], int(bool(cfg.get("escala_verificada")))])
                fcsv.flush()
                ac = [r["v"] for r in res if r["aceptada"]]
                # cola = fotogramas leidos y aun sin procesar: si crece sin parar, el equipo no da
                # abasto (al arrancar es normal que suba: el directo entrega varios segundos de golpe)
                print(f"t={t_m:7.1f}s  mediana {np.median(ac) if ac else float('nan'):.3f} m/s  "
                      f"{len(ac)}/{N_ESTACIONES} | " +
                      " ".join(f"{r['v']:+.2f}{'' if r['aceptada'] else '*'}" for r in res) +
                      f" | cola {lector.cola.qsize()}")

            coste_proceso += time.perf_counter() - c0
            if args.duracion and t >= args.duracion:
                break
            if args.sin_ventana:
                ultimo = frame
                if args.vista_cada and res and t - t_ult_vista >= args.vista_cada:
                    guardar_vista(ultimo, geom, res, cfg, t, len(filas) / T, args)
                    t_ult_vista = t
                continue

            # el directo llega a rafagas (al arrancar entrega varios segundos de golpe): se reproduce
            # a ritmo real segun el PTS, y si el proceso va retrasado se dibuja solo 1 de cada 3
            retraso = (time.time() - reloj_ini) - t
            if retraso < 0:
                time.sleep(min(-retraso, 0.1))
            elif retraso > 2.0 and int(t * lector.fps) % 3:
                continue
            estado = {"titulo": os.path.basename(args.archivo) if args.archivo else ETIQUETA, "t": t,
                      "llenado": len(filas) / T, "retraso": max(retraso, 0.0),
                      "px_muestra": geom.px_por_muestra, "verificada": bool(cfg.get("escala_verificada"))}
            if not congelado or ultimo is None:
                ultimo = frame
            vista = dibujar(ultimo, geom, res, estado, editando, con_panel)
            cv2.imshow(ventana, vista)
            if escala_ventana is None and not pantalla_completa:
                escala_ventana = ajustar_ventana(ventana, *vista.shape[:2])
            k = cv2.waitKey(1) & 0xFF
            if k == ord("q") or cv2.getWindowProperty(ventana, cv2.WND_PROP_VISIBLE) < 1:
                break
            if k == ord("e"):
                editando = not editando
            elif k == ord("g"):
                guardar_config(cfg)
                print(f"config guardada en {ARCHIVO_CONFIG}")
            elif k == ord("r"):
                filas.clear(); res = None; gen += 1
            elif k == ord(" "):
                congelado = not congelado
            elif k == ord("f"):
                pantalla_completa = not pantalla_completa
                cv2.setWindowProperty(ventana, cv2.WND_PROP_FULLSCREEN,
                                      cv2.WINDOW_FULLSCREEN if pantalla_completa else cv2.WINDOW_NORMAL)
                if not pantalla_completa:
                    ajustar_ventana(ventana, *vista.shape[:2], escala_ventana)
            elif k == ord("p"):
                # cambia la proporcion de la imagen: la ventana se reajusta a la nueva
                con_panel = not con_panel
                escala_ventana = None
            elif k in (ord("+"), ord("-")) and not pantalla_completa:
                escala_ventana *= 1.15 if k == ord("+") else 1 / 1.15
                ajustar_ventana(ventana, *vista.shape[:2], escala_ventana)
    except KeyboardInterrupt:
        pass
    finally:
        if ultimo is not None:
            guardar_vista(ultimo, geom, res, cfg, t, len(filas) / T, args)
        lector.parar.set()
        fcsv.close()
        if n_fotogramas:
            print(f"{n_fotogramas} fotogramas, {t:.1f} s de flujo en {time.time() - reloj_arranque:.1f} s "
                  f"de reloj; lectura+muestreo {1000 * coste_proceso / n_fotogramas:.1f} ms/fotograma "
                  f"en el hilo principal (el directo da uno cada {1000 / lector.fps:.0f} ms); "
                  f"cola final {lector.cola.qsize()}")
            if medidor.n:
                print(f"medida: {1000 * medidor.segundos / medidor.n:.0f} ms de media en {medidor.n} "
                      f"medidas (cada {PASO_MEDIDA_S:g} s de flujo)")
        if not args.sin_ventana:
            # en OpenCV sin interfaz (opencv-python-headless, el de la Raspberry) esto da error
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
