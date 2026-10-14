"""Velocidad del Myoshoji que implican los aforos oficiales del puente Ochiai (落合橋).

Los CSV de esta carpeta son los resultados de calidad del agua de la cuenca del Kanda que publica la
Oficina de Medio Ambiente de Tokio, tal como se descargan (Shift-JIS). En cada muestreo apuntan el
caudal (流量, m3/s) y el calado total (全水深, m). Velocidad media = Q / (ancho mojado x calado), y la
superficial ~ media / 0.85. El ancho mojado en tiempo seco no se publica: se dan dos supuestos.

    python velocidad_ochiai.py
"""
import csv, glob, os
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
Q, H, filas = [], [], []
for ruta in sorted(glob.glob(os.path.join(AQUI, "tokyo_calidad_agua_kanda_*.csv"))):
    with open(ruta, encoding="shift_jis", errors="replace") as f:
        lector = csv.reader(f)
        cab = next(lector)
        iq, ih = cab.index("流量"), cab.index("全水深")       # el valor va en la columna del titulo
        for r in lector:
            if len(r) <= ih or "妙正寺" not in r[1]:
                continue
            try:
                q, h = float(r[iq]), float(r[ih])
            except ValueError:
                continue
            filas.append((r[6], r[7], r[2], q, h))
            # fuera crecidas y errores de transcripcion (hay un calado de 18 m)
            if 0.02 < h < 1.0 and q < 2.0:
                Q.append(q)
                H.append(h)
Q, H = np.array(Q), np.array(H)
print(f"{len(filas)} muestreos del Myoshoji en el puente Ochiai, {len(Q)} validos (tiempo seco)")
print(f"  caudal  mediana {np.median(Q):.2f} m3/s  [p10 {np.percentile(Q, 10):.2f}, p90 {np.percentile(Q, 90):.2f}]")
print(f"  calado  mediana {np.median(H):.2f} m     [p10 {np.percentile(H, 10):.2f}, p90 {np.percentile(H, 90):.2f}]")
for B in (6.0, 8.8):
    V = Q / (B * H)
    print(f"  ancho mojado {B} m: velocidad media {np.median(V):.2f} m/s [p10 {np.percentile(V, 10):.2f}, "
          f"p90 {np.percentile(V, 90):.2f}] -> superficial ~{np.median(V) / 0.85:.2f} m/s")
with open(os.path.join(AQUI, "myoshoji_ochiai.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["anio", "fecha", "punto", "caudal_m3s", "calado_m"])
    w.writerows(filas)
