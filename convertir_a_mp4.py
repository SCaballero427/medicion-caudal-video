"""Convierte un video a .mp4 para poder verlo comodamente. Con perdida, a proposito.

Para que sirve
--------------
`estabilizar_video.py` escribe en FFV1 sin perdida, porque su salida alimenta al PIV y cualquier
degradacion del patron de trazadores se le resta a la senal. El precio es que el archivo es
enorme (1.1 GB para 8 s de 4K) y que muchos reproductores y navegadores no abren FFV1 en MKV.

Este script hace la conversion contraria: coge ese video y produce un .mp4 normal, comodo de
abrir, compartir y arrastrar por la linea de tiempo. **La salida es para mirar, no para
procesar.** Si se le pasa este .mp4 al notebook en vez del FFV1, se vuelve a meter justo el
ruido que el FFV1 evitaba.

Uso
---
    python convertir_a_mp4.py ENTRADA [SALIDA] [--escala 0.5]

Ejemplo (el caso del canal Sile Main Canal):

    python convertir_a_mp4.py analisis_USGS_SMC/entradas/SMC_estabilizado.mkv

Sin SALIDA, escribe junto al original con el sufijo _previsualizacion.mp4.

Nota sobre el codec: OpenCV en este entorno no puede escribir H.264 (la DLL de OpenH264 que
trae tiene una version incompatible), asi que se usa mp4v (MPEG-4 Part 2). Comprime menos que
H.264 pero lo abre cualquier reproductor. Con --escala 0.5 el archivo baja a la cuarta parte,
que para revisar visualmente la estabilizacion suele sobrar.
"""

import argparse
import sys
import time
from pathlib import Path

import cv2


def convertir(entrada, salida=None, escala=1.0, codec="mp4v"):
    """Reescribe `entrada` como .mp4, opcionalmente reduciendo la resolucion."""
    entrada = Path(entrada)
    if salida is None:
        salida = entrada.with_name(entrada.stem + "_previsualizacion.mp4")
    salida = Path(salida)

    cap = cv2.VideoCapture(str(entrada))
    if not cap.isOpened():
        raise SystemExit(f"No se pudo abrir el video: {entrada}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    ancho = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Las dimensiones deben ser pares: muchos codecs rechazan lados impares.
    ancho_dst = int(ancho * escala) // 2 * 2
    alto_dst = int(alto * escala) // 2 * 2

    print(f"Entrada : {entrada}  ({entrada.stat().st_size / 1e6:.1f} MB)")
    print(f"          {ancho}x{alto} @ {fps:.3f} fps, {n_total} fotogramas")
    print(f"Salida  : {salida}")
    print(f"          {ancho_dst}x{alto_dst}, codec {codec} (con perdida)\n")

    salida.parent.mkdir(parents=True, exist_ok=True)
    escritor = cv2.VideoWriter(str(salida), cv2.VideoWriter_fourcc(*codec), fps,
                               (ancho_dst, alto_dst))
    if not escritor.isOpened():
        raise SystemExit(f"No se pudo abrir el escritor de video con el codec {codec}.")

    t0 = time.perf_counter()
    escritos = 0
    while True:
        ok, cuadro = cap.read()
        if not ok:
            break
        if (ancho_dst, alto_dst) != (ancho, alto):
            # INTER_AREA es el remuestreo correcto al reducir: promedia en vez de submuestrear.
            cuadro = cv2.resize(cuadro, (ancho_dst, alto_dst), interpolation=cv2.INTER_AREA)
        escritor.write(cuadro)
        escritos += 1
        if escritos % 50 == 0:
            print(f"  {escritos}/{n_total} fotogramas")
    escritor.release()
    cap.release()

    tam_org = entrada.stat().st_size
    tam_new = salida.stat().st_size
    print(f"\n{escritos} fotogramas en {time.perf_counter() - t0:.1f} s")
    print(f"Listo: {salida} ({tam_new / 1e6:.1f} MB, "
          f"{tam_org / tam_new:.1f}x mas pequeno que el original)")
    print("\nRecordatorio: este .mp4 es solo para verlo. El notebook debe seguir leyendo el")
    print("FFV1 sin perdida, o el PIV pierde parte del patron de trazadores.")
    return salida


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Convierte un video a .mp4 para visualizarlo (con perdida).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("entrada", type=Path, help="video de entrada")
    p.add_argument("salida", type=Path, nargs="?", default=None,
                   help="mp4 de salida (def. <entrada>_previsualizacion.mp4)")
    p.add_argument("--escala", type=float, default=1.0,
                   help="factor de reduccion, p.ej. 0.5 para la mitad de lado (def. 1.0)")
    p.add_argument("--codec", default="mp4v", help="fourcc del codec (def. mp4v)")
    a = p.parse_args(argv)

    if not a.entrada.exists():
        raise SystemExit(f"No existe el video de entrada: {a.entrada}")
    if not 0 < a.escala <= 1:
        raise SystemExit("--escala debe estar entre 0 y 1")

    convertir(a.entrada, a.salida, escala=a.escala, codec=a.codec)


if __name__ == "__main__":
    sys.exit(main())
