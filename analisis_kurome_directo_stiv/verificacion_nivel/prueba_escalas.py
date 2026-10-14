"""Prueba: medir un tramo de dia solo con escalas lentas (filas promedio de 0.133 s o 0.5 s), en las que
las ondas de superficie, que se deshacen en < 0.5 s, se promedian; lo que queda es lo que persiste, que es
lo que arrastra la corriente. Compara con el programa tal cual y con el proceso de motas.

    python prueba_escalas.py <video.ts> <segundo_inicio> <segundos> <variante>
    variantes: programa | lenta30 | lenta60 | motas
"""
import os, sys
import numpy as np, cv2

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "validacion"))
import correr
sd = correr.sd

video, inicio, segundos, variante = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
modo = "dia"
if variante == "lenta30":
    sd.ESCALAS = ((0.133, 30.0),)
elif variante == "lenta60":
    sd.ESCALAS = ((0.5, 60.0),)
elif variante == "motas":
    modo = "noche"
sd.PASO_MEDIDA_S = 5.0
sd.elegir_camara("myoshoji")
cfg = sd.cargar_config()
# recorte del video: se salta hasta el inicio decodificando (el .ts no tiene indice fiable)
cap = cv2.VideoCapture(video)
cap.set(cv2.CAP_PROP_POS_MSEC, inicio * 1000)
tmp = os.path.join(AQUI, "salidas", "diagnostico", f"_tramo_{variante}_{int(inicio)}.avi")
vw = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*"FFV1"), 30.0, (1280, 720))
for _ in range(int(segundos * 30)):
    ok, f = cap.read()
    if not ok:
        break
    vw.write(f)
vw.release()
geom, med = correr.bucle(tmp, cfg, True, modo, None, False)
os.remove(tmp)
acc = [[r["v"] for r in res if r["aceptada"]] for _, res in med]
sec = [np.median(v) for v in acc if len(v) >= 3]
por_est = [np.median([res[i]["v"] for _, res in med if res[i]["aceptada"]]) if any(res[i]["aceptada"] for _, res in med) else np.nan
           for i in range(sd.N_ESTACIONES)]
print(f"{variante:9s} (inicio {inicio:.0f} s): {len(sec)}/{len(med)} medidas de seccion, mediana {np.median(sec) if sec else float('nan'):.3f} m/s; "
      f"por estacion " + " ".join(f"{v:.3f}" for v in por_est))
