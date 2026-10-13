"""Ultimo intento sobre el campo lejano, con un algoritmo que no comparte nada con STIV.

Todo lo que hace `experimento_alcance.py` es STIV discutiendo consigo mismo: cambia la banda o el
paso temporal, pero el estimador sigue siendo el tensor sobre una STI. Aqui se usa **correlacion
de conjunto**, que no comparte ni la STI, ni el tensor, ni la banda de lineas paralelas.

El parche rectificado se muestrea a la **resolucion nativa de la imagen** en cada banda -- una
muestra por pixel, para no sobremuestrear, que es justo lo que rompe la STI alli -- y se
correlacionan pares de fotogramas a desfases crecientes. Si hay agua detectable el pico se
desplaza en proporcion al desfase; si no la hay, se queda clavado en cero.

Es una prueba de PRESENCIA, no una medida. La velocidad que deduce en el control cercano no tiene
por que coincidir con la de STIV: el parche abarca todo el ancho con trazador y la correlacion de
conjunto la domina la zona con mas particulas, que es la mitad derecha lenta. Lo que importa es que
en el control el pico se mueve y en el campo lejano no, con el mismo codigo y el mismo parche.

Uso
---
    python correlacion_arbitro.py
"""
import os
import sys

import cv2
import numpy as np

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "analisis_canal_riego_stiv"))
import stiv_canal as sc  # noqa: E402

# ----------------------------------------------------------------------------------
# >>> AJUSTABLE <<<
# ----------------------------------------------------------------------------------
# (X0, X1, Y0, Y1, etiqueta). X se limita a la banda con trazador del caso principal.
PARCHES = [
    (0.10, 0.90, 1.60, 2.80, "cerca (control)"),
    (0.10, 0.90, 3.30, 4.90, "media"),
    (0.10, 0.90, 5.20, 7.80, "lejos"),
]
DESFASES = (30, 60, 120, 240, 400)
N_FRAMES = 1500
PASO_PAREJAS = 7


def main():
    cap, n, fps = sc.abrir_video()
    sc.FPS_REAL[0] = fps
    ok, f = cap.read()
    cap.release()
    g0 = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    geo = sc.Geometria(g0)

    def resolucion(Y):
        p = geo.a_imagen([[0, Y]])[0]
        q = geo.a_suelo([[p[0], p[1] + 1]])[0]
        return abs(q[1] - Y)

    mask = np.zeros(g0.shape, np.uint8)
    mask[0:sc.FILA_BORDE_FIN - 40, :] = 255
    cv2.fillPoly(mask, [geo.poligono_agua()], 0)
    p0 = cv2.goodFeaturesToTrack(g0, 600, 0.01, 7, mask=mask)

    planes = []
    for (x0, x1, y0, y1, et) in PARCHES:
        r = resolucion((y0 + y1) / 2)
        ny = max(24, int((y1 - y0) / r))
        nx = max(24, int((x1 - x0) / r))
        GX, GY = np.meshgrid(np.linspace(x0, x1, nx), np.linspace(y0, y1, ny))
        I = geo.a_imagen(np.column_stack([GX.ravel(), GY.ravel()]))
        planes.append(dict(et=et, nx=nx, ny=ny, pts=I.astype(np.float32),
                           dY=(y1 - y0) / (ny - 1),
                           buf=np.zeros((N_FRAMES, ny, nx), np.float32)))
        print("%-16s %3dx%-3d  1 px de imagen = %.4f alt.cam  paso del parche %.4f"
              % (et, nx, ny, r, (y1 - y0) / (ny - 1)))
    print()

    cap = cv2.VideoCapture(sc.ARCHIVO_VIDEO)
    leidos = 0
    for i in range(N_FRAMES):
        ok, f = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        A, _ = sc.estimar_estabilizacion(g0, g, p0)
        t = sc.realzar(g)
        for P in planes:
            xy = P["pts"] @ A[:, :2].T + A[:, 2]
            mx = np.ascontiguousarray(xy[:, 0].reshape(P["ny"], P["nx"]), np.float32)
            my = np.ascontiguousarray(xy[:, 1].reshape(P["ny"], P["nx"]), np.float32)
            P["buf"][i] = cv2.remap(t, mx, my, cv2.INTER_LINEAR)
        leidos = i + 1
    cap.release()
    print("%d fotogramas\n" % leidos)

    def ensemble(B, lag):
        acc = None
        k = 0
        for i in range(0, len(B) - lag, PASO_PAREJAS):
            a = B[i] - B[i].mean()
            b = B[i + lag] - B[i + lag].mean()
            na, nb = np.sqrt((a * a).sum()), np.sqrt((b * b).sum())
            if na < 1e-9 or nb < 1e-9:
                continue
            c = np.fft.irfft2(np.fft.rfft2(b) * np.conj(np.fft.rfft2(a)), s=a.shape)
            acc = c / (na * nb) if acc is None else acc + c / (na * nb)
            k += 1
        if not k:
            return None
        acc = np.fft.fftshift(acc / k)
        cy, cx = np.unravel_index(np.argmax(acc), acc.shape)
        return (acc.max(), cy - acc.shape[0] // 2, cx - acc.shape[1] // 2,
                acc[acc.shape[0] // 2, acc.shape[1] // 2])

    print("desfase        pico   dY(px) dX(px)   cero    v deducida")
    for P in planes:
        B = P["buf"][:leidos]
        print("== %s ==" % P["et"])
        for lag in DESFASES:
            if lag >= leidos:
                continue
            r = ensemble(B, lag)
            if r is None:
                continue
            pk, dy, dx, z = r
            print("  %4d (%5.1f s)  %.4f  %+5d  %+5d   %.4f   %+.4f  %s"
                  % (lag, lag / fps, pk, dy, dx, z, dy * P["dY"] * fps / lag,
                     "<-- pico clavado en cero" if (dy == 0 and dx == 0) else ""))
        print()
    print("referencia de STIV en el campo cercano: +0.059 alt.cam/s")


if __name__ == "__main__":
    main()
