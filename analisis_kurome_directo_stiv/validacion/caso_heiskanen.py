"""Heiskanen et al., Oulankajoki, Reolink RLC-810A, 20-05-2023: stiv_directo.py contra ADCP.
Geometria: las 20 lineas de busqueda del dataset, proyectadas con su modelo de camara (variante 7:
sin espejo, la que alinea las lineas con el flujo optico) sobre el plano del agua (nivel del dia).
La referencia (ADCP) solo se abre al final."""
import sys, glob, json, numpy as np
from proyeccion import leer_modelo, proyectar, lineas, BASE
from correr import correr, por_estacion
import os
VARIANTE = os.environ.get("VARIANTE", "")
if "sigma" in VARIANTE:
    import sigma_por_estacion

Z_AGUA = 160.75            # N2000, nivel diario del 20-05-2023 (WaterLevel_data, geometria)
V_ESP = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0   # a priori; se barre aparte
BANDA = 0.40               # m, ~26 % de la separacion entre estaciones (regla de Bradano)
videos = sorted(glob.glob(f"{BASE}/Surface_flow_velocities/Raw_data/Oulankajoki_River/2023/RGB/*RLC-810A.mp4"))
if len(sys.argv) > 2:
    videos = [v for v in videos if any(h in v for h in sys.argv[2].split(","))]

m = leer_modelo(f"{BASE}/Camera_models/Oulankajoki_River/Reolink RLC-810A/Camera_model_ReolinkRLC810A.xml")
Lm = lineas()
n = len(Lm)
L = float(np.median(np.hypot(Lm[:, 2] - Lm[:, 0], Lm[:, 3] - Lm[:, 1])))
W = float(np.hypot(*(Lm[-1, :2] - Lm[0, :2])))
# la linea 1 del dataset mide 3.15 m y las otras 19 miden 4.00: su fin no sirve de esquina. El
# rectangulo usa el inicio de la 1 con la direccion y el largo de las demas.
esquinas = np.array([Lm[0, 0:2], Lm[0, 0:2] + Lm[1, 2:4] - Lm[1, 0:2], Lm[-1, 2:4], Lm[-1, 0:2]])
cuad, _ = proyectar(m, np.c_[esquinas, np.full(4, Z_AGUA)], "xyz", True, -1, -1)
print(f"L {L:.3f} m, W {W:.3f} m, {n} estaciones cada {W/(n-1):.3f} m; cuad {np.round(cuad).astype(int).tolist()}")
params = dict(N_ESTACIONES=n, MARGEN_ORILLA=0.0, LARGO_LINEA_M=L, CENTRO_LINEA=0.5, ANCHO_BANDA_M=BANDA,
              V_ESPERADA=V_ESP, FPS_CAMARA=None, FILTRO_DIRECCIONAL=False)

todas = {}
for v in videos:
    hora = v.split("_")[-2]
    geom, med = correr(v, cuad.tolist(), L, W, params, orientacion_auto=False)
    pe = por_estacion(med, n)
    todas[hora] = {"est": pe, "medidas": [(t, [(r["v"], r["aceptada"], r["motivos"], r["coherencia"], r["escala"], r["motas"]) for r in res]) for t, res in med]}
    print(f"  {hora}: " + " ".join(f"{p['v']:.2f}/{p['aceptadas']}" if p["aceptadas"] else
                                    f"--({'/'.join(k[:5] for k in p['motivos'])})" for p in pe))
json.dump(todas, open(f"salidas/heiskanen_v{V_ESP:g}{VARIANTE}.json", "w"), default=float)

# ---------------- comparacion (solo aqui se abre la referencia) ----------------
adcp = np.genfromtxt(f"{BASE}/ADCP_measurements/Oulankajoki_River/Oulanka_ADCP_20052023.csv",
                     delimiter=",", skip_header=1, usecols=(0, 1))
autores = np.genfromtxt(f"{BASE}/Surface_flow_velocities/Processed_data/STIV/Oulankajoki_River/2023/RGB/STIV_RGB_20052023.csv",
                        delimiter=",", skip_header=1)
track = autores[:, 0]          # posicion de cada linea sobre el eje del ADCP (dada por los autores)
paso = W / (n - 1)
v_adcp = np.array([np.median(adcp[np.abs(adcp[:, 1] - x) <= paso / 2, 0]) for x in track])
print("\nest track  ADCP  autores(6h) | " + " ".join(sorted(todas)))
for i in range(n):
    print(f"{i+1:3d} {track[i]:5.1f}  {v_adcp[i]:.2f}  {autores[i,2]:.2f}       | " +
          " ".join(f"{todas[h]['est'][i]['v']:5.2f}" if todas[h]['est'][i]['aceptadas'] else "   --" for h in sorted(todas)))
for h in sorted(todas):
    v = np.array([e["v"] for e in todas[h]["est"]])
    ok = np.isfinite(v)
    if ok.sum() < 2:
        print(f"{h}: {ok.sum()} estaciones"); continue
    sesgo = 100 * (np.median(v[ok] / v_adcp[ok]) - 1)
    rmse = np.sqrt(np.mean((v[ok] - v_adcp[ok]) ** 2))
    print(f"{h}: {ok.sum():2d}/20 estaciones, mediana {np.median(v[ok]):.3f} m/s, sesgo mediano vs ADCP {sesgo:+.1f} %, RMSE {rmse:.3f}")
ok = np.isfinite(autores[:, 2])
print(f"autores (6 h): mediana {np.median(autores[:,2]):.3f}, sesgo {100*(np.median(autores[:,2]/v_adcp)-1):+.1f} %, "
      f"RMSE {np.sqrt(np.mean((autores[:,2]-v_adcp)**2)):.3f}; ADCP mediana {np.median(v_adcp):.3f}")
