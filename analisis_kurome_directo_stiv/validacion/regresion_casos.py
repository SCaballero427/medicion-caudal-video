"""Grabaciones de la regresion: caso -> (camara, video[, modo]). Las de grabaciones/ (FFV1, 1-4 GB cada
una) estan fuera de git y se rehacen con grabar.py; los dos clips de raspberry/prueba/ si estan."""
import os

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grabaciones")
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CASOS = {
    "kurome": ("kurome", f"{D}/kurome.avi"),
    "myoshoji": ("myoshoji", f"{D}/myoshoji.avi"),
    "myoshoji_largo": ("myoshoji", f"{D}/myoshoji_largo.avi"),
    "myoshoji_dia20": ("myoshoji", f"{R}/raspberry/prueba/myoshoji_20s.mp4", "dia"),
    "myoshoji_noche": ("myoshoji", f"{R}/raspberry/prueba/myoshoji_noche_90s.mp4"),
    "shimoda": ("shimoda", f"{D}/shimoda.avi"),
    "shimoda2": ("shimoda", f"{D}/shimoda2.avi"),
    "shimoda3": ("shimoda", f"{D}/shimoda3.avi"),
    "akigawa": ("akigawa", f"{D}/akigawa.avi"),
}
