"""Pasa un video grabado por el MISMO codigo de medida de stiv_directo.py (Geometria, Buffers con el
canal de motas, medir con la cascada de escalas, modo auto por saturacion), midiendo cada PASO_MEDIDA_S
como el programa en directo. Solo cambia la geometria y los parametros POR CAMARA; los del metodo
(bloques, coherencia, actividad, escalas...) se dejan como estan en el programa."""
import os, sys, time, numpy as np, cv2

# el programa de verdad, no una copia: lo que se valida es exactamente lo que corre en directo
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import stiv_directo as sd

POR_CAMARA = ("N_ESTACIONES", "MARGEN_ORILLA", "LARGO_LINEA_M", "CENTRO_LINEA", "ANCHO_BANDA_M",
              "V_ESPERADA", "FPS_CAMARA", "FILTRO_DIRECCIONAL", "MEDIR_NOCHE")


def correr(video, cuad, L, W, params, orientacion_auto=True, modo="auto", fin_s=None, verbose=True):
    # una geometria propia no es ninguna camara de CAMARAS: no hereda el "medir_noche" de la ultima elegida
    sd.MEDIR_NOCHE = True
    for k, v in params.items():
        if k not in POR_CAMARA:
            raise ValueError(f"{k} no es un parametro por camara")
        setattr(sd, k, v)
    sd.V_MAX_FISICA = 3 * sd.V_ESPERADA
    return bucle(video, {"cuadrilatero_px": cuad, "largo_m": L, "ancho_m": W}, orientacion_auto, modo,
                 fin_s, verbose)


def correr_camara(video, camara, modo="auto", fin_s=None, verbose=True, ajustes=None):
    """Con los ajustes de una camara del programa (CAMARAS + su config_stiv_directo.json). `ajustes`
    cambia valores por camara, como los "ajustes" de fuentes.json (p. ej. {"v_esperada": 1.0})."""
    sd.elegir_camara(camara, ajustes=ajustes)
    return bucle(video, sd.cargar_config(), True, modo, fin_s, verbose)


def bucle(video, cfg, orientacion_auto, modo, fin_s, verbose):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1 if orientacion_auto else 0)
    fps = cap.get(cv2.CAP_PROP_FPS)
    geom = sd.Geometria(cfg, fps)
    bufs = sd.Buffers(geom)
    if verbose:
        print(f"  {os.path.basename(video)}: {fps:.2f} fps, DS {geom.ds*1000:.1f} mm = "
              f"{geom.px_por_muestra:.2f} px/muestra (mediana), {len(geom.xs)} muestras por linea, "
              f"filas por escala {geom.n_filas}")
    n, t_ult, medidas, brillos, modo_act = 0, -1e9, [], [], None
    candidato, repeticiones, t_ult_modo = None, 0, -1e9
    c0 = time.perf_counter()
    while True:
        ok, f = cap.read()
        if not ok:
            break
        t = n / fps
        if fin_s and t > fin_s:
            break
        if modo_act is None:
            modo_act = modo if modo != "auto" else ("noche" if sd.es_noche(geom, f) else "dia")
            t_ult_modo = t
            if verbose:
                print(f"  modo {modo_act} (saturacion {geom.saturacion(f):.1f})")
        elif modo == "auto" and t - t_ult_modo >= 5.0:
            # como ejecutar(): una lectura cada 5 s y cambio tras tres seguidas iguales (al anochecer la
            # camara pasa a infrarrojo); el STI se vacia porque mezclaria los dos procesos
            t_ult_modo = t
            visto = "noche" if sd.es_noche(geom, f) else "dia"
            if visto != modo_act:
                repeticiones = repeticiones + 1 if visto == candidato else 1
                candidato = visto
                if repeticiones >= 3:
                    modo_act, repeticiones, brillos = visto, 0, []
                    bufs.vaciar()
                    if verbose:
                        print(f"  t={t:.0f} s: cambio a modo {modo_act}")
            else:
                candidato, repeticiones = None, 0
        if modo_act == "noche" and n % max(1, int(round(fps))) == 0:
            brillos = (brillos + [geom.brillo(f)])[-30:]
        bufs.agregar(geom.procesar(f, modo_act), geom.procesar(f, "noche") if modo_act == "dia" else None)
        if bufs.rapida_llena() and t - t_ult >= sd.PASO_MEDIDA_S:
            bs = [np.stack(b) if b is not None else None for b in bufs.instantanea()]
            bm = ([np.stack(b) if b is not None else None for b in bufs.instantanea(1)]
                  if modo_act == "dia" else None)
            br = np.median(np.stack(brillos), axis=0) if brillos else None
            res = sd.medir(bs, geom, geom.cobertura(*f.shape[:2]), modo_act, br, bm)
            for r in res:
                r.pop("sti", None)
                r["modo"] = modo_act
            medidas.append((t, res))
            t_ult = t
        n += 1
    cap.release()
    if verbose:
        print(f"  {n} fotogramas, {len(medidas)} medidas en {time.perf_counter() - c0:.0f} s")
    return geom, medidas


def por_estacion(medidas, n_est):
    """Mediana de las medidas aceptadas de cada estacion, fraccion aceptada y motivos de rechazo."""
    filas = []
    for i in range(n_est):
        rs = [res[i] for _, res in medidas]
        acc = [r for r in rs if r["aceptada"]]
        v = np.array([r["v"] for r in acc])
        motivos = {}
        for r in rs:
            if not r["aceptada"]:
                motivos[r["motivos"]] = motivos.get(r["motivos"], 0) + 1
        filas.append({"estacion": i, "n": len(rs), "aceptadas": len(acc),
                      "v": float(np.median(v)) if len(v) else np.nan,
                      "q25": float(np.percentile(v, 25)) if len(v) else np.nan,
                      "q75": float(np.percentile(v, 75)) if len(v) else np.nan,
                      "coh": float(np.median([r["coherencia"] for r in acc])) if acc else np.nan,
                      "escalas": "".join("rml"[r["escala"]].upper() if r["motas"] else "rml"[r["escala"]]
                                         for r in acc[:1]) + (f" motas {sum(r['motas'] for r in acc)}" if any(r["motas"] for r in acc) else ""),
                      "motivos": motivos})
    return filas
