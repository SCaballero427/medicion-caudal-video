#!/usr/bin/env bash
# Ordenes para manejar el STIV en la Raspberry Pi. Uso:  ./raspberry/stiv.sh <orden>
set -uo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$RAIZ/.venv/bin/python"
CONF="$RAIZ/raspberry/stiv.conf"
CLIP="raspberry/prueba/myoshoji_20s.mp4"            # de dia (guardado en gris: hay que forzar --modo dia)
CLIP_NOCHE="raspberry/prueba/myoshoji_noche_90s.mp4"  # de noche: motas sobre agua negra, ~0.05 m/s
cd "$RAIZ"

ayuda() {
    cat <<'EOF'
Uso: ./raspberry/stiv.sh <orden>

  prueba [n]       mide el video de prueba que trae el paquete (sin camara ni internet) y dice si la
                   Pi da abasto; n = vueltas seguidas (1), para ver si se calienta. Para el servicio.
  prueba-noche     lo mismo con el video de noche (modo noche, escalas lentas: tarda mas)
  prueba-conf [s]  ejecuta s segundos (60 por defecto) con lo que diga stiv.conf (camara/YouTube)
  activar          arranque automatico en cada encendido, y lo arranca ya
  desactivar       quita el arranque automatico y lo para
  arrancar | parar | reiniciar    (reiniciar: tras cambiar el codigo o stiv.conf)
  estado           si esta corriendo y sus ultimas lineas
  registro         lo que imprime, en vivo (Ctrl+C para salir; el programa sigue)
  medidas          ultimas filas de cada CSV de medidas
  salud            temperatura, recortes de velocidad por calor/alimentacion, disco y memoria
  editar           abre stiv.conf con nano (guardar: Ctrl+O Enter, salir: Ctrl+X)
EOF
}

parar_si_activo() {
    # tambien si solo esta activado: entre dos relanzamientos is-active da falso y el servicio
    # volveria a arrancar a mitad de la prueba, compitiendo con ella por la CPU
    if systemctl is-active --quiet stiv 2>/dev/null || systemctl is-enabled --quiet stiv 2>/dev/null; then
        echo "(se para el servicio durante la prueba; para volver a ponerlo en marcha: ./raspberry/stiv.sh arrancar)"
        sudo systemctl stop stiv
    fi
}

temperatura() {
    if command -v vcgencmd > /dev/null; then vcgencmd measure_temp | cut -d= -f2
    elif [ -r /sys/class/thermal/thermal_zone0/temp ]; then
        awk '{printf "%.1f'"'"'C\n", $1/1000}' /sys/class/thermal/thermal_zone0/temp
    else echo "?"; fi
}

orden="${1:-ayuda}"
case "$orden" in
    prueba)
        [ -f "$CLIP" ] || { echo "falta $CLIP"; exit 1; }
        parar_si_activo
        vueltas="${2:-1}"
        echo "temperatura antes: $(temperatura)"
        for _ in $(seq "$vueltas"); do
            "$PY" stiv_directo.py --camara myoshoji --archivo "$CLIP" --modo dia --sin-ventana --paso-medida 2 --vista-cada 5 \
                2>&1 | grep -v '^\[h264'
        done
        echo "temperatura despues: $(temperatura)"
        cat <<'EOF'

Como leerlo (ultima linea):
  - "X s de flujo en Y s de reloj": si Y es MENOR que X, la Pi procesa mas rapido que el tiempo real.
  - "medida: Z ms": cuanto tarda cada medida; tiene que ser menor que --paso-medida (5 s en stiv.conf).
  - Las velocidades de este video NO valen como medida (esta recodificado); solo prueban que funciona.
  Imagen: salidas/myoshoji/ultima_vista.png (traela al PC con traer_resultados.ps1).
EOF
        ;;
    prueba-noche)
        [ -f "$CLIP_NOCHE" ] || { echo "falta $CLIP_NOCHE"; exit 1; }
        parar_si_activo
        echo "temperatura antes: $(temperatura)"
        "$PY" stiv_directo.py --camara myoshoji --archivo "$CLIP_NOCHE" --modo auto --sin-ventana --paso-medida 5 --vista-cada 10 \
            2>&1 | grep -v '^\[h264'
        echo "temperatura despues: $(temperatura)"
        echo
        echo "Tiene que decir 'modo noche' y, a partir de t=30 s, medir varias estaciones a ~0.03-0.07 m/s"
        echo "(letra m o l tras cada valor: escala de 30 s o de 60 s). Imagen: salidas/myoshoji/ultima_vista.png"
        ;;
    prueba-conf)
        [ -f "$CONF" ] || { echo "falta $CONF: ejecuta antes raspberry/instalar.sh"; exit 1; }
        parar_si_activo
        set -a; . "$CONF"; set +a
        # shellcheck disable=SC2086  # STIV_ARGS se parte en palabras a proposito
        "$PY" stiv_directo.py --sin-ventana $STIV_ARGS --duracion "${2:-60}" 2>&1 | grep -v '^\[h264'
        ;;
    activar)     sudo systemctl enable --now stiv && echo "activado: arrancara solo en cada encendido" ;;
    desactivar)  sudo systemctl disable --now stiv && echo "desactivado y parado" ;;
    arrancar)    sudo systemctl start stiv && echo "arrancado" ;;
    parar)       sudo systemctl stop stiv && echo "parado" ;;
    reiniciar)   sudo systemctl restart stiv && echo "reiniciado" ;;
    estado)      systemctl status stiv --no-pager -n 15 ;;
    registro)    journalctl -u stiv -f -n 30 ;;
    medidas)
        for f in salidas/*/medidas_directo.csv; do
            [ -f "$f" ] || continue
            echo "== $f ($(($(wc -l < "$f") - 1)) filas)"; tail -n 9 "$f"
        done
        ;;
    salud)
        echo "temperatura: $(temperatura)   (por encima de ~80 C la Pi se frena sola)"
        if command -v vcgencmd > /dev/null; then
            t="$(vcgencmd get_throttled | cut -d= -f2)"
            echo "get_throttled: $t   (0x0 = nunca se ha frenado; otro valor = calor o fuente insuficiente)"
        fi
        echo; df -h "$RAIZ" | sed 1d | awk '{print "disco: " $4 " libres de " $2 " (" $5 " usado)"}'
        free -h | awk '/Mem:/ {print "memoria: " $7 " disponibles de " $2}'
        echo "encendida: $(uptime -p)"
        echo "servicio: $(systemctl is-active stiv 2>/dev/null) / arranque automatico: $(systemctl is-enabled stiv 2>/dev/null)"
        ;;
    editar)      nano "$CONF" && echo "si cambiaste algo: ./raspberry/stiv.sh reiniciar" ;;
    ayuda|-h|--help) ayuda ;;
    *) echo "orden desconocida: $orden"; echo; ayuda; exit 1 ;;
esac
