"""Estabiliza un video de dron usando SOLO OpenCV, como entrada del notebook de STIV.

Por que existe este script si ya hay estabilizar_video.py
--------------------------------------------------------
`estabilizar_video.py` resuelve el mismo problema pero llamando a funciones internas de pyorc
(`pyorc.cv.get_ms_gftt` y `pyorc.cv.transform`). Eso es lo correcto cuando lo que viene despues
es pyorc, porque garantiza que el resultado es el mismo que habria producido `stabilize=`.

El notebook de STIV (`analisis_USGS_SMC_stiv/`) no usa pyorc en ningun punto: implementa la
velocimetria desde cero sobre OpenCV. Si su video de entrada dependiera de pyorc, la cadena
completa dejaria de ser independiente y la comparacion entre los dos metodos ya no seria limpia.
Por eso aqui se reimplementa la estabilizacion con OpenCV a secas.

Que hace, en tres pasos
-----------------------
1. Busca rasgos con esquinas marcadas (`goodFeaturesToTrack`) SOLO en la zona fija, o sea el
   terreno y el hormigon que quedan FUERA del poligono del agua. Se detectan una unica vez,
   sobre el primer fotograma, que pasa a ser el sistema de referencia.
2. Sigue esos mismos rasgos hasta cada fotograma con flujo optico piramidal
   (`calcOpticalFlowPyrLK`), tomando como semilla la posicion que tenian en el fotograma
   anterior. Es seguimiento directo contra el fotograma 0, no encadenado, asi que el error NO
   se acumula a lo largo del video; la semilla solo sirve para que el flujo optico nunca tenga
   que resolver un salto grande de golpe.
3. Ajusta con `estimateAffinePartial2D` (rotacion + traslacion + escala uniforme, con RANSAC)
   la transformacion que devuelve cada fotograma a la posicion del fotograma 0, y la aplica con
   `warpAffine`.

Se usa una semejanza y no una homografia completa a proposito: el vuelo es cenital y estacionario,
de modo que el movimiento residual del dron es practicamente un desplazamiento con un giro muy
pequeno. Una homografia tendria grados de libertad de sobra y ajustaria tambien ruido.

Uso
---
    python estabilizar_stiv.py ENTRADA SALIDA --poligono "0,420 3840,420 3840,1500 0,1500"

El poligono encierra el AGUA, en pixeles [columna,fila]. Todo lo que queda FUERA se toma como
terreno inmovil. Debe ir algo por fuera de la linea de agua: si se cuela agua en la zona fija,
el movimiento del agua se interpreta como movimiento de la camara y la correccion sale al reves.

Ejemplo real (Sile Main Canal, el caso del notebook analisis_USGS_SMC_stiv):

    python estabilizar_stiv.py \
        USGS/Video/SMC_D_RC_022_08172020_AC.mp4 \
        analisis_USGS_SMC_stiv/entradas/SMC_estabilizado_stiv.mkv \
        --poligono "0,420 3840,420 3840,1500 0,1500" --fin 249

`--inicio` y `--fin` son indices de fotograma, ambos inclusive: 250 fotogramas es `--fin 249`.

Por que el codec por defecto es FFV1 y no mp4v
----------------------------------------------
STIV mide la pendiente de las estelas que dejan los trazadores en la imagen espacio-temporal, y
esa pendiente se estima a partir de gradientes de intensidad. Un codec con perdida introduce
ruido de bloque justo en esos gradientes. FFV1 es sin perdida: los fotogramas se releen
identicos bit a bit. Cuesta unas 5 veces mas disco (~1.1 GB frente a ~220 MB para 250 fotogramas
4K) y esa es su unica desventaja. Con `--codec mp4v` se obtiene el archivo pequeno, a sabiendas.
"""

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# Codecs que no pierden informacion al recodificar. Cualquier otro degrada la textura de los
# trazadores, que es de donde sale la senal del STIV, asi que se avisa por pantalla.
CODECS_SIN_PERDIDA = {"FFV1", "HFYU", "LAGS", "RAWV"}

# Parametros del seguimiento. winSize y maxLevel fijan cuanto salto tolera el flujo optico:
# 31 px de ventana en 4 niveles de piramide cubren desplazamientos de varios cientos de pixeles,
# muy por encima de la deriva real de un dron en vuelo estacionario.
LK = dict(winSize=(31, 31), maxLevel=4,
          criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
GFTT = dict(maxCorners=600, qualityLevel=0.01, minDistance=30, blockSize=7)


def parsear_poligono(texto):
    """Convierte "0,420 3840,420 ..." en [[0, 420], [3840, 420], ...]."""
    vertices = []
    for par in texto.split():
        col, fila = par.split(",")
        vertices.append([int(col), int(fila)])
    if len(vertices) < 3:
        raise argparse.ArgumentTypeError("el poligono necesita al menos 3 vertices")
    return vertices


def mascara_zona_fija(poligono, alto, ancho):
    """Devuelve 255 FUERA del poligono (terreno) y 0 dentro (agua).

    Es la convencion que espera goodFeaturesToTrack en su argumento `mask`: marca donde SE PUEDE
    buscar, y lo que se puede buscar aqui son referencias inmoviles.
    """
    agua = np.zeros((alto, ancho), np.uint8)
    cv2.fillPoly(agua, [np.array([poligono], dtype=np.int32)], 255)
    return np.where(agua == 255, 0, 255).astype(np.uint8)


def leer_gris(cap):
    """Lee el siguiente fotograma y devuelve (color, gris), o (None, None) si se acabo."""
    ok, cuadro = cap.read()
    if not ok:
        return None, None
    return cuadro, cv2.cvtColor(cuadro, cv2.COLOR_BGR2GRAY)


def medir_temblor(archivo, n_frames, mascara, inicio=0):
    """Salto rigido en pixeles entre fotogramas CONSECUTIVOS, medido sobre la zona fija.

    Es la medida que decide si la estabilizacion ha servido de algo, y la que se imprime antes y
    despues. Importa el salto entre fotogramas consecutivos y no la deriva total porque STIV, como
    PIV, mide desplazamiento de un fotograma al siguiente: el temblor se suma directamente a la
    velocidad del agua.
    """
    cap = cv2.VideoCapture(str(archivo))
    cap.set(cv2.CAP_PROP_POS_FRAMES, inicio)
    _, previo = leer_gris(cap)
    if previo is None:
        cap.release()
        return np.array([])

    saltos = []
    for _ in range(n_frames - 1):
        _, actual = leer_gris(cap)
        if actual is None:
            break
        pts0 = cv2.goodFeaturesToTrack(previo, mask=mascara, **GFTT)
        if pts0 is not None:
            pts1, estado, _ = cv2.calcOpticalFlowPyrLK(previo, actual, pts0, None, **LK)
            ok = estado.ravel() == 1
            if ok.sum() >= 3:
                # estimateAffinePartial2D descarta con RANSAC lo que no encaja (hierba movida
                # por el viento, sombras que cambian), asi que el salto que devuelve es el del
                # conjunto rigido, no el del punto mas ruidoso.
                M, _ = cv2.estimateAffinePartial2D(pts0[ok], pts1[ok])
                if M is not None:
                    saltos.append(float(np.hypot(M[0, 2], M[1, 2])))
        previo = actual
    cap.release()
    return np.array(saltos)


def estimar_transformaciones(entrada, mascara, inicio, fin):
    """Devuelve, por fotograma, la matriz 2x3 que lo devuelve a la posicion del fotograma inicial.

    Tambien devuelve, por fotograma, cuantos puntos sobrevivieron al seguimiento y el error
    residual mediano del ajuste. Son los dos numeros que delatan si el seguimiento se ha perdido.
    """
    cap = cv2.VideoCapture(str(entrada))
    cap.set(cv2.CAP_PROP_POS_FRAMES, inicio)
    _, ref = leer_gris(cap)
    if ref is None:
        raise SystemExit("No se pudo leer el fotograma inicial.")

    # Los rasgos se detectan UNA sola vez, sobre el fotograma de referencia. A partir de aqui
    # siempre se busca este mismo conjunto: asi cada transformacion se mide contra el fotograma 0
    # y no contra el anterior, que es lo que evita que el error se acumule.
    p_ref = cv2.goodFeaturesToTrack(ref, mask=mascara, **GFTT)
    if p_ref is None or len(p_ref) < 10:
        raise SystemExit("Muy pocos rasgos fijos: revisa el poligono, quiza cubre casi toda la imagen.")
    print(f"  rasgos de referencia detectados fuera del agua: {len(p_ref)}")

    matrices = [np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], np.float32)]
    n_validos = [len(p_ref)]
    residuos = [0.0]

    # p_previo es la posicion que tenian los rasgos en el fotograma anterior. Se le pasa a
    # calcOpticalFlowPyrLK como semilla (OPTFLOW_USE_INITIAL_FLOW) para que nunca arranque desde
    # cero: la busqueda sigue siendo contra `ref`, pero partiendo de un punto ya muy cercano.
    p_previo = p_ref.copy()

    for k in range(inicio + 1, fin + 1):
        _, gris = leer_gris(cap)
        if gris is None:
            break
        p_k, estado, _ = cv2.calcOpticalFlowPyrLK(
            ref, gris, p_ref, p_previo.copy(),
            flags=cv2.OPTFLOW_USE_INITIAL_FLOW, **LK)
        ok = estado.ravel() == 1
        M = None
        if ok.sum() >= 3:
            # src = donde estan los rasgos AHORA, dst = donde estaban en la referencia.
            # La matriz resultante es por tanto la que devuelve el fotograma a su sitio.
            M, inliers = cv2.estimateAffinePartial2D(p_k[ok], p_ref[ok],
                                                     method=cv2.RANSAC, ransacReprojThreshold=3.0)
        if M is None:
            # Si el ajuste falla se repite la ultima matriz valida: es preferible dejar el
            # fotograma como estaba a aplicarle una transformacion inventada.
            print(f"  AVISO: fotograma {k} sin ajuste valido, se repite la transformacion anterior")
            matrices.append(matrices[-1].copy())
            n_validos.append(int(ok.sum()))
            residuos.append(np.nan)
        else:
            # Residuo: cuanto se aparta cada rasgo de la posicion que predice la semejanza.
            proyectado = (M[:, :2] @ p_k[ok].reshape(-1, 2).T).T + M[:, 2]
            residuos.append(float(np.median(np.linalg.norm(proyectado - p_ref[ok].reshape(-1, 2),
                                                           axis=1))))
            matrices.append(M.astype(np.float32))
            n_validos.append(int(ok.sum()))
            p_previo = p_k
        if (k - inicio) % 50 == 0:
            print(f"  {k - inicio}/{fin - inicio} fotogramas seguidos")

    cap.release()
    return matrices, np.array(n_validos), np.array(residuos)


def estabilizar(entrada, salida, poligono, inicio=0, fin=None, fourcc="FFV1", verificar=25):
    """Escribe en `salida` el video `entrada` con el movimiento de camara compensado."""
    entrada, salida = Path(entrada), Path(salida)
    cap = cv2.VideoCapture(str(entrada))
    if not cap.isOpened():
        raise SystemExit(f"No se pudo abrir el video: {entrada}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    fin = n_total - 1 if fin is None else min(fin, n_total - 1)
    n_frames = fin - inicio + 1

    print(f"Entrada : {entrada}")
    print(f"          {ancho}x{alto} @ {fps:.3f} fps, {n_total} fotogramas")
    print(f"Salida  : {salida}")
    print(f"          fotogramas {inicio} a {fin} ({n_frames} en total)\n")

    mascara = mascara_zona_fija(poligono, alto, ancho)
    if mascara.max() == 0:
        raise SystemExit("El poligono cubre la imagen entera: no queda zona fija de referencia.")
    print(f"Zona fija de referencia: {100 * (mascara > 0).mean():.1f} % de la imagen\n")

    # --- 1) Estimar la transformacion de cada fotograma ---------------------------------------
    print("Estimando el movimiento de la camara (OpenCV puro)...")
    t0 = time.perf_counter()
    matrices, n_validos, residuos = estimar_transformaciones(entrada, mascara, inicio, fin)
    t_estimacion = time.perf_counter() - t0
    print(f"  {len(matrices)} transformaciones en {t_estimacion:.1f} s")
    print(f"  rasgos seguidos por fotograma: mediana {np.median(n_validos):.0f}, "
          f"minimo {n_validos.min()}")
    print(f"  residuo del ajuste: mediana {np.nanmedian(residuos):.2f} px, "
          f"maximo {np.nanmax(residuos):.2f} px")

    # Deriva total: cuanto se movio el dron de principio a fin. Es informativa, no un problema
    # en si; lo que estropea la velocimetria es el salto entre fotogramas consecutivos.
    deriva = np.array([np.hypot(m[0, 2], m[1, 2]) for m in matrices])
    print(f"  deriva acumulada respecto al fotograma inicial: maxima {deriva.max():.1f} px\n")

    # --- 2) Aplicarla y escribir el video nuevo ------------------------------------------------
    salida.parent.mkdir(parents=True, exist_ok=True)
    escritor = cv2.VideoWriter(str(salida), cv2.VideoWriter_fourcc(*fourcc), fps, (ancho, alto))
    if not escritor.isOpened():
        raise SystemExit(f"No se pudo abrir el escritor de video con el codec {fourcc}.")

    if fourcc.upper() not in CODECS_SIN_PERDIDA:
        print(f"  AVISO: {fourcc} recodifica con perdida. STIV mide gradientes de intensidad,")
        print("  y esa perdida se le resta a la senal. Usa FFV1 salvo que el tamano del")
        print("  archivo sea el problema.\n")

    print("Aplicando la correccion y escribiendo...")
    t0 = time.perf_counter()
    cap = cv2.VideoCapture(str(entrada))
    cap.set(cv2.CAP_PROP_POS_FRAMES, inicio)
    escritos = 0
    # Muestra de los primeros fotogramas ya corregidos, para comprobar despues que el archivo
    # escrito contiene exactamente eso y no una version degradada por el codec.
    muestra = []
    for M in matrices:
        ok, cuadro = cap.read()
        if not ok:
            break
        # INTER_LINEAR y BORDER_REPLICATE: la correccion es de decimas de pixel, asi que la
        # interpolacion bilineal basta y no merece la pena suavizar mas de lo imprescindible.
        corregido = cv2.warpAffine(cuadro, M, (ancho, alto),
                                   flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        if verificar and len(muestra) < verificar:
            muestra.append(corregido.copy())
        escritor.write(corregido)
        escritos += 1
        if escritos % 50 == 0:
            print(f"  {escritos}/{len(matrices)} fotogramas")
    t_escritura = time.perf_counter() - t0
    escritor.release()
    cap.release()
    print(f"  {escritos} fotogramas escritos en {t_escritura:.1f} s\n")

    # --- 3) Comprobar la fidelidad de lo escrito -----------------------------------------------
    if verificar and muestra:
        cap_out = cv2.VideoCapture(str(salida))
        difs = []
        for referencia in muestra:
            ok, leido = cap_out.read()
            if not ok:
                break
            difs.append(np.abs(referencia.astype(np.float32) - leido.astype(np.float32)).mean())
        cap_out.release()
        error = float(np.mean(difs)) if difs else float("nan")
        print(f"Fidelidad sobre {len(difs)} fotogramas releidos del archivo:")
        print(f"  error medio frente a la correccion en memoria: {error:.4f} niveles de gris")
        if error == 0:
            print("  sin perdida: el archivo contiene exactamente los fotogramas corregidos\n")
        else:
            print(f"  el codec {fourcc} ha degradado la imagen; con FFV1 este valor es 0\n")

    # --- 4) Comprobar que la estabilizacion ha servido de algo ---------------------------------
    if verificar:
        n = min(verificar, escritos)
        print(f"Verificacion del temblor sobre los primeros {n} fotogramas:")
        antes = medir_temblor(entrada, n, mascara, inicio=inicio)
        despues = medir_temblor(salida, n, mascara)
        print(f"  salto entre fotogramas, video crudo : mediana {np.median(antes):.2f} px | "
              f"max {antes.max():.2f} px")
        print(f"  salto entre fotogramas, estabilizado: mediana {np.median(despues):.2f} px | "
              f"max {despues.max():.2f} px")
        if np.median(despues) > 0:
            print(f"  reduccion del temblor: {np.median(antes) / np.median(despues):.1f}x")
        if np.median(despues) >= np.median(antes):
            print("\n  AVISO: el temblor no ha bajado. Revisa el poligono: probablemente deja")
            print("  agua fuera, y entonces el agua se toma como referencia fija.")

    print(f"\nListo. {salida} ({salida.stat().st_size / 1e6:.1f} MB)")
    print(f"Tiempo total: {t_estimacion + t_escritura:.1f} s")
    return salida


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Estabiliza un video de dron con OpenCV puro (sin pyorc), para el notebook de STIV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("entrada", type=Path, help="video de entrada")
    p.add_argument("salida", type=Path, help="video estabilizado que se genera")
    p.add_argument("--poligono", type=parsear_poligono, required=True,
                   help='vertices del agua, "col,fila col,fila ..." en pixeles')
    p.add_argument("--inicio", type=int, default=0, help="primer fotograma, inclusive (def. 0)")
    p.add_argument("--fin", type=int, default=None,
                   help="ultimo fotograma, inclusive (def. el ultimo del video)")
    p.add_argument("--codec", default="FFV1",
                   help="fourcc del codec de salida (def. FFV1, sin perdida; usa .mkv o .avi)")
    p.add_argument("--verificar", type=int, default=25,
                   help="fotogramas para medir fidelidad y temblor; 0 lo salta")
    a = p.parse_args(argv)

    if not a.entrada.exists():
        raise SystemExit(f"No existe el video de entrada: {a.entrada}")

    estabilizar(a.entrada, a.salida, a.poligono, inicio=a.inicio, fin=a.fin,
                fourcc=a.codec, verificar=a.verificar)


if __name__ == "__main__":
    sys.exit(main())
