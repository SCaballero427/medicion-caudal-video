"""Filtro adaptado por hipotesis de velocidad sobre los 81 s enteros, para el campo lejano.

Que es y por que no es mas de lo mismo
--------------------------------------
`analisis_canal_lejano_stiv/` dejo demostrado que el campo lejano del canal no es medible **ni
por el tensor de estructura ni por correlacion de conjunto**. Este es el ultimo intento, y usa
la unica familia de metodos que quedaba sin probar: integrar coherentemente sobre **todo** el
video en vez de sobre bloques.

La idea: para cada velocidad candidata `v` se recorre la trayectoria que seguiria una particula
a esa velocidad, `s(t) = s0 + v*t`, y se suma la imagen a lo largo de ella. Si `v` es la de
verdad, cada particula se apila consigo misma en fase y aparece un pico; si no lo es, se
difumina. Es "track-before-detect" clasico, y equivale a la transformada de Radon de la STI.

Lo que lo hace distinto de lo ya probado son tres cosas, y conviene ser preciso sobre cual pesa:

- **Se integra sobre la ventana de residencia entera**, no sobre bloques de 64 fotogramas como
  el tensor. Para una senal por debajo del ruido en cada fotograma, eso es lo unico que importa.
- **Se muestrea a la resolucion nativa de la imagen**, no al DS de 45 grados, que es precisamente
  el submuestreo que aliaseaba la STI en el campo lejano.
- **Se puntua con el maximo, no con la energia.** La energia de una proyeccion esta determinada
  por el espectro de potencia 2D (teorema de proyeccion-corte), asi que puntuar asi es repetir el
  `cresta_fft` del caso principal. El maximo y la curtosis no lo estan.

Nota honesta sobre esa ultima: la apuesta inicial fue que la **curtosis** seria el discriminador,
porque con trazador escaso la velocidad correcta concentra las particulas en pocos picos altos y
la incorrecta las reparte con la misma energia. La validacion sintetica la desmintio -- con
decenas de particulas sobre ~170 posiciones la proyeccion no es lo bastante dispersa y la
curtosis resulto ser el mas flojo de los tres. El que manda es el **maximo normalizado por MAD**,
que es el detector clasico de track-before-detect. Se calculan los tres y se reportan los tres.

Que se responde, y con que controles
------------------------------------
Un metodo que solo se aplica al sitio donde no se sabe la respuesta no dice nada. Aqui van
cuatro cosas a la vez:

1. **Validacion sintetica.** Se inyecta una estela de velocidad conocida en ruido y se comprueba
   que el filtro la recupera. Sin esto no se sabe si un fracaso es del agua o del codigo.
2. **Control positivo.** El campo cercano, donde la respuesta se conoce (+0.059). Si el filtro no
   lo encuentra ahi, su veredicto sobre el campo lejano no vale nada.
3. **Hipotesis nula por barajado.** Se permuta el orden de los fotogramas, lo que destruye toda
   coherencia temporal pero conserva la estadistica espacial de cada uno. Cualquier pico que
   sobreviva a eso es un artefacto del metodo, no agua. Da el umbral de significacion.
4. **Escalera de degradacion.** Se reduce el campo CERCANO por factores crecientes, simulando
   alejarlo, hasta que la deteccion muere. Eso convierte un "no lo encuentro" en un "hace falta
   tanta resolucion", que es la pregunta util.

Uso
---
    python filtro_adaptado.py                 # todo (~10 min)
    python filtro_adaptado.py --solo-sintetico
    python filtro_adaptado.py --frames 1200
"""
import argparse
import csv
import json
import os
import sys

import cv2
import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "analisis_canal_riego_stiv"))
import stiv_canal as sc  # noqa: E402

DIR_CASO = os.path.dirname(os.path.abspath(__file__))
DIR_SALIDAS = os.path.join(DIR_CASO, "salidas")

# ----------------------------------------------------------------------------------
# >>> AJUSTABLE <<<
# ----------------------------------------------------------------------------------
# Bandas: (X0, X1, Y0, Y1, etiqueta). X se limita a la mitad con trazador del caso.
BANDAS = [
    (0.10, 0.90, 1.60, 2.90, "cerca"),
    (0.10, 0.90, 3.30, 4.90, "media"),
    (0.10, 0.90, 5.00, 8.50, "lejos"),
]
# Velocidades candidatas, en alturas de camara/s, ambos signos. El rango se limita a +-0.15 --
# unas 2.5 veces la del caso -- y no a la celeridad de onda que se sospechaba (~1.2) por una
# razon de diseno: la ventana de integracion tiene que ser el tiempo que una particula tarda en
# cruzar la banda a la velocidad MAS RAPIDA del barrido, asi que ampliar el rango acorta la
# ventana para todos y tira la sensibilidad. La hipotesis de onda ya quedo descartada aparte, en
# `analisis_canal_lejano_stiv/`, por el ensayo de diezmado temporal.
V_MIN, V_MAX, N_CAND = -0.15, 0.15, 121
# Lineas paralelas dentro de la banda de X, promediadas como en el caso.
N_LINEAS = 15
# Barajados para la hipotesis nula. Cada uno da una curva completa; el umbral es el maximo
# sobre todos ellos y sobre todas las velocidades.
N_BARAJADOS = 12
# Factores de reduccion de la escalera de degradacion. 1 = sin tocar.
FACTORES = [1.0, 1.5, 2.0, 3.0, 4.5, 6.5]
SEMILLA = 20260818


# ==================================================================================
# el filtro
# ==================================================================================
def proyecciones(sti, vs, fps, ds, n_ventana=None):
    """Suma a lo largo de la trayectoria, para cada velocidad candidata.

    Devuelve `(P, C)`, ambos de forma (n_ventanas, n_cand, n_muestras): la proyeccion y el
    numero de muestras validas que la formaron en cada posicion.

    Tres cosas que la primera version hizo mal y que la invalidaban, todas descubiertas porque
    **el control positivo no recuperaba la velocidad conocida del campo cercano**:

    1. **El desplazamiento no puede ser circular.** Se implemento con el teorema del
       desplazamiento de Fourier, que es rapido y exacto para fracciones, pero envuelve: cuando
       la trayectoria se sale de la banda reaparece por el otro lado y mezcla senal. Aqui se
       desplaza con relleno de ceros y se lleva la **cuenta de muestras validas** en cada
       posicion, de modo que una trayectoria que abandona la banda simplemente deja de sumar.

    2. **El tiempo de integracion tiene que ser el mismo para todas las candidatas.** Una
       particula solo esta dentro de la banda mientras la cruza -- unos 22 s a la velocidad real,
       no los 81 del video -- asi que integrar el video entero anade ruido puro el 73 % del
       tiempo. Y como una candidata lenta permanece mas, acumula mas promediado y sale
       artificialmente favorecida: por eso el pico se iba a +0.015. Se integra en ventanas de
       `n_ventana` fotogramas, iguales para todas las velocidades.

    3. **Cada ventana se puntua por separado y se promedian las PUNTUACIONES**, no las
       proyecciones. Promediar las proyecciones supondria que la misma particula esta en la misma
       posicion en todas las ventanas, que es justo lo que no pasa: solo promedia ruido. Lo
       correcto es combinar detecciones, no senales.
    """
    NF, n = sti.shape
    if n_ventana is None or n_ventana >= NF:
        ventanas = [(0, NF)]
    else:
        ventanas = [(w, w + n_ventana) for w in range(0, NF - n_ventana + 1, n_ventana)]
    s0 = np.arange(n)
    P = np.zeros((len(ventanas), len(vs), n), np.float32)
    C = np.zeros((len(ventanas), len(vs), n), np.float32)
    for j, (w0, w1) in enumerate(ventanas):
        blk = sti[w0:w1]
        tt = np.arange(w1 - w0)
        for i, v in enumerate(vs):
            idx = s0[None, :] + (v * tt / fps / ds)[:, None]
            i0 = np.floor(idx).astype(np.int64)
            fr = idx - i0
            val = (i0 >= 0) & (i0 + 1 < n)
            i0c = np.clip(i0, 0, n - 2)
            fila = np.take_along_axis(blk, i0c, axis=1) * (1 - fr) + \
                np.take_along_axis(blk, i0c + 1, axis=1) * fr
            P[j, i] = np.where(val, fila, 0.0).sum(axis=0)
            C[j, i] = val.sum(axis=0)
    return P / np.maximum(C, 1), C


def puntuar(PC, cual="pico", cobertura_min=0.8):
    """Puntua cada (ventana, candidata) y promedia sobre ventanas. Devuelve (n_cand,).

    Solo se puntuan las posiciones cuya trayectoria ha permanecido dentro de la banda al menos
    `cobertura_min` del tiempo de la ventana. Sin ese recorte, las posiciones del borde -- que
    reciben cuatro muestras -- tienen una varianza enorme y disparan maximos espurios: es lo que
    inflaba el techo de la hipotesis nula y ahogaba la deteccion.
    """
    P, C = PC
    nv, nc, n = P.shape
    out = np.zeros(nc)
    for j in range(nv):
        for i in range(nc):
            m = C[j, i] >= cobertura_min * C[j, i].max()
            if m.sum() < 8:
                continue
            out[i] += _score(P[j, i][m], cual)
    return out / max(nv, 1)


def _score(P, cual):
    """Estadistico de cada proyeccion. Tres, porque no miden lo mismo.

    - `pico`: (max - mediana) / MAD. Es el detector clasico de "track-before-detect": si la
      velocidad es la correcta, cada particula se apila consigo misma y sobresale. Es el que
      manda, y el que mejor se comporta con trazador escaso.
    - `curtosis`: cuarto momento. Estadistico de orden superior, no determinado por el espectro.
      Resulto ser flojo aqui -- con decenas de particulas repartidas sobre ~160 posiciones la
      proyeccion no es lo bastante dispersa -- pero se reporta porque es el que separaria un
      apilamiento en pocos picos de uno repartido.
    - `varianza`: segundo orden. Se incluye a proposito para dejar constancia de que **no aporta
      nada nuevo**: por el teorema de proyeccion-corte, barrer la varianza contra la velocidad es
      exactamente recorrer el espectro de potencia 2D por rectas, que es lo que ya hace
      `cresta_fft` en el caso principal.
    """
    Q = P - P.mean()
    if cual == "varianza":
        return float((Q ** 2).mean())
    if cual == "curtosis":
        m2 = float((Q ** 2).mean())
        return float((Q ** 4).mean() / max(m2 ** 2, 1e-30))
    med = float(np.median(Q))
    mad = float(np.median(np.abs(Q - med))) * 1.4826
    return float((Q.max() - med) / max(mad, 1e-30))


ESTADISTICOS = ("pico", "curtosis", "varianza")


def ventana_residencia(ancho_banda, fps, v_max=V_MAX):
    """Fotogramas que tarda una particula en cruzar la banda a la velocidad mas rapida barrida.

    Es el tiempo de integracion util: mas alla, la trayectoria ya ha salido de la banda y solo
    anade ruido. Se usa el mismo para todas las candidatas para que compitan en igualdad.
    """
    return max(60, int(ancho_banda / max(v_max, 1e-6) * fps))


def analizar_todo(sti, vs, fps, ds, rng, n_barajados=N_BARAJADOS, n_ventana=None):
    """Como `analizar`, pero calculando las proyecciones UNA vez y puntuandolas de tres formas.

    Las proyecciones no dependen del estadistico, asi que recalcularlas por cada uno triplicaba
    el trabajo del barrido, que es lo unico caro aqui.
    """
    P_real = proyecciones(sti, vs, fps, ds, n_ventana)
    P_inv = proyecciones(sti[::-1].copy(), vs, fps, ds, n_ventana)
    P_nulos = []
    for _ in range(n_barajados):
        P_nulos.append(proyecciones(sti[rng.permutation(sti.shape[0])], vs, fps, ds, n_ventana))
    res = {}
    for cual in ESTADISTICOS:
        nulos = np.array([puntuar(Pn, cual) for Pn in P_nulos])
        res[cual] = dict(real=puntuar(P_real, cual), invertido=puntuar(P_inv, cual),
                         nulos=nulos, nulo_max=nulos.max(axis=0),
                         nulo_med=nulos.mean(axis=0), nulo_std=nulos.std(axis=0))
    return res


def analizar(sti, vs, fps, ds, rng, n_barajados=N_BARAJADOS, cual="pico"):
    """Curva real, curva de tiempo invertido y distribucion nula por barajado.

    El barajado de fotogramas destruye toda coherencia temporal y conserva la estadistica
    espacial de cada uno. Con una salvedad que hay que tener presente: **cerca de v = 0 la nula
    no vale**, porque sumar a lo largo de una trayectoria de velocidad nula es la media temporal,
    que no depende del orden de los fotogramas. Por eso el veredicto excluye una banda alrededor
    de cero (y por eso ademas se resta la media temporal por posicion al construir la STI, que ya
    deja el termino v = 0 en nada).
    """
    P = proyecciones(sti, vs, fps, ds)
    real = puntuar(P, cual)
    invertido = puntuar(proyecciones(sti[::-1].copy(), vs, fps, ds), cual)
    nulos = []
    for _ in range(n_barajados):
        idx = rng.permutation(sti.shape[0])
        nulos.append(puntuar(proyecciones(sti[idx], vs, fps, ds), cual))
    nulos = np.array(nulos)
    return dict(real=real, invertido=invertido, nulos=nulos,
                nulo_max=nulos.max(axis=0), nulo_med=nulos.mean(axis=0),
                nulo_std=nulos.std(axis=0))


# Banda alrededor de v = 0 que se excluye del veredicto, en alturas de camara/s. Debajo de esto
# la trayectoria apenas se separa de la horizontal en 81 s y la nula por barajado no discrimina.
ZONA_MUERTA = 0.012


def veredicto(res, vs, zona_muerta=ZONA_MUERTA):
    """Pico de la curva real, fuera de la zona muerta, y su significacion contra la nula."""
    ok = np.abs(vs) >= zona_muerta
    idx = np.where(ok)[0]
    # El pico se busca sobre el z respecto a la nula EN CADA VELOCIDAD, no sobre el score en
    # bruto. Importa: el score en bruto tiene una linea base que depende de v, porque a mayor
    # velocidad la mascara de cobertura deja menos posiciones y el maximo sobre menos puntos es
    # sistematicamente menor (estadistica de extremos). Eso empujaba el argmax hacia velocidades
    # bajas. Restar y dividir por la nula de esa misma velocidad aplana la linea base.
    z_v = (res["real"] - res["nulo_med"]) / np.maximum(res["nulo_std"], 1e-12)
    i = idx[int(np.argmax(z_v[ok]))]
    pico, v_pico = float(res["real"][i]), float(vs[i])
    # techo estricto: maximo de la nula sobre todas las velocidades utiles y todos los barajados
    techo = float(res["nulos"][:, ok].max())
    mu = float(res["nulo_med"][ok].mean())
    sd = float(res["nulo_std"][ok].mean())
    z = float(z_v[i])
    z_i = (res["invertido"] - res["nulo_med"]) / np.maximum(res["nulo_std"], 1e-12)
    j = idx[int(np.argmax(z_i[ok]))]
    return dict(v_pico=v_pico, score=pico, techo_nulo=techo,
                supera_nulo=bool(pico > techo), z=z,
                v_pico_invertido=float(vs[j]))


# ==================================================================================
# 1. validacion sintetica
# ==================================================================================
def sintetico(vs, fps, ds, rng, v_real=0.059, n=160, NF=2429, amp=6.0, n_part=40, ruido=1.0):
    """Estelas de velocidad conocida en ruido, con la misma escasez que el video real."""
    sti = rng.normal(0, ruido, (NF, n)).astype(np.float32)
    for _ in range(n_part):
        t0 = rng.integers(0, NF)
        s0 = rng.uniform(0, n)
        dur = int(rng.integers(NF // 6, NF))
        tt = np.arange(t0, min(NF, t0 + dur))
        ss = s0 + v_real * (tt - t0) / fps / ds
        m = (ss >= 0) & (ss < n - 1)
        tt, ss = tt[m], ss[m]
        i0 = ss.astype(int)
        f = ss - i0
        sti[tt, i0] += amp * (1 - f)
        sti[tt, i0 + 1] += amp * f
    return sti - sti.mean(axis=0, keepdims=True)


# ==================================================================================
# lectura de bandas
# ==================================================================================
def afines_del_original(video, geo, NF):
    """Transformaciones de estabilizacion estimadas UNA vez sobre el video original.

    Hacen falta para los experimentos que degradan el video: a 16 kb/s el fotograma queda tan
    liso que `goodFeaturesToTrack` no encuentra ni una esquina y la estabilizacion falla. Pero
    ademas, estimarla por separado en cada version degradada meteria un confusor -- la
    estabilizacion seria peor justo donde hay menos textura, y no se sabria si lo que se pierde
    es senal o encuadre. El movimiento de camara es el mismo en todas las versiones, asi que se
    mide en el original y se reutiliza.
    """
    cap, ntot, fps = sc.abrir_video(video)
    NF = min(NF, ntot)
    ok, f = cap.read()
    g0 = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    mask = np.zeros(g0.shape, np.uint8)
    mask[0:sc.FILA_BORDE_FIN - 40, :] = 255
    cv2.fillPoly(mask, [geo.poligono_agua()], 0)
    p0 = cv2.goodFeaturesToTrack(g0, 600, 0.01, 7, mask=mask)
    out = np.zeros((NF, 2, 3), np.float64)
    out[0] = np.array([[1.0, 0, 0], [0, 1.0, 0]])
    for i in range(1, NF):
        ok, f = cap.read()
        if not ok:
            out = out[:i]
            break
        A, _ = sc.estimar_estabilizacion(g0, cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), p0)
        out[i] = A
    cap.release()
    return out


def construir_stis(video, geo, bandas, NF, factor=1.0, verbose=True, afines=None):
    """STI de cada banda, muestreada a la resolucion NATIVA de la imagen.

    `factor` reduce el fotograma antes del realce, para la escalera de degradacion: simula
    alejar la camara, que es lo que hace las particulas mas pequenas y mas tenues.

    `afines`, si se pasa, son las transformaciones de estabilizacion ya calculadas (ver
    `afines_del_original`); si no, se estiman sobre este mismo video.
    """
    def resolucion(Y):
        p = geo.a_imagen([[0, Y]])[0]
        q = geo.a_suelo([[p[0], p[1] + 1]])[0]
        return abs(q[1] - Y)

    cap, ntot, fps = sc.abrir_video(video)
    NF = min(NF, ntot)
    ok, f = cap.read()
    g0 = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    mask = np.zeros(g0.shape, np.uint8)
    mask[0:sc.FILA_BORDE_FIN - 40, :] = 255
    cv2.fillPoly(mask, [geo.poligono_agua()], 0)
    p0 = cv2.goodFeaturesToTrack(g0, 600, 0.01, 7, mask=mask)

    planes = []
    for (x0, x1, y0, y1, et) in bandas:
        ds = resolucion((y0 + y1) / 2) * factor       # al reducir, un pixel cubre mas suelo
        n = max(32, int((y1 - y0) / ds))
        Yv = np.linspace(y0, y1, n)
        Xs = np.linspace(x0, x1, N_LINEAS)
        M = np.empty((N_LINEAS, n, 2), np.float32)
        for b, X in enumerate(Xs):
            M[b] = geo.a_imagen(np.column_stack([np.full(n, X), Yv]))
        planes.append(dict(et=et, n=n, ds=(y1 - y0) / (n - 1), pts=M.reshape(-1, 2),
                           sti=np.zeros((NF, n), np.float32), y0=y0, y1=y1))
    leidos = 0
    for i in range(NF):
        if i > 0:
            ok, f = cap.read()
            if not ok:
                break
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        else:
            g = g0
        if afines is not None:
            A = afines[i] if i < len(afines) else afines[-1]
        elif p0 is None:
            A = np.array([[1.0, 0, 0], [0, 1.0, 0]])
        else:
            A, _ = sc.estimar_estabilizacion(g0, g, p0)
        if factor != 1.0:
            # reducir y volver a ampliar: las particulas pierden tamano y contraste igual que
            # si la camara estuviera mas lejos, pero la geometria no cambia
            h, w = g.shape
            chico = cv2.resize(g, (max(8, int(w / factor)), max(8, int(h / factor))),
                               interpolation=cv2.INTER_AREA)
            g = cv2.resize(chico, (w, h), interpolation=cv2.INTER_LINEAR)
        t = sc.realzar(g)
        for P in planes:
            xy = P["pts"] @ A[:, :2].T + A[:, 2]
            mx = np.ascontiguousarray(xy[:, 0].reshape(N_LINEAS, P["n"]), np.float32)
            my = np.ascontiguousarray(xy[:, 1].reshape(N_LINEAS, P["n"]), np.float32)
            P["sti"][i] = cv2.remap(t, mx, my, cv2.INTER_LINEAR).mean(axis=0)
        leidos = i + 1
        if verbose and (i + 1) % 500 == 0:
            print("   %d/%d" % (i + 1, NF), flush=True)
    cap.release()
    for P in planes:
        P["sti"] = P["sti"][:leidos]
        P["sti"] -= P["sti"].mean(axis=0, keepdims=True)
    return planes, fps, leidos


# ==================================================================================
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--video", default=sc.ARCHIVO_VIDEO)
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--solo-sintetico", action="store_true")
    ap.add_argument("--sin-escalera", action="store_true")
    ap.add_argument("--solo-escalera", action="store_true")
    a = ap.parse_args()
    os.makedirs(DIR_SALIDAS, exist_ok=True)
    rng = np.random.default_rng(SEMILLA)
    vs = np.linspace(V_MIN, V_MAX, N_CAND)

    cap, ntot, fps = sc.abrir_video(a.video)
    sc.FPS_REAL[0] = fps
    ok, f0 = cap.read()
    cap.release()
    geo = sc.Geometria(cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY))
    NF = ntot if a.frames is None else min(a.frames, ntot)

    filas = []

    # ---- 1. validacion sintetica -------------------------------------------------
    print("== 1. validacion sintetica (el filtro, contra una estela de v conocida) ==")
    print("   caso            estadistico   pico en    score   techo nulo   z      veredicto")
    ds_sint = 0.0075
    for v_real, amp, et in ((0.059, 6.0, "senal clara"),
                            (0.059, 1.5, "senal debil"),
                            (None, 0.0, "solo ruido")):
        st = (sintetico(vs, fps, ds_sint, rng, v_real=0.0, amp=0.0, n_part=0)
              if v_real is None else
              sintetico(vs, fps, ds_sint, rng, v_real=v_real, amp=amp))
        nv = ventana_residencia(160 * ds_sint, fps)
        todos = analizar_todo(st, vs, fps, ds_sint, rng, n_barajados=8, n_ventana=nv)
        for cual in ESTADISTICOS:
            ver = veredicto(todos[cual], vs)
            print("   %-14s %-11s  %+.4f  %8.2f  %8.2f  %+6.1f   %s"
                  % (et if cual == "pico" else "", cual, ver["v_pico"], ver["score"],
                     ver["techo_nulo"], ver["z"],
                     "DETECTA" if ver["supera_nulo"] else "no"))
            filas.append(dict(experimento="sintetico", banda=et, estadistico=cual,
                              factor=1.0, v_inyectada=v_real if v_real else 0.0, **ver))
        print()
    if a.solo_sintetico:
        return

    # ---- 2. las tres bandas ------------------------------------------------------
    planes, leidos = [], 0
    if not a.solo_escalera:
        print("\n== 2. bandas reales (%d fotogramas) ==" % NF)
        planes, fps, leidos = construir_stis(a.video, geo, BANDAS, NF)
        print()
        print("   banda   estadistico   pico en    score   techo nulo   z      veredicto")
    for P in planes:
        nv = ventana_residencia(P["y1"] - P["y0"], fps)
        todos = analizar_todo(P["sti"], vs, fps, P["ds"], rng, n_ventana=nv)
        for cual in ESTADISTICOS:
            ver = veredicto(todos[cual], vs)
            print("   %-7s %-11s  %+.4f  %8.2f  %8.2f  %+6.1f   %s"
                  % (P["et"] if cual == "pico" else "", cual, ver["v_pico"], ver["score"],
                     ver["techo_nulo"], ver["z"],
                     "DETECTA" if ver["supera_nulo"] else "no"))
            filas.append(dict(experimento="banda", banda=P["et"], estadistico=cual,
                              factor=1.0, n=P["n"], ds=P["ds"], **ver))
        vi = veredicto(todos["pico"], vs)["v_pico_invertido"]
        print("           (n=%d, ds=%.4f, ventana %d fotogramas = %.1f s; con el tiempo"
              " invertido el pico va a %+.4f)" % (P["n"], P["ds"], nv, nv / fps, vi))
        r = todos["pico"]
        np.save(os.path.join(DIR_SALIDAS, "curva_%s.npy" % P["et"]),
                np.vstack([vs, r["real"], r["invertido"], r["nulo_max"]]))
        print()

    # ---- 3. escalera de degradacion ----------------------------------------------
    if not a.sin_escalera:
        print("\n== 3. escalera: se degrada el campo CERCANO hasta perder la deteccion ==")
        print("   (factor f simula alejar la camara f veces; el campo lejano equivale a f=6.5)")
        for fac in FACTORES:
            pl, _, _ = construir_stis(a.video, geo, [BANDAS[0]], NF, factor=fac, verbose=False)
            P = pl[0]
            nv = ventana_residencia(P["y1"] - P["y0"], fps)
            todos = analizar_todo(P["sti"], vs, fps, P["ds"], rng, n_barajados=8, n_ventana=nv)
            ver = veredicto(todos["pico"], vs)
            print("   f=%.1f  n=%3d  pico en %+.4f  score %6.2f  techo %5.2f  z=%+6.1f  %s"
                  % (fac, P["n"], ver["v_pico"], ver["score"], ver["techo_nulo"], ver["z"],
                     "DETECTA" if ver["supera_nulo"] else "NO detecta"))
            for cual in ESTADISTICOS:
                filas.append(dict(experimento="escalera", banda="cerca", estadistico=cual,
                                  factor=fac, n=P["n"], ds=P["ds"],
                                  **veredicto(todos[cual], vs)))

    with open(os.path.join(DIR_SALIDAS, "filtro_adaptado.csv"), "w", newline="",
              encoding="utf-8") as fh:
        campos = sorted({k for f in filas for k in f})
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)
    with open(os.path.join(DIR_SALIDAS, "config_filtro.json"), "w", encoding="utf-8") as fh:
        json.dump({"v_min": V_MIN, "v_max": V_MAX, "n_cand": N_CAND,
                   "n_lineas": N_LINEAS, "n_barajados": N_BARAJADOS,
                   "factores": FACTORES, "semilla": SEMILLA, "bandas": BANDAS,
                   "n_frames": leidos, "fps": fps,
                   "video_md5": "7b8576e5f9f37d789041a2b1a0f0eb57",
                   "hereda_de": "analisis_canal_riego_stiv/stiv_canal.py"}, fh, indent=2)
    print("\nescrito: salidas/filtro_adaptado.csv, salidas/config_filtro.json, curva_*.npy")


if __name__ == "__main__":
    main()
