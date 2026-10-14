"""Rio Bradano (HARMONIOUS), video ya ortorrectificado a 0.009 m/px: stiv_directo.py contra las 7
verticales de referencia. Geometria y parametros por camara del caso analisis_bradano_stiv (estaciones
en la rejilla de 1 m de la referencia, flujo hacia arriba en la imagen, V_ESPERADA 0.9, banda 24 px);
los del metodo, los del programa. La velocidad de referencia solo se abre al final."""
import os, sys, json, numpy as np
from correr import correr, por_estacion
import xlsx

DATOS = os.path.join(os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")), "datasets vision velocimetria", "data", "RiverBradano")
VIDEO = f"{DATOS}/Stabilised/Video/RiverBradano_24_fps_Stabilised.avi"
ESC = 0.009                      # m/px (Readme del dataset)
FILA, COL0, PASO_PX, N = 706, 456, 111, 9
L = 4.8                          # m: 128 muestras x DS del caso original (533 px)
W = (N - 1) * PASO_PX * ESC
V_ESP = float(sys.argv[1]) if len(sys.argv) > 1 else 0.9
h = L / ESC / 2
c1 = COL0 + (N - 1) * PASO_PX
# mundo (x aguas abajo = arriba en la imagen, y = a traves) -> imagen
cuad = [[COL0, FILA + h], [COL0, FILA - h], [c1, FILA - h], [c1, FILA + h]]
params = dict(N_ESTACIONES=N, MARGEN_ORILLA=0.0, LARGO_LINEA_M=L, CENTRO_LINEA=0.5,
              ANCHO_BANDA_M=24 * ESC, V_ESPERADA=V_ESP, FPS_CAMARA=None, FILTRO_DIRECCIONAL=False)
modo = sys.argv[2] if len(sys.argv) > 2 else "auto"
geom, med = correr(VIDEO, cuad, L, W, params, modo=modo)
pe = por_estacion(med, N)
for p in pe:
    print(f"  est {p['estacion']} (col {COL0 + PASO_PX * p['estacion']}): "
          + (f"{p['v']:.3f} m/s [{p['q25']:.2f}-{p['q75']:.2f}] coh {p['coh']:.2f}, {p['aceptadas']}/{p['n']} {p['escalas']}"
             if p["aceptadas"] else f"rechazada {p['motivos']}"))
json.dump(pe, open(f"salidas/bradano_v{V_ESP:g}_{modo}.json", "w"), default=float)

# ---------------- comparacion (solo aqui se abre la referencia) ----------------
ref = [f for f in xlsx.leer(f"{DATOS}/Reference/Validation_Data_RiverBradano.xlsx")
       if str(f.get("A", "")).startswith("Vert")]
v_ref = np.array([f["D"] for f in ref])
assert all(int(f["B"]) == COL0 + PASO_PX * i and int(f["C"]) == FILA for i, f in enumerate(ref))
v = np.array([p["v"] for p in pe[:len(ref)]])
ok = np.isfinite(v)
print("\nvertical  ref    directo")
for i in range(len(ref)):
    print(f"  {i+1}     {v_ref[i]:.2f}   {v[i]:.2f}" if ok[i] else f"  {i+1}     {v_ref[i]:.2f}     --")
if ok.sum():
    print(f"{ok.sum()}/{len(ref)} verticales; sesgo (media) {100*(v[ok].mean()/v_ref[ok].mean()-1):+.1f} %, "
          f"RMSE {np.sqrt(np.mean((v[ok]-v_ref[ok])**2)):.3f} m/s, r {np.corrcoef(v[ok], v_ref[ok])[0,1]:+.3f}")
