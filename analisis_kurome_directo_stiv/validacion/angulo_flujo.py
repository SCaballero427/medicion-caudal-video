"""Que variante del modelo de camara alinea las lineas de busqueda con el flujo medido (sin referencia).
Flujo optico Farneback a media resolucion, promediado en el tiempo; para cada linea se compara la
direccion del flujo a lo largo de ella con la direccion de la linea proyectada, en la imagen y en el mundo."""
import sys, numpy as np, cv2
from proyeccion import leer_modelo, proyectar, lineas, BASE

video, z = sys.argv[1], float(sys.argv[2])
m = leer_modelo(f"{BASE}/Camera_models/Oulankajoki_River/Reolink RLC-810A/Camera_model_ReolinkRLC810A.xml")
cap = cv2.VideoCapture(video); cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 0)
E = 0.5
g = []
for i in range(60):
    ok, f = cap.read()
    g.append(cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), None, fx=E, fy=E))
fl = np.mean([cv2.calcOpticalFlowFarneback(g[i], g[i + 2], None, 0.5, 4, 31, 3, 5, 1.1, 0)
              for i in range(0, 56, 2)], axis=0) / E / 2          # px de imagen completa por fotograma
L = lineas()
n = len(L)
P = np.concatenate([np.c_[L[:, 0:2], np.full(n, z)], np.c_[L[:, 2:4], np.full(n, z)]])
for var, (sx, sy) in ((6, (-1, 1)), (7, (-1, -1))):
    p, _ = proyectar(m, P, "xyz", True, sx, sy)
    a, b = p[:n], p[n:]
    # homografia mundo(plano z) -> imagen para pasar el flujo al mundo
    H, _ = cv2.findHomography(np.r_[L[:, 0:2], L[:, 2:4]].astype(np.float32), p.astype(np.float32))
    Hi = np.linalg.inv(H)
    filas = []
    for i in range(n):
        ts = np.linspace(0.1, 0.9, 9)
        pts = a[i] + ts[:, None] * (b[i] - a[i])
        v = np.array([fl[int(q[1] * E), int(q[0] * E)] for q in pts]).mean(axis=0)
        dir_img = (b[i] - a[i]) / np.linalg.norm(b[i] - a[i])
        ang_img = np.degrees(np.arctan2(dir_img[0] * v[1] - dir_img[1] * v[0], dir_img @ v))
        c = pts[4]
        w0 = cv2.perspectiveTransform(c.reshape(1, 1, 2).astype(np.float64), Hi)[0, 0]
        w1 = cv2.perspectiveTransform((c + v).reshape(1, 1, 2).astype(np.float64), Hi)[0, 0]
        vw = (w1 - w0) * 25.0
        dl = (L[i, 2:4] - L[i, 0:2]) / np.linalg.norm(L[i, 2:4] - L[i, 0:2])
        ang_w = np.degrees(np.arctan2(dl[0] * vw[1] - dl[1] * vw[0], dl @ vw))
        filas.append((i + 1, np.linalg.norm(v), ang_img, ang_w, np.linalg.norm(vw), vw @ dl))
    f = np.array(filas)
    print(f"variante {var}: angulo flujo-linea en imagen mediana {np.median(np.abs(((f[:,2]+90)%180)-90)):.1f} grados, "
          f"en el mundo {np.median(np.abs(((f[:,3]+90)%180)-90)):.1f}; |v| mundo por linea (m/s):")
    print("   " + " ".join(f"{r[0]:.0f}:{r[4]:.2f}({r[3]:+.0f})" for r in filas))
