"""Escritura de video en H.264, mandando los fotogramas a ffmpeg por una tuberia.

Por que no `cv2.VideoWriter`
---------------------------
OpenCV en este entorno no puede escribir H.264: la DLL de OpenH264 que trae es de una
version que no le sirve, asi que el unico codec disponible acaba siendo `mp4v`, o sea
**MPEG-4 Parte 2**, el de estilo DivX de los 90. Los `.mp4` que salian asi no se pueden
ver en el navegador ni en el visor de VSCode -- Chromium solo decodifica H.264, VP8/VP9
y AV1 -- y hacia falta VLC. Ademas comprime mucho peor: 106 MB para los mismos 38 s que
el video original del USGS resuelve en 65 MB.

La solucion estaba en el propio workspace: `RIVeR-STIV_1.0/ffmpeg.exe` viene compilado
con **libx264**. Aqui se le pasan los fotogramas en crudo por `stdin`, de modo que se
codifica en la misma pasada, sin fichero intermedio y sin recodificar algo ya comprimido.
Medido sobre `velocidad_sin_nivel.mp4`: 106 MB en mp4v -> **51 MB en H.264 a CRF 20**, con
una diferencia de 2.6 niveles de gris de media, invisible.

Uso
---
Sustituye a `cv2.VideoWriter` con la misma interfaz:

    vw = abrir(ruta, fps, (ancho, alto))
    vw.write(fotograma)      # BGR, uint8
    vw.release()

Si no encuentra ffmpeg avisa y cae en `cv2.VideoWriter` con mp4v, para que nada deje de
funcionar por esto.
"""
import os
import shutil
import subprocess

import cv2
import numpy as np

# CRF de x264: 0 sin perdida, 23 el valor por defecto, mas alto peor. 20 es "alta
# calidad": la mitad de tamaño que mp4v sin diferencia visible, elegido para que el video
# aguante volver a analizarlo o ampliarlo.
CRF = 20
PRESET = "medium"

# ffmpeg del bundle de RIVeR, que es el unico que hay en el workspace. Si no esta, se
# busca en el PATH.
_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FFMPEG = os.path.join(_RAIZ, "RIVeR-STIV_1.0", "ffmpeg.exe")
if not os.path.exists(FFMPEG):
    FFMPEG = shutil.which("ffmpeg") or ""


class EscritorH264:
    """Tuberia a ffmpeg con la interfaz de cv2.VideoWriter."""

    def __init__(self, ruta, fps, tam, crf=CRF, preset=PRESET):
        w, h = tam
        # yuv420p exige lados pares; si el lienzo trae un lado impar se rellena con una
        # fila o columna negra en vez de recortar, para no perder nada de lo dibujado.
        self.w, self.h = w, h
        self.wp, self.hp = w + (w % 2), h + (h % 2)
        cmd = [FFMPEG, "-y", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "bgr24",
               "-s", f"{self.wp}x{self.hp}", "-r", f"{fps:.6f}",
               "-i", "pipe:0", "-an",
               "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", ruta]
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def isOpened(self):
        return self.p.poll() is None

    def write(self, fr):
        if (fr.shape[1], fr.shape[0]) != (self.wp, self.hp):
            lienzo = np.zeros((self.hp, self.wp, 3), fr.dtype)
            lienzo[:fr.shape[0], :fr.shape[1]] = fr
            fr = lienzo
        self.p.stdin.write(np.ascontiguousarray(fr).tobytes())

    def release(self):
        try:
            self.p.stdin.close()
        except Exception:
            pass
        self.p.wait()


def abrir(ruta, fps, tam, crf=CRF, preset=PRESET):
    """Escritor H.264 si hay ffmpeg; si no, el de OpenCV con mp4v y un aviso."""
    if FFMPEG and os.path.exists(FFMPEG):
        return EscritorH264(ruta, fps, tam, crf, preset)
    print("AVISO: no se encontro ffmpeg, se escribe en mp4v (MPEG-4 Parte 2). Ese video "
          "no se vera en el navegador ni en VSCode; hara falta VLC.")
    return cv2.VideoWriter(ruta, cv2.VideoWriter_fourcc(*"mp4v"), fps, tam)
