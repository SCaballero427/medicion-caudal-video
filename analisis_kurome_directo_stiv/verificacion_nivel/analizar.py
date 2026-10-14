"""Mide una grabacion de grabar_directo.py con el codigo del programa en directo y la cruza con el nivel
del agua que publica el Gobierno de Tokio para la estacion de la misma camara (上高田上 en el Myoshoji).

    python analizar.py grabaciones/myoshoji_20261014_1530JST.ts
    python analizar.py <video.ts> --paso 5 --v-esperada 1.0     # en crecida: el agua va mucho mas rapido

Nivel: primero el CSV diario del archivo historico (Tokyo_Suii_AAAAMMDD.csv, cada 10 min, en cm; aparece
al dia siguiente); si aun no esta, la tabla de 10 min de la pagina de la estacion (las ultimas 4 h).
Salidas en salidas/: <base>_medidas.csv (cada medida), <base>_10min.csv (velocidad y nivel por tramo de
10 min) y <base>_grafica.png.

Lo que esto valida y lo que no: el nivel no es velocidad. Sirve para ver si la velocidad sigue al nivel
(sube y baja con el, con forma razonable). Los m/s no se pueden comprobar: la pagina no da caudal ni
cota del fondo, y el largo de la escala del Myoshoji es supuesto. Con tiempo seco el nivel se mueve
1-2 cm y no hay nada que comparar.
"""
import argparse, csv, json, os, re, sys, urllib.request
from datetime import datetime, timedelta, timezone
import numpy as np, cv2

AQUI = os.path.dirname(os.path.abspath(__file__))
# los titulos de los directos estan en japones: la consola de Windows (cp1252) no los imprime
for _f in (sys.stdout, sys.stderr):
    _f.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(AQUI, "..", "validacion"))
import correr
sd = correr.sd

JST = timezone(timedelta(hours=9))
# estacion de nivel de cada camara en el sistema de Tokio (nombre en el CSV, codigo de la pagina)
ESTACIONES = {"myoshoji": ("上高田上", "222013")}
WEB = "https://www.kasen-suibo.metro.tokyo.lg.jp/im"
MIN_ESTACIONES = 3          # estaciones aceptadas para que una medida cuente como de seccion


def leer(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                                  timeout=30).read()


def nivel_csv(estacion, dia):
    """{hora JST: nivel en m} del CSV diario, o None si aun no esta publicado."""
    try:
        txt = leer(f"{WEB}/other/Tokyo_Suii_{dia:%Y%m%d}.csv").decode("shift_jis", "replace")
    except Exception:
        return None
    out = {}
    for fila in csv.reader(txt.splitlines()):
        if len(fila) >= 3 and fila[1] == estacion and fila[2].strip().lstrip("-").isdigit():
            h, m = map(int, fila[0].split(":"))
            # "24:00" seria el cierre del dia; las horas son las de la etiqueta del tramo
            out[datetime(dia.year, dia.month, dia.day, tzinfo=JST) + timedelta(hours=h, minutes=m)] = int(fila[2]) / 100
    return out or None


def nivel_pagina(codigo, tabla="data10m_suii"):
    """{hora JST: nivel en m} de una tabla de la pagina: data10m_suii (cada 10 min, ultimas 4 h) o
    data1h_suii (cada hora, ultimas 24 h)."""
    html = leer(f"{WEB}/uryosuii/tsim0105g_{codigo}.html").decode("utf-8", "replace")
    ahora = re.search(r"(\d{4})/(\d{2})/(\d{2}) (\d{2}):(\d{2}) 時点", html)
    tabla = re.search(rf'id="{tabla}".*?</table>', html, re.S).group(0)
    filas = re.findall(r"<tr>(.*?)</tr>", tabla, re.S)
    horas = re.findall(r"<td>\s*(\d{1,2}:\d{2})\s*</td>", filas[0])
    valores = [re.sub(r"<.*?>", "", v).strip() for v in re.findall(r"<td[^>]*>(.*?)</td>", filas[1], re.S)]
    y, mo, d, hh, mm = map(int, ahora.groups())
    ref = datetime(y, mo, d, hh, mm, tzinfo=JST)
    out = {}
    for h, v in zip(horas, valores):
        hh2, mm2 = map(int, h.split(":"))
        t = ref.replace(hour=hh2 % 24, minute=mm2)
        if t > ref + timedelta(minutes=5):         # la tabla cruza la medianoche
            t -= timedelta(days=1)
        try:
            out[t] = float(v)
        except ValueError:
            pass
    return out


def a_hora_real(t_video, segmentos, t0):
    """Hora JST de un instante del video, siguiendo los segmentos (salta los huecos de la grabacion)."""
    i = np.searchsorted(segmentos[:, 0], t_video, side="right") - 1
    i = max(i, 0)
    return t0 + timedelta(seconds=float(segmentos[i, 1] + (t_video - segmentos[i, 0])))


def grafica(ruta, tramos, titulo):
    """Dos paneles (nivel arriba, velocidad abajo) con OpenCV: el .venv no tiene matplotlib."""
    W, H, M = 1200, 700, 80
    img = np.full((H, W, 3), 255, np.uint8)
    ts = [t for t, *_ in tramos]
    t0, t1 = ts[0], ts[-1] + timedelta(minutes=1)
    x = lambda t: int(M + (W - 2 * M) * (t - t0).total_seconds() / max((t1 - t0).total_seconds(), 1))
    # un tramo de velocidad con menos de la mitad de medidas validas se dibuja hueco y sin unir: es un
    # valor de pocas medidas (al anochecer, 4 de 120) y no debe parecer igual de firme que uno de 120
    firme = [r[6] > 0 and r[5] >= 0.5 * r[6] for r in tramos]
    paneles = [("nivel (m)", [r[1] for r in tramos], (200, 90, 0), 60, 320, [True] * len(tramos)),
               ("velocidad superficial (m/s, escala supuesta; hueco = menos de la mitad de medidas validas)",
                [r[2] for r in tramos], (0, 120, 230), 380, 640, firme)]
    for nombre, vals, color, y0, y1, solido in paneles:
        v = np.array([np.nan if a is None else a for a in vals], float)
        cv2.rectangle(img, (M, y0), (W - M, y1), (180, 180, 180), 1)
        cv2.putText(img, nombre, (M, y0 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
        if not np.isfinite(v).any():
            cv2.putText(img, "sin datos", (W // 2 - 50, (y0 + y1) // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 200), 2)
            continue
        lo, hi = np.nanmin(v), np.nanmax(v)
        pad = max((hi - lo) * 0.2, 0.02 if nombre.startswith("nivel") else 0.05)
        lo, hi = lo - pad, hi + pad
        y = lambda a: int(y1 - (y1 - y0) * (a - lo) / (hi - lo))
        for k in range(5):
            a = lo + (hi - lo) * k / 4
            cv2.putText(img, f"{a:.2f}", (8, y(a) + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (90, 90, 90), 1, cv2.LINE_AA)
            cv2.line(img, (M, y(a)), (W - M, y(a)), (235, 235, 235), 1)
        # solo se unen tramos seguidos: una linea por encima de un tramo sin medida dibujaria algo no medido
        pts = [(x(t), y(a)) if np.isfinite(a) else None for t, a in zip(ts, v)]
        for p, q, sp, sq in zip(pts, pts[1:], solido, solido[1:]):
            if p and q and sp and sq:
                cv2.line(img, p, q, color, 2, cv2.LINE_AA)
        for p, sp in zip(pts, solido):
            if p:
                cv2.circle(img, p, 4 if sp else 5, color, -1 if sp else 2, cv2.LINE_AA)
    for t in ts:
        cv2.putText(img, f"{t:%H:%M}", (x(t) - 20, H - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.putText(img, titulo, (M, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.imwrite(ruta, img)


def medir_grabacion(video, a):
    """Mide una grabacion (o lee sus medidas ya guardadas con --reusar). Devuelve (meta, filas) con una fila
    por medida: (hora JST, t en el video, estaciones aceptadas, v mediana de seccion o None, por motas, modo)."""
    base = os.path.splitext(os.path.abspath(video))[0]
    with open(base + ".json", encoding="utf-8") as f:
        meta = json.load(f)
    seg = list(csv.DictReader(open(base + "_segmentos.csv", encoding="utf-8")))
    # hora real del inicio de cada segmento: la del programa (EXT-X-PROGRAM-DATE-TIME) si viene; si no,
    # la de descarga menos lo ya grabado (aproximada, con el retraso del directo, ~10 s)
    if seg and seg[0]["hora_programa"]:
        t0 = datetime.fromisoformat(seg[0]["hora_programa"].replace("Z", "+00:00")).astimezone(JST)
        reales = [(datetime.fromisoformat(s["hora_programa"].replace("Z", "+00:00")).astimezone(JST) - t0).total_seconds()
                  for s in seg]
        fuente_hora = "hora de programa de los segmentos"
    else:
        t0 = datetime.fromisoformat(seg[0]["hora_descarga_jst"])
        reales = [(datetime.fromisoformat(s["hora_descarga_jst"]) - t0).total_seconds() for s in seg]
        fuente_hora = "hora de descarga (aproximada)"
    segmentos = np.array([[float(s["inicio_en_video_s"]), r] for s, r in zip(seg, reales)])
    huecos = [h["en_video_s"] for h in meta.get("huecos", [])]
    print(f"{meta['video']}: {meta['segundos'] / 60:.1f} min, {len(huecos)} huecos; hora: {fuente_hora}")

    os.makedirs(os.path.join(AQUI, "salidas"), exist_ok=True)
    # con el modo forzado las medidas van a otro archivo, para no pisar las del modo automatico
    nombre = os.path.join(AQUI, "salidas", os.path.basename(base) + ("" if a.modo == "auto" else f"_{a.modo}"))
    filas = []
    if a.reusar and os.path.exists(nombre + "_medidas.csv"):
        for r in csv.DictReader(open(nombre + "_medidas.csv", encoding="utf-8")):
            filas.append((datetime.fromisoformat(r["hora_jst"]), float(r["t_video_s"]), int(r["estaciones_aceptadas"]),
                          float(r["v_mediana_seccion_ms"]) if r["v_mediana_seccion_ms"] else None, int(r["por_motas"]),
                          r.get("modo", "")))
        print(f"  {len(filas)} medidas de {os.path.basename(nombre)}_medidas.csv")
        return meta, filas
    sd.PASO_MEDIDA_S = a.paso
    ajustes = {"v_esperada": a.v_esperada} if a.v_esperada else None
    geom, medidas = correr.correr_camara(video, meta["camara"], modo=a.modo, ajustes=ajustes)
    for t, res in medidas:
        # tras un hueco el STI mezcla dos momentos durante una ventana: esas medidas no cuentan
        if any(0 <= t - h < sd.VENTANA_S for h in huecos):
            continue
        v = [r["v"] for r in res if r["aceptada"]]
        filas.append((a_hora_real(t, segmentos, t0), t, len(v), float(np.median(v)) if len(v) >= MIN_ESTACIONES else None,
                      sum(r["motas"] for r in res if r["aceptada"]), res[0]["modo"]))
    with open(nombre + "_medidas.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["hora_jst", "t_video_s", "estaciones_aceptadas", "v_mediana_seccion_ms", "por_motas", "modo"])
        for h, t, n, v, mo, modo in filas:
            w.writerow([h.isoformat(timespec="seconds"), round(t, 2), n, "" if v is None else round(v, 4), mo, modo])
    return meta, filas


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("videos", nargs="+", help="una o varias grabaciones de la misma camara: se analizan juntas")
    ap.add_argument("--paso", type=float, default=5.0,
                    help="segundos entre medidas (el directo mide cada 1 s; 5 da lo mismo por tramo y tarda 5 veces menos)")
    ap.add_argument("--v-esperada", type=float, help="velocidad esperada de la camara (en crecida, mas alta)")
    ap.add_argument("--reusar", action="store_true",
                    help="no volver a medir las grabaciones que ya tengan salidas/<base>_medidas.csv; solo volver a "
                         "bajar el nivel (se publica con ~15 min de retraso)")
    ap.add_argument("--modo", choices=("auto", "dia", "noche"), default="auto",
                    help="auto como el programa (noche = camara en infrarrojo, saturacion ~0); forzarlo sirve "
                         "para la noche en color con farolas, que el automatico toma por dia")
    a = ap.parse_args()

    metas, filas = [], []
    for video in a.videos:
        meta, f = medir_grabacion(video, a)
        metas.append(meta)
        filas += f
    camaras = {m["camara"] for m in metas}
    if len(camaras) > 1:
        sys.exit(f"grabaciones de camaras distintas: {camaras}")
    camara = camaras.pop()
    filas.sort(key=lambda r: r[0])
    bases = [os.path.splitext(m["video"])[0] for m in metas]
    nombre = os.path.join(AQUI, "salidas", bases[0] if len(bases) == 1 else
                          f"{bases[0]}_a_{bases[-1].split('_')[-1]}") + ("" if a.modo == "auto" else f"_{a.modo}")

    # nivel: CSV diario de cada dia que toca la grabacion; si falta, la tabla de la pagina
    estacion, codigo = ESTACIONES[camara]
    nivel, fuente_nivel = {}, set()
    for dia in sorted({r[0].date() for r in filas}):
        n = nivel_csv(estacion, dia)
        if n:
            nivel.update(n)
            fuente_nivel.add("CSV diario")
    t_ini, t_fin = filas[0][0], filas[-1][0]
    if not nivel:
        nivel = nivel_pagina(codigo)
        fuente_nivel.add("pagina, cada 10 min (ultimas 4 h)")
        if min(nivel) > t_ini:
            # la grabacion empieza antes de lo que cubre la tabla de 10 min: la horaria (24 h, un valor a
            # las :20 de cada hora) interpolada a 10 min. Solo hasta que salga el CSV diario
            horario = nivel_pagina(codigo, "data1h_suii")
            th = sorted(horario)
            if th and th[0] <= t_ini:
                ref = th[0]
                rejilla = [t_ini.replace(minute=t_ini.minute // 10 * 10, second=0, microsecond=0) + timedelta(minutes=10 * k)
                           for k in range(int((t_fin - t_ini).total_seconds() // 600) + 3)]
                seg = lambda t: (t - ref).total_seconds()
                valores = np.interp([seg(t) for t in rejilla], [seg(t) for t in th], [horario[t] for t in th])
                nivel = {t: round(float(v), 3) for t, v in zip(rejilla, valores) if t not in nivel} | nivel
                fuente_nivel = {"pagina, horaria interpolada a 10 min (aun no esta el CSV diario)"}

    # tramos de 10 min con la etiqueta de la hora de nivel: (T - 10 min, T]. Todos los del intervalo
    # grabado, tambien los que caen entre dos grabaciones (sin velocidad): el nivel si se midio
    tramos = []
    for T in sorted(nivel):
        if not filas or T <= filas[0][0] or T - timedelta(minutes=10) > filas[-1][0]:
            continue
        en = [r for r in filas if T - timedelta(minutes=10) < r[0] <= T]
        vs = [r[3] for r in en if r[3] is not None]
        modos = {r[5] for r in en if r[5]}
        modo = "" if not modos else (modos.pop() if len(modos) == 1 else "mixto")
        tramos.append((T, nivel[T], float(np.median(vs)) if vs else None,
                       float(np.percentile(vs, 25)) if vs else None, float(np.percentile(vs, 75)) if vs else None,
                       len(vs), len(en), modo))
    with open(nombre + "_10min.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["hora_jst", "nivel_m", "v_mediana_ms", "v_q25", "v_q75", "medidas_validas", "medidas", "modo"])
        for r in tramos:
            w.writerow([r[0].strftime("%Y-%m-%d %H:%M")] + ["" if x is None else round(x, 4) for x in r[1:5]] + list(r[5:]))

    print(f"\nnivel: {', '.join(sorted(fuente_nivel))} (estacion {estacion})")
    if not any(r[6] for r in tramos):
        print(f"ningun tramo de nivel cubre la grabacion ({filas[0][0]:%H:%M}-{filas[-1][0]:%H:%M} JST; ultimo nivel "
              f"publicado {max(nivel):%H:%M} JST): la pagina publica cada 10 min, volver a correrlo mas tarde")
        return
    print("hora JST  nivel(m)  v mediana (m/s)  [q25-q75]  medidas validas  modo")
    for T, nv, v, q1, q3, n, nt, modo in tramos:
        print(f"  {T:%H:%M}   {nv:.2f}     " + (f"{v:.3f}  [{q1:.3f}-{q3:.3f}]" if v is not None else "  --                 ")
              + f"   {n}/{nt}" + (f"   {modo}" if nt else "   (sin grabacion)"))
    ok = [(r[1], r[2]) for r in tramos if r[2] is not None]
    if len(ok) >= 4:
        nv, v = np.array(ok).T
        rango = 100 * (nv.max() - nv.min())
        r = np.corrcoef(nv, v)[0, 1] if nv.std() > 0 and v.std() > 0 else float("nan")
        print(f"\nnivel: rango {rango:.0f} cm; velocidad: {v.min():.3f}-{v.max():.3f} m/s; correlacion {r:+.2f}")
        if rango < 5:
            print("  el nivel apenas se mueve: la correlacion no significa nada (hace falta lluvia)")
    for modo in ("dia", "noche"):
        vs = [r[3] for r in filas if r[5] == modo and r[3] is not None]
        if vs:
            print(f"  modo {modo}: {len(vs)} medidas, mediana {np.median(vs):.3f} m/s")
    grafica(nombre + "_grafica.png", tramos,
            f"{', '.join(m['video'] for m in metas)} (hora de Japon) | nivel {estacion} | velocidad con escala supuesta")
    print(f"\n{nombre}_10min.csv, _grafica.png (y un _medidas.csv por grabacion)")


if __name__ == "__main__":
    main()
