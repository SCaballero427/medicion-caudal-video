"""Espectro numero de onda - frecuencia del STI largo (vista en planta, a lo largo del flujo).

Lo que la corriente arrastra (motas, espuma, textura pasiva) cae sobre la recta f = U k que pasa por el
origen. Las ondas de superficie caen sobre la curva de dispersion de ondas capilares-gravedad desplazada
por la corriente: f = U k + sqrt(g K tanh(K h) + (sigma/rho) K^3) / (2 pi), K = 2 pi k. Si la energia
del STI esta sobre la curva y no sobre una recta, lo que mide el STIV de dia son ondas, no la corriente.

    python espectro_kw.py <video.ts> <segundo_inicio> <etiqueta> [--tophat] [--banda 1]
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
ap.add_argument("--segundos", type=float, default=120.0)
ap.add_argument("--tophat", action="store_true")
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
stis = [[] for _ in range(3)]
n = 0
while len(stis[0]) < a.segundos / DT:
    ok, f = cap.read()
    if not ok:
        break
    n += 1
    if n % 2:
        continue
    gris = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    if a.tophat:
        gris = cv2.morphologyEx(gris, cv2.MORPH_TOPHAT, nucleo)
    p = cv2.warpPerspective(gris, g.rect_a_imagen, (W, H), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR).astype(np.float32)
    for b in range(3):
        stis[b].append(p[cortes[b]:cortes[b + 1]:3, x0:x1])  # una fila de cada 3 a lo ancho de la banda

FS, KS = 1 / DT, esc                       # muestras por s y por m
G_, SIGMA_RHO = 9.81, 0.0728 / 1000.0
salida = os.path.join(AQUI, "salidas", "diagnostico")
os.makedirs(salida, exist_ok=True)
paneles = []
print(f"{a.etiqueta}{' (top-hat)' if a.tophat else ''}: {len(stis[0])} fotogramas reales, {esc:.1f} px/m")
for b in range(3):
    S = np.stack(stis[b])                   # (T, Y, X)
    S -= S.mean(axis=0)
    T, Y, X = S.shape
    win = np.outer(np.hanning(T), np.hanning(X)).astype(np.float32)
    # potencia media sobre las filas de la banda (cada fila es un STI a lo largo del flujo)
    Pw = np.zeros((T, X), np.float64)
    for y in range(Y):
        Pw += np.abs(np.fft.fft2(S[:, y, :] * win)) ** 2
    Pw = np.fft.fftshift(Pw)
    f = np.fft.fftshift(np.fft.fftfreq(T, DT))           # Hz
    k = np.fft.fftshift(np.fft.fftfreq(X, 1 / KS))       # ciclos/m
    # con I(x - c t), la energia de k > 0 cae en f < 0 (convenio de numpy): aguas abajo = -f
    kpos = k > 0.15
    P = Pw[:, kpos][::-1]                                 # filas: f creciente = aguas abajo
    fr = -f[::-1]
    kk = k[kpos]
    # ajuste de U: la recta (advencion pura) y la curva de dispersion desplazada, por energia capturada
    def energia(fun, ancho=0.25):
        tot = 0.0
        for j, kj in enumerate(kk):
            fc = fun(kj)
            sel = np.abs(fr - fc) <= ancho
            tot += P[sel, j].sum()
        return tot / P.sum()
    Us = np.arange(0.0, 0.81, 0.01)
    rec = [energia(lambda kj, U=U: U * kj) for U in Us]
    disp = lambda kj, U, h=0.2: U * kj + np.sqrt(G_ * 2 * np.pi * kj * np.tanh(2 * np.pi * kj * h)
                                                 + SIGMA_RHO * (2 * np.pi * kj) ** 3) / (2 * np.pi)
    cur = [energia(lambda kj, U=U: disp(kj, U)) for U in Us]
    ur, uc = Us[int(np.argmax(rec))], Us[int(np.argmax(cur))]
    print(f"  banda {['0-2', '3-5', '6-8'][b]}: recta f=U k -> U {ur:.2f} m/s ({max(rec) * 100:.1f} % de la energia); "
          f"ondas desplazadas -> U {uc:.2f} m/s ({max(cur) * 100:.1f} %)")
    # figura: log potencia, k 0..max, f -FMAX..FMAX, con las curvas de referencia
    FMAX = 7.5
    sel_f = np.abs(fr) <= FMAX
    img = np.log10(P[sel_f] + 1e-9)
    lo, hi = np.percentile(img, (50, 99.9))
    img = np.clip((img - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)[::-1]   # f creciente hacia arriba
    img = cv2.resize(img, (500, 500), interpolation=cv2.INTER_AREA)
    img = cv2.applyColorMap(img, cv2.COLORMAP_VIRIDIS)
    px = lambda kj: int(kj / kk.max() * 499)
    py = lambda fj: int((FMAX - fj) / (2 * FMAX) * 499)
    for fun, color, nombre in ((lambda kj: 0.48 * kj, (0, 140, 255), "f=0.48k"),
                               (lambda kj: 0.05 * kj, (255, 255, 255), "f=0.05k"),
                               (lambda kj: disp(kj, 0.05), (0, 0, 255), "ondas+0.05"),
                               (lambda kj: 0.05 * kj - disp(kj, 0.0), (255, 0, 255), "ondas aguas arriba")):
        pts = [(px(kj), py(fun(kj))) for kj in np.linspace(kk.min(), kk.max(), 200) if abs(fun(kj)) <= FMAX]
        for p_, q_ in zip(pts, pts[1:]):
            cv2.line(img, p_, q_, color, 1, cv2.LINE_AA)
    cv2.putText(img, f"banda {['0-2', '3-5', '6-8'][b]}  k 0-{kk.max():.0f} c/m, f +-{FMAX} Hz", (5, 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    paneles.append(img)
leyenda = np.zeros((40, 1500, 3), np.uint8)
cv2.putText(leyenda, "naranja f=0.48k (advencion a 0.48)  blanco f=0.05k (advencion a 0.05)  rojo: ondas aguas abajo sobre U=0.05  "
            "magenta: ondas aguas arriba", (5, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
cv2.imwrite(os.path.join(salida, f"espectro_kw_{a.etiqueta}{'_tophat' if a.tophat else ''}.png"),
            np.vstack([np.hstack(paneles), leyenda]))
