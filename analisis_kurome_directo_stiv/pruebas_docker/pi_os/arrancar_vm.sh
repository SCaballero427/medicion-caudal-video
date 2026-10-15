#!/bin/bash
# Arranca Raspberry Pi OS en QEMU. La primera vez "graba la tarjeta": descomprime la imagen oficial
# en el volumen, escribe el user-data de cloud-init en la particion de arranque (lo mismo que hace
# Raspberry Pi Imager al ponerle usuario y SSH) y agranda el disco al tamano de la microSD; la
# expansion de la particion la hace luego el propio sistema en su primer arranque, como en la Pi.
set -euo pipefail

DISCO=/datos/sd.img
TAMANO_SD=${TAMANO_SD:-32G}       # microSD de 32 GB, la que pide raspberry/LEEME.md
CPUS=${CPUS:-4}                   # Pi 4B: 4 nucleos Cortex-A72
MEMORIA=${MEMORIA:-4G}            # Pi 4B de 4 GB
USUARIO=${USUARIO:-stiv}
CLAVE=${CLAVE:-clave}
NOMBRE_EQUIPO=${NOMBRE_EQUIPO:-stiv-rio}
TRABAJO=/run/vm
mkdir -p "$TRABAJO"

# desplazamiento en bytes de la particion n de la imagen
particion() { sfdisk -d "$1" | awk -v p="$1$2" '$1 == p {gsub(",","",$4); print $4 * 512}'; }

if [ ! -f "$DISCO" ]; then
    echo "== primer arranque: grabando la 'tarjeta SD' (imagen oficial de Raspberry Pi OS)"
    xz -dc /opt/raspios/sd.img.xz > "$DISCO.tmp"
    arranque=$(particion "$DISCO.tmp" 1)

    # cloud-init: el formato del ejemplo oficial de Raspberry Pi (enable_ssh, sudo sin contrasena)
    llave=""
    if [ -s /llave/llave_prueba.pub ]; then
        llave="  ssh_authorized_keys:
  - $(cat /llave/llave_prueba.pub)"
    fi
    cat > "$TRABAJO/user-data" <<EOF
#cloud-config
hostname: $NOMBRE_EQUIPO
manage_etc_hosts: true
users:
- name: $USUARIO
  groups: users,adm,dialout,audio,netdev,video,plugdev,cdrom,games,input,gpio,spi,i2c,render,sudo
  shell: /bin/bash
  lock_passwd: false
  passwd: $(openssl passwd -6 "$CLAVE")
  sudo: ALL=(ALL) NOPASSWD:ALL
$llave
enable_ssh: true
ssh_pwauth: true
EOF
    mcopy -o -i "$DISCO.tmp@@$arranque" "$TRABAJO/user-data" ::user-data
    qemu-img resize -q -f raw "$DISCO.tmp" "$TAMANO_SD"
    mv "$DISCO.tmp" "$DISCO"
    echo "== tarjeta lista ($TAMANO_SD); usuario $USUARIO"
fi

# Lo que el firmware de la Pi leeria de la particion de arranque: initramfs8 y cmdline.txt. Se leen
# en cada arranque, porque el sistema los reescribe (p. ej. quita "resize" tras expandir).
arranque=$(particion "$DISCO" 1)
mcopy -o -n -i "$DISCO@@$arranque" ::initramfs8 "$TRABAJO/initramfs8"
mcopy -o -n -i "$DISCO@@$arranque" ::cmdline.txt "$TRABAJO/cmdline.txt"
# serial0 es un alias del arbol de dispositivos de la Pi; en la maquina virtual la consola es ttyAMA0
CMDLINE=$(tr -d '\n' < "$TRABAJO/cmdline.txt" | sed 's/console=serial0,/console=ttyAMA0,/')
echo "== cmdline: $CMDLINE"

qemu-system-aarch64 \
    -M virt -cpu cortex-a72 -smp "$CPUS" -m "$MEMORIA" -accel tcg,thread=multi \
    -kernel /opt/kernel/Image -initrd "$TRABAJO/initramfs8" -append "$CMDLINE" \
    -drive file="$DISCO",format=raw,if=virtio,cache=writeback,discard=unmap \
    -netdev user,id=red,hostfwd=tcp::22-:22 -device virtio-net-pci,netdev=red,romfile= \
    -device virtio-rng-pci \
    -display none -monitor none -serial stdio \
    -qmp unix:"$TRABAJO/qmp.sock",server=on,wait=off &
QEMU=$!

# "docker stop" -> boton de apagado de la maquina virtual -> systemd apaga ordenadamente
apagar() {
    echo "== apagando Raspberry Pi OS (boton de apagado)"
    { echo '{"execute":"qmp_capabilities"}'; sleep 1; echo '{"execute":"system_powerdown"}'; sleep 1; } \
        | socat - UNIX-CONNECT:"$TRABAJO/qmp.sock" > /dev/null 2>&1 || true
    for _ in $(seq 100); do kill -0 "$QEMU" 2> /dev/null || return 0; sleep 1; done
    echo "== no se apago en 100 s: se corta"
    kill "$QEMU" 2> /dev/null || true
}
trap apagar TERM INT
# wait vuelve tambien cuando llega la senal; se repite hasta que QEMU termine de verdad
while kill -0 "$QEMU" 2> /dev/null; do wait "$QEMU" || true; done
