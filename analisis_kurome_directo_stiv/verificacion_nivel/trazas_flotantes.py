"""Trazas de lo que flota, en la vista en planta: el realce de motas (top-hat) acumulado durante N
segundos, coloreado por el tiempo (azul al principio, rojo al final). Un objeto que flota deja una traza
cuya longitud es su velocidad por N segundos; se lee con la reticula de 1 m. Ademas sigue las motas
fotograma a fotograma (vecino mas cercano, solo las que duran >= 3 s) y da la velocidad mediana por
banda: un arbitro que no comparte nada con el STIV ni con la correlacion de conjunto.

    python trazas_flotantes.py <video.ts> <segundo_inicio> <etiqueta> [--segundos 10]
"""
import argparse, os, sys
import numpy as np, cv2

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, ".."))
import stiv_directo as sd

ap = argparse.ArgumentParser()
ap.add_argument("video")
ap.add_argument("inicio", type=float)
ap.add_argument("etiqueta")
ap.add_argument("--segundos", type=float, default=10.0)
ap.add_argument("--seguimiento", type=float, default=60.0, help="segundos de seguimiento de motas")
a = ap.parse_args()

sd.elegir_camara("myoshoji")
g = sd.Geometria(sd.cargar_config(), 30.0)
DT = 1 / 15.0
esc = g.rect_esc
W, H = g.rect_tam
(x0, y0), (x1, y1) = g.a_rect([[g.xs[0], g.ys[0] - sd.ANCHO_BANDA_M], [g.xs[-1], g.ys[-1] + sd.ANCHO_BANDA_M]])
x0, y0, x1, y1 = int(x0), int(max(y0, 0)), int(x1), int(min(y1, H))
cortes = np.linspace(y0, y1, 4).astype(int)
nucleo = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (sd.NUCLEO_TOPHAT, sd.NUCLEO_TOPHAT))

cap = cv2.VideoCapture(a.video)
cap.set(cv2.CAP_PROP_POS_MSEC, a.inicio * 1000)
n_total = int(max(a.segundos, a.seguimiento) / DT)
realce, fondo, n = [], None, 0
while len(realce) < n_total:
    ok, f = cap.read()
    if not ok:
        break
    n += 1
    if n % 2:
        continue
    gris = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    th = cv2.morphologyEx(gris, cv2.MORPH_TOPHAT, nucleo)
    realce.append(cv2.warpPerspective(th, g.rect_a_imagen, (W, H), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR))
    if fondo is None:
        fondo = cv2.warpPerspective(gris, g.rect_a_imagen, (W, H), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR)
R = np.stack(realce).astype(np.float32)
# lo que no se mueve (reflejos fijos, bordes) se quita con la mediana temporal, como en el modo noche
R = np.clip(R - np.median(R[::4], axis=0), 0, None)

# 1) imagen de trazas: maximo por color de tiempo sobre los primeros N segundos
m = int(a.segundos / DT)
umbral = np.percentile(R[:m], 99.7)
img = cv2.cvtColor((fondo * 0.5).astype(np.uint8), cv2.COLOR_GRAY2BGR)
for k in range(m):
    mask = R[k] > umbral
    color = cv2.applyColorMap(np.uint8([[int(255 * k / max(m - 1, 1))]]), cv2.COLORMAP_JET)[0, 0]
    img[mask] = color
for xm in np.arange(0, (W / esc), 1.0):                         # reticula de 1 m
    cv2.line(img, (int(xm * esc), 0), (int(xm * esc), H), (90, 90, 90), 1)
for ym in np.arange(0, (H / esc), 1.0):
    cv2.line(img, (0, int(ym * esc)), (W, int(ym * esc)), (90, 90, 90), 1)
cv2.rectangle(img, (x0, y0), (x1, y1), (0, 255, 0), 1)
cv2.putText(img, f"{a.etiqueta}: {a.segundos:.0f} s, azul->rojo, reticula 1 m, flujo ->", (8, 18),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
salida = os.path.join(AQUI, "salidas", "diagnostico")
os.makedirs(salida, exist_ok=True)
cv2.imwrite(os.path.join(salida, f"trazas_{a.etiqueta}.png"), img)

# 2) seguimiento de motas: centroides por fotograma, enlace al vecino mas cercano hacia adelante
umbral_s = np.percentile(R, 99.8)
cents = []
for k in range(len(R)):
    nl, lab, st, cen = cv2.connectedComponentsWithStats((R[k] > umbral_s).astype(np.uint8))
    ok_ = (st[1:, cv2.CC_STAT_AREA] >= 2) & (st[1:, cv2.CC_STAT_AREA] <= 60)
    c = cen[1:][ok_]
    c = c[(c[:, 0] >= x0) & (c[:, 0] < x1) & (c[:, 1] >= y0) & (c[:, 1] < y1)]
    cents.append(c)
RADIO = 1.2 * DT * esc + 2.0          # hasta 1.2 m/s entre dos fotogramas reales
pistas, vivas = [], []
for k, c in enumerate(cents):
    usados = set()
    nuevas = []
    for p in vivas:
        if len(c) == 0:
            pistas.append(p); continue
        d = np.hypot(c[:, 0] - p[-1][1], c[:, 1] - p[-1][2])
        j = int(np.argmin(d))
        if d[j] <= RADIO and j not in usados:
            usados.add(j)
            p.append((k, c[j, 0], c[j, 1]))
            nuevas.append(p)
        else:
            pistas.append(p)
    for j in range(len(c)):
        if j not in usados:
            nuevas.append([(k, c[j, 0], c[j, 1])])
    vivas = nuevas
pistas += vivas
MIN_DUR = 3.0
res = {0: [], 1: [], 2: []}
for p in pistas:
    if (p[-1][0] - p[0][0]) * DT < MIN_DUR:
        continue
    p = np.array(p)
    t = p[:, 0] * DT
    vx = np.polyfit(t, p[:, 1], 1)[0] / esc
    vy = np.polyfit(t, p[:, 2], 1)[0] / esc
    resid = np.std(p[:, 1] - np.polyval(np.polyfit(t, p[:, 1], 1), t)) / esc
    if resid > 0.15:                          # una pista que zigzaguea no es un objeto que flota
        continue
    b = int(np.clip(np.searchsorted(cortes, np.median(p[:, 2])) - 1, 0, 2))
    res[b].append((vx, vy))
print(f"{a.etiqueta}: {len(R)} fotogramas reales, {sum(len(c) for c in cents)} motas detectadas, "
      f"{sum(len(v) for v in res.values())} pistas rectas de >= {MIN_DUR:.0f} s")
for b in range(3):
    v = np.array(res[b])
    if len(v):
        print(f"  banda {['0-2', '3-5', '6-8'][b]}: {len(v):4d} pistas, v a lo largo mediana {np.median(v[:, 0]):+.3f} m/s "
              f"[q25 {np.percentile(v[:, 0], 25):+.3f}, q75 {np.percentile(v[:, 0], 75):+.3f}], de traves {np.median(v[:, 1]):+.3f}")
    else:
        print(f"  banda {['0-2', '3-5', '6-8'][b]}: sin pistas")
