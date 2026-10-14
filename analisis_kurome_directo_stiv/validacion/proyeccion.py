"""Modelo de camara de Heiskanen (formato GeoCorrectionParameter de Hydro-STIV) -> pixeles.
Prueba convenciones de rotacion/signo y dibuja las lineas de busqueda sobre el fotograma nativo."""
import os, sys, itertools, xml.etree.ElementTree as ET
import numpy as np, cv2

WORKSPACE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BASE = os.path.join(WORKSPACE, "datasets vision velocimetria", "Heiskanen_et_al_river_flow_camera_data")


def leer_modelo(ruta):
    r = ET.parse(ruta).getroot()
    return {e.tag: float(e.text) if e.text not in ("true", "false") else e.text for e in r}


def rx(a): c, s = np.cos(a), np.sin(a); return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
def ry(a): c, s = np.cos(a), np.sin(a); return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
def rz(a): c, s = np.cos(a), np.sin(a); return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def matriz(m, orden, traspuesta):
    R = {"xyz": rx(m["Omega"]) @ ry(m["Phi"]) @ rz(m["Kappa"]),
         "zyx": rz(m["Kappa"]) @ ry(m["Phi"]) @ rx(m["Omega"])}[orden]
    return R.T if traspuesta else R


def proyectar(m, XYZ, orden, traspuesta, sx, sy):
    R = matriz(m, orden, traspuesta)
    d = np.asarray(XYZ, float) - [m["X0"], m["Y0"], m["Z0"]]
    u, v, w = (d @ R).T          # filas de R^T . d
    x = m["Xc"] + sx * m["C"] * u / w
    y = m["Yc"] + sy * m["C"] * v / w
    return np.stack([x, y], 1), w


def lineas(rio="OulankajokiRiver"):
    a = np.genfromtxt(f"{BASE}/STIV_search_lines/Search_lines_{rio}.csv", delimiter=",", skip_header=1)
    return a[:, 1:5]


if __name__ == "__main__":
    modelo, frame_path, z = sys.argv[1], sys.argv[2], float(sys.argv[3])
    m = leer_modelo(modelo)
    L = lineas(sys.argv[4] if len(sys.argv) > 4 else "OulankajokiRiver")
    P = np.concatenate([np.c_[L[:, 0:2], np.full(len(L), z)], np.c_[L[:, 2:4], np.full(len(L), z)]])
    img = cv2.imread(frame_path)
    for k, (orden, tr, sx, sy) in enumerate(itertools.product(("xyz", "zyx"), (False, True), (1, -1), (1, -1))):
        p, w = proyectar(m, P, orden, tr, sx, sy)
        dentro = ((p[:, 0] >= 0) & (p[:, 0] < 3840) & (p[:, 1] >= 0) & (p[:, 1] < 2160)).mean()
        print(k, orden, tr, sx, sy, f"dentro {dentro:.2f} signo_w {np.sign(w).mean():+.1f}",
              f"x {p[:,0].min():.0f}..{p[:,0].max():.0f} y {p[:,1].min():.0f}..{p[:,1].max():.0f}")
        if dentro > 0.9:
            im = img.copy()
            n = len(L)
            for i in range(n):
                a, b = p[i] / 4, p[i + n] / 4
                cv2.line(im, tuple(int(t) for t in a), tuple(int(t) for t in b), (0, 0, 255), 2)
                cv2.circle(im, tuple(int(t) for t in a), 3, (0, 255, 0), -1)
                cv2.putText(im, str(i + 1), tuple(int(t) for t in b), 0, 0.4, (255, 0, 255), 1)
            cv2.imwrite(f"proy_{k}.jpg", im)
