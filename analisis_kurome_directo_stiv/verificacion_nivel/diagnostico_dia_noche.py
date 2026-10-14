"""Diagnostico: por que el Myoshoji mide ~0.48 m/s de dia y ~0.07 m/s de noche con el mismo nivel.

Arbitro independiente del STIV (no usa STI, ni tensor, ni bandas de lineas): correlacion cruzada 2D de
conjunto sobre la vista en planta rectificada, a varios desfases. Si lo que se correlaciona es agua que
avanza, el desplazamiento del pico crece en proporcion al desfase (velocidad constante); si son ondas,
reflejos o nada, no. Ademas guarda un STI largo (2 min, brillo crudo) con las dos velocidades candidatas
dibujadas, para verlo a ojo.

    python diagnostico_dia_noche.py <video.ts> <segundo_inicio> <etiqueta> [--tophat]
"""
import argparse, os, sys
import numpy as np, cv2

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, ".."))
import stiv_directo as sd

ap = argparse.ArgumentParser()
ap.add_argument("video")
ap.add_argument("inicio", type=float, help="segundo del video donde empieza el tramo")
ap.add_argument("etiqueta")
ap.add_argument("--segundos", type=float, default=120.0)
ap.add_argument("--tophat", action="store_true", help="realce de motas (el del modo noche) antes de correlacionar")
a = ap.parse_args()

sd.elegir_camara("myoshoji")
cfg = sd.cargar_config()
g = sd.Geometria(cfg, 30.0)
DT = 1 / 15.0                                # un fotograma real (YouTube duplica 15 -> 30)
esc = g.rect_esc                             # px de la planta por metro
W, H = g.rect_tam
# region de medida en la planta: lo que cubren las lineas de busqueda
(x0, y0), (x1, y1) = g.a_rect([[g.xs[0], g.ys[0] - sd.ANCHO_BANDA_M], [g.xs[-1], g.ys[-1] + sd.ANCHO_BANDA_M]])
x0, y0, x1, y1 = int(x0), int(max(y0, 0)), int(x1), int(min(y1, H))
# tres bandas a lo ancho: orilla de las estaciones 0-2, centro 3-5, lado del muro 6-8
cortes = np.linspace(y0, y1, 4).astype(int)

cap = cv2.VideoCapture(a.video)
cap.set(cv2.CAP_PROP_POS_MSEC, a.inicio * 1000)
nucleo = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (sd.NUCLEO_TOPHAT, sd.NUCLEO_TOPHAT))
planta, n = [], 0
while len(planta) < a.segundos / DT:
    ok, f = cap.read()
    if not ok:
        break
    n += 1
    if n % 2:
        continue
    gris = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    if a.tophat:
        gris = cv2.morphologyEx(gris, cv2.MORPH_TOPHAT, nucleo)
    p = cv2.warpPerspective(gris, g.rect_a_imagen, (W, H), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR)
    planta.append(p[y0:y1, x0:x1].astype(np.float32))
P = np.stack(planta)
T = len(P)
print(f"{a.etiqueta}: {T} fotogramas reales ({T * DT:.0f} s), region {P.shape[2]}x{P.shape[1]} px "
      f"({P.shape[2] / esc:.1f} x {P.shape[1] / esc:.1f} m), {1000 / esc:.1f} mm/px, brillo medio {P.mean():.1f}")

# STI largo en bruto por el centro de cada banda (a lo largo del flujo), para mirarlo
salida = os.path.join(AQUI, "salidas", "diagnostico")
os.makedirs(salida, exist_ok=True)
paneles = []
for b in range(3):
    fila = (cortes[b] + cortes[b + 1]) // 2 - y0
    sti = P[:, max(fila - 3, 0):fila + 4, :].mean(axis=1)                # banda de 7 px
    lo, hi = np.percentile(sti, (1, 99.5))
    img = cv2.cvtColor(np.clip((sti - lo) / max(hi - lo, 1e-6) * 255, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    img = cv2.resize(img, (img.shape[1], img.shape[0] // 3), interpolation=cv2.INTER_AREA)  # 1 fila = 0.2 s
    # pendientes de referencia: una particula a v m/s recorre v*t*esc px
    for v, color in ((0.48, (0, 140, 255)), (0.07, (255, 120, 0))):
        for x_ini in range(0, img.shape[1], 120):
            t_fin = img.shape[0] * 3 * DT
            cv2.line(img, (x_ini, 0), (int(x_ini + v * t_fin * esc), img.shape[0]), color, 1, cv2.LINE_AA)
    cv2.putText(img, f"banda {['0-2', '3-5', '6-8'][b]}", (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
    paneles.append(img)
sep = np.full((paneles[0].shape[0], 6, 3), 255, np.uint8)
cv2.imwrite(os.path.join(salida, f"sti_largo_{a.etiqueta}{'_tophat' if a.tophat else ''}.png"),
            np.hstack([paneles[0], sep, paneles[1], sep, paneles[2]]))

# correlacion de conjunto 2D: se quita lo quieto (media temporal) y se suman los espectros cruzados
P -= P.mean(axis=0)
hann = np.outer(np.hanning(P.shape[1]), np.hanning(P.shape[2])).astype(np.float32)
LAGS = (1, 2, 4, 8, 15, 30, 60, 120)
print("  desfase(s)  " + "  ".join(f"banda {nb:>3}: v(m/s)  dy(m/s) pico" for nb in ("0-2", "3-5", "6-8")))
for L in LAGS:
    if L >= T:
        break
    fila_txt = []
    for b in range(3):
        sub = P[:, cortes[b] - y0:cortes[b + 1] - y0, :] * hann[cortes[b] - y0:cortes[b + 1] - y0, :]
        F = np.fft.rfft2(sub)
        cc = np.fft.irfft2((np.conj(F[:-L]) * F[L:]).sum(axis=0), s=sub.shape[1:])
        e = np.sqrt((sub[:-L] ** 2).sum() * (sub[L:] ** 2).sum())
        cc = np.fft.fftshift(cc) / max(e, 1e-9)
        cy, cx = np.array(cc.shape) // 2
        # busqueda: hasta 2 m/s a lo largo, +-0.3 m/s de traves
        rx, ry = int(min(2.0 * L * DT * esc, cx - 2)), int(min(0.3 * L * DT * esc + 2, cy - 2))
        ventana = cc[cy - ry:cy + ry + 1, cx - rx:cx + rx + 1]
        k = np.unravel_index(np.argmax(ventana), ventana.shape)
        py, px = k[0] - ry, k[1] - rx

        def sub_px(m, i, n):
            if 0 < i < n - 1:
                y0_, y1_, y2_ = m[i - 1], m[i], m[i + 1]
                den = y0_ - 2 * y1_ + y2_
                return 0.5 * (y0_ - y2_) / den if den != 0 else 0.0
            return 0.0
        dx = px + sub_px(ventana[k[0], :], k[1], ventana.shape[1])
        dy = py + sub_px(ventana[:, k[1]], k[0], ventana.shape[0])
        vx, vy = dx / esc / (L * DT), dy / esc / (L * DT)
        fila_txt.append(f"{vx:+.3f}  {vy:+.3f}  {ventana[k]:.3f}")
    print(f"  {L * DT:6.2f}     " + "    ".join(fila_txt))
