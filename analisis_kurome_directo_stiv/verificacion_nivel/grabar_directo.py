"""Graba el directo de una camara TAL COMO LLEGA (segmentos HLS de YouTube, sin recomprimir) durante N
minutos, y apunta la hora de cada segmento para poder cruzar la grabacion con el nivel del agua.

    python grabar_directo.py                       # myoshoji, 60 min
    python grabar_directo.py --minutos 120
    python grabar_directo.py --cookies cookies.txt # si YouTube pide "confirma que no eres un bot"
    python grabar_directo.py --cookies-navegador firefox

Salida en grabaciones/: <camara>_<AAAAMMDD_HHMM>JST.ts (el video), _segmentos.csv (secuencia, hora de
programa del segmento, duracion, bytes) y .json (resumen: inicio y fin en hora de Japon, huecos).
Sin recomprimir porque es exactamente lo que ve el programa en directo (~1-3 GB/h); en FFV1 serian
~70 GB/h. Python puro, sin ffmpeg: funciona igual en la Raspberry. Ctrl+C corta y deja todo cerrado.
"""
import argparse, csv, json, os, re, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

AQUI = os.path.dirname(os.path.abspath(__file__))
# los titulos de los directos estan en japones: la consola de Windows (cp1252) no los imprime
for _f in (sys.stdout, sys.stderr):
    _f.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(AQUI, ".."))
import stiv_directo as sd

JST = timezone(timedelta(hours=9))
CABECERAS = {"User-Agent": "Mozilla/5.0"}


def leer(url, timeout=30):
    return urllib.request.urlopen(urllib.request.Request(url, headers=CABECERAS), timeout=timeout).read()


def resolver(url_pagina, cookies=None, navegador=None):
    """URL HLS del directo (la misma eleccion de formato que stiv_directo.resolver_url), con cookies si
    hacen falta para pasar el aviso de bot de YouTube."""
    import yt_dlp
    op = {"quiet": True, "no_warnings": True,
          "format": f"bestvideo[height<={sd.ALTURA_MAX}]/best[height<={sd.ALTURA_MAX}]"}
    if cookies:
        op["cookiefile"] = cookies
    if navegador:
        op["cookiesfrombrowser"] = (navegador,)
    # Desde oct 2026 YouTube exige resolver un desafio en JavaScript para dar los formatos ("No video
    # formats found" / "The page needs to be reloaded"): yt-dlp necesita un interprete (deno) y el
    # paquete yt-dlp-ejs. El deno.exe va junto al python del .venv, que no esta en el PATH.
    deno = os.path.join(os.path.dirname(sys.executable), "deno.exe" if os.name == "nt" else "deno")
    if os.path.exists(deno):
        op["js_runtimes"] = {"deno": {"path": deno}}
    with yt_dlp.YoutubeDL(op) as y:
        info = y.extract_info(url_pagina, download=False)
    return info["url"], info.get("title", ""), info.get("live_status")


def lista(url):
    """Segmentos de la lista HLS: [(secuencia, url, duracion_s, hora_programa o None)], duracion objetivo."""
    txt = leer(url, 20).decode("utf-8", "replace")
    lineas = [l.strip() for l in txt.splitlines()]
    if any(l.startswith("#EXT-X-STREAM-INF") for l in lineas):
        # lista maestra: la variante mas alta que no pase de ALTURA_MAX
        variantes = []
        for i, l in enumerate(lineas):
            if l.startswith("#EXT-X-STREAM-INF"):
                m = re.search(r"RESOLUTION=\d+x(\d+)", l)
                variantes.append((int(m.group(1)) if m else 0, urljoin(url, lineas[i + 1])))
        validas = [v for v in variantes if v[0] <= sd.ALTURA_MAX] or variantes
        return lista(max(validas)[1])
    m = re.search(r"#EXT-X-MEDIA-SEQUENCE:(\d+)", txt)
    seq = int(m.group(1)) if m else 0
    m = re.search(r"#EXT-X-TARGETDURATION:(\d+)", txt)
    objetivo = float(m.group(1)) if m else 5.0
    segs, pdt, dur = [], None, None
    for l in lineas:
        if l.startswith("#EXT-X-PROGRAM-DATE-TIME:"):
            pdt = l.split(":", 1)[1]
        elif l.startswith("#EXTINF:"):
            dur = float(l[8:].split(",")[0])
        elif l and not l.startswith("#"):
            segs.append((seq, urljoin(url, l), dur, pdt))
            seq, pdt = seq + 1, None
    return segs, objetivo


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camara", default="myoshoji")
    ap.add_argument("--minutos", type=float, default=60.0)
    ap.add_argument("--cookies", help="cookies.txt exportado de un navegador con sesion en YouTube")
    ap.add_argument("--cookies-navegador", help="leer las cookies de este navegador (firefox, chrome, edge)")
    a = ap.parse_args()

    sd.elegir_camara(a.camara)
    url_hls, titulo, estado = resolver(sd.URL_FUENTE, a.cookies, a.cookies_navegador)
    print(f"{titulo} [{estado}]")
    carpeta = os.path.join(AQUI, "grabaciones")
    os.makedirs(carpeta, exist_ok=True)
    arranque = datetime.now(JST)
    base = os.path.join(carpeta, f"{a.camara}_{arranque:%Y%m%d_%H%M}JST")
    meta = {"camara": a.camara, "pagina": sd.URL_FUENTE, "titulo": titulo, "video": os.path.basename(base) + ".ts",
            "arranque_jst": arranque.isoformat(), "minutos_pedidos": a.minutos,
            "segmentos": 0, "segundos": 0.0, "bytes": 0, "huecos": [], "errores": 0}

    def guardar_meta():
        meta["fin_jst"] = datetime.now(JST).isoformat()
        with open(base + ".json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    fts = open(base + ".ts", "wb")
    fseg = open(base + "_segmentos.csv", "w", newline="", encoding="utf-8")
    w = csv.writer(fseg)
    w.writerow(["secuencia", "hora_programa", "duracion_s", "hora_descarga_jst", "bytes", "inicio_en_video_s"])
    fin = time.time() + a.minutos * 60
    ultimo, errores_seguidos, t_ult_aviso = None, 0, 0.0
    try:
        while time.time() < fin:
            try:
                segs, objetivo = lista(url_hls)
                errores_seguidos = 0
            except Exception as e:
                meta["errores"] += 1
                errores_seguidos += 1
                print(f"  lista HLS: {e}", file=sys.stderr)
                if errores_seguidos % 3 == 0:          # la URL caduca o el emisor se reinicio
                    try:
                        url_hls = resolver(sd.URL_FUENTE, a.cookies, a.cookies_navegador)[0]
                    except Exception as e2:
                        print(f"  no se pudo volver a resolver: {e2}", file=sys.stderr)
                time.sleep(5)
                continue
            if ultimo is None:
                segs = segs[-2:]                   # empezar por lo ultimo, no por la ventana de DVR
            nuevos = [s for s in segs if ultimo is None or s[0] > ultimo]
            if ultimo is not None and nuevos and nuevos[0][0] > ultimo + 1:
                meta["huecos"].append({"despues_de": ultimo, "perdidos": nuevos[0][0] - ultimo - 1,
                                       "en_video_s": round(meta["segundos"], 2)})
                print(f"  hueco: {nuevos[0][0] - ultimo - 1} segmentos perdidos", file=sys.stderr)
            for seq, u, dur, pdt in nuevos:
                datos = leer(u)
                fts.write(datos)
                w.writerow([seq, pdt or "", dur, datetime.now(JST).isoformat(timespec="seconds"), len(datos),
                            round(meta["segundos"], 3)])
                meta["segmentos"] += 1
                meta["segundos"] += dur or 0.0
                meta["bytes"] += len(datos)
                if meta.get("primer_programa") is None and pdt:
                    meta["primer_programa"] = pdt
                ultimo = seq
            fts.flush()
            fseg.flush()
            if time.time() - t_ult_aviso > 60:
                t_ult_aviso = time.time()
                guardar_meta()
                print(f"  {datetime.now(JST):%H:%M:%S} JST: {meta['segundos'] / 60:.1f} min grabados, "
                      f"{meta['bytes'] / 1e6:.0f} MB, {len(meta['huecos'])} huecos")
            time.sleep(max(1.0, objetivo / 2))
    except KeyboardInterrupt:
        print("cortado con Ctrl+C")
    finally:
        fts.close()
        fseg.close()
        guardar_meta()
    print(f"listo: {base}.ts, {meta['segundos'] / 60:.1f} min, {meta['bytes'] / 1e6:.0f} MB, "
          f"{len(meta['huecos'])} huecos")


if __name__ == "__main__":
    main()
