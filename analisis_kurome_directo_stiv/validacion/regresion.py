"""Regresion de un cambio del metodo: python regresion.py <caso> [fin_s].
Corre con el programa tal como esta; para comparar, guardar el json de salidas/ antes de cambiarlo.
Imprime por estacion aceptadas/medidas y mediana, y la mediana de seccion; guarda un json."""
import os, sys, json, numpy as np
from correr import correr_camara, por_estacion
import stiv_directo as sd

from regresion_casos import CASOS

caso = sys.argv[1]
fin = float(sys.argv[2]) if len(sys.argv) > 2 else None
cam, video, *modo = CASOS[caso]
geom, med = correr_camara(video, cam, modo[0] if modo else "auto", fin)
pe = por_estacion(med, sd.N_ESTACIONES)
acc = [r["v"] for _, res in med for r in res if r["aceptada"]]
motas = sum(r["motas"] for _, res in med for r in res if r["aceptada"])
print(f"{caso}: " + " ".join(f"{p['v']:+.2f}/{p['aceptadas']}" if p["aceptadas"] else "--" for p in pe))
print(f"   aceptadas {len(acc)} de {len(med) * sd.N_ESTACIONES} (motas {motas}), mediana {np.median(acc) if acc else float('nan'):+.3f}")
json.dump(pe, open(f"salidas/reg_{caso}.json", "w"), default=float)
