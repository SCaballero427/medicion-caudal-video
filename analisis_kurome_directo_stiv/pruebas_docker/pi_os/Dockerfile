# "Raspberry Pi OS de verdad": la imagen oficial de Raspberry Pi OS Lite (trixie, arm64), sin tocar,
# arrancada en una maquina virtual QEMU (aarch64, cortex-a72 como la Pi 4, 4 nucleos, 4 GB) dentro de
# este contenedor. A diferencia de pi_falsa/ (un Debian con systemd), aqui arranca el sistema entero:
# kernel, initramfs de la imagen (expande la particion como en la tarjeta), cloud-init (crea el
# usuario y activa SSH como lo hace Raspberry Pi Imager) y los servicios de Raspberry Pi OS.
#
# Lo unico que no es de la imagen es el kernel: el de serie no trae controladores para el hardware
# virtual de QEMU (virtio, PCI generico), asi que se recompila desde la misma fuente oficial
# (raspberrypi/linux, etiqueta del mismo dia que el de la imagen), con su misma configuracion, su
# mismo compilador y su mismo nombre de version, mas esos controladores. Asi los modulos que trae la
# imagen siguen cargando.
#
# Sigue siendo emulado: la velocidad NO dice nada de una Pi real, no hay VideoCore (vcgencmd falla),
# ni sensor de temperatura, ni tarjeta SD real. Ver ../LEEME.md.

ARG FECHA=2026-10-06
ARG NOMBRE=2026-10-06-raspios-trixie-arm64-lite
ARG ETIQUETA_KERNEL=stable_20260911
ARG VERSION_KERNEL=6.18.50+rpt-rpi-v8

# -- 1. imagen oficial, comprobada, y la configuracion de su kernel -------------------------------
FROM debian:trixie AS imagen
ARG FECHA
ARG NOMBRE
ARG VERSION_KERNEL
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates xz-utils e2fsprogs fdisk \
    && rm -rf /var/lib/apt/lists/*
RUN url="https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-${FECHA}/${NOMBRE}.img.xz" \
    && curl -fsSL -o /sd.img.xz "$url" && curl -fsSL -o /sd.sha256 "$url.sha256" \
    && echo "$(cut -d' ' -f1 /sd.sha256)  /sd.img.xz" | sha256sum -c - \
    && xz -dc /sd.img.xz > /sd.img \
    && inicio=$(sfdisk -d /sd.img | awk '/sd.img2/ {gsub(",","",$4); print $4}') \
    && tam=$(sfdisk -d /sd.img | awk '/sd.img2/ {gsub(",","",$6); print $6}') \
    && dd if=/sd.img of=/raiz.img bs=4M iflag=skip_bytes,count_bytes \
          skip=$((inicio * 512)) count=$((tam * 512)) status=none \
    && debugfs -R "dump /boot/config-${VERSION_KERNEL} /config" /raiz.img \
    && test -s /config && rm /sd.img /raiz.img

# -- 2. kernel: misma fuente, misma configuracion + el hardware virtual de QEMU -------------------
FROM debian:trixie AS kernel
ARG ETIQUETA_KERNEL
ARG VERSION_KERNEL
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates make bc bison flex libssl-dev libelf-dev kmod cpio python3 \
        gcc gcc-aarch64-linux-gnu libc6-dev \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "$ETIQUETA_KERNEL" https://github.com/raspberrypi/linux /linux
WORKDIR /linux
COPY --from=imagen /config .config
# Todo integrado (=y), no como modulo: el initramfs de la imagen solo lleva modulos de la Pi.
# GPIO_PL061 + KEYBOARD_GPIO: el boton de apagado de QEMU, para que "docker stop" apague el sistema
# ordenadamente. No se activa el reloj PL031: la Pi 4 no tiene reloj propio y aqui tampoco.
RUN scripts/config --enable PCI_HOST_GENERIC --enable VIRTIO_MENU --enable VIRTIO \
        --enable VIRTIO_PCI --enable VIRTIO_MMIO --enable VIRTIO_BLK --enable VIRTIO_NET \
        --enable HW_RANDOM_VIRTIO --enable GPIO_PL061 --enable KEYBOARD_GPIO \
    && make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig \
    && for o in PCI_HOST_GENERIC VIRTIO_PCI VIRTIO_BLK VIRTIO_NET GPIO_PL061 KEYBOARD_GPIO; do \
           grep -q "^CONFIG_$o=y" .config || { echo "falta CONFIG_$o"; exit 1; }; done \
    && test "$(make -s kernelversion)" = "${VERSION_KERNEL%%+*}"
RUN make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- KERNELRELEASE="$VERSION_KERNEL" \
        -j"$(nproc)" Image \
    && test "$(cat include/config/kernel.release)" = "$VERSION_KERNEL"

# -- 3. el contenedor final: QEMU + la imagen + el kernel ------------------------------------------
FROM debian:trixie
RUN apt-get update && apt-get install -y --no-install-recommends \
        qemu-system-arm qemu-utils mtools fdisk xz-utils socat openssl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=imagen /sd.img.xz /opt/raspios/sd.img.xz
COPY --from=kernel /linux/arch/arm64/boot/Image /opt/kernel/Image
COPY arrancar_vm.sh /usr/local/bin/arrancar_vm.sh
# en Windows, git puede dejar el script con finales CRLF, y bash no los acepta
RUN sed -i 's/\r$//' /usr/local/bin/arrancar_vm.sh && chmod +x /usr/local/bin/arrancar_vm.sh
# el disco de la "tarjeta SD" vive en un volumen: sobrevive a parar y volver a arrancar
VOLUME /datos
STOPSIGNAL SIGTERM
CMD ["/usr/local/bin/arrancar_vm.sh"]
