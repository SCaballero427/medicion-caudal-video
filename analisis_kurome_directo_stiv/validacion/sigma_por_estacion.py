"""Variante de prueba (no esta en el programa): antialias con sigma = medio paso de muestreo DE CADA
ESTACION, en vez de uno solo con la mediana. Se activa importando este modulo antes de correr."""
import numpy as np, cv2
import stiv_directo as sd

_orig_recorte = sd.Geometria._preparar_recorte


def _preparar_recorte(self, forma):
    paso = np.hypot(np.diff(self.map_x, axis=1), np.diff(self.map_y, axis=1))
    por_linea = np.median(paso, axis=1)                       # una por fila del mapa (linea)
    sig = np.maximum(0.7, np.round(por_linea / 2 * 2) / 2)    # redondeado a 0.5 px: pocos suavizados
    self._grupos = [(float(s), np.where(sig == s)[0]) for s in np.unique(sig)]
    self.px_por_muestra = float(2 * sig.max())                # el margen del recorte cubre el mayor
    _orig_recorte(self, forma)


def procesar(self, frame, modo="dia"):
    if getattr(self, "_forma", None) != frame.shape:
        self._preparar_recorte(frame.shape)
    y0, y1, x0, x1 = self._recorte
    gris = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    if modo == "noche":
        gris = cv2.morphologyEx(gris, cv2.MORPH_TOPHAT, self._nucleo)
    gris = gris.astype(np.float32)
    out = np.empty(self._mx.shape, np.float32)
    for s, filas in self._grupos:
        b = cv2.GaussianBlur(gris, (0, 0), s)
        out[filas] = cv2.remap(b, self._mx[filas], self._my[filas], cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    return out


sd.Geometria._preparar_recorte = _preparar_recorte
sd.Geometria.procesar = procesar
