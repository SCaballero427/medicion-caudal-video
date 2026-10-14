"""Diagnostico (python destellos.py heiskanen_10-03 | bradano | sile | <caso de regresion_casos>): fraccion de muestras saturadas (brillo crudo >= UMBRAL) por estacion, y percentiles del
brillo crudo, para ver si los destellos del sol se separan del trazador real."""
import sys, os, numpy as np, cv2
V = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, V)
os.chdir(V)
import correr as cr
sd = cr.sd

caso = sys.argv[1]
if caso.startswith("heiskanen"):
    hora = caso.split("_")[1]
    src = open("caso_heiskanen.py", encoding="utf-8").read().split("todas = {}")[0]
    sys.argv = ["x", "1.0"]; exec(src)
    for k, v in params.items(): setattr(sd, k, v)
    video = [v for v in videos if hora in v][0]
    cfg = {"cuadrilatero_px": cuad.tolist(), "largo_m": L, "ancho_m": W}; auto = False
elif caso == "bradano":
    src = open("caso_bradano.py", encoding="utf-8").read().split("modo = sys.argv")[0]
    sys.argv = ["x"]; exec(src)
    for k, v in params.items(): setattr(sd, k, v)
    video = VIDEO; cfg = {"cuadrilatero_px": cuad, "largo_m": L, "ancho_m": W}; auto = True
elif caso == "sile":
    src = open("caso_sile.py", encoding="utf-8").read().split("geom, med = correr")[0]
    sys.argv = ["x"]; exec(src)
    for k, v in params.items(): setattr(sd, k, v)
    video = VIDEO; cfg = {"cuadrilatero_px": cuad, "largo_m": L, "ancho_m": W}; auto = True
else:
    import regresion_casos as rc
    cam, video, *_ = rc.CASOS[caso]
    sd.elegir_camara(cam); cfg = sd.cargar_config(); auto = True
cap = cv2.VideoCapture(video); cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1 if auto else 0)
fps = cap.get(cv2.CAP_PROP_FPS)
g = sd.Geometria(cfg, fps)
br, n = [], 0
while n < fps * 60:
    ok, f = cap.read()
    if not ok: break
    if n % 5 == 0:
        br.append(g.brillo(f))
    n += 1
b = np.stack(br).reshape(len(br), sd.N_ESTACIONES, sd.LINEAS_BANDA, -1)
sat = (b >= 250).mean(axis=(0, 2, 3))
med = np.median(b, axis=0)       # mediana temporal por posicion
print(f"{caso}: sat>=250 por estacion: " + " ".join(f"{x:.3f}" for x in sat))
print(f"   frac posiciones con mediana >= 250: " + " ".join(f"{(m >= 250).mean():.2f}" for m in med))
print(f"   p99 brillo por estacion: " + " ".join(f"{np.percentile(b[:, i], 99):.0f}" for i in range(sd.N_ESTACIONES)))
