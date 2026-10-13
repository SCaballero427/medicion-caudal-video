#!/usr/bin/env bash
# Instala el STIV en la Raspberry Pi: programas del sistema, entorno de Python con sus librerias y
# el servicio que lo arranca solo. Se puede repetir sin miedo (actualiza lo que haya).
#
#   bash raspberry/instalar.sh                        # normal
#   bash raspberry/instalar.sh --sobrescribir-config  # ademas pisa las configs de camara de la Pi
#                                                     # con las que vinieron del PC
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USUARIO="$(id -un)"
SOBRESCRIBIR=0
[ "${1:-}" = "--sobrescribir-config" ] && SOBRESCRIBIR=1

paso() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }

if [ "$(id -u)" -eq 0 ]; then
    echo "Ejecutalo con tu usuario normal, sin sudo (el script pide sudo cuando lo necesita)."
    exit 1
fi

paso "Carpeta: $RAIZ   usuario: $USUARIO   arquitectura: $(uname -m)"
if [ "$(uname -m)" != "aarch64" ]; then
    echo "AVISO: no es un sistema de 64 bits (aarch64). Graba 'Raspberry Pi OS Lite (64-bit)':"
    echo "       en 32 bits OpenCV no tiene paquete listo y la instalacion puede fallar o tardar horas."
fi

paso "1/5 Programas del sistema (python3-venv, ffmpeg)"
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip ffmpeg

paso "2/5 Entorno de Python en $RAIZ/.venv"
python3 -m venv "$RAIZ/.venv"
"$RAIZ/.venv/bin/pip" install --upgrade pip
"$RAIZ/.venv/bin/pip" install --upgrade -r "$RAIZ/raspberry/requirements-raspberry.txt"
"$RAIZ/.venv/bin/python" -c "import cv2, numpy, yt_dlp; print('librerias ok: OpenCV', cv2.__version__, '| numpy', numpy.__version__, '| yt-dlp', yt_dlp.version.__version__)"

paso "3/5 Configuracion"
if [ ! -f "$RAIZ/raspberry/stiv.conf" ]; then
    cp "$RAIZ/raspberry/stiv.conf.ejemplo" "$RAIZ/raspberry/stiv.conf"
    echo "creado raspberry/stiv.conf (prueba con el video que trae el paquete)"
else
    echo "raspberry/stiv.conf ya existe: se deja como esta"
fi
# configs de camara traidas del PC (cuadrilatero, URL...): solo si la Pi no tiene ya la suya
if [ -d "$RAIZ/raspberry/config_pc" ]; then
    for origen in "$RAIZ"/raspberry/config_pc/*/config_stiv_directo.json; do
        [ -f "$origen" ] || continue
        camara="$(basename "$(dirname "$origen")")"
        destino="$RAIZ/salidas/$camara/config_stiv_directo.json"
        if [ ! -f "$destino" ] || [ "$SOBRESCRIBIR" -eq 1 ]; then
            mkdir -p "$(dirname "$destino")"
            cp "$origen" "$destino"
            echo "config de '$camara' copiada desde el PC"
        else
            echo "config de '$camara': la Pi ya tiene una, se conserva (--sobrescribir-config para pisarla)"
        fi
    done
fi
chmod +x "$RAIZ"/raspberry/*.sh

paso "4/5 Servicio (arranque automatico)"
if [ -d /run/systemd/system ]; then
    sed -e "s|__USUARIO__|$USUARIO|g" -e "s|__RAIZ__|$RAIZ|g" "$RAIZ/raspberry/stiv.service" \
        | sudo tee /etc/systemd/system/stiv.service > /dev/null
    sudo systemctl daemon-reload
    if systemctl is-enabled --quiet stiv 2>/dev/null || systemctl is-active --quiet stiv; then
        sudo systemctl restart stiv
        echo "servicio activado: reiniciado con el codigo nuevo"
    else
        echo "servicio instalado pero NO activado: activalo con  ./raspberry/stiv.sh activar"
    fi
else
    echo "AVISO: este sistema no usa systemd; el servicio no se instala (prueba a mano con stiv.sh prueba)"
fi

paso "5/5 Listo"
cat <<EOF
Siguientes pasos (desde $RAIZ):
  ./raspberry/stiv.sh prueba      # 20 s del video de prueba: comprueba que todo va y cuanto tarda la Pi
  ./raspberry/stiv.sh activar     # que arranque solo en cada encendido (y ahora)
  ./raspberry/stiv.sh ayuda       # el resto de ordenes
EOF
