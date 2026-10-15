"""Capturas ligeras de los videos del dataset y de los resultados de las pruebas, para GitHub.

Los videos del dataset (`datasets vision velocimetria/`, 45 GB) y los videos de resultados no caben en
el repositorio de forma razonable; esta carpeta guarda en su lugar una imagen de cada uno, en JPEG
reducido. Tres partes, cada una se puede rehacer por separado:

    python generar_capturas.py videos       # un fotograma de cada video del dataset + hojas de contacto
    python generar_capturas.py resultados   # por caso: el video original de entrada + figuras y videos de resultado
    python generar_capturas.py validacion   # re-corre validacion/caso_*.py y dibuja una medida

Se ejecuta desde esta carpeta con el .venv del programa en directo (numpy + OpenCV, sin pyorc):

    ..\\analisis_kurome_directo_stiv\\.venv\\Scripts\\python.exe generar_capturas.py videos
"""
import csv, glob, io, os, runpy, shutil, sys, contextlib
import numpy as np
import cv2

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
DATASET = os.path.join(RAIZ, "datasets vision velocimetria")
ANIDADA = os.path.join(RAIZ, "test_pyorc")
VALIDACION = os.path.join(RAIZ, "analisis_kurome_directo_stiv", "validacion")

EXTENSIONES = (".mp4", ".avi", ".mov", ".mkv", ".mts")
LADO_VIDEO = 640          # px del lado mayor de cada captura del dataset: se reconoce el rio, pesa ~40 KB
LADO_RESULTADO = 1280     # los resultados llevan texto y flechas que tienen que leerse
LADO_VALIDACION = 1600    # el dibujo del programa: video + vista rectificada + panel de STI
CALIDAD = 72
BRILLO_OSCURO = 20        # mediana por debajo de esto la captura sin estirar es negra. Mediana y no media:
                          # en el Bradano el agua esta a 0.12/255 pero la orilla de grava sube la media


def guardar_jpg(ruta, img, lado):
    h, w = img.shape[:2]
    k = lado / max(h, w)
    if k < 1:
        img = cv2.resize(img, (round(w * k), round(h * k)), interpolation=cv2.INTER_AREA)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, CALIDAD, cv2.IMWRITE_JPEG_OPTIMIZE, 1])
    buf.tofile(ruta)      # imwrite no acepta rutas con caracteres fuera de ASCII en Windows
    return img


def leer_imagen(ruta):
    return cv2.imdecode(np.fromfile(ruta, np.uint8), cv2.IMREAD_COLOR)


def estirar(img):
    """Estiramiento de contraste por percentiles. Solo para que la captura no sea un rectangulo negro:
    se anota en el indice, para que nadie lo tome por el aspecto real del video."""
    lo, hi = np.percentile(img, [1, 99.5])
    return np.clip((img.astype(np.float32) - lo) * 255 / max(hi - lo, 1), 0, 255).astype(np.uint8)


def fotograma(ruta, fraccion=0.5):
    """El fotograma en `fraccion` de la duracion; si el contenedor no deja saltar, el primero."""
    cap = cv2.VideoCapture(ruta)
    if not cap.isOpened():
        return None, {}
    info = {"ancho": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), "alto": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": cap.get(cv2.CAP_PROP_FPS), "fotogramas": int(cap.get(cv2.CAP_PROP_FRAME_COUNT))}
    n = max(0, int(info["fotogramas"] * fraccion))
    cap.set(cv2.CAP_PROP_POS_FRAMES, n)
    ok, f = cap.read()
    if not ok:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok, f = cap.read()
        n = 0
    cap.release()
    info["capturado"] = n
    return (f if ok else None), info


def grupo_de(rel):
    """Hoja de contacto a la que va cada video: un dataset por hoja, Heiskanen partido por rio."""
    p = rel.replace("\\", "/").split("/")
    if p[0] == "data":
        return "HARMONIOUS"
    if p[0].startswith("Heiskanen"):
        return "Heiskanen_" + p[3]          # Surface_flow_velocities/Raw_data/<rio>
    if p[0] == "Boneyardcreek":
        return "Boneyard_Creek"
    return "Otros"


def rotulo_de(rel):
    """Nombre bajo cada miniatura. En HARMONIOUS hay videos que se llaman "1", "10" u "output2": si el
    nombre no dice de que rio es, se le antepone."""
    p = rel.replace("\\", "/").split("/")
    nombre = os.path.splitext(p[-1])[0]
    if p[0] == "data" and p[1].lower().replace("river", "")[:4] not in nombre.lower():
        return f"{p[1]}/{nombre}"
    return nombre


def hoja_contacto(entradas, ruta, ancho_mini=240, columnas=8):
    """Mosaico de miniaturas con el nombre de cada video debajo."""
    alto_txt = 16
    minis = []
    for img, nombre in entradas:
        h, w = img.shape[:2]
        m = cv2.resize(img, (ancho_mini, round(h * ancho_mini / w)), interpolation=cv2.INTER_AREA)
        if m.shape[0] > ancho_mini:                 # videos verticales: no estirar la fila
            m = cv2.resize(img, (round(w * ancho_mini / h), ancho_mini), interpolation=cv2.INTER_AREA)
        minis.append((m, nombre))
    alto_celda = max(m.shape[0] for m, _ in minis) + alto_txt + 6
    filas = -(-len(minis) // columnas)
    lienzo = np.full((filas * alto_celda, columnas * (ancho_mini + 6), 3), 255, np.uint8)
    for k, (m, nombre) in enumerate(minis):
        y0, x0 = (k // columnas) * alto_celda + 3, (k % columnas) * (ancho_mini + 6) + 3
        lienzo[y0:y0 + m.shape[0], x0:x0 + m.shape[1]] = m
        cv2.putText(lienzo, nombre[:40], (x0, y0 + alto_celda - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.32,
                    (0, 0, 0), 1, cv2.LINE_AA)
    guardar_jpg(ruta, lienzo, 99999)


# ───────────────────────────────────── 1. videos del dataset ─────────────────────────────────────
def capturas_videos():
    rutas = sorted(os.path.join(d, f) for d, _, fs in os.walk(DATASET) for f in fs
                   if f.lower().endswith(EXTENSIONES))
    # el unico dataset de HARMONIOUS sin video publica solo fotogramas: se toma el primero
    murg = os.path.join(DATASET, "data", "MurgRiver", "Frames")
    sueltas = sorted(os.path.join(murg, f) for f in os.listdir(murg)
                     if f.lower().endswith((".png", ".jpg", ".tif", ".gif")))[:1] if os.path.isdir(murg) else []
    filas, grupos = [], {}
    for k, ruta in enumerate(rutas + sueltas, 1):
        rel = os.path.relpath(ruta, DATASET)
        if ruta in sueltas:
            f = leer_imagen(ruta)
            if f is None:                                   # GIF: OpenCV lo lee como video
                f, _ = fotograma(ruta, 0)
            info = {"ancho": f.shape[1], "alto": f.shape[0], "fps": 0, "fotogramas": 1, "capturado": 0}
        else:
            f, info = fotograma(ruta)
        if f is None:
            print(f"  [{k}/{len(rutas)}] NO SE PUDO LEER {rel}")
            filas.append({"video": rel, "error": "no se pudo leer"})
            continue
        estirado = float(np.median(f)) < BRILLO_OSCURO
        if estirado:
            f = estirar(f)
        salida = os.path.join(AQUI, "videos", os.path.splitext(rel)[0] + ".jpg")
        mini = guardar_jpg(salida, f, LADO_VIDEO)
        grupos.setdefault(grupo_de(rel), []).append((mini, rotulo_de(rel)))
        dur = info["fotogramas"] / info["fps"] if info["fps"] else 0
        filas.append({"video": rel.replace("\\", "/"), "captura": os.path.relpath(salida, AQUI).replace("\\", "/"),
                      "ancho": info["ancho"], "alto": info["alto"], "fps": round(info["fps"], 3),
                      "fotogramas": info["fotogramas"], "duracion_s": round(dur, 1),
                      "tamano_MB": round(os.path.getsize(ruta) / 1e6, 1),
                      "fotograma_capturado": info["capturado"], "contraste_estirado": int(estirado), "error": ""})
        print(f"  [{k}/{len(rutas) + len(sueltas)}] {rel}  {info['ancho']}x{info['alto']}"
              + ("  (estirado)" if estirado else ""))
    campos = ["video", "captura", "ancho", "alto", "fps", "fotogramas", "duracion_s", "tamano_MB",
              "fotograma_capturado", "contraste_estirado", "error"]
    with open(os.path.join(AQUI, "indice_videos.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, campos, restval="")
        w.writeheader()
        w.writerows(filas)
    for g, entradas in grupos.items():
        hoja_contacto(entradas, os.path.join(AQUI, "hojas_contacto", f"{g}.jpg"))
        print(f"  hoja de contacto {g}: {len(entradas)} videos")


# ───────────────────────────────────── 2. resultados de los casos ─────────────────────────────────
# Por caso, las dos mitades de la prueba lado a lado en la misma carpeta:
#   entrada_*.jpg  el video ORIGINAL que entra al algoritmo, tal cual (fotograma de la mitad)
#   el resto       lo que el algoritmo SACA: sus figuras y dos fotogramas de cada video de resultado
# "entradas" son (etiqueta, ruta absoluta); "videos" y "figuras" van relativos a la carpeta del caso.
# Los videos de entrada que no estan en datasets vision velocimetria/ (Ngwerere, SMC, el canal de
# WhatsApp, las grabaciones de los directos) no tienen captura en videos/: esta es la unica que hay.
DS = DATASET
WHATSAPP = os.path.join(RAIZ, "videos", "WhatsApp Video 2026-08-16 at 8.07.12 PM.mp4")
SMC = os.path.join(ANIDADA, "USGS", "Video", "SMC_D_RC_022_08172020_AC.mp4")
DIRECTO = os.path.join(RAIZ, "analisis_kurome_directo_stiv")
GRABACIONES = os.path.join(DIRECTO, "validacion", "grabaciones")
CASOS = [
    {"nombre": "ngwerere", "carpeta": os.path.join(ANIDADA, "analisis_ngwerere"), "algoritmo": "LSPIV (pyorc)",
     "entradas": [("ngwerere", os.path.join(ANIDADA, "ngwerere", "ngwerere_20191103.mp4"))],
     "videos": [], "figuras": ["salidas/fig*.png"]},
    {"nombre": "smc_pyorc", "carpeta": os.path.join(ANIDADA, "analisis_USGS_SMC_pyorc"), "algoritmo": "LSPIV (pyorc)",
     "entradas": [("SMC_D_RC_022", SMC)],
     "videos": ["salidas/velocidad_flechas_pyorc.mp4"], "figuras": ["salidas/fig*.png"]},
    {"nombre": "smc_stiv", "carpeta": os.path.join(ANIDADA, "analisis_USGS_SMC_stiv"), "algoritmo": "STIV (OpenCV)",
     "entradas": [("SMC_D_RC_022", SMC)],
     "videos": ["salidas/video_velocimetria.mp4"], "figuras": ["salidas/fig*.png"]},
    {"nombre": "boneyard", "carpeta": os.path.join(ANIDADA, "analisis_boneyard_stiv"), "algoritmo": "STIV (OpenCV)",
     "entradas": [("20180610-082000", os.path.join(DS, "Boneyardcreek", "boneyardcreek_video",
                                                   "03337000_bullet_20180610-082000.mp4"))],
     "videos": [f"salidas/{v}.mp4" for v in ("velocidad_tiempo_real", "velocidad_manual", "velocidad_sin_nivel",
                                              "velocidad_nivel", "velocidad_nivel_chapa", "velocidad_nivel_curva")],
     "figuras": ["salidas/fig*.png"]},
    {"nombre": "bradano", "carpeta": os.path.join(ANIDADA, "analisis_bradano_stiv"), "algoritmo": "STIV (OpenCV)",
     "entradas": [("RiverBradano", os.path.join(DS, "data", "RiverBradano", "Stabilised", "Video",
                                                "RiverBradano_24_fps_Stabilised.avi"))],
     "videos": ["salidas/velocidad_tiempo_real.mp4"], "figuras": ["salidas/fig*.png"]},
    {"nombre": "arrow", "carpeta": os.path.join(ANIDADA, "analisis_arrow_stiv"), "algoritmo": "STIV (OpenCV)",
     "entradas": [("sin_sembrar", os.path.join(DS, "data", "RiverArrow", "Stabilised", "GoPro_Stable_trans_Unseeded",
                                               "Video", "Arrow_GoPro_Unseeded_Stabilised.avi")),
                  ("sembrado", os.path.join(DS, "data", "RiverArrow", "Stabilised", "GoPro_stable_trans_seeded",
                                            "Video", "Arrow_GoPro_Seeded_Stabilised.avi"))],
     "videos": ["salidas/velocidad_tiempo_real.mp4"], "figuras": ["salidas/fig*.png"]},
    {"nombre": "hommerich", "carpeta": os.path.join(ANIDADA, "analisis_hommerich_stiv"), "algoritmo": "STIV (OpenCV)",
     "entradas": [("20241010_081717", os.path.join(DS, "Hommerich", "20241010_081717.mp4"))],
     "videos": ["salidas/velocidad_tiempo_real.mp4"], "figuras": []},
    {"nombre": "canal_riego", "carpeta": os.path.join(ANIDADA, "analisis_canal_riego_stiv"), "algoritmo": "STIV (OpenCV)",
     "entradas": [("whatsapp", WHATSAPP)],
     "videos": ["salidas/velocidad_tiempo_real.mp4"], "figuras": ["salidas/fig*.png"]},
    {"nombre": "canal_lejano", "carpeta": os.path.join(ANIDADA, "analisis_canal_lejano_stiv"), "algoritmo": "STIV (experimento)",
     "entradas": [("whatsapp", WHATSAPP)],
     "videos": ["salidas/video_alcance.mp4"], "figuras": ["salidas/sti_*.png"]},
    {"nombre": "canal_filtro_adaptado", "carpeta": os.path.join(ANIDADA, "analisis_canal_filtro_adaptado"),
     "algoritmo": "filtro adaptado (experimento)", "entradas": [("whatsapp", WHATSAPP)],
     "videos": ["salidas/video_filtro.mp4"], "figuras": ["salidas/fig*.png"]},
    {"nombre": "canal_completo", "carpeta": os.path.join(ANIDADA, "analisis_canal_completo_stiv"),
     "algoritmo": "STIV + modelo Shiono-Knight", "entradas": [("whatsapp", WHATSAPP)],
     "videos": ["salidas/canal_completo.mp4"], "figuras": ["salidas/fig*.png"]},
    {"nombre": "canal_stiv_puro", "carpeta": os.path.join(ANIDADA, "analisis_canal_stiv_puro"), "algoritmo": "STIV (OpenCV)",
     "entradas": [("whatsapp", WHATSAPP)], "videos": ["salidas/stiv_puro.mp4"], "figuras": []},
    {"nombre": "canal_seccion_completa", "carpeta": os.path.join(ANIDADA, "analisis_canal_seccion_completa"),
     "algoritmo": "STIV + estaciones deducidas", "entradas": [("whatsapp", WHATSAPP)],
     "videos": ["salidas/seccion_completa.mp4"], "figuras": []},
    # el programa en directo mide streams de YouTube: la "entrada" es su grabacion FFV1 sin tocar
    {"nombre": "directo", "carpeta": DIRECTO, "algoritmo": "STIV en tiempo real (stiv_directo.py)",
     "entradas": [(c, os.path.join(GRABACIONES, c + ".avi")) for c in ("myoshoji", "kurome", "shimoda")],
     "videos": [], "figuras": ["salidas/*/ultima_vista.png", "verificacion_nivel/salidas/*.png",
                               "verificacion_nivel/salidas/diagnostico/*.png"]},
]


def capturas_resultados():
    for caso in CASOS:
        destino = os.path.join(AQUI, "resultados", caso["nombre"])
        for etiqueta, ruta in caso["entradas"]:
            f, _ = fotograma(ruta, 0.5)
            if f is None:
                print(f"  NO SE PUDO LEER {ruta}")
                continue
            nombre = f"entrada_{etiqueta}.jpg"
            if float(np.median(f)) < BRILLO_OSCURO:      # mismo criterio que en videos/ (el Bradano)
                f, nombre = estirar(f), f"entrada_{etiqueta}_estirado.jpg"
            guardar_jpg(os.path.join(destino, nombre), f, LADO_RESULTADO)
            print(f"  {caso['nombre']}: {nombre}  <- {os.path.relpath(ruta, RAIZ)}")
        for v in caso["videos"]:
            ruta = os.path.join(caso["carpeta"], v)
            base = os.path.splitext(os.path.basename(v))[0]
            for frac in (0.25, 0.75):        # dos instantes: se ve que la medida no es un fotograma fijo
                f, _ = fotograma(ruta, frac)
                if f is None:
                    print(f"  NO SE PUDO LEER {ruta}")
                    break
                guardar_jpg(os.path.join(destino, f"{base}_{int(frac * 100)}pct.jpg"), f, LADO_RESULTADO)
            print(f"  {caso['nombre']}: {v}")
        for patron in caso["figuras"]:
            for ruta in sorted(glob.glob(os.path.join(caso["carpeta"], patron))):
                rel = os.path.relpath(ruta, caso["carpeta"]).replace("\\", "/")
                # ultima_vista.png se repite por camara: la camara (carpeta) pasa al nombre
                nombre = (rel.split("/")[-2] + "_" if rel.endswith("ultima_vista.png") else "") \
                    + os.path.splitext(os.path.basename(ruta))[0] + ".jpg"
                guardar_jpg(os.path.join(destino, nombre), leer_imagen(ruta), LADO_RESULTADO)
                print(f"  {caso['nombre']}: {rel}")


# ───────────────────────────── 3. validacion del programa en directo ─────────────────────────────
def capturas_validacion():
    """Los caso_*.py de validacion/ solo dejan texto y JSON. Se re-corren tal cual (mismo codigo, misma
    referencia) interceptando sd.medir para quedarse con el fotograma de cada medida, y se dibuja la
    medida del MEDIO del video con dibujar() del propio programa: ni la mejor ni la peor, para no
    escoger. Los JSON que escriben van a una carpeta temporal, no pisan los de validacion/salidas."""
    sys.path.insert(0, VALIDACION)
    import correr as C
    sd = C.sd
    bucle_original, medir_original, procesar_original = C.bucle, sd.medir, sd.Geometria.procesar
    estado = {"frame": None, "medidas": []}

    def procesar(self, frame, modo="dia"):
        estado["frame"] = frame
        return procesar_original(self, frame, modo)

    def medir(*a, **k):
        res = medir_original(*a, **k)
        # copia superficial: bucle() quita el "sti" de cada resultado despues, y el panel lo necesita
        ok, jpg = cv2.imencode(".jpg", estado["frame"], [cv2.IMWRITE_JPEG_QUALITY, 95])
        estado["medidas"].append((jpg, a[1], [dict(r) for r in res], a[3] if len(a) > 3 else k.get("modo", "dia")))
        return res

    def bucle(video, cfg, orientacion_auto, modo, fin_s, verbose):
        estado["medidas"] = []
        geom, med = bucle_original(video, cfg, orientacion_auto, modo, fin_s, verbose)
        if estado["medidas"]:
            i = len(estado["medidas"]) // 2
            jpg, g, res, modo_act = estado["medidas"][i]
            t = med[i][0] if i < len(med) else 0.0
            frame = cv2.imdecode(jpg, cv2.IMREAD_COLOR)
            img = sd.dibujar(frame, g, res, {"titulo": f"Validacion: {os.path.basename(video)}", "t": t,
                                             "llenado": 1.0, "retraso": 0.0, "modo": modo_act,
                                             "px_muestra": g.px_por_muestra, "verificada": True}, False)
            nombre = estado["caso"] + ("_" + video.split("_")[-2] if estado["caso"] == "heiskanen" else "")
            # la cabecera de dibujar() esta pensada para la pantalla: en un 4K reducido no se lee, asi
            # que se repite lo esencial en una franja propia, a tamano legible
            k = LADO_VALIDACION / img.shape[1]
            img = cv2.resize(img, (LADO_VALIDACION, round(img.shape[0] * k)), interpolation=cv2.INTER_AREA)
            ac = [r["v"] for r in res if r["aceptada"]]
            textos = [f"{os.path.basename(video)}  |  stiv_directo.py, modo {modo_act}  |  medida {i + 1} de "
                      f"{len(estado['medidas'])} (la del medio), t = {t:.0f} s",
                      f"estaciones aceptadas {len(ac)} de {len(res)}  |  mediana de la seccion "
                      + (f"{np.median(ac):.3f} m/s" if ac else "--") + "  |  verde = aceptada, rojo = rechazada"]
            franja = np.full((58, img.shape[1], 3), 20, np.uint8)
            for j, tx in enumerate(textos):
                cv2.putText(franja, tx, (10, 22 + 26 * j), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 1, cv2.LINE_AA)
            img = np.vstack([img, franja])
            guardar_jpg(os.path.join(AQUI, "resultados", "validacion_directo", nombre + ".jpg"), img, LADO_VALIDACION)
            print(f"  -> captura {nombre}.jpg (medida {i + 1} de {len(estado['medidas'])}, t = {t:.0f} s)")
        return geom, med

    C.bucle, sd.medir, sd.Geometria.procesar = bucle, medir, procesar
    temporal = os.path.join(AQUI, "_temporal")
    os.makedirs(os.path.join(temporal, "salidas"), exist_ok=True)
    os.chdir(temporal)
    for caso in ("sile", "bradano", "heiskanen"):
        estado["caso"] = caso
        print(f"== caso_{caso}.py")
        sys.argv = [f"caso_{caso}.py"]
        texto = io.StringIO()
        with contextlib.redirect_stdout(texto):
            runpy.run_path(os.path.join(VALIDACION, f"caso_{caso}.py"), run_name="__main__")
        print(texto.getvalue())
        with open(os.path.join(AQUI, "resultados", "validacion_directo", f"{caso}.txt"), "w", encoding="utf-8") as fh:
            fh.write(texto.getvalue())
    os.chdir(AQUI)
    shutil.rmtree(temporal)       # los JSON re-escritos ya estan en validacion/salidas: no se guardan dos veces


if __name__ == "__main__":
    partes = {"videos": capturas_videos, "resultados": capturas_resultados, "validacion": capturas_validacion}
    for p in sys.argv[1:] or list(partes):
        partes[p]()
