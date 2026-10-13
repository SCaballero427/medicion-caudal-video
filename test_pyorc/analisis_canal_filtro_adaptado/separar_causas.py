"""Resolucion o bitrate: cual de los dos mata el trazador.

Las escaleras bajan las dos cosas a la vez (se mantiene el numero de bits por pixel), asi que no
separan las causas -- y esa separacion es justo la que decide si hace falta otra camara o basta
con grabar a mas calidad. Aqui se cruzan las dos variables por separado sobre el campo CERCANO,
donde se sabe que hay trazador de sobra.
"""
import csv, os, subprocess, sys
import cv2, numpy as np
_R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_R, "analisis_canal_riego_stiv"))
import stiv_canal as sc
import filtro_adaptado as fa
import escalera_honesta as eh
import supervivencia_trazador as st

CASOS = [
    ("original",            1.0, 661, "el video tal cual"),
    ("solo menos bitrate",  1.0,  16, "misma resolucion, el bitrate del campo lejano"),
    ("solo menos resolucion", 6.5, 661, "resolucion del campo lejano, bitrate generoso"),
    ("las dos (= lejano)",  6.5,  16, "lo que de verdad ocurre en el campo lejano"),
]
DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp_causas")


def preparar(entrada, salida, factor, kb, w=1024, h=576):
    nw, nh = int(round(w / factor / 2)) * 2, int(round(h / factor / 2)) * 2
    chico = salida.replace(".mp4", "_c.mp4")
    subprocess.run([eh.FFMPEG, "-y", "-loglevel", "error", "-i", entrada,
                    "-vf", "scale=%d:%d:flags=area" % (nw, nh),
                    "-c:v", "libx264", "-preset", "medium", "-profile:v", "baseline",
                    "-b:v", "%dk" % kb, "-maxrate", "%dk" % (kb * 2),
                    "-bufsize", "%dk" % (kb * 4), "-pix_fmt", "yuv420p", "-an", chico], check=True)
    subprocess.run([eh.FFMPEG, "-y", "-loglevel", "error", "-i", chico,
                    "-vf", "scale=%d:%d:flags=bilinear" % (w, h),
                    "-c:v", "libx264", "-preset", "medium", "-crf", "12",
                    "-pix_fmt", "yuv420p", "-an", salida], check=True)
    return nw, nh


def main():
    os.makedirs(DIR, exist_ok=True)
    cap, ntot, fps = sc.abrir_video()
    sc.FPS_REAL[0] = fps
    ok, f0 = cap.read(); cap.release()
    geo = sc.Geometria(cv2.cvtColor(f0, cv2.COLOR_BGR2GRAY))
    rng = np.random.default_rng(fa.SEMILLA)
    vs = np.linspace(fa.V_MIN, fa.V_MAX, fa.N_CAND)
    print("estimando la estabilizacion UNA vez sobre el original...")
    AF = fa.afines_del_original(sc.ARCHIVO_VIDEO, geo, ntot)
    filas = []
    print("%-22s %-11s %5s  %8s  %8s  %s" % ("caso", "tamano", "kb/s", "px>4", "score/techo", "veredicto"))
    for nom, fac, kb, _d in CASOS:
        ruta = os.path.join(DIR, nom.replace(" ", "_") + ".mp4")
        nw, nh = preparar(sc.ARCHIVO_VIDEO, ruta, fac, kb)
        surv = st.medir(ruta)
        pl, _, _ = fa.construir_stis(ruta, geo, [eh.BANDA], ntot, verbose=False, afines=AF)
        P = pl[0]
        nv = fa.ventana_residencia(P["y1"] - P["y0"], fps)
        t = fa.analizar_todo(P["sti"], vs, fps, P["ds"], rng, n_barajados=8, n_ventana=nv)
        v = fa.veredicto(t["pico"], vs)
        print("%-22s %4dx%-6d %5d  %8.5f  %5.2f/%-5.2f  %s"
              % (nom, nw, nh, kb, surv["frac_4"], v["score"], v["techo_nulo"],
                 "DETECTA (v=%+.4f)" % v["v_pico"] if v["supera_nulo"] else "NO detecta"))
        filas.append(dict(caso=nom, factor=fac, kbps=kb, ancho=nw, alto=nh, **surv, **v))
    with open(os.path.join(fa.DIR_SALIDAS, "separar_causas.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys())); w.writeheader(); w.writerows(filas)
    print("\nescrito: salidas/separar_causas.csv")


if __name__ == "__main__":
    main()
