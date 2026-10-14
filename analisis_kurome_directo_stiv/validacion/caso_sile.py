"""USGS Sile Main Canal: stiv_directo.py sobre el video ORIGINAL (sin estabilizar, como en campo)
contra el aforo ADV. Geometria del caso analisis_USGS_SMC_stiv (filas 438/1463, columnas 600-3400,
flujo a -1 grado, 11 verticales interiores cada 6 in); parametros por camara: V_ESPERADA 0.95 y banda
del 26 % de la separacion. La referencia solo se abre al final."""
import os, sys, json, numpy as np
from correr import correr, por_estacion

# el mp4 original solo esta en la copia anidada del workspace (USGS/Video de la raiz no lo tiene)
VIDEO = os.path.join(os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")), "test_pyorc", "USGS", "Video", "SMC_D_RC_022_08172020_AC.mp4")
FILA_SUP, FILA_INF, ANCHO = 438, 1463, 1.8288
COL_INI, COL_FIN, ANG = 600, 3400, np.radians(-1.0)
e = ANCHO / (FILA_INF - FILA_SUP)
L = (COL_FIN - COL_INI) * e
W = ANCHO
N = 11
SENTIDO = int(sys.argv[2]) if len(sys.argv) > 2 else 1     # +1: aguas abajo = +x de la imagen


def a_imagen(xw, yw):
    t = SENTIDO * (xw / e - (COL_FIN - COL_INI) / 2)
    return [0.5 * (COL_INI + COL_FIN) + t * np.cos(ANG), FILA_SUP + yw / e + t * np.sin(ANG)]


cuad = [a_imagen(0, 0), a_imagen(L, 0), a_imagen(L, W), a_imagen(0, W)]
params = dict(N_ESTACIONES=N, MARGEN_ORILLA=1 / 12, LARGO_LINEA_M=L, CENTRO_LINEA=0.5,
              ANCHO_BANDA_M=0.04, V_ESPERADA=float(sys.argv[1]) if len(sys.argv) > 1 else 0.95,
              FPS_CAMARA=None, FILTRO_DIRECCIONAL=False)
geom, med = correr(VIDEO, cuad, L, W, params, modo="auto")
pe = por_estacion(med, N)
s = np.r_[0, geom.ys, ANCHO]
print("y de las estaciones:", np.round(geom.ys, 4))
for p in pe:
    print(f"  vertical {p['estacion']+1}: " + (f"{p['v']:.3f} m/s [{p['q25']:.2f}-{p['q75']:.2f}] coh {p['coh']:.2f}, "
          f"{p['aceptadas']}/{p['n']}" if p["aceptadas"] else f"rechazada {p['motivos']}"))
json.dump({"est": pe, "medidas": [(t, [(r["v"], r["aceptada"]) for r in res]) for t, res in med]},
          open("salidas/sile.json", "w"), default=float)

# caudal como el caso: verticales rechazadas por interpolacion lineal entre las aceptadas, ceros en
# los muros, ALFA 0.92, seccion rectangular de 1.073 m (Station_Stage_SileCanal.csv)
ALFA, PROF = 0.92, np.r_[0, np.full(N, 1.073), 0]
Q = []
for t, res in med:
    v = np.array([r["v"] if r["aceptada"] else np.nan for r in res])
    ok = np.isfinite(v)
    if ok.sum() < 2:
        continue
    v[~ok] = np.interp(geom.ys[~ok], geom.ys[ok], v[ok])
    Q.append(float(np.trapezoid(ALFA * np.r_[0, v, 0] * PROF, s)))
Q = np.array(Q)

# ---------------- comparacion (solo aqui se abren las referencias) ----------------
Q_AFORO = 1.4362
V_ADV = np.array([0.6298, 0.7973, 0.8132, 0.8121, 0.8220, 0.8518, 0.8508, 0.8458, 0.8094, 0.8146, 0.7365])
V_CASO = np.array([0.5865, 0.7316, 0.8365, 0.8784, 0.9615, 0.9738, 0.9420, 0.9560, 0.8939, 0.8488, 1.3448])
ACEPT_CASO = np.array([0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0], bool)
v = np.array([p["v"] for p in pe])
ok = np.isfinite(v)
print("\nvert  ADV(media)  directo*0.92  | superficial: caso STIV  directo")
for i in range(N):
    print(f" {i+1:2d}    {V_ADV[i]:.3f}      " + (f"{ALFA*v[i]:.3f}" if ok[i] else "  -- ") +
          f"        |              {V_CASO[i]:.3f}{'' if ACEPT_CASO[i] else '(rech)'}  " + (f"{v[i]:.3f}" if ok[i] else "--"))
print(f"{ok.sum()}/{N} verticales; ADV vs 0.92*directo: sesgo {100*(np.mean(ALFA*v[ok])/np.mean(V_ADV[ok])-1):+.1f} %, "
      f"RMSE {np.sqrt(np.mean((ALFA*v[ok]-V_ADV[ok])**2)):.3f}; alfa implicito {np.mean(V_ADV[ok]/v[ok]):.3f}")
both = ok & ACEPT_CASO
print(f"directo vs caso STIV (superficial, {both.sum()} verticales aceptadas en ambos): "
      f"dif media {100*(np.mean(v[both])/np.mean(V_CASO[both])-1):+.1f} %")
if len(Q):
    print(f"Q ({len(Q)} medidas): mediana {np.median(Q):.4f} m3/s, q05-q95 {np.percentile(Q,5):.4f}-{np.percentile(Q,95):.4f}; "
          f"aforo {Q_AFORO} -> {100*(np.median(Q)/Q_AFORO-1):+.1f} %  (caso STIV en video entero: 1.4493)")
