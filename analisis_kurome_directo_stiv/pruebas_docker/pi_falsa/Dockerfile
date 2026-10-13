# "Raspberry Pi falsa": Debian 13 para ARM de 64 bits (Raspberry Pi OS es Debian), con systemd de
# verdad y SSH, para probar el paquete raspberry/ sin tener la placa. Se construye para linux/arm64:
# Docker Desktop lo emula con QEMU, asi que es LENTO y su velocidad no dice nada de una Pi real.
FROM debian:trixie

# python3 viene de serie en Raspberry Pi OS Lite. dbus tambien: sin el, `systemctl status` como
# usuario normal falla ("Failed to connect to system scope bus").
RUN apt-get update && apt-get install -y --no-install-recommends \
        systemd systemd-sysv dbus openssh-server sudo python3 ca-certificates procps nano \
    && rm -rf /var/lib/apt/lists/*

# como en Raspberry Pi OS: un usuario normal con sudo. Aqui sudo NO pide contrasena, para que la
# prueba no necesite a nadie delante; en la Pi real si la pide (por eso subir_a_raspberry usa ssh -t).
RUN useradd -m -s /bin/bash stiv && echo 'stiv:clave' | chpasswd && usermod -aG sudo stiv \
    && echo 'stiv ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/stiv \
    && mkdir -p /home/stiv/.ssh && chmod 700 /home/stiv/.ssh && chown -R stiv:stiv /home/stiv/.ssh \
    && systemctl enable ssh

# systemd como proceso principal, para poder probar el servicio y el arranque automatico
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
