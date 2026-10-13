"""Monta el video ejecutivo de ISATECK: medicion de caudal con camaras, en ~40 s.

Que es
------
Tres bloques y nada mas:

    1. Portada: el titulo, con el hueco del logo libre.
    2. El video del canal, con numeros encima que dicen que es cada cosa.
    3. El video del arroyo, con numeros encima para la vista rectificada y el nivel.

Sin resultados, sin comparaciones, sin explicar el algoritmo. El guion esta en `guion.md`.

Que NO hace
-----------
No toca nada de lo que ya hay. Los dos `.mp4` de origen se abren en solo lectura, ningun
script ni notebook de los casos se modifica, y la salida va a `Escritorio/videos`.

Decisiones que no son de estilo
-------------------------------
* **El hueco del logo se deja vacio.** Si `logo_isateck.png` esta en esta carpeta se pega
  solo; si no, el sitio queda en blanco a proposito, para colocarlo despues por fuera. No
  se dibuja ningun texto de relleno que luego habria que tapar.
* **Los clips se recortan para quitar la jerga que llevan grabada** (cabeceras con
  parametros, leyendas tecnicas del pie). Se recorta por coordenadas de pixel; los videos
  originales quedan intactos.
* **Los textos se dibujan con Pillow y Segoe UI, no con `cv2.putText`**: las fuentes
  Hershey de OpenCV no tienen acentos.
* **Los clips van a velocidad real.** Los origenes son de 30,02 y 24,20 fps y el lienzo va
  a 30: para cada fotograma de salida se toma el de origen mas cercano EN EL TIEMPO.
* La codificacion la hace `escritor_video.abrir` del caso Boneyard, que manda los
  fotogramas por tuberia a `RIVeR-STIV_1.0/ffmpeg.exe` con libx264. Se importa, no se
  copia. Sale H.264 + yuv420p + faststart, que es lo que se puede compartir.

Uso
---
    python video_ejecutivo\\montar_demo.py              # montaje completo
    python video_ejecutivo\\montar_demo.py --previo     # 1 PNG por bloque, sin codificar
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parent.parent
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "analisis_boneyard_stiv"))
from escritor_video import abrir as abrir_video          # noqa: E402

VIDEO_CANAL = RAIZ / "analisis_USGS_SMC_stiv" / "salidas" / "video_velocimetria.mp4"
VIDEO_ARROYO = RAIZ / "analisis_boneyard_stiv" / "salidas" / "velocidad_nivel_curva.mp4"
CONFIG_ARROYO = RAIZ / "analisis_boneyard_stiv" / "salidas" / "config_stiv_manual.json"
LOGO = AQUI / "logo_isateck.png"

SALIDA = Path.home() / "Desktop" / "videos" / "ISATECK_medicion_de_caudal.mp4"
DIR_PREVIO = AQUI / "previo"

# ===========================================================================================
#  >>> AJUSTABLE <<<  Formato y montaje
# ===========================================================================================
ANCHO, ALTO, FPS = 1920, 1080, 30
CRF = 18

DUR_PORTADA = 5.0
T0_CANAL, DUR_CANAL = 3.0, 17.0     # segundo de arranque y duracion de cada clip
T0_ARROYO, DUR_ARROYO = 8.0, 16.0
FUNDIDO_FINAL = 0.6                 # salida a blanco, para no cortar en seco

# Recortes en pixeles del video de origen.
#   Canal 1920x844: cabecera 0-45, imagen 46-747, pie 748-843. Del pie solo interesa la
#   primera linea (reloj, velocidad y caudal), que acaba hacia la fila 796; las dos
#   siguientes son leyenda tecnica.
RECORTE_CANAL = (0, 46, 1920, 798)
#   Arroyo 1442x586: se quitan los bordes negros, la fila de parametros de arriba y la
#   etiqueta "mira_rectificada". Se conservan LOS DOS paneles, porque la vista rectificada
#   es una de las cosas que se quiere ensenar.
RECORTE_ARROYO = (18, 60, 1424, 573)

# ===========================================================================================
#  Marca: verde y blanco
# ===========================================================================================
BLANCO = (255, 255, 255)
VERDE = (23, 122, 31)
VERDE_OSC = (11, 79, 19)
TEXTO = (28, 38, 30)
TENUE = (106, 121, 109)
BORDE = (203, 222, 205)
AVISO = (186, 196, 188)       # gris claro, para el aviso sobre la franja negra del video
GCP = (255, 193, 37)          # ambar para los puntos de apoyo: el verde ya es de los numeros

# El aviso que va encima de la franja negra de los dos clips, con su posicion en pixeles
# del FOTOGRAMA YA ESCALADO de cada uno (la franja negra es parte del video de origen).
#   El texto es corto porque en el arroyo solo hay un hueco de ~450 px entre las cifras del
#   pie y la barra de color; uno mas largo se monta encima de una de las dos.
AVISO_TEXTO = "Vídeo preprocesado, no en directo"
AVISO_CANAL = None
AVISO_ARROYO = None

# Geometria con la que `velocidad_nivel_curva.py` compuso el video del arroyo: cada panel es
# el fotograma escalado a 500 px de alto, tras un hueco de 18 px y bajo una cabecera de 34.
# El fotograma de la camara es de 1280x720, y eso se comprueba solo: con esa altura el panel
# sale de 888 px de ancho, que es exactamente lo que mide en el video montado.
BNY_HUECO, BNY_CABECERA, BNY_PANEL = 18, 34, 500
BNY_ORIGINAL = (1280, 720)

MARGEN = 100
ALTO_BARRA = 96
HUECO_LOGO = (MARGEN, 20, 340, 56)      # x, y, ancho maximo, alto: el sitio del logo

ANCHO_VIDEO = 1720
Y_VIDEO = 132

_FUENTES = {
    "bold": ["seguibl.ttf", "seguisb.ttf", "arialbd.ttf"],
    "semi": ["seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"],
    "reg": ["segoeui.ttf", "arial.ttf"],
    "light": ["segoeuil.ttf", "segoeui.ttf", "arial.ttf"],
}


def fuente(estilo, px):
    for nombre in _FUENTES[estilo]:
        ruta = Path("C:/Windows/Fonts") / nombre
        if ruta.exists():
            return ImageFont.truetype(str(ruta), px)
    return ImageFont.load_default()


def cargar_logo():
    """El logo recortado a su contenido, o None si todavia no esta puesto.

    Se recorta el margen porque la version cuadrada trae mucho blanco alrededor y dentro
    de la barra el nombre quedaria diminuto.
    """
    if not LOGO.exists():
        return None
    img = Image.open(LOGO)
    if img.mode == "RGBA":
        caja = img.split()[3].getbbox()
    else:
        img = img.convert("RGB")
        ys, xs = np.where(np.array(img.convert("L")) < 245)
        caja = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1) if len(xs) else None
    return img.crop(caja) if caja else img


# ===========================================================================================
#  Lienzo
# ===========================================================================================
class Lienzo:
    def __init__(self):
        self.img = Image.new("RGB", (ANCHO, ALTO), BLANCO)
        self.d = ImageDraw.Draw(self.img)

    def bgr(self):
        return np.ascontiguousarray(np.array(self.img)[:, :, ::-1])

    def pegar(self, bgr, x, y):
        self.img.paste(Image.fromarray(bgr[:, :, ::-1]), (int(x), int(y)))

    def logo_en(self, logo, x, y, alto, centrado=False):
        """Pega el logo ajustado a una altura. Si no hay logo, deja el hueco vacio."""
        if logo is None:
            return
        w = int(logo.width * alto / logo.height)
        im = logo.resize((w, alto), Image.LANCZOS)
        self.img.paste(im, (int(x - w // 2) if centrado else int(x), int(y)),
                       im if im.mode == "RGBA" else None)

    def txt(self, xy, s, f, color=TEXTO, anchor="la"):
        self.d.text(xy, s, font=f, fill=color, anchor=anchor)

    def regla(self, x0, y, x1, color=BORDE, grosor=2):
        self.d.rectangle([x0, y, x1, y + grosor - 1], fill=color)

    def barra(self, logo):
        """Barra superior: solo el hueco del logo y una linea verde. Nada mas."""
        x, y, _, h = HUECO_LOGO
        self.logo_en(logo, x, y, h)
        self.regla(0, ALTO_BARRA, ANCHO, VERDE, 5)
        return self

    def leyenda(self, textos, y):
        """La lista numerada debajo del video. Va en el fondo: ahi no pisa nada."""
        for i, s in enumerate(textos, 1):
            self.d.ellipse([MARGEN, y, MARGEN + 42, y + 42], fill=VERDE)
            self.txt((MARGEN + 21, y + 20), str(i), fuente("bold", 25), BLANCO, anchor="mm")
            self.txt((MARGEN + 66, y + 2), s, fuente("reg", 34), TEXTO)
            y += 60


def capa_numeros(marcas, esc, tam, nota=None, poligonos=()):
    """Los circulos numerados, los puntos de apoyo y el aviso, como capa aparte.

    Tienen que aplicarse despues de pegar cada fotograma, no dibujarse en el fondo: el
    clip se pega sobre esa misma zona en cada fotograma y los borraria.
    """
    w, h = tam
    capa = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    for pts, vertices in poligonos:
        p = [(int(round(x * esc)), int(round(y * esc))) for x, y in pts]
        d.line(p + [p[0]], fill=GCP + (255,), width=3, joint="curve")
        for cx, cy in (p if vertices else []):
            d.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=GCP + (255,),
                      outline=BLANCO + (255,), width=3)
    for i, (mx, my) in enumerate(marcas, 1):
        cx, cy = int(mx * esc), int(my * esc)
        d.ellipse([cx - 24, cy - 24, cx + 24, cy + 24], fill=VERDE + (255,),
                  outline=BLANCO + (255,), width=4)
        d.text((cx, cy - 1), str(i), font=fuente("bold", 28), fill=BLANCO + (255,),
               anchor="mm")
    if nota:
        # Va sobre la franja negra que ya trae el video, en gris claro: se lee sin competir
        # con las cifras que hay al lado.
        texto, (nx, ny), anchor = nota
        d.text((nx, ny), texto, font=fuente("reg", 25), fill=AVISO + (255,), anchor=anchor)
    arr = np.array(capa)
    alfa = (arr[:, :, 3:4].astype(np.float32) / 255.0)
    return np.ascontiguousarray(arr[:, :, 2::-1]).astype(np.float32), alfa


# ===========================================================================================
#  Bloques
# ===========================================================================================
def portada(logo):
    L = Lienzo()
    # El logo va centrado arriba; si no esta el archivo, este hueco queda en blanco a
    # proposito para colocarlo despues.
    L.logo_en(logo, ANCHO // 2, 210, 190, centrado=True)
    L.regla(ANCHO // 2 - 90, 470, ANCHO // 2 + 90, VERDE, 6)
    L.txt((ANCHO // 2, 540), "Medición de caudal", fuente("bold", 96), VERDE_OSC, anchor="ma")
    L.txt((ANCHO // 2, 660), "con cámaras, sin contacto", fuente("bold", 96), VERDE,
          anchor="ma")
    return L.bgr()


def marco_clip(logo, fr_muestra, marcas, textos, nota, poligonos=()):
    """El fondo fijo del bloque de video: barra, marco del clip y leyenda, mas la capa
    de numeros, puntos de apoyo y aviso que se aplica encima de cada fotograma."""
    h = int(round(ANCHO_VIDEO * fr_muestra.shape[0] / fr_muestra.shape[1]))
    x, y = (ANCHO - ANCHO_VIDEO) // 2, Y_VIDEO
    L = Lienzo().barra(logo)
    L.d.rectangle([x - 3, y - 3, x + ANCHO_VIDEO + 2, y + h + 2], outline=BORDE, width=3)
    L.leyenda(textos, y + h + 40)
    capa = capa_numeros(marcas, ANCHO_VIDEO / fr_muestra.shape[1], (ANCHO_VIDEO, h),
                        nota, poligonos)
    return L.bgr(), (x, y), (ANCHO_VIDEO, h), capa


def geometria_arroyo():
    """Los cuatro puntos de apoyo del arroyo y el rectangulo en que se convierten.

    Salen de `config_stiv_manual.json`, que los guarda en pixeles del video original de la
    camara. Aqui se les aplica la misma composicion con la que se monto el video (panel
    escalado, hueco, cabecera) y despues el recorte de esta pieza, de modo que caen justo
    encima de donde se ven. En la vista rectificada esos mismos cuatro puntos son, por
    construccion, un rectangulo: dibujarlo al lado es lo que ensena que rectificar es
    mandar el cuadrilatero a un rectangulo.
    """
    cfg = json.loads(CONFIG_ARROYO.read_text(encoding="utf-8"))
    rx, ry = RECORTE_ARROYO[0], RECORTE_ARROYO[1]
    eo = BNY_PANEL / BNY_ORIGINAL[1]
    quad = [(BNY_HUECO + x * eo - rx, BNY_CABECERA + y * eo - ry)
            for x, y in cfg["cuadrilatero"]]

    an, la = cfg["ancho_real"] * cfg["esc"], cfg["largo_real"] * cfg["esc"]
    mx, my = cfg["margen"] * an, cfg["margen"] * la
    er = BNY_PANEL / (la + 2 * my)
    x_r = BNY_HUECO + int(BNY_ORIGINAL[0] * eo) + BNY_HUECO
    rect = [(x_r + px * er - rx, BNY_CABECERA + py * er - ry)
            for px, py in [(mx, my), (mx + an, my), (mx + an, my + la), (mx, my + la)]]
    return quad, rect


class Clip:
    """Un trozo de video, recortado y remuestreado al ritmo del lienzo.

    Se lee en secuencia y para cada fotograma de salida se avanza hasta el de origen mas
    cercano en el tiempo, de modo que la duracion real se conserva aunque los fps no
    coincidan: el reloj que llevan grabado los videos sigue siendo cierto.
    """

    def __init__(self, ruta, t0, recorte, marco, xy, tam, capa):
        self.cap = cv2.VideoCapture(str(ruta))
        if not self.cap.isOpened():
            raise SystemExit(f"No se pudo abrir {ruta}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.i0 = int(round(t0 * self.fps))
        self.recorte, self.marco, self.xy, self.tam = recorte, marco, xy, tam
        self.capa_bgr, self.capa_alfa = capa
        self.idx, self.fr = -1, None

    def __call__(self, i):
        objetivo = self.i0 + int(round(i / FPS * self.fps))
        while self.idx < objetivo:
            ok, fr = self.cap.read()
            if not ok:
                break
            self.idx += 1
            self.fr = fr
        salida = self.marco.copy()
        if self.fr is not None:
            x0, y0, x1, y1 = self.recorte
            fr = cv2.resize(self.fr[y0:y1, x0:x1], self.tam,
                            interpolation=cv2.INTER_AREA).astype(np.float32)
            fr = fr * (1 - self.capa_alfa) + self.capa_bgr * self.capa_alfa
            x, y = self.xy
            salida[y:y + self.tam[1], x:x + self.tam[0]] = fr.astype(np.uint8)
        return salida


def fotograma(ruta, t, recorte):
    cap = cv2.VideoCapture(str(ruta))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * fps)))
    ok, fr = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"No se pudo leer un fotograma de {ruta}")
    x0, y0, x1, y1 = recorte
    return fr[y0:y1, x0:x1]


# ===========================================================================================
#  Montaje
# ===========================================================================================
def construir(logo):
    fr_canal = fotograma(VIDEO_CANAL, 10.0, RECORTE_CANAL)
    fr_arroyo = fotograma(VIDEO_ARROYO, 18.0, RECORTE_ARROYO)

    # Coordenadas en pixeles del fotograma YA recortado de cada caso.
    marco_c, xy_c, tam_c, capa_c = marco_clip(
        logo, fr_canal,
        [(425, 215), (748, 357), (950, 715)],
        ["Puntos de medición, repartidos de orilla a orilla",
         "Velocidad del agua en cada punto, en metros por segundo",
         "Velocidad media y caudal, actualizados en vivo"],
        AVISO_CANAL)
    quad, rect = geometria_arroyo()
    marco_a, xy_a, tam_a, capa_a = marco_clip(
        logo, fr_arroyo,
        [(400, 400), (830, 250), (1150, 274), (90, 292)],
        ["La imagen de la cámara",
         "Los cuatro puntos de referencia (GCP) con los que se rectifica",
         "Vista de la cámara rectificada, se simula una visión desde arriba del agua",
         "El nivel del agua, leído a partir del pluviómetro"],
        AVISO_ARROYO, [(quad, True), (rect, False)])

    clip_c = Clip(VIDEO_CANAL, T0_CANAL, RECORTE_CANAL, marco_c, xy_c, tam_c, capa_c)
    clip_a = Clip(VIDEO_ARROYO, T0_ARROYO, RECORTE_ARROYO, marco_a, xy_a, tam_a, capa_a)

    port = portada(logo)
    return [
        ("01_portada", DUR_PORTADA, lambda i: port),
        ("02_canal", DUR_CANAL, clip_c),
        ("03_arroyo", DUR_ARROYO, clip_a),
    ]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--previo", action="store_true",
                    help="escribe un PNG por bloque en previo/ y no codifica nada")
    ap.add_argument("--salida", default=str(SALIDA))
    a = ap.parse_args()

    for r in (VIDEO_CANAL, VIDEO_ARROYO):
        print(f"{'OK  ' if r.exists() else 'FALTA'}  {r}")
        if not r.exists():
            raise SystemExit("Falta material de origen.")
    logo = cargar_logo()
    print(f"{'OK  ' if logo else 'SIN '}  {LOGO}"
          + ("" if logo else "   <-- el hueco queda en blanco; deja aqui el PNG"))

    bloques = construir(logo)
    total = sum(int(round(s * FPS)) for _, s, _ in bloques)
    print(f"\n{len(bloques)} bloques, {total} fotogramas, {total/FPS:.1f} s\n")

    if a.previo:
        DIR_PREVIO.mkdir(exist_ok=True)
        for viejo in DIR_PREVIO.glob("*.png"):
            viejo.unlink()
        for nombre, seg, gen in bloques:
            cv2.imwrite(str(DIR_PREVIO / f"{nombre}.png"), gen(int(round(seg * FPS)) // 2))
            print(f"  {nombre}.png")
        print(f"\nPrevisualizacion en {DIR_PREVIO}")
        return

    Path(a.salida).parent.mkdir(parents=True, exist_ok=True)
    vw = abrir_video(a.salida, FPS, (ANCHO, ALTO), crf=CRF)
    t0 = time.perf_counter()
    blanco = np.full((ALTO, ANCHO, 3), 255, np.uint8)
    n_fin = int(round(FUNDIDO_FINAL * FPS))
    hechos = 0
    for b, (nombre, seg, gen) in enumerate(bloques):
        n = int(round(seg * FPS))
        ultimo = b == len(bloques) - 1
        for i in range(n):
            fr = gen(i)
            # Solo dos fundidos en toda la pieza: la entrada desde blanco y la salida.
            if b == 0 and i < n_fin:
                fr = cv2.addWeighted(blanco, 1 - (i + 1) / n_fin, fr, (i + 1) / n_fin, 0)
            elif ultimo and i >= n - n_fin:
                p = (n - i) / n_fin
                fr = cv2.addWeighted(blanco, 1 - p, fr, p, 0)
            vw.write(fr)
            hechos += 1
        print(f"  {nombre:14s} {n:4d} fotogramas   ({hechos/total:4.0%})")
    vw.release()

    mb = Path(a.salida).stat().st_size / 1e6
    print(f"\nListo: {a.salida}")
    print(f"  {total} fotogramas, {total/FPS:.1f} s, {mb:.1f} MB, "
          f"montado en {time.perf_counter()-t0:.1f} s")


if __name__ == "__main__":
    main()
