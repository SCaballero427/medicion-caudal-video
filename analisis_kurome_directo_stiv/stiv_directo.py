"""STIV en tiempo real sobre directos de YouTube de camaras de vigilancia de rios de Tokio.

Camaras preparadas (`--camara`, por defecto myoshoji):
    myoshoji  rio Myoshoji en Kamitakada (Nakano)          youtube.com/watch?v=huAp4q7lxiQ
    kurome    rio Kurome en el puente Koma (Higashikurume) youtube.com/watch?v=loW9744B-Co
    shimoda   rio Kurome en el puente Shimoda (Higashikurume) youtube.com/watch?v=bpL7MAbdoI8
    akigawa   rio Aki en Todohara (Akiruno)                youtube.com/watch?v=ZRUh9gNk8-g

Al arrancar resuelve el flujo HLS del directo con yt-dlp, lo abre con OpenCV y empieza a medir
inmediatamente: cada fotograma se muestrea a lo largo de las lineas de busqueda, las filas se apilan
en un STI deslizante por estacion y cada PASO_MEDIDA segundos se recalcula la velocidad superficial
con el tensor de estructura. pyorc no se importa en ningun momento.

    python stiv_directo.py                    # directo, con ventana
    python stiv_directo.py --elegir           # menu con las fuentes de fuentes.json (arrancar.bat)
    python stiv_directo.py --camara kurome    # la otra camara
    python stiv_directo.py --sin-ventana --duracion 120     # directo, solo CSV
    python stiv_directo.py --archivo clip.mp4 # mismo algoritmo sobre un video grabado
    python stiv_directo.py --camara sitio1 --fuente rtsp://usuario:clave@IP:554/Streaming/Channels/101
                                              # camara propia (RTSP, p. ej. Hikvision): nombre nuevo,
                                              # su config y sus salidas van a salidas/sitio1/

En una Raspberry Pi (sin pantalla): --sin-ventana, y --vista-cada 30 para tener la imagen anotada
al dia en salidas/<camara>/ultima_vista.png. Ver raspberry/LEEME.md.

La ventana muestra dos vistas a la vez: el directo tal cual y la vista RECTIFICADA (en planta, el
agua como se veria desde arriba, con el flujo de izquierda a derecha), las dos con las lineas, las
flechas y los valores; debajo, el STI de cada estacion.

Noche y agua lenta: --modo auto (por defecto) pasa a modo noche cuando la camara se pone en blanco y
negro (infrarrojo): realza las motas brillantes que flotan (basura, burbujas) y excluye el
deslumbramiento de las farolas. Y cada estacion se mide en la escala de tiempo que su velocidad
necesita: 10 s fotograma a fotograma si el agua corre, filas promediadas en ventanas de 30 o 60 s
si va muy despacio (de noche, en el Myoshoji, ~0.05 m/s: 0.1 px por fotograma).

Fuentes: fuentes.json lista los directos y videos entre los que se puede cambiar (menu al arrancar con
--elegir; en la ventana, c = siguiente y 1-9 = ir a esa). Para anadir uno basta una linea en ese archivo.

Teclas en la ventana: q salir | e editar el cuadrilatero (arrastrar esquinas) | g guardar config |
c siguiente fuente | 1-9 ir a la fuente n de fuentes.json |
r vaciar el buffer | espacio congelar la imagen (la medida sigue) | f pantalla completa |
+ / - agrandar / achicar | p ocultar/mostrar el panel de STI (mas sitio para el video). La ventana abre al ~90 % de la pantalla y se redimensiona con el raton.

LA ESCALA ES UN SUPUESTO mientras `escala_verificada` sea false en la config: las dimensiones del
cuadrilatero no vienen de ningun levantamiento, y la pantalla lo dice. La forma del perfil y la
coherencia no dependen de ellas; los m/s si, linealmente en el sentido del flujo.
"""
import argparse
import csv
import json
import os
import queue
import sys
import threading
import time
from collections import deque
from datetime import datetime


def _asegurar_librerias():
    """Si este Python no tiene las librerias (p. ej. el interprete que elige el IDE), relanza el
    script con el .venv de la carpeta en vez de fallar mas tarde al resolver el directo."""
    import importlib.util
    faltan = [m for m in ("cv2", "numpy", "yt_dlp") if importlib.util.find_spec(m) is None]
    if not faltan:
        return
    import subprocess
    carpeta = os.path.dirname(os.path.abspath(__file__))
    py = os.path.join(carpeta, ".venv", "Scripts" if os.name == "nt" else "bin",
                      "python.exe" if os.name == "nt" else "python")
    if os.path.exists(py) and os.path.normcase(os.path.abspath(sys.executable)) != os.path.normcase(py):
        print(f"faltan {', '.join(faltan)} en {sys.executable}; relanzando con {py}", file=sys.stderr)
        sys.exit(subprocess.call([py, os.path.abspath(__file__), *sys.argv[1:]]))
    sys.exit(f"faltan librerias: {', '.join(faltan)}. Instalar con:\n"
             f'  "{sys.executable}" -m pip install -r "{os.path.join(carpeta, "requirements.txt")}"')


_asegurar_librerias()

import cv2  # noqa: E402 - despues de comprobar que existe
import numpy as np  # noqa: E402

# ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
# │ >>> AJUSTABLE <<<  por camara                                                                  │
# └──────────────────────────────────────────────────────────────────────────────────────────────┘
# cuadrilatero: 4 esquinas en la imagen de un rectangulo real de largo x ancho m sobre el agua, en el
#   orden [aguas arriba-orilla A, aguas abajo-orilla A, aguas abajo-orilla B, aguas arriba-orilla B].
#   Trazado a ojo sobre el borde del agua; largo y ancho son un SUPUESTO en las dos camaras (no hay
#   ancho publicado de ninguno de los dos cauces en esos puntos; se busco).
# v_esperada: solo fija DS (estelas a 45 grados); sale de una correlacion de conjunto en el directo.
# ancho_banda_m: ~2/3 del espaciado entre estaciones.
CAMARAS = {
    "myoshoji": {
        "url": "https://www.youtube.com/watch?v=huAp4q7lxiQ",
        "etiqueta": "Rio Myoshoji, Kamitakada (Nakano) - directo Tokyo Suibou",
        # la camara mira a lo largo del cauce y el agua se ALEJA (sube en la imagen): correlacion
        # de conjunto -1 px por fotograma real en las tres zonas bajas. Aguas arriba = abajo en la
        # imagen; orilla A = muro izquierdo (vertical en la imagen), B = muro derecho. El borde
        # lejano se queda bajo la zona de piedras (y~365): el agua blanca es estacionaria y da 0
        # coherente. No es un salto (la ortofoto no muestra ninguna estructura); de noche el blanco
        # de esa zona es el reflejo de una farola. Ancho 8.8 m +-0.7 de coronacion a coronacion
        # (ortofoto, 2026-10-13); el largo de 10 m sigue siendo un supuesto.
        "cuadrilatero": [[360, 700], [360, 385], [697, 385], [1010, 700]],
        "largo_m": 10.0, "ancho_m": 8.8,
        # lineas de 9 m (antes 6): llegan a la parte cercana, donde hay mas pixeles por metro y
        # pasan las burbujas junto al muro derecho
        "v_esperada": 0.30, "largo_linea_m": 9.0, "centro_linea": 0.50, "ancho_banda_m": 0.60,
        "fps_camara": 15.0, "filtro_direccional": False,
        # De noche esta camara no ve el agua que fluye (verificacion_nivel/, 2026-10-14): sigue en
        # color con las farolas y lo unico visible en el agua son destellos de las farolas sobre
        # ondulaciones casi fijas (las piedras del fondo), que avanzan a 0.04-0.07 m/s. El modo noche,
        # el seguimiento de motas y la correlacion de conjunto los miden igual, y no son la corriente:
        # con el mismo nivel, de dia se mide 0.46-0.50 m/s, y el caudal oficial del puente Ochiai
        # (Q 0.38 m3/s, 0.13 m de calado, 2005-2009) da ~0.4-0.6 m/s en superficie. Se mide y se dibuja,
        # pero ninguna estacion se acepta ("noche_no_valida").
        "medir_noche": False,
    },
    "kurome": {
        "url": "https://www.youtube.com/watch?v=loW9744B-Co",
        "etiqueta": "Rio Kurome, puente Koma (Higashikurume) - directo Tokyo Suibou",
        # el agua avanza hacia la DERECHA: +8 px, -1 px en 4 fotogramas reales en el rapido
        "cuadrilatero": [[100, 500], [1100, 360], [1100, 500], [100, 680]],
        "largo_m": 15.0, "ancho_m": 6.0,
        "v_esperada": 0.40, "largo_linea_m": 8.0, "centro_linea": 0.50, "ancho_banda_m": 0.30,
        "fps_camara": 15.0, "filtro_direccional": False,
    },
    "shimoda": {
        "url": "https://www.youtube.com/watch?v=bpL7MAbdoI8",
        "etiqueta": "Rio Kurome, puente Shimoda (Higashikurume) - directo Tokyo Suibou",
        # el agua va de derecha a izquierda, HACIA el puente (el agua blanca bajo el puente es un
        # rapido aguas abajo): estelas del STI y correlacion 2D lo confirman. Orilla A = la lejana
        # (arriba en la imagen), B = la cercana. El cuadrilatero sigue el borde del agua que se
        # mueve (mapa de |I(t+1)-I(t)|); a la derecha la hierba de la orilla A tapa el agua.
        # Medido el 2026-10-13 (lluvia): 4-5 px por fotograma real junto a la orilla B (~1.3 m/s con
        # esta escala supuesta) y 10-30 px en el centro, donde a 15 fps la textura ya no sobrevive
        # de un fotograma al siguiente: con agua asi solo miden las estaciones 7-8. v_esperada 0.6
        # (tope fisico 1.8): con 0.4 el tensor media bien pero todo caia por encima de 1.2 m/s.
        "cuadrilatero": [[1040, 440], [448, 346], [480, 480], [1080, 600]],
        "largo_m": 12.0, "ancho_m": 5.0,
        "v_esperada": 0.60, "largo_linea_m": 9.0, "centro_linea": 0.50, "ancho_banda_m": 0.35,
        # Filtro direccional (2026-10-13, 18 h): con el agua a 1-1.5 m/s las ondas de la superficie,
        # casi regulares, avanzan entre dos fotogramas reales mas de media longitud de onda y el STI
        # muestra una trama cruzada (estelas "\\" reales y "/" estroboscopicas): signos opuestos en
        # estaciones vecinas, "ambiguo" y "v_max" (0-6 estaciones-medida aceptadas en 90 s). Con el
        # filtro: 156-162, casi siempre 9/9, mediana 0.94-1.00 m/s con DS de 2, 3 y 4 px (no sigue
        # al muestreo, luego no es un artefacto del filtro).
        "fps_camara": 15.0, "filtro_direccional": True,
    },
    "akigawa": {
        "url": "https://www.youtube.com/watch?v=ZRUh9gNk8-g",
        "etiqueta": "Rio Aki, Todohara (Akiruno) - directo Tokyo Suibou",
        # rio ancho visto de lado desde la orilla cercana (paseo de madera abajo a la derecha). El
        # agua va de IZQUIERDA a DERECHA, hacia el puente: estelas diagonales del STI y correlacion
        # 2D a 8 fotogramas (+10/+15 px). Orilla A = la lejana (barra de grava), B = la cercana
        # (hierba). A la izquierda hay un rapido con olas fijas (rayas verticales en el STI) y parte
        # del agua la congela el codec; bajo el puente, un reflejo de sol fijo (x 750-830).
        # 2026-10-13 17:40 (atardeciendo): NO MIDE. Entre fotogramas reales la imagen cambia 0.3-0.6
        # niveles de gris, la textura que avanza (2-6 px por fotograma) la tapan las olas fijas y el
        # codec, y la coherencia se queda en 0.1-0.36 (umbral 0.40) en cualquier zona, muestreo o
        # proceso (tambien el de motas). Escala supuesta 30 x 12 m. Queda como fuente por si mide
        # con otra luz o mas caudal.
        "cuadrilatero": [[60, 440], [1100, 372], [1100, 450], [60, 640]],
        "largo_m": 30.0, "ancho_m": 12.0,
        "v_esperada": 1.0, "largo_linea_m": 26.0, "centro_linea": 0.50, "ancho_banda_m": 0.80,
        "fps_camara": 15.0, "filtro_direccional": False,
    },
}
# Plantilla para una camara que no esta en la lista (--camara <nombre nuevo>). El cuadrilatero es un
# rectangulo centrado en una imagen 1280x720 que HAY que arrastrar sobre el agua (tecla e, en el PC);
# todo se guarda en salidas/<nombre>/config_stiv_directo.json y desde ahi manda el JSON.
# fps_camara None = la camara entrega fotogramas reales al ritmo del flujo (RTSP directo, sin
# duplicados como los de YouTube).
CAMARA_NUEVA = {
    "url": None, "etiqueta": None,
    "cuadrilatero": [[340, 620], [340, 260], [940, 260], [940, 620]],
    "largo_m": 10.0, "ancho_m": 6.0,
    "v_esperada": 0.50, "largo_linea_m": 6.0, "centro_linea": 0.50, "ancho_banda_m": 0.40,
    "fps_camara": None, "filtro_direccional": False, "medir_noche": True,
}
CAMARA_POR_DEFECTO = "myoshoji"
ALTURA_MAX = 720            # mejor formato de estos directos; 1080 no existe en este canal

# -- metodo, comun a todas las camaras --
N_ESTACIONES = 9
MARGEN_ORILLA = 0.06        # fraccion del ancho que se deja sin estacion junto a cada borde
LINEAS_BANDA = 7            # lineas paralelas por estacion (normalizadas y promediadas)

VENTANA_S = 10.0            # longitud temporal del STI
PASO_MEDIDA_S = 1.0         # cada cuanto se recalcula
LADO_BLOQUE = 48            # bloques del tensor, 50 % de solape

# FPS_CAMARA (por camara, ver elegir_camara): en los directos de YouTube la camara emite 15 fps y
# YouTube duplica cada fotograma (patron 2,2,2... medido en 150 de 150 cambios). El STI rapido toma
# UNA fila por fotograma real (el promedio de cada par) y la actividad se mide entre fotogramas
# reales. None = sin duplicados.
# Por que una fila por fotograma real (2026-10-13): con los duplicados el STI es una escalera, y en
# cuanto el agua avanza mas de ~1.5 muestras por fila el tensor la lee mal. STI sintetico de pendiente
# conocida: 2.0 -> 2.14 (+7 %), 2.5 -> 3.15 (+26 %, coherencia 0.54), 3.0 -> 5.6; sin duplicados,
# exacto hasta 3. El Kurome de dia (~2.4 muestras/fila) salia un 20 % alto.
# Mediana de |I(t + 1/15 s) - I(t)| en el bloque, en niveles de gris. El agua que el codificador
# congela (bloques "skip") da EXACTAMENTE 0.00 aunque sea una estela vertical perfectamente
# coherente; el agua con textura da 0.7-5.6. Medido de noche sobre 300 filas x 9 estaciones.
ACTIVIDAD_MIN = 0.5
# Fraccion de pixeles activos para que un bloque cuente. Lo que frena el agua congelada por el codec es
# la mascara POR PIXEL (los pixeles quietos no aportan al tensor); esta fraccion decide cuanto trazador
# hace falta en el bloque. De dia se queda en 0.5. De noche baja a 0.1: el trazador son motas sueltas
# sobre agua negra, y con 0.5 casi ningun bloque llegaba (Bradano, agua a 0.01-0.36/255 con particulas:
# 1 de 7 verticales -> 5 de 7, sesgo -4.5 %; Myoshoji de noche 220 -> 318 medidas, misma mediana,
# aunque esas resultaron ser destellos de farola: ver "medir_noche").
# No se baja de dia porque ahi no hay exclusion de reflejos: en Heiskanen con el sol de cara (agua
# saturada) 0.1 aceptaba 14 de 20 estaciones a +36 %, que con 0.5 se rechazan como "sin textura". Los
# destellos no se separan por saturacion (las estaciones buenas del Myoshoji de dia estan saturadas en
# un 70-80 %). Pruebas y regresion en validacion/README.md.
FRACCION_ACTIVA = 0.5
FRACCION_ACTIVA_NOCHE = 0.1
N_BLOQUES_MIN = 6           # bloques activos necesarios para que una estacion cuente
# 0.40 como en Boneyard (textura fina). Con la mascara de actividad la coherencia ya no es la que
# frena la trampa del cero; el STI nocturno del rapido da 0.3-0.55 con estelas claras a simple vista,
# y un STI sintetico con duplicados da 0.99 y pendiente exacta, asi que lo bajo es la textura.
COH_MIN = 0.40

# -- escalas de tiempo del STI (cascada) --
# (segundos por fila, ventana en s). 0 = cada fotograma. Cada estacion se mide en la PRIMERA escala
# que resuelve su movimiento (|pendiente| >= P_MIN muestras por fila); solo baja a una mas lenta si la
# rapida dice "demasiado lento" o no ve textura. En las lentas se exige ademas |pendiente| <= P_MAX:
# una estela casi horizontal en una escala lenta es agua rapida que esa escala no puede resolver
# (aliasing), y no se acepta. Las filas lentas son el PROMEDIO de los fotogramas que abarcan, que es
# el antialias temporal. Medido de noche en el Myoshoji (79 s): la rapida da pendiente 0.2 (lento),
# la de 0.133 s mide 0.05-0.07 m/s con la estela a ~35 grados y la de 0.5 s da lo mismo; un
# artefacto no sobrevive a ese cambio de escala. CORRECCION (2026-10-14): esa estela es real pero NO
# es la corriente; son destellos de farola sobre ondulaciones casi fijas que avanzan despacio. El agua
# va a ~0.4-0.5 m/s de dia con el mismo nivel y lo confirma el caudal oficial (ver "medir_noche").
# Las escalas lentas siguen siendo utiles para agua lenta de verdad; lo que fallaba era el trazador.
ESCALAS =((0.0, 10.0), (0.133, 30.0), (0.5, 60.0))
P_MIN = 0.3
P_MAX = 2.5
VENTANA_S = ESCALAS[0][1]

# -- modo noche --
# De noche la camara pasa a infrarrojo (blanco y negro) y el agua es negra y quieta: la senal son
# motas brillantes sueltas de 2-6 px que flotan. Top-hat con un elemento de 9 px deja solo lo que es
# mas brillante que su entorno inmediato y de ese tamano: borra los reflejos grandes de las farolas y
# los bloques congelados del codec. Despues se resta la mediana temporal de cada posicion (lo que no
# se mueve) sin dividir por la desviacion, que amplificaria el ruido del agua negra.
MODO_POR_DEFECTO = "auto"
NUCLEO_TOPHAT = 9
# Deslumbramiento de farolas: los destellos de una luz fija sobre las ondas son motas del mismo
# tamano que la basura pero viajan con las ondas, no con la corriente (dieron 0.3-0.9 m/s donde el
# resto media 0.06). Brillo mediano del agua medido de noche: 4-41; farolas 59-255. Las posiciones
# por encima de BRILLO_REFLEJO no cuentan.
BRILLO_REFLEJO = 60.0
# auto: noche si la saturacion media del recuadro de medida (|B-G| + |G-R|) baja de esto. Medido:
# 0.0 exacto con la camara en infrarrojo.
SATURACION_NOCHE = 1.5
# ... o si el brillo mediano a lo largo de las lineas baja de esto: el Myoshoji no pasa a infrarrojo,
# sigue en color con las farolas (saturacion 8-10) y la saturacion sola tomaba la noche por dia
# (2026-10-14). Medido: de dia 66-126 en todas las grabaciones, atardecer aun valido 59, noche en
# color 37-45, infrarrojo 14.
BRILLO_NOCHE = 50.0


def es_noche(geom, frame):
    return (geom.saturacion(frame) < SATURACION_NOCHE
            or float(np.median(geom.brillo(frame))) < BRILLO_NOCHE)


def elegir_camara(nombre, fuente=None, ajustes=None):
    """Fija las constantes de la camara elegida; sus salidas van a salidas/<camara>/.

    Las camaras de CAMARAS toman sus valores del codigo. Una camara nueva parte de CAMARA_NUEVA y,
    si ya tiene config guardada, toma de ella la URL y los parametros por camara (asi se configura
    una Raspberry editando solo el JSON). `fuente` sustituye la URL en cualquier caso, y `ajustes`
    (los "ajustes" de una entrada de fuentes.json) cualquiera de los valores por camara.
    """
    global CAMARA, URL_FUENTE, ETIQUETA, CUADRILATERO_SEMILLA, LARGO_SEMILLA_M, ANCHO_SEMILLA_M
    global V_ESPERADA, LARGO_LINEA_M, CENTRO_LINEA, ANCHO_BANDA_M, V_MAX_FISICA, FPS_CAMARA
    global FILTRO_DIRECCIONAL, MEDIR_NOCHE
    global CARPETA_SALIDAS, ARCHIVO_CONFIG, ARCHIVO_CSV, ARCHIVO_VISTA
    CARPETA_SALIDAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "salidas", nombre)
    ARCHIVO_CONFIG = os.path.join(CARPETA_SALIDAS, "config_stiv_directo.json")
    ARCHIVO_CSV = os.path.join(CARPETA_SALIDAS, "medidas_directo.csv")
    ARCHIVO_VISTA = os.path.join(CARPETA_SALIDAS, "ultima_vista.png")
    c = dict(CAMARAS.get(nombre, CAMARA_NUEVA))
    if nombre not in CAMARAS and os.path.exists(ARCHIVO_CONFIG):
        with open(ARCHIVO_CONFIG, encoding="utf-8") as f:
            guardada = json.load(f)
        par = guardada.get("parametros", {})
        c["url"] = guardada.get("url") or c["url"]
        c["etiqueta"] = guardada.get("etiqueta") or c["etiqueta"]
        for clave, global_ in (("v_esperada", "V_ESPERADA"), ("largo_linea_m", "LARGO_LINEA_M"),
                               ("centro_linea", "CENTRO_LINEA"), ("ancho_banda_m", "ANCHO_BANDA_M"),
                               ("fps_camara", "FPS_CAMARA"),
                               ("filtro_direccional", "FILTRO_DIRECCIONAL"),
                               ("medir_noche", "MEDIR_NOCHE")):
            if global_ in par:
                c[clave] = par[global_]
    for clave, valor in (ajustes or {}).items():
        if clave in c:
            c[clave] = valor
    if fuente:
        c["url"] = fuente
    CAMARA, URL_FUENTE = nombre, c["url"]
    ETIQUETA = c["etiqueta"] or f"Camara {nombre}"    # putText no dibuja japones
    CUADRILATERO_SEMILLA = [list(p) for p in c["cuadrilatero"]]
    LARGO_SEMILLA_M, ANCHO_SEMILLA_M = c["largo_m"], c["ancho_m"]
    V_ESPERADA, LARGO_LINEA_M = c["v_esperada"], c["largo_linea_m"]
    CENTRO_LINEA, ANCHO_BANDA_M = c["centro_linea"], c["ancho_banda_m"]
    FPS_CAMARA = c["fps_camara"]
    FILTRO_DIRECCIONAL = bool(c.get("filtro_direccional"))
    MEDIR_NOCHE = bool(c.get("medir_noche", True))
    V_MAX_FISICA = 3 * V_ESPERADA


elegir_camara(CAMARA_POR_DEFECTO)


# ─────────────────────────────────────────── fuentes ─────────────────────────────────────────────
# Lista de directos y videos entre los que se cambia (menu al arrancar, teclas c y 1-9). Cada entrada:
#   titulo   lo que se ve en el menu y en la ventana
#   camara   nombre de la camara: fija la geometria y la carpeta salidas/<camara>/ (una de CAMARAS o
#            un nombre nuevo, que parte de CAMARA_NUEVA y se ajusta con e + g)
#   url      directo (YouTube, rtsp://...); si falta, el de la camara
#   archivo  video grabado (relativo a esta carpeta), en vez del directo
#   modo     auto / dia / noche (si falta, auto)
#   ajustes  valores por camara que cambiar, p. ej. {"fps_camara": 15.0} para un directo de YouTube
#            nuevo que duplique fotogramas como los de Tokyo Suibou
ARCHIVO_FUENTES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fuentes.json")


def cargar_fuentes():
    """Las entradas de fuentes.json; sin el archivo (p. ej. en la Raspberry), una por camara de CAMARAS."""
    if not os.path.exists(ARCHIVO_FUENTES):
        return [{"titulo": c["etiqueta"], "camara": n} for n, c in CAMARAS.items()]
    with open(ARCHIVO_FUENTES, encoding="utf-8") as f:
        fuentes = json.load(f)
    if isinstance(fuentes, dict):
        fuentes = fuentes.get("fuentes", [])
    for i, e in enumerate(fuentes, 1):
        if not isinstance(e, dict) or not e.get("camara"):
            sys.exit(f"fuentes.json: la entrada {i} necesita al menos \"camara\"")
        e.setdefault("titulo", e.get("archivo") or e.get("url") or e["camara"])
    return fuentes


def ruta_archivo(archivo):
    if not archivo or os.path.isabs(archivo):
        return archivo
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), archivo))


def args_de_fuente(base, entrada):
    """Copia de los argumentos con la camara, la URL, el archivo y el modo de una entrada."""
    a = argparse.Namespace(**vars(base))
    a.camara, a.fuente = entrada["camara"], entrada.get("url")
    a.archivo = ruta_archivo(entrada.get("archivo"))
    a.modo = entrada.get("modo", MODO_POR_DEFECTO)
    a.ajustes, a.titulo = entrada.get("ajustes"), entrada["titulo"]
    return a


def indice_fuente(args, fuentes):
    """Que entrada de la lista corresponde a los argumentos de la linea de comandos (o None)."""
    for i, e in enumerate(fuentes):
        archivo = ruta_archivo(e.get("archivo"))
        if e["camara"] != args.camara:
            continue
        if args.archivo or archivo:
            if args.archivo and archivo and os.path.normcase(os.path.abspath(args.archivo)) == \
                    os.path.normcase(os.path.abspath(archivo)):
                return i
        elif not args.fuente or args.fuente == e.get("url"):
            return i
    return None


def menu_fuentes(fuentes):
    print("Fuentes (fuentes.json):")
    for i, e in enumerate(fuentes, 1):
        tipo = "video" if e.get("archivo") else "directo"
        print(f"  {i}. {e['titulo']}  [{tipo}, camara {e['camara']}]")
    try:
        r = input(f"Numero (Enter = 1): ").strip()
    except EOFError:
        r = ""
    n = int(r) if r.isdigit() and 1 <= int(r) <= len(fuentes) else 1
    return n - 1


# ───────────────────────────────────────── configuracion ─────────────────────────────────────────
def cargar_config():
    if os.path.exists(ARCHIVO_CONFIG):
        with open(ARCHIVO_CONFIG, encoding="utf-8") as f:
            return json.load(f)
    return {"camara": CAMARA, "url": URL_FUENTE, "etiqueta": ETIQUETA, "cuadrilatero_px": CUADRILATERO_SEMILLA, "largo_m": LARGO_SEMILLA_M,
            "ancho_m": ANCHO_SEMILLA_M, "escala_verificada": False}


def guardar_config(cfg):
    os.makedirs(CARPETA_SALIDAS, exist_ok=True)
    salida = dict(cfg)
    salida["parametros"] = {k: globals()[k] for k in (
        "V_ESPERADA", "N_ESTACIONES", "MARGEN_ORILLA", "LARGO_LINEA_M", "CENTRO_LINEA",
        "LINEAS_BANDA", "ANCHO_BANDA_M", "VENTANA_S", "PASO_MEDIDA_S", "LADO_BLOQUE", "FPS_CAMARA",
        "ACTIVIDAD_MIN", "FRACCION_ACTIVA", "FRACCION_ACTIVA_NOCHE", "N_BLOQUES_MIN", "COH_MIN", "V_MAX_FISICA", "ESCALAS", "P_MIN", "P_MAX",
        "NUCLEO_TOPHAT", "BRILLO_REFLEJO", "SATURACION_NOCHE", "BRILLO_NOCHE", "FILTRO_DIRECCIONAL",
        "MEDIR_NOCHE")}
    with open(ARCHIVO_CONFIG, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────── geometria ───────────────────────────────────────────
class Geometria:
    """Rectangulo del mundo (x aguas abajo, y desde la orilla lejana, en m) <-> imagen."""

    def __init__(self, cfg, fps):
        self.cuad = np.float32(cfg["cuadrilatero_px"])
        self.L, self.W = float(cfg["largo_m"]), float(cfg["ancho_m"])
        mundo = np.float32([[0, 0], [self.L, 0], [self.L, self.W], [0, self.W]])
        self.H = cv2.getPerspectiveTransform(mundo, self.cuad)          # mundo -> imagen
        # fotogramas del flujo por fotograma real de la camara (2 en YouTube: 15 fps duplicados a 30)
        self.k_real = max(1, int(round(fps / FPS_CAMARA))) if FPS_CAMARA else 1
        self.dt = self.k_real / fps
        # DS = V.dt pone las estelas a 45 grados, donde el error angular pesa menos
        self.ds = V_ESPERADA * self.dt
        x0 = self.L * CENTRO_LINEA - LARGO_LINEA_M / 2
        self.xs = x0 + self.ds * np.arange(int(round(LARGO_LINEA_M / self.ds)))
        m = MARGEN_ORILLA * self.W
        self.ys = np.linspace(m, self.W - m, N_ESTACIONES)
        offs = np.linspace(-ANCHO_BANDA_M / 2, ANCHO_BANDA_M / 2, LINEAS_BANDA)
        yy = (self.ys[:, None] + offs[None, :]).reshape(-1)               # (N_EST*NB,)
        X, Y = np.meshgrid(self.xs, yy)
        p = self.a_imagen(np.stack([X.ravel(), Y.ravel()], 1))
        # remap no admite mapas de mas de SHRT_MAX de largo: se deja en 2D (filas = lineas)
        self.map_x = p[:, 0].reshape(X.shape).astype(np.float32)
        self.map_y = p[:, 1].reshape(X.shape).astype(np.float32)
        # pixeles de imagen por muestra (para el aviso de submuestreo y el suavizado antialias)
        paso = np.hypot(np.diff(self.map_x, axis=1), np.diff(self.map_y, axis=1))
        self.px_por_muestra = float(np.median(paso))
        # escalas de tiempo: fotogramas por fila y filas por ventana
        self.fps = fps
        self.k_escalas = [self.k_real if d <= 0 else max(self.k_real, int(round(d * fps))) for d, _ in ESCALAS]
        self.n_filas = [int(round(w * fps / k)) for (_, w), k in zip(ESCALAS, self.k_escalas)]
        self.dt_filas = [k / fps for k in self.k_escalas]
        self._preparar_rectificada()

    def _preparar_rectificada(self, alto=720):
        """Vista en planta: x (aguas abajo) hacia la derecha, y (orilla A -> B) hacia abajo, con un
        margen alrededor del rectangulo para ver el contexto."""
        m = 0.15 * max(self.L, self.W)
        self.rect_margen = m
        self.rect_esc = alto / (self.W + 2 * m)                        # px por metro
        self.rect_tam = (int(round((self.L + 2 * m) * self.rect_esc)), alto)
        S = np.float64([[self.rect_esc, 0, m * self.rect_esc], [0, self.rect_esc, m * self.rect_esc], [0, 0, 1]])
        self.rect_a_imagen = self.H @ np.linalg.inv(S)                  # pixel rectificado -> imagen

    def a_rect(self, pts):
        pts = np.float64(pts).reshape(-1, 2)
        return (pts + self.rect_margen) * self.rect_esc

    def a_imagen(self, pts):
        return cv2.perspectiveTransform(np.float32(pts).reshape(-1, 1, 2), self.H).reshape(-1, 2)

    def muestrear(self, gris):
        # fuera del fotograma la muestra vale 0: con desviacion temporal nula su z es 0 y no pesa
        return cv2.remap(gris, self.map_x, self.map_y, cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    def procesar(self, frame, modo="dia"):
        """Fotograma BGR -> fila de muestras. Igual que gris + suavizado + muestrear, pero solo
        sobre el recuadro que tocan las lineas: en una Raspberry Pi el suavizado del fotograma
        entero era la mayor parte del coste por fotograma. En modo noche, top-hat antes."""
        if getattr(self, "_forma", None) != frame.shape:
            self._preparar_recorte(frame.shape)
        y0, y1, x0, x1 = self._recorte
        gris = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
        if modo == "noche":
            gris = cv2.morphologyEx(gris, cv2.MORPH_TOPHAT, self._nucleo)
        # antialias isotropo antes de muestrear: sigma ~ medio paso de muestreo, nunca < 0.7 px
        gris = cv2.GaussianBlur(gris.astype(np.float32), (0, 0), self.sigma)
        return cv2.remap(gris, self._mx, self._my, cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    def brillo(self, frame):
        """Brillo crudo a lo largo de las lineas (sin realce ni suavizado): para el deslumbramiento."""
        if getattr(self, "_forma", None) != frame.shape:
            self._preparar_recorte(frame.shape)
        y0, y1, x0, x1 = self._recorte
        gris = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(np.float32)
        return cv2.remap(gris, self._mx, self._my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                         borderValue=0)

    def saturacion(self, frame):
        """Saturacion media del recuadro de medida: ~0 con la camara en infrarrojo (noche)."""
        if getattr(self, "_forma", None) != frame.shape:
            self._preparar_recorte(frame.shape)
        y0, y1, x0, x1 = self._recorte
        r = frame[y0:y1:4, x0:x1:4].astype(np.int16)
        return float((np.abs(r[..., 0] - r[..., 1]) + np.abs(r[..., 1] - r[..., 2])).mean())

    def _preparar_recorte(self, forma):
        alto, ancho = forma[:2]
        self.sigma = max(0.7, self.px_por_muestra / 2)
        # el margen cubre el nucleo del suavizado: dentro del recuadro el resultado es el mismo
        # que suavizando el fotograma entero
        self._nucleo = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (NUCLEO_TOPHAT, NUCLEO_TOPHAT))
        m = int(np.ceil(4 * self.sigma)) + 2 + NUCLEO_TOPHAT
        x0 = max(int(np.floor(self.map_x.min())) - m, 0)
        x1 = min(int(np.ceil(self.map_x.max())) + m + 1, ancho)
        y0 = max(int(np.floor(self.map_y.min())) - m, 0)
        y1 = min(int(np.ceil(self.map_y.max())) + m + 1, alto)
        if x0 >= x1 or y0 >= y1:          # lineas fuera del fotograma: se usa entero
            x0, x1, y0, y1 = 0, ancho, 0, alto
        self._recorte = (y0, y1, x0, x1)
        self._mx, self._my = self.map_x - x0, self.map_y - y0
        self._forma = forma

    def cobertura(self, alto, ancho):
        """Fraccion de cada estacion que cae dentro del fotograma (depende solo de la geometria)."""
        dentro = ((self.map_x >= 0) & (self.map_x <= ancho - 1) &
                  (self.map_y >= 0) & (self.map_y <= alto - 1))
        return dentro.reshape(N_ESTACIONES, -1).mean(axis=1)


# ─────────────────────────────────────────── el metodo ───────────────────────────────────────────
def pendiente_tensor(sti, actividad, fraccion_activa=None):
    """Pendiente (muestras/fila) por tensor de estructura en bloques, mediana ponderada por coherencia.

    Solo cuentan los bloques activos: sin esa seleccion, el agua congelada por el codificador es una
    estela vertical de coherencia ~0.9 y la mediana devuelve 0.00 con toda confianza. Bloques de
    LADO_BLOQUE con 50 % de solape, sumados por celdas de medio bloque (sin bucle Python por bloque).
    """
    gs = cv2.Scharr(sti, cv2.CV_32F, 1, 0)
    gt = cv2.Scharr(sti, cv2.CV_32F, 0, 1)
    # mascara por pixel: el codificador congela parches DENTRO del agua activa, y esos parches son
    # rayas verticales que arrastran la pendiente hacia 0 y hunden la coherencia
    m = (cv2.blur(actividad, (5, 5)) >= ACTIVIDAD_MIN).astype(np.float32)
    T, K = sti.shape
    c = max(min(LADO_BLOQUE, T, K) // 2, 1)
    nt, nk = T // c, K // c
    if nt < 2 or nk < 2:
        return np.nan, 0.0, 0

    def bloques(img):
        celdas = img[:nt * c, :nk * c].reshape(nt, c, nk, c).sum(axis=(1, 3), dtype=np.float64)
        return celdas[:-1, :-1] + celdas[1:, :-1] + celdas[:-1, 1:] + celdas[1:, 1:]

    activos = bloques(m) / (4 * c * c) >= (FRACCION_ACTIVA if fraccion_activa is None else fraccion_activa)
    jss, jtt, jst = bloques(m * gs * gs)[activos], bloques(m * gt * gt)[activos], bloques(m * gs * gt)[activos]
    n_activos = int(activos.sum())
    tr = jss + jtt
    ok = tr > 1e-9
    jss, jtt, jst, tr = jss[ok], jtt[ok], jst[ok], tr[ok]
    if tr.size == 0:
        return np.nan, 0.0, n_activos
    l1 = 0.5 * (tr + np.hypot(jss - jtt, 2 * jst))
    coh = ((2 * l1 - tr) / tr) ** 2
    # I(s,t) = f(s - v t)  =>  (Gs, Gt) ~ (1, -v): el gradiente va segun el autovector MAYOR
    # (jst, l1 - jss), o (l1 - jtt, jst) si el primero degenera; v = -ey/ex
    ex, ey = jst.copy(), l1 - jss
    deg = (np.abs(ex) < 1e-12) & (np.abs(ey) < 1e-12)
    ex[deg], ey[deg] = (l1 - jtt)[deg], jst[deg]
    ok = np.abs(ex) >= 1e-12
    if not ok.any():
        return np.nan, 0.0, n_activos
    vs, cs = -ey[ok] / ex[ok], coh[ok]
    o = np.argsort(vs)
    acum = np.cumsum(cs[o])
    if acum[-1] <= 0:
        return np.nan, 0.0, n_activos
    v = vs[o][np.searchsorted(acum, acum[-1] / 2)]
    return float(v), float(np.average(cs, weights=cs)), n_activos


def construir_stis(buffer, lag, modo="dia"):
    """buffer: (T, N_EST*NB, K) muestras crudas -> STIs normalizados y actividades, (N_EST, T, K)."""
    T, R, K = buffer.shape
    if modo == "noche":
        # motas sobre agua negra: restar lo que no se mueve (mediana temporal; con una de cada 4 filas
        # basta y cuesta 4 veces menos) y quedarse con el exceso de brillo. Sin dividir por la
        # desviacion de cada posicion, que igualaria el ruido del agua negra a las motas.
        e = np.clip(buffer - np.median(buffer[::4], axis=0), 0, None)
        sti = e.reshape(T, N_ESTACIONES, LINEAS_BANDA, K).mean(axis=2).transpose(1, 0, 2)
        sti = sti / (sti.std(axis=(1, 2), keepdims=True) + 1e-6)
    else:
        # normalizacion temporal por posicion: quita lo estatico (piedras, reflejos fijos, la
        # vegetacion que invade la banda) sin parametros, y deja a todas las lineas el mismo peso
        m = buffer.mean(axis=0)
        s = buffer.std(axis=0)
        z = (buffer - m) / np.where(s > 1e-3, s, np.inf)
        sti = z.reshape(T, N_ESTACIONES, LINEAS_BANDA, K).mean(axis=2).transpose(1, 0, 2)
    crudo = buffer.reshape(T, N_ESTACIONES, LINEAS_BANDA, K).mean(axis=2).transpose(1, 0, 2)
    # actividad entre fotogramas REALES (cada fila ya lo es): un parche congelado da 0 exacto
    actividad = np.empty_like(crudo)
    actividad[:, lag:] = np.abs(crudo[:, lag:] - crudo[:, :-lag])
    actividad[:, :lag] = actividad[:, lag:2 * lag]
    # suavizado de 1 fila y 1 muestra: quita ruido de pixel sin cambiar la pendiente (STI sintetico)
    sti = np.stack([cv2.GaussianBlur(np.ascontiguousarray(x, np.float32), (0, 0), 1.0, sigmaY=1.0)
                    for x in sti])
    if FILTRO_DIRECCIONAL:
        sti = np.stack([filtro_direccional(x) for x in sti])
    return sti, np.ascontiguousarray(actividad, np.float32)


def filtro_direccional(sti):
    """Deja solo lo que avanza aguas ABAJO (+x del cuadrilatero). Un patron I(s - v t) con v > 0 pone
    su energia en k_t = -v k_s, es decir donde k_t y k_s tienen signo contrario; lo que avanza aguas
    arriba (ondas, y la imagen estroboscopica del agua rapida cuando avanza mas de media longitud de
    onda por fila) cae en los cuadrantes de igual signo, que se anulan. Los ejes se conservan (lo
    quieto lo trata la mascara de actividad). Impone el sentido del flujo: solo por camara, y con el
    cuadrilatero bien orientado (aguas arriba -> aguas abajo)."""
    T, K = sti.shape
    F = np.fft.fft2(sti)
    F[(np.fft.fftfreq(T)[:, None] * np.fft.fftfreq(K)[None, :]) > 0] = 0
    return np.real(np.fft.ifft2(F)).astype(np.float32)


def medir(buffers, geom, cobertura, modo="dia", brillo=None, buffers_motas=None):
    """buffers: uno por escala de ESCALAS, (T, N_EST*NB, K), o None si esa escala aun se esta
    llenando. brillo: brillo crudo mediano por posicion (N_EST*NB, K), para el deslumbramiento.
    buffers_motas (de dia): las mismas filas con el realce de motas del modo noche; una estacion que
    no se puede medir con el proceso de dia se reintenta con ellas.
    Devuelve una lista de dicts, una por estacion, con la escala en la que se midio."""
    deslumbrado = None
    if modo == "noche" and brillo is not None:
        # una posicion cuenta como deslumbrada si lo esta en cualquiera de las lineas de la banda
        deslumbrado = (brillo.reshape(N_ESTACIONES, LINEAS_BANDA, -1) > BRILLO_REFLEJO).any(axis=1)
    cache = {}
    # de noche (solo en modo noche, que tiene la exclusion de reflejos) basta menos trazador por bloque;
    # el reintento de motas de dia sigue con la fraccion de dia (ver FRACCION_ACTIVA)
    fraccion = FRACCION_ACTIVA_NOCHE if modo == "noche" else FRACCION_ACTIVA

    def escala(bufs, proceso, j):
        """(pendiente, coherencia, bloques, sti) por estacion en la escala j, calculado una vez."""
        if (proceso, j) not in cache:
            stis, act = construir_stis(bufs[j], 1, proceso)
            if deslumbrado is not None:
                for i in range(N_ESTACIONES):
                    act[i][:, deslumbrado[i]] = 0
            cache[(proceso, j)] = [(*pendiente_tensor(stis[i], act[i], fraccion), stis[i])
                                   for i in range(N_ESTACIONES)]
        return cache[(proceso, j)]

    def cascada(i, bufs, proceso):
        elegida, motivo, primera = None, "sin_medida", None
        for j, buf in enumerate(bufs):
            if buf is None:
                if motivo in ("lento", "sin_textura"):
                    motivo += "_esperando"        # la escala mas lenta aun se esta llenando
                break
            pend, coh, n_act, sti = escala(bufs, proceso, j)[i]
            if primera is None:
                primera = (j, pend, coh, n_act, sti)
            valida = np.isfinite(pend) and n_act >= N_BLOQUES_MIN and coh >= COH_MIN
            if valida and abs(pend) >= P_MIN and (j == 0 or abs(pend) <= P_MAX):
                elegida = (j, pend, coh, n_act, sti)
                break
            if valida and abs(pend) > P_MAX:
                motivo = "ambiguo"                # estela casi horizontal en una escala lenta
                break
            motivo = ("lento" if valida else "sin_textura" if n_act < N_BLOQUES_MIN
                      else "coherencia" if np.isfinite(pend) else "sin_medida")
        return elegida, motivo, primera

    res = []
    for i in range(N_ESTACIONES):
        elegida, motivo, primera = cascada(i, buffers, modo)
        motas = False
        # De dia, el agua en sombra junto a un muro puede no tener textura y llevar solo burbujas
        # sueltas: el proceso de dia las diluye (actividad de la banda ~0, coherencia 0.14-0.33) y
        # el de motas las mide (Myoshoji, estaciones 6-8: 0.02-0.05 m/s, coherencia 0.7-0.9, igual
        # en dos escalas). "ambiguo" no se reintenta: es agua rapida, no falta de textura.
        if elegida is None and buffers_motas is not None and motivo != "ambiguo":
            otra = cascada(i, buffers_motas, "noche")[0]
            if otra is not None:
                elegida, motas = otra, True
        j, pend, coh, n_act, sti = elegida or primera or (0, np.nan, 0.0, 0, None)
        v = pend * geom.ds / geom.dt_filas[j] if np.isfinite(pend) else np.nan
        motivos = [] if elegida else [motivo]
        if modo == "noche" and not MEDIR_NOCHE:
            motivos.append("noche_no_valida")      # ver "medir_noche" en CAMARAS
        if cobertura[i] < 0.8:
            motivos.append("fuera_de_campo")
        if elegida and abs(v) > V_MAX_FISICA:
            motivos.append("v_max")
        res.append({"estacion": i, "y_m": float(geom.ys[i]), "v": v, "pendiente": pend,
                    "coherencia": coh, "bloques_activos": n_act, "cobertura": float(cobertura[i]),
                    "escala": j, "dt_fila": geom.dt_filas[j], "motas": motas,
                    "aceptada": not motivos, "motivos": "+".join(motivos), "sti": sti})
    return res


# ───────────────────────────────────────── lectura del directo ───────────────────────────────────
def resolver_url(url_pagina):
    import yt_dlp
    opciones = {"quiet": True, "no_warnings": True,
                "format": f"bestvideo[height<={ALTURA_MAX}]/best[height<={ALTURA_MAX}]"}
    # YouTube a veces bloquea una conexion ("Sign in to confirm you're not a bot"); con las cookies
    # de un navegador donde se haya iniciado sesion (archivo cookies.txt) vuelve a dejar pasar
    if os.environ.get("STIV_COOKIES"):
        opciones["cookiefile"] = os.environ["STIV_COOKIES"]
    with yt_dlp.YoutubeDL(opciones) as y:
        info = y.extract_info(url_pagina, download=False)
    return info["url"], info.get("title", ""), info.get("live_status")


class Lector(threading.Thread):
    """Lee el flujo en un hilo aparte y entrega (pts_s, fotograma). Reconecta si se corta."""

    def __init__(self, origen, es_archivo):
        super().__init__(daemon=True)
        self.origen, self.es_archivo = origen, es_archivo
        # YouTube se resuelve con yt-dlp; cualquier otra URL (rtsp://, http://...m3u8) se abre tal cual
        self.es_youtube = not es_archivo and ("youtube.com" in origen or "youtu.be" in origen)
        # 150 fotogramas = 5 s a 30 fps, ~415 MB a 1280x720. Con 600 el pico de memoria llego a 1.3 GB
        # al procesar un archivo (la lectura va por delante): demasiado para una Raspberry de 4 GB.
        # Si se llena, el lector espera; no se pierde la sincronia del STI.
        self.cola = queue.Queue(maxsize=150)
        self.parar = threading.Event()
        self.fps = 30.0
        self.titulo = ""
        self.listo = threading.Event()
        self.error = None
        self.abierto = False

    def abrir(self):
        if self.es_youtube:
            fuente, self.titulo, estado = resolver_url(self.origen)
            if estado != "is_live":
                print(f"aviso: el video no esta en directo (live_status={estado})", file=sys.stderr)
        else:
            fuente = self.origen
        if self.es_archivo:
            cap = cv2.VideoCapture(fuente, cv2.CAP_FFMPEG)
        else:
            # sin tiempos de espera, una camara que se cuelga deja read() bloqueado para siempre y
            # nunca se llega a reconectar
            cap = cv2.VideoCapture(fuente, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 15000,
                                                            cv2.CAP_PROP_READ_TIMEOUT_MSEC, 15000])
        if not cap.isOpened():
            raise RuntimeError("OpenCV no pudo abrir el flujo")
        f = cap.get(cv2.CAP_PROP_FPS)
        self.fps = f if f and 1 < f < 121 else 30.0
        return cap

    def run(self):
        intentos = 0
        while not self.parar.is_set():
            try:
                cap = self.abrir()
            except Exception as e:  # noqa: BLE001 - se reintenta, el directo es inestable
                self.error = e
                intentos += 1
                if intentos > 5 or self.es_archivo:
                    self.listo.set()
                    self.cola.put(None)
                    return
                time.sleep(3)
                continue
            intentos = 0
            self.abierto = True
            self.listo.set()
            while not self.parar.is_set():
                ok, frame = cap.read()
                if not ok:
                    break
                pts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                self.cola.put((pts, frame))
            cap.release()
            if self.parar.is_set():
                return
            if self.es_archivo:
                self.cola.put(None)
                return
            print("flujo cortado, reconectando...", file=sys.stderr)
            self.cola.put("corte")


def detener_lector(lector):
    """Para el hilo lector y vacia su cola: si estaba bloqueado metiendo un fotograma en la cola llena,
    se desbloquea y termina (si no, seguiria vivo con el flujo abierto y ~400 MB de fotogramas)."""
    lector.parar.set()
    for _ in range(3):
        try:
            while True:
                lector.cola.get_nowait()
        except queue.Empty:
            pass
        lector.join(timeout=0.2)


class Buffers:
    """Las filas del STI en todas las escalas de ESCALAS: cada fila es el promedio de k fotogramas
    consecutivos. En la rapida k = fotogramas por fotograma real (el par de duplicados de YouTube);
    en las lentas, el promedio es ademas el antialias temporal."""

    def __init__(self, geom, canales=2):
        # canal 0: el proceso del modo actual; canal 1 (de dia): realce de motas, para reintentar
        self.k = geom.k_escalas
        self.colas = [[deque(maxlen=n) for n in geom.n_filas] for _ in range(canales)]
        self.vaciar()

    def vaciar(self):
        for canal in self.colas:
            for c in canal:
                c.clear()
        self.suma = [[None] * len(self.k) for _ in self.colas]
        self.cuenta = [[0] * len(self.k) for _ in self.colas]
        self.ult = None

    def agregar(self, *filas):
        """Una fila por canal; None = ese canal no se alimenta (p. ej. el de motas de noche)."""
        self.ult = filas
        for c, fila in enumerate(filas):
            if fila is None:
                continue
            for j in range(len(self.k)):
                if self.k[j] == 1:
                    self.colas[c][j].append(fila)
                    continue
                if self.suma[c][j] is None:
                    self.suma[c][j] = fila.astype(np.float32, copy=True)
                else:
                    self.suma[c][j] += fila
                self.cuenta[c][j] += 1
                if self.cuenta[c][j] == self.k[j]:
                    self.colas[c][j].append(self.suma[c][j] / self.k[j])
                    self.suma[c][j], self.cuenta[c][j] = None, 0

    def repetir_ultima(self):
        """Rellena un hueco de PTS repitiendo el ultimo fotograma (lo que hace YouTube)."""
        if self.ult is not None:
            self.agregar(*self.ult)

    def rapida_llena(self):
        return len(self.colas[0][0]) == self.colas[0][0].maxlen

    def llenado(self):
        return [len(c) / c.maxlen for c in self.colas[0]]

    def instantanea(self, canal=0):
        """Copia barata (listas de referencias) de las escalas llenas; None las que aun no lo estan."""
        return [list(c) if len(c) == c.maxlen else None for c in self.colas[canal]]


class Medidor(threading.Thread):
    """Mide en un hilo aparte: la medida cuesta ~140 ms y el directo entrega un fotograma cada 33."""

    def __init__(self):
        super().__init__(daemon=True)
        self.entrada = queue.Queue(maxsize=1)
        self.salida = queue.Queue()
        self.n, self.segundos = 0, 0.0     # para el resumen: cuanto cuesta cada medida

    def libre(self):
        return self.entrada.empty() and self.salida.empty()

    def detener(self):
        try:
            self.entrada.get_nowait()
        except queue.Empty:
            pass
        self.entrada.put(None)

    def run(self):
        while True:
            item = self.entrada.get()
            if item is None:
                return
            gen, t, filas, filas_motas, geom, cobertura, modo, brillos = item
            c0 = time.perf_counter()
            buffers = [np.stack(f) if f is not None else None for f in filas]
            motas = ([np.stack(f) if f is not None else None for f in filas_motas]
                     if modo == "dia" else None)
            brillo = np.median(np.stack(brillos), axis=0) if brillos else None
            res = medir(buffers, geom, cobertura, modo, brillo, motas)
            self.n, self.segundos = self.n + 1, self.segundos + time.perf_counter() - c0
            self.salida.put((gen, t, res))


# ──────────────────────────────────────────── ventana ────────────────────────────────────────────
FRACCION_PANTALLA = 0.90    # tamano inicial de la ventana respecto a la pantalla


def tamano_pantalla():
    """Resolucion de la pantalla principal en pixeles fisicos."""
    try:
        import ctypes
        u32 = ctypes.windll.user32
        # sin esto Windows reescala la ventana por DPI (borrosa) y GetSystemMetrics miente
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:  # noqa: BLE001 - Windows antiguo
            u32.SetProcessDPIAware()
        return u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
    except Exception:  # noqa: BLE001 - no es Windows
        return 1920, 1080


def ajustar_ventana(ventana, alto_img, ancho_img, escala=None):
    """Da a la ventana el mayor tamano que cabe en FRACCION_PANTALLA sin deformar la imagen
    (o `escala` veces ese tamano) y la centra. Devuelve la escala base usada."""
    sw, sh = tamano_pantalla()
    base = min(FRACCION_PANTALLA * sw / ancho_img, FRACCION_PANTALLA * sh / alto_img)
    f = base if escala is None else escala
    w, h = int(ancho_img * f), int(alto_img * f)
    cv2.resizeWindow(ventana, w, h)
    cv2.moveWindow(ventana, max((sw - w) // 2, 0), max((sh - h) // 2 - 20, 0))
    return f


# ──────────────────────────────────────────── dibujo ─────────────────────────────────────────────
ALTO_PANEL = 210


COLOR_OK, COLOR_NO, COLOR_FLECHA = (80, 220, 80), (60, 60, 200), (0, 255, 255)
NOMBRE_ESCALA = ("10s", "30s", "60s")


def segundos_flecha(res):
    """Cuantos segundos de recorrido representa una flecha: los necesarios para que la mediana mida
    ~1 m (entre 2 y 60 s). Con 2 s fijos, el agua de la noche (0.05 m/s) daba flechas de 10 cm."""
    ac = [abs(r["v"]) for r in res or [] if r["aceptada"]]
    if not ac:
        return 2.0
    return float(np.clip(1.0 / max(np.median(ac), 1e-3), 2.0, 60.0))


def vista_rectificada(frame, geom, res, t_flecha=2.0):
    """El agua en planta (como desde arriba): x aguas abajo hacia la derecha, orilla A arriba. Las
    lineas son horizontales y las flechas tienen longitud real (2 s de recorrido)."""
    w, h = geom.rect_tam
    rect = cv2.warpPerspective(frame, geom.rect_a_imagen, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=(40, 40, 40))
    esq = geom.a_rect([[0, 0], [geom.L, 0], [geom.L, geom.W], [0, geom.W]]).astype(np.int32)
    cv2.polylines(rect, [esq], True, (90, 90, 90), 1, cv2.LINE_AA)
    for i, y in enumerate(geom.ys):
        r = res[i] if res else None
        color = (120, 120, 120) if r is None else COLOR_OK if r["aceptada"] else COLOR_NO
        a, b = geom.a_rect([[geom.xs[0], y], [geom.xs[-1], y]]).astype(int)
        cv2.line(rect, tuple(a), tuple(b), color, 1, cv2.LINE_AA)
        cv2.putText(rect, str(i), tuple(a + [-16, 5]), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
        if r is not None and r["aceptada"]:
            xc = (geom.xs[0] + geom.xs[-1]) / 2
            p0, p1 = geom.a_rect([[xc, y], [xc + t_flecha * r["v"], y]]).astype(int)
            cv2.arrowedLine(rect, tuple(p0), tuple(p1), COLOR_FLECHA, 2, cv2.LINE_AA, tipLength=0.3)
            cv2.putText(rect, f"{r['v']:.3f}", tuple(p1 + [6, -6]), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        COLOR_FLECHA, 1, cv2.LINE_AA)
    # barra de escala de 1 m y rotulos
    x0, y0 = 15, h - 20
    x1 = int(x0 + geom.rect_esc)
    cv2.line(rect, (x0, y0), (x1, y0), (255, 255, 255), 2)
    cv2.putText(rect, "1 m", (x0, y0 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    capa = rect.copy()
    cv2.rectangle(capa, (0, 0), (w, 30), (0, 0, 0), -1)
    rect = cv2.addWeighted(capa, 0.65, rect, 0.35, 0)
    cv2.putText(rect, "VISTA RECTIFICADA (en planta, flujo ->)", (10, 20), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(rect, "A", (5, int(geom.a_rect([[0, 0]])[0, 1]) + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(rect, "B", (5, int(geom.a_rect([[0, geom.W]])[0, 1]) + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (200, 200, 200), 1, cv2.LINE_AA)
    return rect


def dibujar(frame, geom, res, estado, editando, con_panel=True):
    img = frame.copy()
    t_flecha = segundos_flecha(res)
    cv2.polylines(img, [geom.cuad.astype(np.int32)], True, (0, 200, 255) if editando else (90, 90, 90),
                  2 if editando else 1, cv2.LINE_AA)
    if editando:
        for p in geom.cuad.astype(int):
            cv2.circle(img, tuple(p), 9, (0, 200, 255), 2, cv2.LINE_AA)
    for i, y in enumerate(geom.ys):
        a, b = geom.a_imagen([[geom.xs[0], y], [geom.xs[-1], y]])
        r = res[i] if res else None
        color = (120, 120, 120)
        if r is not None:
            color = (80, 220, 80) if r["aceptada"] else (60, 60, 200)
        cv2.line(img, tuple(a.astype(int)), tuple(b.astype(int)), color, 1, cv2.LINE_AA)
        cv2.putText(img, str(i), tuple((a + [-18, 5]).astype(int)), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    color, 1, cv2.LINE_AA)
        if r is not None and r["aceptada"]:
            # flecha = t_flecha s de recorrido en el mundo; la punta se proyecta, asi la perspectiva la
            # acorta
            xc = (geom.xs[0] + geom.xs[-1]) / 2
            p0, p1 = geom.a_imagen([[xc, y], [xc + t_flecha * r["v"], y]])
            cv2.arrowedLine(img, tuple(p0.astype(int)), tuple(p1.astype(int)), (0, 255, 255), 2,
                            cv2.LINE_AA, tipLength=0.25)
            cv2.putText(img, f"{r['v']:.3f}", tuple((p1 + [6, -6]).astype(int)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
    # cabecera
    llen = estado["llenado"] if isinstance(estado["llenado"], (list, tuple)) else [estado["llenado"]]
    lineas = [estado["titulo"][:70],
              f"STIV en directo | modo {estado.get('modo', 'dia')} | t={estado['t']:.1f}s | "
              f"retraso {estado['retraso']:.1f}s | {estado['px_muestra']:.2f} px/muestra",
              "STI " + "  ".join(f"{n} {x:.0%}" for n, x in zip(NOMBRE_ESCALA, llen)) +
              ("  | filtro direccional" if FILTRO_DIRECCIONAL else "")]
    if res:
        ac = [r["v"] for r in res if r["aceptada"]]
        med = f"{np.median(ac):.3f} m/s" if ac else "sin estaciones validas"
        lineas.append(f"mediana seccion: {med}  ({len(ac)}/{len(res)} estaciones) | flecha = "
                      f"{t_flecha:.0f} s de recorrido")
    if not estado["verificada"]:
        lineas.append("ESCALA SUPUESTA: m/s sin verificar (ver config)")
    if estado.get("fuente"):
        lineas.append(estado["fuente"])
    y0 = 22
    capa = img.copy()
    cv2.rectangle(capa, (0, 0), (600, 10 + 20 * len(lineas)), (0, 0, 0), -1)
    img = cv2.addWeighted(capa, 0.65, img, 0.35, 0)
    for j, t in enumerate(lineas):
        col = (0, 140, 255) if t.startswith("ESCALA") else (255, 255, 255)
        cv2.putText(img, t, (10, y0 + 20 * j), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(img, t, (10, y0 + 20 * j), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1, cv2.LINE_AA)
    if editando:
        cv2.putText(img, "EDITANDO: arrastra las esquinas, 'e' para terminar, 'g' para guardar",
                    (10, img.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 2,
                    cv2.LINE_AA)
    # las dos vistas lado a lado: el directo (a la izquierda, a su tamano real, para que el raton
    # siga en coordenadas de la imagen al editar) y la rectificada
    rect = vista_rectificada(frame, geom, res, t_flecha)
    if rect.shape[0] != img.shape[0]:
        rect = cv2.resize(rect, (int(rect.shape[1] * img.shape[0] / rect.shape[0]), img.shape[0]))
    img = np.hstack([img, np.full((img.shape[0], 4, 3), 255, np.uint8), rect])
    if not con_panel:
        return img
    # panel inferior: el STI de cada estacion con la pendiente ajustada, para auditar cada flecha
    panel = np.zeros((ALTO_PANEL, img.shape[1], 3), np.uint8)
    w = img.shape[1] // N_ESTACIONES
    for i in range(N_ESTACIONES):
        x0 = i * w
        if res and res[i]["sti"] is not None:
            r = res[i]
            s = r["sti"]
            s8 = np.clip(127 + 40 * s, 0, 255).astype(np.uint8)
            hh = ALTO_PANEL - 20
            th = cv2.resize(s8, (w - 4, hh), interpolation=cv2.INTER_AREA)
            panel[18:18 + hh, x0 + 2:x0 + w - 2] = th[..., None]
            if np.isfinite(r["pendiente"]):
                # pendiente en muestras/fila -> en pixeles del recuadro
                kx = (w - 4) / s.shape[1]
                ky = hh / s.shape[0]
                cx = x0 + w / 2
                dx = r["pendiente"] * kx * (hh / 2) / ky
                col = (80, 220, 80) if r["aceptada"] else (60, 60, 200)
                ok, q0, q1 = cv2.clipLine((x0 + 2, 18, w - 4, hh), (int(cx - dx), 18),
                                          (int(cx + dx), 18 + hh))
                if ok:
                    cv2.line(panel, q0, q1, col, 1, cv2.LINE_AA)
            et = (f"{i}: {r['v']:+.3f} m/s  c{r['coherencia']:.2f} b{r['bloques_activos']} "
                  f"{NOMBRE_ESCALA[r['escala']]}{' motas' if r.get('motas') else ''}" if r["aceptada"] else
                  f"{i}: {r['motivos'].split('+')[0]}  c{r['coherencia']:.2f} b{r['bloques_activos']}")
            col = (80, 220, 80) if r["aceptada"] else (60, 60, 200)
        else:
            et, col = f"{i}: llenando", (150, 150, 150)
        cv2.putText(panel, et, (x0 + 4, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.38, col, 1, cv2.LINE_AA)
    return np.vstack([img, panel])


def ocultar_clave(url):
    """rtsp://usuario:clave@host -> rtsp://usuario:***@host, para no imprimir contrasenas."""
    if "://" in url and "@" in url.split("://", 1)[1]:
        esquema, resto = url.split("://", 1)
        cred, host = resto.split("@", 1)
        if ":" in cred:
            return f"{esquema}://{cred.split(':', 1)[0]}:***@{host}"
    return url


def titulo_de(args):
    if getattr(args, "titulo", None):
        return args.titulo
    return os.path.basename(args.archivo) if args.archivo else ETIQUETA


def pantalla_espera(ventana, texto):
    """Imagen provisional mientras se abre un flujo (resolver un directo de YouTube tarda segundos)."""
    img = np.zeros((360, 1280, 3), np.uint8)
    cv2.putText(img, texto[:80], (30, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(img, "abriendo...", (30, 215), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (160, 160, 160), 1,
                cv2.LINE_AA)
    cv2.imshow(ventana, img)
    cv2.waitKey(1)


def guardar_vista(frame, geom, res, cfg, t, llenado, args, modo="dia"):
    """Imagen anotada a disco. Se escribe en un temporal y se renombra, para que quien la lea desde
    otro equipo (p. ej. el PC mirando la Raspberry) nunca vea una imagen a medio escribir."""
    estado = {"titulo": titulo_de(args),
              "t": t, "llenado": llenado, "retraso": 0.0, "modo": modo,
              "px_muestra": geom.px_por_muestra, "verificada": bool(cfg.get("escala_verificada"))}
    os.makedirs(CARPETA_SALIDAS, exist_ok=True)
    tmp = ARCHIVO_VISTA[:-4] + ".tmp.png"
    cv2.imwrite(tmp, dibujar(frame, geom, res, estado, False))
    os.replace(tmp, ARCHIVO_VISTA)


# ─────────────────────────────────────────── bucle ───────────────────────────────────────────────
def main():
    global PASO_MEDIDA_S
    # el titulo del directo es japones y la consola de Windows es cp1252
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--camara", default=CAMARA_POR_DEFECTO,
                    help=f"camara: {', '.join(sorted(CAMARAS))} o un nombre nuevo para una propia "
                         f"(por defecto {CAMARA_POR_DEFECTO})")
    ap.add_argument("--fuente", help="URL del video en directo (rtsp://..., http://...); sustituye "
                                     "a la de la camara y queda guardada en su config")
    ap.add_argument("--archivo", help="procesar un video grabado en vez del directo")
    ap.add_argument("--sin-ventana", action="store_true", help="sin interfaz, solo CSV")
    ap.add_argument("--duracion", type=float, default=0, help="segundos de flujo a procesar (0 = sin fin)")
    ap.add_argument("--paso-medida", type=float, default=PASO_MEDIDA_S,
                    help=f"segundos entre medidas (por defecto {PASO_MEDIDA_S:g})")
    ap.add_argument("--modo", choices=("auto", "dia", "noche"), default=MODO_POR_DEFECTO,
                    help="auto (por defecto): noche cuando la camara pasa a blanco y negro (infrarrojo)")
    ap.add_argument("--vista-cada", type=float, default=0,
                    help="sin ventana: guardar la imagen anotada cada N s de flujo (0 = solo al salir)")
    ap.add_argument("--elegir", action="store_true",
                    help="menu en la consola con las fuentes de fuentes.json (lo usa arrancar.bat)")
    args = ap.parse_args()
    args.ajustes, args.titulo = None, None
    # la fecha del archivo identifica la version: cambiar de fuente (c, 1-9) NO recarga el codigo,
    # hay que cerrar y volver a abrir el programa
    version = datetime.fromtimestamp(os.path.getmtime(os.path.abspath(__file__)))
    print(f"stiv_directo.py version {version:%Y-%m-%d %H:%M}")
    PASO_MEDIDA_S = args.paso_medida
    fuentes = cargar_fuentes()
    if args.elegir and fuentes:
        args = args_de_fuente(args, fuentes[menu_fuentes(fuentes)])
    actual = indice_fuente(args, fuentes)
    anterior = None
    while True:
        try:
            siguiente = ejecutar(args, fuentes, actual)
        except RuntimeError as e:
            if anterior is None:
                sys.exit(str(e))
            # la fuente nueva no abre (YouTube bloqueado, camara apagada...): se vuelve a la de antes
            print(f"{e}\nse vuelve a la fuente anterior", file=sys.stderr)
            args, actual = anterior
            anterior = None
            continue
        if siguiente is None:
            break
        anterior = (args, actual)
        args, actual = args_de_fuente(args, fuentes[siguiente]), siguiente
    if not args.sin_ventana:
        # en OpenCV sin interfaz (opencv-python-headless, el de la Raspberry) esto da error
        cv2.destroyAllWindows()


VENTANA = "STIV directo"


def ejecutar(args, fuentes, actual):
    """Mide una fuente hasta que se cierra (devuelve None) o se pide otra con c / 1-9 (devuelve su
    indice en `fuentes`). RuntimeError si no se puede abrir."""
    if not args.camara.replace("_", "").replace("-", "").isalnum():
        raise RuntimeError(f"camara '{args.camara}': solo letras, numeros, '_' y '-' "
                           f"(es el nombre de su carpeta)")
    elegir_camara(args.camara, args.fuente, args.ajustes)
    if not args.archivo and not URL_FUENTE:
        raise RuntimeError(f"la camara '{args.camara}' es nueva y no tiene URL: pasa --fuente rtsp://... "
                           f"o pon \"url\" en su entrada de fuentes.json")
    if args.archivo and not os.path.exists(args.archivo):
        raise RuntimeError(f"no existe el video {args.archivo}")
    if not args.sin_ventana:
        # WINDOW_NORMAL: redimensionable con el raton; KEEPRATIO: sin deformar la imagen. Con ella
        # OpenCV devuelve el raton en coordenadas de la imagen, asi que editar sigue funcionando.
        # La ventana es la misma para todas las fuentes: al cambiar no se cierra.
        cv2.namedWindow(VENTANA, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        cv2.setWindowTitle(VENTANA, f"STIV directo - {titulo_de(args)}")
        pantalla_espera(VENTANA, titulo_de(args))

    cfg = cargar_config()
    if args.fuente and cfg.get("url") != args.fuente:
        cfg["url"] = args.fuente
        guardar_config(cfg)
    if not os.path.exists(ARCHIVO_CONFIG):
        guardar_config(cfg)
    if not args.archivo and URL_FUENTE.startswith("rtsp"):
        # por TCP: por UDP se pierden paquetes en cuanto la red titubea y salen fotogramas rotos
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
    lector = Lector(args.archivo or URL_FUENTE, bool(args.archivo))
    print(f"abriendo {args.archivo}" if args.archivo else
          "resolviendo el flujo..." if lector.es_youtube else f"conectando a {ocultar_clave(URL_FUENTE)}")
    lector.start()
    lector.listo.wait()
    if not lector.abierto:
        raise RuntimeError(f"no se pudo abrir el flujo: {lector.error}")
    geom = Geometria(cfg, lector.fps)
    if FILTRO_DIRECCIONAL:
        print("filtro direccional activo: solo cuenta lo que avanza aguas abajo")
    print(f"{lector.titulo}\nfps {lector.fps:g} | DS {geom.ds * 1000:.1f} mm = {geom.px_por_muestra:.2f} px "
          f"| {len(geom.xs)} muestras/linea | escalas STI: " +
          ", ".join(f"{n} filas cada {dt * 1000:.0f} ms" for n, dt in zip(geom.n_filas, geom.dt_filas)))
    if geom.px_por_muestra < 0.2:
        print("aviso: DS < 0.2 px de imagen, el STI estaria submuestreado (aliasing)", file=sys.stderr)

    os.makedirs(CARPETA_SALIDAS, exist_ok=True)
    cabecera = ["hora_local", "t_flujo_s", "estacion", "y_m", "v_m_s", "coherencia", "bloques_activos",
                "aceptada", "motivos", "escala_verificada", "s_por_fila", "modo"]
    # si el CSV esta abierto en otro programa (Excel lo bloquea en Windows) no se puede apartar ni
    # escribir: entonces se escribe en uno nuevo con fecha en vez de abortar
    archivo_csv = ARCHIVO_CSV
    alternativo = ARCHIVO_CSV[:-4] + datetime.now().strftime("_%Y%m%d_%H%M%S.csv")
    if os.path.exists(archivo_csv):
        try:
            with open(archivo_csv, encoding="utf-8") as f:
                antiguo = f.readline().strip().split(",") != cabecera
        except PermissionError:
            archivo_csv, antiguo = alternativo, False
        if antiguo:
            # CSV de una version anterior con otras columnas: se aparta en vez de mezclar
            viejo = ARCHIVO_CSV[:-4] + datetime.now().strftime("_hasta_%Y%m%d_%H%M%S.csv")
            try:
                os.replace(archivo_csv, viejo)
                print(f"CSV con columnas antiguas apartado en {os.path.basename(viejo)}")
            except PermissionError:
                archivo_csv = alternativo
    try:
        nuevo = not os.path.exists(archivo_csv)
        fcsv = open(archivo_csv, "a", newline="", encoding="utf-8")
    except PermissionError:
        archivo_csv, nuevo = alternativo, True
        fcsv = open(archivo_csv, "a", newline="", encoding="utf-8")
    if archivo_csv != ARCHIVO_CSV:
        print(f"aviso: {os.path.basename(ARCHIVO_CSV)} esta abierto en otro programa (Excel?); "
              f"las medidas van a {os.path.basename(archivo_csv)}", file=sys.stderr)
    wcsv = csv.writer(fcsv)
    if nuevo:
        wcsv.writerow(cabecera)

    bufs = Buffers(geom)
    # modo noche/dia: fijo si se pide, o automatico por la saturacion (con histeresis: tres lecturas
    # seguidas iguales, una cada 5 s, para no oscilar al amanecer y al anochecer)
    modo = args.modo if args.modo != "auto" else None
    candidato, repeticiones, t_ult_modo = None, 0, -1e9
    brillos = deque(maxlen=30)    # brillo crudo a lo largo de las lineas, uno por segundo (deslumbramiento)
    medidor = Medidor()
    medidor.start()
    gen = 0                 # cambia cada vez que el buffer deja de ser continuo; descarta medidas viejas
    pts_prev, t_ult_medida, res = None, -1e9, None
    t_ini_flujo, reloj_ini, t = None, None, 0.0
    reanclar = False        # tras una discontinuidad, el reloj del flujo se re-ancla para que t siga creciendo
    n_fotogramas, coste_proceso = 0, 0.0
    t_ult_vista, reloj_arranque = 0.0, time.time()
    editando, congelado, arrastre, ultimo = False, False, None, None
    ventana = VENTANA
    cambio = None           # indice de la fuente pedida con c / 1-9
    texto_fuente = (f"fuente {actual + 1}/{len(fuentes)} | c siguiente, 1-{min(len(fuentes), 9)} elegir"
                    if actual is not None else f"c / 1-{min(len(fuentes), 9)}: fuentes de fuentes.json"
                    ) if len(fuentes) > 1 else ""
    escala_ventana, pantalla_completa = None, False   # la escala se fija con el primer fotograma
    con_panel = True

    if not args.sin_ventana:
        def raton(evento, x, y, flags, _):
            nonlocal arrastre, geom, res, gen
            if not editando:
                return
            if evento == cv2.EVENT_LBUTTONDOWN:
                d = np.hypot(*(geom.cuad - [x, y]).T)
                arrastre = int(np.argmin(d)) if d.min() < 30 else None
            elif evento == cv2.EVENT_MOUSEMOVE and arrastre is not None:
                cfg["cuadrilatero_px"][arrastre] = [int(x), int(y)]
                geom = Geometria(cfg, lector.fps)
                bufs.vaciar(); brillos.clear(); res = None; gen += 1
            elif evento == cv2.EVENT_LBUTTONUP and arrastre is not None:
                arrastre = None
                bufs.vaciar(); brillos.clear(); res = None; gen += 1
        cv2.setMouseCallback(ventana, raton)

    try:
        while True:
            item = lector.cola.get()
            if item is None:
                break
            if item == "corte":
                bufs.vaciar(); pts_prev = None; reanclar = True; gen += 1
                continue
            pts, frame = item
            c0 = time.perf_counter()
            n_fotogramas += 1
            if t_ini_flujo is None:
                t_ini_flujo, reloj_ini = pts, time.time()
            # modo noche/dia
            if args.modo == "auto" and (modo is None or t - t_ult_modo >= 5.0):
                t_ult_modo = t
                visto = "noche" if es_noche(geom, frame) else "dia"
                if modo is None:
                    modo = visto
                    print(f"modo {modo} (saturacion {geom.saturacion(frame):.1f})")
                elif visto != modo:
                    repeticiones = repeticiones + 1 if visto == candidato else 1
                    candidato = visto
                    if repeticiones >= 3:
                        modo, repeticiones = visto, 0
                        bufs.vaciar(); brillos.clear(); res = None; gen += 1
                        print(f"cambio a modo {modo}: el STI vuelve a llenarse")
                else:
                    candidato, repeticiones = None, 0
            if modo == "noche" and n_fotogramas % max(1, int(round(lector.fps))) == 1:
                brillos.append(geom.brillo(frame))
            fila = geom.procesar(frame, modo)
            # el STI exige filas equiespaciadas en tiempo: un hueco de PTS se rellena repitiendo la
            # ultima fila (lo mismo que hace YouTube con los duplicados). Un salto de mas de 1 s o un
            # PTS que RETROCEDE (camara o emisor reiniciado: el tiempo vuelve a empezar en 0, medido
            # con un servidor RTSP de prueba) es una discontinuidad: STI vacio y reloj re-anclado.
            # Sin re-anclar, t volvia atras y no se media hasta superar el t de antes del corte.
            if pts_prev is not None:
                pasos = (pts - pts_prev) * lector.fps
                if pasos < -0.5 or pasos > lector.fps + 1:
                    bufs.vaciar(); gen += 1; reanclar = True
                else:
                    for _ in range(int(round(pasos)) - 1):
                        bufs.repetir_ultima()
            if reanclar:
                t_ini_flujo = pts - (t + 1.0 / lector.fps)
                reloj_ini = time.time() - (t + 1.0 / lector.fps)
                reanclar = False
            # de dia, el mismo fotograma con el realce de motas (ver medir)
            bufs.agregar(fila, geom.procesar(frame, "noche") if modo == "dia" else None)
            pts_prev = pts
            t = pts - t_ini_flujo

            if bufs.rapida_llena() and t - t_ult_medida >= PASO_MEDIDA_S and medidor.libre():
                # las deques guardan referencias: copiar las listas es barato y el hilo apila
                medidor.entrada.put((gen, t, bufs.instantanea(), bufs.instantanea(1), geom,
                                     geom.cobertura(*frame.shape[:2]), modo, list(brillos)))
                t_ult_medida = t
            while not medidor.salida.empty():
                g_m, t_m, res_m = medidor.salida.get()
                if g_m != gen:
                    continue
                res = res_m
                hora = datetime.now().isoformat(timespec="seconds")
                for r in res:
                    wcsv.writerow([hora, f"{t_m:.2f}", r["estacion"], f"{r['y_m']:.3f}", f"{r['v']:.4f}",
                                   f"{r['coherencia']:.3f}", r["bloques_activos"], int(r["aceptada"]),
                                   r["motivos"], int(bool(cfg.get("escala_verificada"))),
                                   f"{r['dt_fila']:.3f}", modo + ("+motas" if r.get("motas") else "")])
                fcsv.flush()
                ac = [r["v"] for r in res if r["aceptada"]]
                # cola = fotogramas leidos y aun sin procesar: si crece sin parar, el equipo no da
                # abasto (al arrancar es normal que suba: el directo entrega varios segundos de golpe)
                # r/m/l = escala rapida (10 s), media (30 s) o lenta (60 s) en la que se midio; en mayusculas
                # si se midio con el realce de motas (agua sin textura con burbujas sueltas)
                print(f"t={t_m:7.1f}s {modo:5s} mediana {np.median(ac) if ac else float('nan'):.3f} m/s  "
                      f"{len(ac)}/{N_ESTACIONES} | " +
                      " ".join(f"{r['v']:+.3f}{('RML' if r.get('motas') else 'rml')[r['escala']]}"
                               if r["aceptada"] else
                               f"{r['motivos'].split('+')[0][:6]:>7s}" for r in res) +
                      f" | cola {lector.cola.qsize()}")

            coste_proceso += time.perf_counter() - c0
            if args.duracion and t >= args.duracion:
                break
            if args.sin_ventana:
                ultimo = frame
                if args.vista_cada and res and t - t_ult_vista >= args.vista_cada:
                    guardar_vista(ultimo, geom, res, cfg, t, bufs.llenado(), args, modo)
                    t_ult_vista = t
                continue

            # el directo llega a rafagas (al arrancar entrega varios segundos de golpe): se reproduce
            # a ritmo real segun el PTS, y si el proceso va retrasado se dibuja solo 1 de cada 3
            retraso = (time.time() - reloj_ini) - t
            if retraso < 0:
                time.sleep(min(-retraso, 0.1))
            elif retraso > 2.0 and int(t * lector.fps) % 3:
                continue
            estado = {"titulo": titulo_de(args), "t": t, "fuente": texto_fuente,
                      "llenado": bufs.llenado(), "retraso": max(retraso, 0.0), "modo": modo,
                      "px_muestra": geom.px_por_muestra, "verificada": bool(cfg.get("escala_verificada"))}
            if not congelado or ultimo is None:
                ultimo = frame
            vista = dibujar(ultimo, geom, res, estado, editando, con_panel)
            cv2.imshow(ventana, vista)
            if escala_ventana is None and not pantalla_completa:
                escala_ventana = ajustar_ventana(ventana, *vista.shape[:2])
            k = cv2.waitKey(1) & 0xFF
            if k == ord("q") or cv2.getWindowProperty(ventana, cv2.WND_PROP_VISIBLE) < 1:
                break
            if fuentes and (k == ord("c") or ord("1") <= k <= ord("9")):
                n = len(fuentes)
                pedida = ((actual + 1) % n if actual is not None else 0) if k == ord("c") else k - ord("1")
                if pedida < n and pedida != actual:
                    cambio = pedida
                    print(f"cambiando a: {fuentes[pedida]['titulo']}")
                    break
            if k == ord("e"):
                editando = not editando
            elif k == ord("g"):
                guardar_config(cfg)
                print(f"config guardada en {ARCHIVO_CONFIG}")
            elif k == ord("r"):
                bufs.vaciar(); brillos.clear(); res = None; gen += 1
            elif k == ord(" "):
                congelado = not congelado
            elif k == ord("f"):
                pantalla_completa = not pantalla_completa
                cv2.setWindowProperty(ventana, cv2.WND_PROP_FULLSCREEN,
                                      cv2.WINDOW_FULLSCREEN if pantalla_completa else cv2.WINDOW_NORMAL)
                if not pantalla_completa:
                    ajustar_ventana(ventana, *vista.shape[:2], escala_ventana)
            elif k == ord("p"):
                # cambia la proporcion de la imagen: la ventana se reajusta a la nueva
                con_panel = not con_panel
                escala_ventana = None
            elif k in (ord("+"), ord("-")) and not pantalla_completa:
                escala_ventana *= 1.15 if k == ord("+") else 1 / 1.15
                ajustar_ventana(ventana, *vista.shape[:2], escala_ventana)
    except KeyboardInterrupt:
        pass
    finally:
        if ultimo is not None:
            guardar_vista(ultimo, geom, res, cfg, t, bufs.llenado(), args, modo)
        detener_lector(lector)
        medidor.detener()
        fcsv.close()
        if n_fotogramas:
            print(f"{n_fotogramas} fotogramas, {t:.1f} s de flujo en {time.time() - reloj_arranque:.1f} s "
                  f"de reloj; lectura+muestreo {1000 * coste_proceso / n_fotogramas:.1f} ms/fotograma "
                  f"en el hilo principal (el directo da uno cada {1000 / lector.fps:.0f} ms); "
                  f"cola final {lector.cola.qsize()}")
            if medidor.n:
                print(f"medida: {1000 * medidor.segundos / medidor.n:.0f} ms de media en {medidor.n} "
                      f"medidas (cada {PASO_MEDIDA_S:g} s de flujo)")
    return cambio


if __name__ == "__main__":
    main()
