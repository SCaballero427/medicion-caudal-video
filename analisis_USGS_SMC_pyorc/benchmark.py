"""Medida de los recursos que consume cada etapa del pipeline.

Para que sirve
--------------
El PIV es con diferencia la etapa cara del pipeline, y su coste no es obvio: xarray y dask
construyen el calculo de forma perezosa, asi que el tiempo no se gasta donde parece. La linea
que dispara el trabajo de verdad es `to_netcdf`, no `get_piv`. Midiendo por bloques se ve
donde se va el tiempo y cuanta memoria hace falta antes de subir N_FRAMES o bajar la
resolucion.

Que se mide
-----------
- **tiempo de reloj**: lo que tarda de verdad, incluida la espera por disco.
- **tiempo de CPU**: suma de todos los nucleos. Dividido por el tiempo de reloj da cuantos
  nucleos se estan usando en paralelo de media. Si sale ~1 en el PIV, no se esta paralelizando.
- **RAM pico**: el maximo de memoria residente del proceso durante el bloque. Es el numero que
  decide si un video mas largo cabe o no. Se muestrea en un hilo aparte, porque leer la memoria
  solo al principio y al final se pierde justo el pico.
- **RAM neta**: lo que queda ocupado al terminar el bloque. Un valor alto significa que el
  bloque ha dejado datos vivos (un dataset cargado, por ejemplo), no que haya fugado.

Uso
---
    import benchmark

    with benchmark.medir("PIV: get_piv + to_netcdf"):
        piv = da_norm_proj.frames.get_piv()
        piv.to_netcdf(SALIDA_PIV_CRUDO)

    benchmark.tabla()   # DataFrame con todo lo medido hasta ahora
"""

import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

import pandas as pd
import psutil

#: Todas las mediciones de la sesion, en orden. `medir` va anadiendo aqui.
MEDICIONES = []


@dataclass
class Medicion:
    """Resultado de cronometrar un bloque de codigo."""

    etiqueta: str
    segundos: float
    cpu_segundos: float
    ram_pico_mb: float
    ram_neta_mb: float
    extra: dict = field(default_factory=dict)

    @property
    def nucleos_medios(self):
        """Nucleos usados en paralelo de media. 1.0 = un solo hilo saturado."""
        return self.cpu_segundos / self.segundos if self.segundos > 0 else 0.0

    def __str__(self):
        return (f"{self.etiqueta}: {self.segundos:.1f} s | "
                f"CPU {self.cpu_segundos:.1f} s ({self.nucleos_medios:.1f} nucleos) | "
                f"RAM pico {self.ram_pico_mb:.0f} MB")


class _VigilanteRAM(threading.Thread):
    """Muestrea la memoria del proceso en segundo plano para capturar el pico real."""

    def __init__(self, proceso, intervalo=0.05):
        super().__init__(daemon=True)
        self.proceso = proceso
        self.intervalo = intervalo
        self.pico = proceso.memory_info().rss
        self._parar = threading.Event()

    def run(self):
        while not self._parar.is_set():
            try:
                self.pico = max(self.pico, self.proceso.memory_info().rss)
            except psutil.Error:
                break
            # wait() en vez de sleep() para poder cortar en cuanto termine el bloque.
            self._parar.wait(self.intervalo)

    def parar(self):
        self._parar.set()
        self.join(timeout=1.0)
        return self.pico


@contextmanager
def medir(etiqueta, registro=None, verbose=True, **extra):
    """Cronometra un bloque y guarda tiempo, CPU y memoria.

    Parametros
    ----------
    etiqueta : str
        Nombre con el que aparecera en la tabla.
    registro : list, opcional
        Donde acumular el resultado. Por defecto, la lista global MEDICIONES.
    verbose : bool
        Imprimir el resumen al terminar.
    **extra
        Cualquier dato del contexto que convenga guardar junto a la medida
        (n_frames=250, resolution=0.004...). Aparece como columnas en la tabla.
    """
    registro = MEDICIONES if registro is None else registro
    proceso = psutil.Process(os.getpid())

    ram_inicial = proceso.memory_info().rss
    vigilante = _VigilanteRAM(proceso)
    vigilante.start()

    cpu_0 = proceso.cpu_times()
    # perf_counter es monotono: no lo afectan los cambios de hora del sistema.
    t_0 = time.perf_counter()
    try:
        yield
    finally:
        # En finally para que un error dentro del bloque no deje el hilo vivo ni pierda
        # la medida de lo que si se llego a ejecutar.
        segundos = time.perf_counter() - t_0
        cpu_1 = proceso.cpu_times()
        pico = vigilante.parar()

        m = Medicion(
            etiqueta=etiqueta,
            segundos=segundos,
            cpu_segundos=(cpu_1.user - cpu_0.user) + (cpu_1.system - cpu_0.system),
            ram_pico_mb=pico / 1e6,
            ram_neta_mb=(proceso.memory_info().rss - ram_inicial) / 1e6,
            extra=extra,
        )
        registro.append(m)
        if verbose:
            print(f"  [bench] {m}")


def tabla(registro=None):
    """Devuelve un DataFrame con todas las mediciones acumuladas."""
    registro = MEDICIONES if registro is None else registro
    if not registro:
        return pd.DataFrame()
    filas = []
    for m in registro:
        fila = {
            "etapa": m.etiqueta,
            "segundos": round(m.segundos, 2),
            "cpu_s": round(m.cpu_segundos, 2),
            "nucleos": round(m.nucleos_medios, 2),
            "ram_pico_mb": round(m.ram_pico_mb, 1),
            "ram_neta_mb": round(m.ram_neta_mb, 1),
        }
        fila.update(m.extra)
        filas.append(fila)
    df = pd.DataFrame(filas)
    # Porcentaje del tiempo total, para ver de un vistazo quien manda.
    df["pct_tiempo"] = (100 * df["segundos"] / df["segundos"].sum()).round(1)
    return df


def entorno():
    """Ficha de la maquina, para que los tiempos signifiquen algo al releerlos."""
    vm = psutil.virtual_memory()
    return {
        "cpu_nucleos_fisicos": psutil.cpu_count(logical=False),
        "cpu_nucleos_logicos": psutil.cpu_count(logical=True),
        "ram_total_gb": round(vm.total / 1e9, 1),
        "ram_disponible_gb": round(vm.available / 1e9, 1),
    }


def reiniciar(registro=None):
    """Vacia las mediciones. Util si se reejecuta el notebook sin reiniciar el kernel."""
    (MEDICIONES if registro is None else registro).clear()
