"""STIV desde cero sobre un video de WhatsApp de un canal de riego, sin ningun dato de campo.

Que es este caso
----------------
Un video de movil (1024x576, 29.975 fps, 81 s, 661 kb/s) de un canal de riego revestido de
hormigon, grabado a pulso desde una obra de paso mirando practicamente por el eje del canal.
No hay GCPs, no hay ancho medido, no hay aforo, no hay seccion, no hay nada. Solo el video.
pyorc no se importa en ningun momento.

Por eso el resultado sale en **unidades afines**, igual que en `analisis_boneyard_stiv/`: la
velocidad es correcta salvo una constante global, y se reporta en alturas de camara por
segundo y en anchos de canal por segundo. El dia que alguien mida el ancho del canal, la
conversion a m/s es una multiplicacion y no hay que reprocesar nada.

Las tres cosas que hacen medible este video
-------------------------------------------
1. **Realce morfologico top-hat, y es la leccion del caso.** A 661 kb/s el codificador aplana
   la superficie del agua: la STI en crudo esta dominada por macrobloques de H.264 y la
   correlacion de conjunto da 0.95 con el pico CLAVADO en desplazamiento cero, la firma del
   video sin senal del caso Arrow. Pero la senal existe: son detritos vegetales sueltos,
   pequenos y brillantes. Un top-hat con elemento de 5 px los aisla y **borra los bloques**,
   porque un bloque es una region plana y el top-hat solo deja lo que es mas brillante que su
   entorno inmediato. Con eso la STI pasa de ruido a estelas rectas y limpias.

2. **Seleccion de bloques por senal en el tensor.** Con trazadores escasos, la mayoria de los
   bloques de la STI no contienen ninguna estela, solo el residuo estatico -- que es una
   estela de pendiente cero perfectamente coherente, la trampa de Boneyard. La mediana
   ponderada por coherencia sobre TODOS los bloques da 0.000 con coherencia 0.7 en las 15
   estaciones, incluidas las que a ojo tienen estelas evidentes. Se toma la mediana solo sobre
   los bloques cuyo maximo supera el cuantil `CUANTIL_SENAL`, es decir los que de verdad
   contienen una particula.

3. **Banda de lineas paralelas** en vez de una sola linea, el truco de `analisis_bradano_stiv/`,
   por la misma razon: el trazador es escaso y hay que sumar estructura de varias lineas.

Como se comprueba la rectificacion, y como NO
---------------------------------------------
Las dos orillas del canal son paralelas en el mundo y convergen en la imagen en el punto de
fuga longitudinal, ajustado por RANSAC sobre el gradiente fila a fila. Con roll nulo, la
horizontal que pasa por ese punto es el horizonte, y la homografia que lo manda al infinito
deja el plano del agua en afinidad.

**Que el ancho del canal salga constante NO valida nada**, y conviene tenerlo claro porque
resulta tentador: el punto de fuga se calcula como la interseccion de las dos rectas de orilla,
asi que la homografia las manda a paralelas *por construccion*. La variacion medida es
1.97e-16, epsilon de maquina, y sale asi para cualquier FOCAL. Es una identidad algebraica que
solo sirve para detectar un error de programacion en la homografia, no para juzgar la geometria.

Lo que si valida la geometria es que **las estelas de la STI salen rectas**. Si el horizonte
estuviera mal, una particula a velocidad constante trazaria una estela CURVA, porque recorreria
cada vez mas pixeles al acercarse y la correccion aplicada no lo compensaria. Salen rectas
(fig2 y fig3). Es una comprobacion visual, no una cota, igual que la de la distorsion en
Boneyard. La segunda, mas debil, es la calidad del ajuste RANSAC de las dos orillas.

Lo que NO se puede medir, y es parte del resultado
--------------------------------------------------
La mitad izquierda del canal no tiene ni un trazador: 4 a 31 detecciones frente a 1.500-16.000
en la derecha. Los detritos caen de la vegetacion que cuelga de la orilla derecha y viajan en
una banda por ese lado. Las estaciones de la izquierda se rechazan y **no se rellenan** -- no
hay seccion que integrar, asi que rellenar solo inventaria datos (misma regla que Boneyard y
Bradano, la contraria que SMC).

Uso
---
    python stiv_canal.py                    # medida completa + figuras + CSV
    python stiv_canal.py --frames 800       # prueba corta
    python stiv_canal.py --sin-figuras      # solo numeros
"""
import argparse
import csv
import json
import os
import sys
import time

import cv2
import numpy as np

DIR_CASO = os.path.dirname(os.path.abspath(__file__))
DIR_SALIDAS = os.path.join(DIR_CASO, "salidas")
ARCHIVO_VIDEO = r"C:\Users\Sergio\Desktop\videos\WhatsApp Video 2026-08-16 at 8.07.12 PM.mp4"

# ----------------------------------------------------------------------------------
# >>> AJUSTABLE <<<  Geometria
# ----------------------------------------------------------------------------------
# FOCAL no se puede medir: el video viene reencodeado por WhatsApp y no queda EXIF. 780 px
# equivale a unos 26 mm en 35 mm sobre un fotograma de 1024 px de ancho, que es la camara
# principal tipica de un movil. Cambia la inclinacion deducida y por tanto la escala
# longitudinal; la sensibilidad esta medida y se imprime al final (ver `barrer_focal`).
FOCAL = 780.0
# Filas donde se busca la orilla. Por debajo de 560 empieza la obra de paso y por encima de 60
# el canal ya no se distingue del fondo.
FILA_BORDE_INI, FILA_BORDE_FIN, FILA_BORDE_PASO = 60, 560, 10
# Retranqueo desde cada orilla, en alturas de camara. La ultima banda contra la orilla derecha
# acumula 157.484 detecciones top-hat con velocidad ~0: es el borde del agua y el hormigon
# mojado, no agua. 0.10 es lo minimo que lo deja fuera.
RETRANQUEO = 0.10

# ----------------------------------------------------------------------------------
# >>> AJUSTABLE <<<  Realce de particulas
# ----------------------------------------------------------------------------------
# Elemento estructurante del top-hat. 5 px es algo mayor que un detrito (2-4 px) y bastante
# menor que un macrobloque (16 px), que es exactamente la separacion que se necesita.
TOPHAT_K = 5
# Desenfoque previo, para que el ruido de un solo pixel del codec no sobreviva al top-hat.
SIGMA_PREVIO = 0.8

# ----------------------------------------------------------------------------------
# >>> AJUSTABLE <<<  Construccion de la STI
# ----------------------------------------------------------------------------------
# Velocidad esperada, en alturas de camara/s. NO se ajusta contra el resultado: sale de la
# correlacion de conjunto sobre parches rectificados (0.038) redondeada al alza tras ver la
# pendiente de las estelas. Solo fija DS.
V_ESPERADA = 0.056
# Tramo del canal que se mide, en alturas de camara desde la camara. Por debajo de 1.40 entra
# la obra de paso en sombra. El limite de arriba se puso al principio heredando el criterio de
# Boneyard, y luego se MIDIO en `analisis_canal_lejano_stiv/`: por encima de 3.20 el paso DS cae
# por debajo de ~0.2 px de imagen y la STI se aliasea, con lo que el tensor devuelve velocidades
# hasta 20 veces mayores CON COHERENCIA 0.98. Partiendo esta banda en dos, la mitad cercana sola
# da 0.0580 contra los 0.0590 de la banda entera (1.7 %) y la mitad lejana la rechaza el propio
# control de calidad, asi que 3.20 es un limite seguro aunque generoso.
Y_MIN, Y_MAX = 1.40, 3.20
N_ESTACIONES = 15
# Ancho de la banda de lineas paralelas y numero de lineas. 0.10 es el 68 % del paso entre
# estaciones -- mucho mas ancho que el 22-24 % de Bradano y Arrow, y a proposito: aqui el
# trazador es mas escaso que en Bradano y el perfil transversal es suave, asi que promediar a
# traves cuesta poca resolucion y compra mucha senal. Medido: con 3 lineas (banda 0.035) la
# coherencia va de 0.48 a 0.75 y el sesgo salta erraticamente entre +5 y +29 %; con 11 lineas
# sube a 0.65-0.86 y el sesgo se estabiliza. Con 21 lineas (banda 0.20) no mejora nada y se
# pierde resolucion transversal, asi que 11 es donde deja de pagar.
BANDA = 0.10
N_LINEAS = 11

# ----------------------------------------------------------------------------------
# >>> AJUSTABLE <<<  Tensor de estructura
# ----------------------------------------------------------------------------------
LADO_BLOQUE = 64
SOLAPE = 0.5
SIGMA_TENSOR = 1.2
# Cuantil de seleccion por senal. NO se elige por su resultado: se elige midiendo cuantos
# bloques contienen de verdad una particula. Medido sobre las estaciones con trazador, entre el
# 11 y el 21 % de los bloques de 64 px superan el umbral, asi que quedarse con el 15 % mas
# brillante (q = 0.85) es justo quedarse con esos. Es el parametro que hace funcionar el tensor
# en este video; su sensibilidad esta medida en el README.
CUANTIL_SENAL = 0.85

# ----------------------------------------------------------------------------------
# >>> AJUSTABLE <<<  Control de calidad
# ----------------------------------------------------------------------------------
# Coherencia minima sobre los bloques seleccionados. Medido: las estaciones con trazador dan
# 0.67-0.85, las que no tienen 0.32-0.43 y la lamina de agua contra la orilla 0.56.
COH_MIN = 0.60
# Densidad de particulas de la estacion: fraccion de celdas (fotograma, posicion) en las que
# ALGUNA linea de la banda supera UMBRAL_PARTICULA. Es el discriminador de ESTE caso, y es de
# dos lados. Lo que falla aqui no es el contraste ni el brillo -- el agua con trazador y el agua
# sin trazador tienen exactamente el mismo brillo y el mismo contraste temporal, asi que ni el
# criterio de Boneyard ni el de Bradano separan nada. Lo que las separa es cuantas particulas
# hay. Medido sobre el video completo, quedan tres poblaciones:
#     agua sin trazador   0.00001 - 0.00039   (estaciones 1 a 7, mitad izquierda)
#     agua con trazador   0.00575 - 0.01969   (estaciones 8 a 13, banda de detritos)
#     orilla derecha      0.07779             (estacion 14, hormigon mojado y borde del agua)
# El hueco de abajo es de factor 15 y el de arriba de factor 4; los dos umbrales van dentro.
# Lo que este criterio NO separa, y hay que decirlo: la estacion 0, pegada a la orilla
# IZQUIERDA, da 0.01023, o sea plena banda de agua con trazador. Esa la paran la coherencia
# (0.580 contra 0.60, por poco) y la cota fisica, que la caza por un factor 13. Ver
# `motivos_rechazo`.
DENSIDAD_MIN = 0.004
DENSIDAD_MAX = 0.05
UMBRAL_PARTICULA = 4.0
# Cota fisica, como en el video_velocidad.py del caso SMC: 3 veces la velocidad esperada.
V_MAX_FISICA = 3.0 * V_ESPERADA


# ==================================================================================
# 1. Geometria: orillas, punto de fuga, rectificacion
# ==================================================================================
def detectar_orillas(gris):
    """Ajusta x = a*y + b a cada orilla por el maximo gradiente horizontal fila a fila."""
    H, W = gris.shape
    izq, der = [], []
    for y in range(FILA_BORDE_INI, FILA_BORDE_FIN, FILA_BORDE_PASO):
        fila = cv2.GaussianBlur(gris[y:y + 1, :].astype(np.float32), (9, 1), 0).ravel()
        d = np.abs(np.diff(fila))
        izq.append((int(np.argmax(d[:W // 2])), y))
        der.append((int(W // 2 + np.argmax(d[W // 2:])), y))
    return _ransac_recta(np.array(izq, float)), _ransac_recta(np.array(der, float))


def _ransac_recta(P, tol=6.0, iters=600):
    rng = np.random.default_rng(0)
    mejor = (0, 0.0, 0.0)
    for _ in range(iters):
        i = rng.choice(len(P), 2, replace=False)
        (x1, y1), (x2, y2) = P[i]
        if abs(y1 - y2) < 20:
            continue
        a = (x1 - x2) / (y1 - y2)
        b = x1 - a * y1
        n = (np.abs(P[:, 0] - (a * P[:, 1] + b)) < tol).sum()
        if n > mejor[0]:
            mejor = (n, a, b)
    _, a, b = mejor
    m = np.abs(P[:, 0] - (a * P[:, 1] + b)) < tol
    A = np.polyfit(P[m, 1], P[m, 0], 1)
    return float(A[0]), float(A[1]), int(m.sum()), int(len(P))


class Geometria:
    """Rectificacion del plano del agua a partir del punto de fuga longitudinal.

    El plano queda metrico salvo la altura de camara, que se toma como unidad. Las coordenadas
    de suelo son (X, Y): X transversal (0 en el eje del canal), Y distancia a la camara a lo
    largo del canal. La velocidad se mide en +Y.
    """

    def __init__(self, gris, focal=FOCAL):
        H, W = gris.shape
        self.W, self.H = W, H
        (self.al, self.bl, ni, nt), (self.ar, self.br, ni2, nt2) = detectar_orillas(gris)
        self.inliers = (ni, nt, ni2, nt2)
        self.yv = (self.br - self.bl) / (self.al - self.ar)
        self.xv = self.al * self.yv + self.bl
        self.focal = focal
        cx, cy = W / 2.0, H / 2.0
        self.inclinacion = np.arctan2(cy - self.yv, focal)
        K = np.array([[focal, 0, cx], [0, focal, cy], [0, 0, 1]])
        s, c = np.sin(self.inclinacion), np.cos(self.inclinacion)
        # suelo (X, Y, 1) -> imagen, camara a altura 1
        self.Hgi = K @ np.array([[1, 0, 0], [0, -s, c], [0, c, s]])
        self.Hig = np.linalg.inv(self.Hgi)
        # ancho del canal y eje, medidos en el plano rectificado
        ys = np.linspace(FILA_BORDE_INI + 60, FILA_BORDE_FIN - 40, 9)
        Gl = self.a_suelo(np.column_stack([self.al * ys + self.bl, ys]))
        Gr = self.a_suelo(np.column_stack([self.ar * ys + self.br, ys]))
        anchos = Gr[:, 0] - Gl[:, 0]
        self.ancho = float(np.mean(anchos))
        self.ancho_variacion = float((anchos.max() - anchos.min()) / self.ancho)
        self.X_izq = float(np.mean(Gl[:, 0]))
        self.X_der = float(np.mean(Gr[:, 0]))

    def a_imagen(self, P):
        P = np.atleast_2d(np.asarray(P, float))
        q = np.column_stack([P, np.ones(len(P))]) @ self.Hgi.T
        return q[:, :2] / q[:, 2:]

    def a_suelo(self, P):
        P = np.atleast_2d(np.asarray(P, float))
        q = np.column_stack([P, np.ones(len(P))]) @ self.Hig.T
        return q[:, :2] / q[:, 2:]

    def poligono_agua(self):
        """Poligono del agua en la imagen, para excluirlo al estabilizar."""
        ys = np.array([0.0, float(self.H)])
        xl = self.al * ys + self.bl
        xr = self.ar * ys + self.br
        return np.array([[xl[0], ys[0]], [xr[0], ys[0]],
                         [xr[1], ys[1]], [xl[1], ys[1]]], np.int32)

    def estaciones(self):
        return np.linspace(self.X_izq + RETRANQUEO, self.X_der - RETRANQUEO, N_ESTACIONES)

    # -- vista rectificada, para las figuras y el video -----------------------------
    def raster(self, escala=260.0, margen=0.06):
        """Define el lienzo rectificado: X a lo ancho, Y hacia arriba (aguas abajo arriba)."""
        X0, X1 = self.X_izq - margen, self.X_der + margen
        Y0, Y1 = Y_MIN, Y_MAX
        w = int(round((X1 - X0) * escala))
        h = int(round((Y1 - Y0) * escala))
        return dict(X0=X0, X1=X1, Y0=Y0, Y1=Y1, w=w, h=h, escala=escala)

    def mapa_rect(self, rst):
        """Mapa (h, w, 2) de coordenadas de imagen para cada pixel del lienzo rectificado."""
        Xs = np.linspace(rst["X0"], rst["X1"], rst["w"])
        Ys = np.linspace(rst["Y1"], rst["Y0"], rst["h"])   # fila 0 = mas lejos
        GX, GY = np.meshgrid(Xs, Ys)
        I = self.a_imagen(np.column_stack([GX.ravel(), GY.ravel()]))
        return I.reshape(rst["h"], rst["w"], 2).astype(np.float32)

    def rect_a_pix(self, rst, P):
        """Coordenadas de suelo -> pixel del lienzo rectificado."""
        P = np.atleast_2d(np.asarray(P, float))
        x = (P[:, 0] - rst["X0"]) / (rst["X1"] - rst["X0"]) * (rst["w"] - 1)
        y = (rst["Y1"] - P[:, 1]) / (rst["Y1"] - rst["Y0"]) * (rst["h"] - 1)
        return np.column_stack([x, y])


# ==================================================================================
# 2. Lectura, estabilizacion y realce
# ==================================================================================
def realzar(gris):
    """Top-hat morfologico: aisla particulas pequenas y brillantes, borra los macrobloques."""
    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (TOPHAT_K, TOPHAT_K))
    suave = cv2.GaussianBlur(gris, (0, 0), SIGMA_PREVIO)
    return cv2.morphologyEx(suave, cv2.MORPH_TOPHAT, se).astype(np.float32)


def abrir_video(ruta=ARCHIVO_VIDEO):
    cap = cv2.VideoCapture(ruta)
    if not cap.isOpened():
        raise SystemExit("no se puede abrir el video: %s" % ruta)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    return cap, n, fps


def estimar_estabilizacion(gris0, gris, p0):
    """Afinidad que lleva el marco de referencia (fotograma 0) al fotograma actual.

    Se rastrea SIEMPRE contra el fotograma 0, no en cadena, para que el error no se acumule
    (misma decision que `estabilizar_stiv.py` en la raiz del workspace).
    """
    p1, st, _ = cv2.calcOpticalFlowPyrLK(
        gris0, gris, p0, None, winSize=(21, 21), maxLevel=3,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
    ok = st.ravel() == 1
    if ok.sum() < 20:
        return np.array([[1.0, 0, 0], [0, 1.0, 0]]), 0.0
    A, _ = cv2.estimateAffinePartial2D(p0[ok], p1[ok], method=cv2.RANSAC,
                                       ransacReprojThreshold=2.0)
    if A is None:
        return np.array([[1.0, 0, 0], [0, 1.0, 0]]), 0.0
    d = float(np.median(np.linalg.norm((p1[ok] - p0[ok]).reshape(-1, 2), axis=1)))
    return A, d


# ==================================================================================
# 3. STI
# ==================================================================================
def construir_sti(ruta, geo, n_frames=None, verbose=True):
    """Una sola pasada por el video. Devuelve (STI, Yv, info, densidad).

    STI tiene forma (N_ESTACIONES, n_frames, n_muestras) y lleva la banda promediada y la media
    temporal por posicion ya restada. Se promedia la banda ANTES de restar la media temporal, no
    despues, porque las dos operaciones conmutan y asi solo hay que guardar una STI por estacion
    en vez de una por linea -- 140 MB en lugar de 1.5 GB sobre el video completo.

    `densidad` es, por estacion, la fraccion de celdas (fotograma, posicion) en las que alguna
    linea de la banda supera UMBRAL_PARTICULA. Se cuenta sobre las lineas SIN promediar: si se
    midiera sobre la banda ya promediada, una particula que solo aparece en 1 de las 11 lineas
    quedaria dividida por 11 y no llegaria al umbral, con lo que la densidad saldria 0 incluso en
    estaciones cuyas estelas se ven a simple vista.
    """
    DS = V_ESPERADA / FPS_REAL[0]
    n_mues = int((Y_MAX - Y_MIN) / DS)
    Yv = Y_MIN + DS * np.arange(n_mues)
    Xs = geo.estaciones()
    offs = np.linspace(-BANDA / 2, BANDA / 2, N_LINEAS)
    mapas = np.empty((N_ESTACIONES, N_LINEAS, n_mues, 2), np.float32)
    for a, X in enumerate(Xs):
        for b, o in enumerate(offs):
            mapas[a, b] = geo.a_imagen(np.column_stack([np.full(n_mues, X + o), Yv]))
    pts = mapas.reshape(-1, 2)
    nr = N_ESTACIONES * N_LINEAS

    cap, ntot, fps = abrir_video(ruta)
    NF = ntot if n_frames is None else min(n_frames, ntot)
    ok, f = cap.read()
    if not ok:
        raise SystemExit("video vacio")
    g0 = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    mask = np.zeros(g0.shape, np.uint8)
    mask[0:FILA_BORDE_FIN - 40, :] = 255
    cv2.fillPoly(mask, [geo.poligono_agua()], 0)
    p0 = cv2.goodFeaturesToTrack(g0, 600, 0.01, 7, mask=mask)
    if p0 is None:
        raise SystemExit("no hay puntos estaticos para estabilizar")

    sti = np.zeros((N_ESTACIONES, NF, n_mues), np.float32)
    n_part = np.zeros(N_ESTACIONES, np.int64)
    n_celdas = 0
    derivas = []
    t0 = time.time()
    for i in range(NF):
        if i > 0:
            ok, f = cap.read()
            if not ok:
                break
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        else:
            g = g0
        A, d = estimar_estabilizacion(g0, g, p0)
        derivas.append(d)
        t = realzar(g)
        xy = pts @ A[:, :2].T + A[:, 2]
        v = cv2.remap(t, xy[:, 0].reshape(nr, n_mues).astype(np.float32),
                      xy[:, 1].reshape(nr, n_mues).astype(np.float32), cv2.INTER_LINEAR)
        v = v.reshape(N_ESTACIONES, N_LINEAS, n_mues)
        sti[:, i, :] = v.mean(axis=1)
        n_part += (v.max(axis=1) > UMBRAL_PARTICULA).sum(axis=1)
        n_celdas += n_mues
        if verbose and (i + 1) % 300 == 0:
            print("   %d/%d fotogramas (%.1fs)" % (i + 1, NF, time.time() - t0), flush=True)
    cap.release()
    NF = len(derivas)
    sti = sti[:, :NF, :]
    sti -= sti.mean(axis=1, keepdims=True)
    densidad = n_part / float(max(n_celdas, 1))
    info = {"n_frames": NF, "fps": fps, "DS": DS, "n_muestras": n_mues,
            "deriva_mediana": float(np.median(derivas)),
            "deriva_max": float(np.max(derivas)),
            "segundos": time.time() - t0}
    return sti, Yv, info, densidad


FPS_REAL = [29.975]


# ==================================================================================
# 4. Tensor de estructura con seleccion por senal
# ==================================================================================
def tensor_seleccion(im, blk=LADO_BLOQUE, cuantil=CUANTIL_SENAL,
                     sigma=SIGMA_TENSOR, solape=SOLAPE):
    """Pendiente dominante de la STI, en muestras por fotograma.

    Vectorizado con boxFilter. Devuelve (pendiente, coherencia, n_usados, n_total).
    La mediana ponderada por coherencia se toma SOLO sobre los bloques cuyo maximo supera el
    cuantil pedido, que son los que contienen particula. Sin esa seleccion el residuo estatico
    -- vertical en la STI, o sea pendiente cero -- gana por mayoria.
    """
    im = np.ascontiguousarray(im, dtype=np.float32)
    g = cv2.GaussianBlur(im, (0, 0), sigma)
    gt, gs = np.gradient(g)
    K = (blk, blk)
    Jss = cv2.boxFilter(gs * gs, -1, K, normalize=False)
    Jtt = cv2.boxFilter(gt * gt, -1, K, normalize=False)
    Jst = cv2.boxFilter(gs * gt, -1, K, normalize=False)
    Emax = cv2.dilate(im, np.ones((blk, blk), np.uint8))
    h, w = im.shape
    stp = max(1, int(blk * (1 - solape)))
    off = blk // 2
    r = np.arange(off, h - off, stp)
    c = np.arange(off, w - off, stp)
    if len(r) < 2 or len(c) < 2:
        return np.nan, 0.0, 0, 0
    R, C = np.meshgrid(r, c, indexing="ij")
    jss, jtt, jst, e = Jss[R, C], Jtt[R, C], Jst[R, C], Emax[R, C]
    tr = jss + jtt
    ok = tr > 1e-12
    ang = 0.5 * np.arctan2(2 * jst, jss - jtt)
    coh = np.where(ok, np.hypot(jss - jtt, 2 * jst) / np.maximum(tr, 1e-12), 0.0)
    ang, coh, e = ang[ok], coh[ok], e[ok]
    ntot = int(ang.size)
    if ntot < 8:
        return np.nan, 0.0, 0, ntot
    m = e >= np.quantile(e, cuantil)
    if m.sum() < 5:
        return np.nan, 0.0, 0, ntot
    a, cc = ang[m], coh[m]
    o = np.argsort(a)
    a, cc = a[o], cc[o]
    cw = np.cumsum(cc)
    med = a[np.searchsorted(cw, cw[-1] / 2)]
    return float(-np.tan(med)), float(np.median(cc)), int(m.sum()), ntot


def cresta_fft(im, n_bins=720, r_min=0.06, r_max=0.95):
    """Segundo estimador de la pendiente: la cresta del espectro 2D de la STI.

    Un patron que se traslada, f(s,t) = g(s - m*t), tiene transformada
    G(k_s) * delta(k_s*m + omega): toda su energia vive sobre UNA RECTA por el origen del plano
    (k_s, omega). Asi que la pendiente se puede leer sin tensor ninguno, agrupando la potencia por
    angulo y buscando el maximo. Es la variante espectral clasica de STIV.

    Se incluye porque no comparte con el tensor mas que la STI: el tensor es una medida local
    promediada sobre bloques y esto es una medida global en frecuencia. Si los dos coinciden, la
    pendiente esta en el dato y no en el estimador. Se excluyen la cruz de continua (donde vive el
    residuo estatico) y los radios extremos (ruido de un pixel y el termino medio).

    Devuelve (pendiente, agudeza), donde agudeza es el pico del histograma angular dividido por su
    mediana: cuanto mas alto, mas concentrada esta la energia en una sola direccion.
    """
    a = np.asarray(im, np.float32)
    a = a - a.mean()
    a = a * np.hanning(a.shape[0])[:, None] * np.hanning(a.shape[1])[None, :]
    P = np.abs(np.fft.fftshift(np.fft.fft2(a))) ** 2
    w = np.fft.fftshift(np.fft.fftfreq(a.shape[0]))
    k = np.fft.fftshift(np.fft.fftfreq(a.shape[1]))
    K, W = np.meshgrid(k, w)
    rad = np.hypot(K / 0.5, W / 0.5)
    ok = (rad > r_min) & (rad < r_max) & (np.abs(K) > 2e-3) & (np.abs(W) > 2e-3)
    if ok.sum() < 200:
        return np.nan, 0.0
    th = np.mod(np.arctan2(W[ok], K[ok]), np.pi)
    num, bordes = np.histogram(th, bins=n_bins, range=(0, np.pi), weights=P[ok])
    den, _ = np.histogram(th, bins=n_bins, range=(0, np.pi))
    h = num / np.maximum(den, 1)
    h = np.convolve(np.r_[h[-15:], h, h[:15]], np.ones(11) / 11, mode="same")[15:-15]
    i = int(np.argmax(h))
    med = float(np.median(h))
    return float(-np.tan((bordes[i] + bordes[i + 1]) / 2)), float(h[i] / max(med, 1e-12))


# ==================================================================================
# 5. Medida por estacion + control de calidad
# ==================================================================================
def motivos_rechazo(dens, v, coh):
    """Criterios de calidad de una estacion. Devuelve la lista de los que fallan, vacia si pasa.

    Los criterios se evaluan de forma INDEPENDIENTE, no en cadena, para que el informe diga
    cuantas redes atrapan cada estacion y no solo la primera. Importa: la estacion pegada a la
    orilla izquierda tiene densidad de agua con trazador (0.0102, dentro de los dos umbrales) y
    solo la paran la coherencia -- por 0.02 de margen -- y la cota fisica, que la caza por un
    factor 13. Con la version encadenada eso no se veia.

    Esta funcion es la unica definicion del control de calidad del caso: la usan igual la medida
    sobre el video completo y las ventanas de `video_velocidad.py`.
    """
    motivos = []
    if dens < DENSIDAD_MIN:
        motivos.append("sin_trazador")
    if dens > DENSIDAD_MAX:
        motivos.append("orilla")
    if not np.isfinite(v):
        motivos.append("sin_tensor")
    else:
        if coh < COH_MIN:
            motivos.append("coherencia")
        if abs(v) > V_MAX_FISICA:
            motivos.append("v_no_fisica")
        if v <= 0:
            motivos.append("sentido")
    return motivos


def medir(sti, geo, DS, fps, densidad):
    Xs = geo.estaciones()
    filas = []
    for a in range(len(Xs)):
        im = sti[a]
        dens = float(densidad[a])
        pend, coh, nsel, ntot = tensor_seleccion(im)
        v = pend * DS * fps if np.isfinite(pend) else np.nan
        # segundo estimador, solo diagnostico: no entra en el control de calidad ni en el
        # resultado, esta para poder ver si la pendiente depende del estimador
        pend_f, agudeza = cresta_fft(im)
        v_fft = pend_f * DS * fps if np.isfinite(pend_f) else np.nan
        motivos = motivos_rechazo(dens, v, coh)
        filas.append({
            "estacion": a,
            "X": float(Xs[a]),
            "X_rel": float((Xs[a] - geo.X_izq) / geo.ancho),
            "densidad": dens,
            "coherencia": coh,
            "n_bloques": nsel,
            "n_bloques_total": ntot,
            "v": float(v) if np.isfinite(v) else float("nan"),
            "v_fft": float(v_fft) if np.isfinite(v_fft) else float("nan"),
            "agudeza_fft": agudeza,
            "aceptada": len(motivos) == 0,
            "motivo": ";".join(motivos) if motivos else "",
        })
    return filas


def resumen(filas, geo):
    ac = [f for f in filas if f["aceptada"]]
    if not ac:
        return {"n_aceptadas": 0}
    v = np.array([f["v"] for f in ac])
    return {
        "n_aceptadas": len(ac),
        "n_estaciones": len(filas),
        "v_mediana": float(np.median(v)),
        "v_q05": float(np.percentile(v, 5)),
        "v_q95": float(np.percentile(v, 95)),
        "v_max": float(v.max()),
        "v_min": float(v.min()),
        "v_mediana_anchos": float(np.median(v) / geo.ancho),
        "ancho_canal": geo.ancho,
    }


def barrer_focal(gris, ruta, n_frames=600):
    """Sensibilidad del resultado a FOCAL, que es el unico parametro no medible."""
    out = []
    for F in (600.0, 700.0, 780.0, 900.0, 1000.0):
        geo = Geometria(gris, focal=F)
        sti, Yv, info, dens = construir_sti(ruta, geo, n_frames=n_frames, verbose=False)
        fil = medir(sti, geo, info["DS"], info["fps"], dens)
        r = resumen(fil, geo)
        out.append((F, np.degrees(geo.inclinacion), geo.ancho,
                    r.get("v_mediana", np.nan), r.get("v_mediana_anchos", np.nan)))
    return out


# ==================================================================================
# CLI
# ==================================================================================
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--video", default=ARCHIVO_VIDEO)
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--sin-figuras", action="store_true")
    ap.add_argument("--barrer-focal", action="store_true")
    a = ap.parse_args()
    os.makedirs(DIR_SALIDAS, exist_ok=True)

    cap, ntot, fps = abrir_video(a.video)
    FPS_REAL[0] = fps
    ok, f0 = cap.read()
    cap.release()
    gris0 = cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY)
    print("video: %d fotogramas a %.3f fps (%.1f s), %dx%d" %
          (ntot, fps, ntot / fps, gris0.shape[1], gris0.shape[0]))

    geo = Geometria(gris0)
    print("\n== geometria ==")
    print("  orilla izq  x = %+.4f*y %+.2f   (%d/%d inliers)" %
          (geo.al, geo.bl, geo.inliers[0], geo.inliers[1]))
    print("  orilla der  x = %+.4f*y %+.2f   (%d/%d inliers)" %
          (geo.ar, geo.br, geo.inliers[2], geo.inliers[3]))
    print("  punto de fuga  (%.1f, %.1f)   horizonte y = %.1f" % (geo.xv, geo.yv, geo.yv))
    print("  inclinacion  %.2f deg  (FOCAL = %.0f)" % (np.degrees(geo.inclinacion), geo.focal))
    print("  ancho del canal  %.4f alturas de camara" % geo.ancho)
    # No es una autocomprobacion: el punto de fuga es la interseccion de las dos orillas, asi
    # que la homografia las manda a paralelas por construccion y esto ha de dar 0 siempre.
    # Solo delata un error de programacion en la homografia.
    print("  (identidad de control, ha de ser 0: variacion del ancho = %.1e %%)"
          % (100 * geo.ancho_variacion))

    print("\n== construyendo la STI ==")
    sti, Yv, info, densidad = construir_sti(a.video, geo, n_frames=a.frames)
    print("  %d fotogramas, %d muestras, DS = %.6f alt.cam (%.1f s)" %
          (info["n_frames"], info["n_muestras"], info["DS"], info["segundos"]))
    print("  deriva de camara: mediana %.2f px, maxima %.2f px" %
          (info["deriva_mediana"], info["deriva_max"]))

    filas = medir(sti, geo, info["DS"], info["fps"], densidad)
    print("\n== estaciones ==")
    print("  #   X       dens     coh    v(tensor)  v(FFT)   agud   estado")
    for f in filas:
        print("  %2d  %+.3f  %.5f  %.3f  %+8.4f  %+8.4f  %5.1f  %s" %
              (f["estacion"], f["X"], f["densidad"], f["coherencia"], f["v"],
               f["v_fft"], f["agudeza_fft"], "OK" if f["aceptada"] else f["motivo"]))
    ac = [f for f in filas if f["aceptada"]]
    if ac:
        t = np.array([f["v"] for f in ac]); ff = np.array([f["v_fft"] for f in ac])
        m = np.isfinite(ff) & (ff > 0)
        if m.sum() >= 3:
            print("  los dos estimadores sobre las aceptadas: tensor %.4f, FFT %.4f, "
                  "diferencia mediana %+.1f %%"
                  % (np.median(t[m]), np.median(ff[m]), 100 * np.median(t[m] / ff[m] - 1)))
    r = resumen(filas, geo)
    print("\n== resultado ==")
    if r["n_aceptadas"] == 0:
        print("  ninguna estacion aceptada")
    else:
        print("  estaciones aceptadas   %d de %d" % (r["n_aceptadas"], r["n_estaciones"]))
        print("  v superficial mediana  %.4f alturas de camara/s" % r["v_mediana"])
        print("     q05-q95             %.4f - %.4f" % (r["v_q05"], r["v_q95"]))
        print("  v en anchos de canal   %.4f anchos/s" % r["v_mediana_anchos"])
        print("  (ancho del canal = %.4f alturas de camara)" % r["ancho_canal"])

    with open(os.path.join(DIR_SALIDAS, "perfil_velocidades.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    cfg = {
        "video": a.video, "focal": geo.focal,
        "orilla_izq": [geo.al, geo.bl], "orilla_der": [geo.ar, geo.br],
        "punto_fuga": [geo.xv, geo.yv], "inclinacion_deg": float(np.degrees(geo.inclinacion)),
        "ancho_canal": geo.ancho, "ancho_variacion": geo.ancho_variacion,
        "retranqueo": RETRANQUEO, "tophat_k": TOPHAT_K, "sigma_previo": SIGMA_PREVIO,
        "v_esperada": V_ESPERADA, "Y_min": Y_MIN, "Y_max": Y_MAX,
        "n_estaciones": N_ESTACIONES, "banda": BANDA, "n_lineas": N_LINEAS,
        "lado_bloque": LADO_BLOQUE, "solape": SOLAPE, "sigma_tensor": SIGMA_TENSOR,
        "cuantil_senal": CUANTIL_SENAL, "coh_min": COH_MIN,
        "densidad_min": DENSIDAD_MIN, "densidad_max": DENSIDAD_MAX,
        "umbral_particula": UMBRAL_PARTICULA,
        "v_max_fisica": V_MAX_FISICA, "unidades": "alturas de camara por segundo",
        "info": info, "resumen": r,
    }
    with open(os.path.join(DIR_SALIDAS, "config_stiv_canal.json"), "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)
    print("\nescrito: salidas/perfil_velocidades.csv, salidas/config_stiv_canal.json")

    if a.barrer_focal:
        print("\n== sensibilidad a FOCAL (600 fotogramas) ==")
        for F, tilt, anc, v, va in barrer_focal(gris0, a.video):
            print("  F=%4.0f  incl %5.2f deg  ancho %.4f  v %.4f alt.cam/s  %.4f anchos/s"
                  % (F, tilt, anc, v, va))

    if not a.sin_figuras:
        import figuras
        figuras.todas(gris0, geo, sti, Yv, info, filas, r, a.video)
        print("figuras escritas en salidas/")


if __name__ == "__main__":
    main()
