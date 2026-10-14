"""Graba N segundos del directo de una camara en grabaciones/<nombre>.avi (FFV1, sin perdidas), para
la regresion. python grabar.py <camara> <segundos> [nombre]. Sin perdidas a proposito: recodificar con
perdidas mete ruido que pasa ACTIVIDAD_MIN (lo que le pasa a raspberry/prueba/myoshoji_20s.mp4)."""
import os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import stiv_directo as sd

cv2 = sd.cv2
cam, segundos = sys.argv[1], float(sys.argv[2])
nombre = sys.argv[3] if len(sys.argv) > 3 else cam
sd.elegir_camara(cam)
url, titulo, _ = sd.resolver_url(sd.URL_FUENTE)
print(titulo)
cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
fotogramas = []
t0 = time.time()
while time.time() - t0 < segundos:
    ok, f = cap.read()
    if not ok:
        break
    fotogramas.append(f)
print(len(fotogramas), "fotogramas", fotogramas[0].shape)
carpeta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grabaciones")
os.makedirs(carpeta, exist_ok=True)
alto, ancho = fotogramas[0].shape[:2]
# 30 fps: el ritmo de los directos de YouTube (15 fps de la camara, cada fotograma duplicado)
vw = cv2.VideoWriter(os.path.join(carpeta, f"{nombre}.avi"), cv2.VideoWriter_fourcc(*"FFV1"), 30, (ancho, alto))
for f in fotogramas:
    vw.write(f)
vw.release()
