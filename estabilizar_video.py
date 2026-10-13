"""Estabiliza un video y lo escribe como un video nuevo, listo para procesar con pyorc.

Motivacion
----------
pyorc puede estabilizar por su cuenta pasando el argumento `stabilize` a `pyorc.Video`. El
problema es que lo hace en memoria y en cada ejecucion: si el notebook se corre varias veces,
o se barre un parametro del PIV, la estabilizacion se repite entera cada vez, y en un video 4K
eso son varios minutos por vuelta. Separandola queda un video estabilizado en disco que sirve
de entrada estable para todas las ejecuciones siguientes.

El calculo es exactamente el mismo que hace pyorc por dentro: se reutilizan sus funciones
`pyorc.cv.get_ms_gftt` (estima la transformacion afin de cada fotograma siguiendo rasgos fijos
fuera del agua) y `pyorc.cv.transform` (se la aplica al fotograma). No es una reimplementacion,
asi que el resultado es el que habria producido `stabilize=` dentro del notebook.

Uso
---
    python estabilizar_video.py ENTRADA SALIDA --poligono "0,420 3840,420 3840,1500 0,1500"

El poligono encierra el AGUA, en pixeles [columna,fila]. Todo lo que queda FUERA se considera
terreno inmovil y es lo que se usa como referencia. Debe ir algo por fuera de la linea de agua:
si se cuela agua en la zona fija, el movimiento del agua se interpreta como movimiento de la
camara y la correccion sale al reves.

Ejemplo real (Sile Main Canal, el caso del notebook analisis_USGS_SMC):

    python estabilizar_video.py \
        USGS/Video/SMC_D_RC_022_08172020_AC.mp4 \
        analisis_USGS_SMC/entradas/SMC_estabilizado.mkv \
        --poligono "0,420 3840,420 3840,1500 0,1500" --fin 249

Por que el codec por defecto es FFV1 y no mp4v
----------------------------------------------
Guardar un video intermedio introduce un paso que no existia cuando la estabilizacion iba
dentro del notebook: una recodificacion. Con mp4v (con perdida) el error medio en la zona del
AOI de este video es de 2.1 niveles de gris, un 10 % de la desviacion tipica del propio patron
de trazadores (PSNR 39.7 dB). El PIV mide precisamente correlacion de ese patron, asi que ese
ruido va directo contra la senal que se quiere medir.

FFV1 es sin perdida: los fotogramas se releen identicos bit a bit. Cuesta unas 5 veces mas
disco (~1.1 GB frente a ~220 MB para 250 fotogramas 4K), y esa es la unica desventaja. Con
--codec mp4v se obtiene el archivo pequeno, a sabiendas de lo que se pierde.
"""

import argparse
import sys
import time

import cv2
import numpy as np

import pyorc.cv


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
    """Devuelve 255 FUERA del poligono y 0 dentro, que es lo que espera get_ms_gftt.

    Es la misma convencion que usa pyorc en Video.set_mask_from_exterior: la mascara marca
    donde se pueden buscar rasgos de referencia, o sea el terreno, no el agua.
    """
    mascara = np.zeros((alto, ancho), np.uint8)
    cv2.fillPoly(mascara, [np.array([poligono], dtype=np.int32)], 255)
    # Se invierte: lo que era el agua (255) pasa a 0 y el resto a 255.
    return np.where(mascara == 255, 0, 255).astype(np.uint8)


def medir_temblor(archivo, n_frames, mascara, paso=1):
    """Salto rigido en pixeles entre fotogramas consecutivos, medido sobre la zona fija.

    Sirve para comprobar que la estabilizacion ha servido de algo. Es la misma medida que
    hacia la Parte 1b del notebook, y la que se imprime antes y despues.
    """
    cap = cv2.VideoCapture(str(archivo))
    ok, previo = cap.read()
    if not ok:
        cap.release()
        return np.array([])
    previo = cv2.cvtColor(previo, cv2.COLOR_BGR2GRAY)
    saltos = []
    for _ in range(n_frames - 1):
        ok, actual = cap.read()
        if not ok:
            break
        actual = cv2.cvtColor(actual, cv2.COLOR_BGR2GRAY)
        pts0 = cv2.goodFeaturesToTrack(previo, maxCorners=300, qualityLevel=0.01,
                                       minDistance=30, mask=mascara)
        if pts0 is not None:
            pts1, estado, _ = cv2.calcOpticalFlowPyrLK(previo, actual, pts0, None,
                                                       winSize=(31, 31), maxLevel=3)
            # estimateAffinePartial2D ajusta rotacion + traslacion + escala y descarta con
            # RANSAC los puntos que no encajan (hierba movida por el viento, por ejemplo).
            M, _ = cv2.estimateAffinePartial2D(pts0[estado == 1], pts1[estado == 1])
            if M is not None:
                saltos.append(np.hypot(M[0, 2], M[1, 2]))
        previo = actual
    cap.release()
    return np.array(saltos)


# Codecs que no pierden informacion al recodificar. Cualquier otro degrada el patron de
# trazadores del que vive el PIV, asi que se avisa por pantalla.
CODECS_SIN_PERDIDA = {"FFV1", "HFYU", "LAGS", "RAWV"}


def estabilizar(entrada, salida, poligono, inicio=0, fin=None, fourcc="FFV1", verificar=25):
    """Escribe en `salida` el video `entrada` con el movimiento de camara compensado."""
    from pathlib import Path

    entrada, salida = Path(entrada), Path(salida)
    cap = cv2.VideoCapture(str(entrada))
    if not cap.isOpened():
        raise SystemExit(f"No se pudo abrir el video: {entrada}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fin = n_total - 1 if fin is None else min(fin, n_total - 1)
    n_frames = fin - inicio + 1

    print(f"Entrada : {entrada}")
    print(f"          {ancho}x{alto} @ {fps:.3f} fps, {n_total} fotogramas")
    print(f"Salida  : {salida}")
    print(f"          fotogramas {inicio} a {fin} ({n_frames} en total)\n")

    mascara = mascara_zona_fija(poligono, alto, ancho)
    # Si el poligono cubriera toda la imagen no quedaria terreno donde buscar referencias.
    if mascara.max() == 0:
        raise SystemExit("El poligono cubre la imagen entera: no queda zona fija de referencia.")

    # --- 1) Estimar la transformacion de cada fotograma ---------------------------------
    # get_ms_gftt es la funcion que pyorc usa internamente cuando se le pasa stabilize=.
    print("Estimando el movimiento de la camara...")
    t0 = time.perf_counter()
    ms = pyorc.cv.get_ms_gftt(cap, start_frame=inicio, end_frame=fin, mask=mascara, split=2)
    t_estimacion = time.perf_counter() - t0
    print(f"  {len(ms)} transformaciones en {t_estimacion:.1f} s\n")

    # --- 2) Aplicarla y escribir el video nuevo -----------------------------------------
    salida.parent.mkdir(parents=True, exist_ok=True)
    escritor = cv2.VideoWriter(str(salida), cv2.VideoWriter_fourcc(*fourcc), fps, (ancho, alto))
    if not escritor.isOpened():
        raise SystemExit(f"No se pudo abrir el escritor de video con el codec {fourcc}.")

    if fourcc.upper() not in CODECS_SIN_PERDIDA:
        print(f"  AVISO: {fourcc} recodifica con perdida. El PIV correla el patron de")
        print("  trazadores, y esa perdida se le resta a la senal. Usa FFV1 salvo que el")
        print("  tamano del archivo sea el problema.\n")

    print("Aplicando la correccion y escribiendo...")
    t0 = time.perf_counter()
    cap.set(cv2.CAP_PROP_POS_FRAMES, inicio)
    escritos = 0
    # Se guarda una muestra de los primeros fotogramas ya corregidos para poder comprobar
    # despues que el archivo escrito contiene exactamente eso y no una version degradada.
    muestra_memoria = []
    for m in ms:
        ok, cuadro = cap.read()
        if not ok:
            break
        # transform es warpAffine con la matriz 2x3 que devuelve get_ms_gftt.
        corregido = pyorc.cv.transform(cuadro, m)
        if verificar and len(muestra_memoria) < verificar:
            muestra_memoria.append(corregido.copy())
        escritor.write(corregido)
        escritos += 1
        if escritos % 50 == 0:
            print(f"  {escritos}/{len(ms)} fotogramas")
    t_escritura = time.perf_counter() - t0
    escritor.release()
    cap.release()
    print(f"  {escritos} fotogramas escritos en {t_escritura:.1f} s\n")

    # --- 3) Comprobar la fidelidad de lo escrito ----------------------------------------
    if verificar and muestra_memoria:
        cap_out = cv2.VideoCapture(str(salida))
        difs = []
        for referencia in muestra_memoria:
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

    # --- 4) Comprobar que la estabilizacion ha servido de algo ---------------------------
    if verificar:
        n = min(verificar, escritos)
        print(f"Verificacion sobre los primeros {n} fotogramas:")
        antes = medir_temblor(entrada, n, mascara)
        despues = medir_temblor(salida, n, mascara)
        print(f"  salto entre fotogramas, video crudo : mediana {np.median(antes):.2f} px | "
              f"max {antes.max():.2f} px")
        print(f"  salto entre fotogramas, estabilizado: mediana {np.median(despues):.2f} px | "
              f"max {despues.max():.2f} px")
        if np.median(despues) > 0:
            print(f"  reduccion del temblor: {np.median(antes) / np.median(despues):.1f}x")
        # Si la mediana no baja, el poligono esta mal puesto: se avisa en vez de callar.
        if np.median(despues) >= np.median(antes):
            print("\n  AVISO: el temblor no ha bajado. Revisa el poligono: probablemente deja")
            print("  agua fuera, y entonces el agua se toma como referencia fija.")

    tam_mb = salida.stat().st_size / 1e6
    print(f"\nListo. {salida} ({tam_mb:.1f} MB)")
    print(f"Tiempo total: {t_estimacion + t_escritura:.1f} s")
    return salida


def main(argv=None):
    from pathlib import Path

    p = argparse.ArgumentParser(
        description="Estabiliza un video usando el mismo algoritmo que pyorc.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("entrada", type=Path, help="video de entrada")
    p.add_argument("salida", type=Path, help="video estabilizado que se genera")
    p.add_argument("--poligono", type=parsear_poligono, required=True,
                   help='vertices del agua, "col,fila col,fila ..." en pixeles')
    p.add_argument("--inicio", type=int, default=0, help="primer fotograma (def. 0)")
    p.add_argument("--fin", type=int, default=None,
                   help="ultimo fotograma (def. el ultimo del video)")
    p.add_argument("--codec", default="FFV1",
                   help="fourcc del codec de salida (def. FFV1, sin perdida; usa .mkv o .avi)")
    p.add_argument("--verificar", type=int, default=25,
                   help="fotogramas para medir el temblor antes/despues; 0 lo salta")
    a = p.parse_args(argv)

    if not a.entrada.exists():
        raise SystemExit(f"No existe el video de entrada: {a.entrada}")

    estabilizar(a.entrada, a.salida, a.poligono, inicio=a.inicio, fin=a.fin,
                fourcc=a.codec, verificar=a.verificar)


if __name__ == "__main__":
    sys.exit(main())
