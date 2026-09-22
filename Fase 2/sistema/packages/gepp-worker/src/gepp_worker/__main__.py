"""`python -m gepp_worker`: vigilante y trabajador en procesos separados (ADR-009).

En procesos separados para que un detector lento no detenga la captura: el vigilante sigue
encolando mientras el trabajador procesa. Se comunican solo por Redis.

Configuración desde el entorno (ver `.env.example`):

    GEPP_BD_URL · GEPP_REDIS_URL · GEPP_CARPETA_VIGILADA · GEPP_CARPETA_EVIDENCIA
    GEPP_FPS_OBJETIVO · GEPP_FUENTE_ID (fuente a la que pertenece la carpeta, 1 por defecto)
    GEPP_GUION_FALSO   ruta a un guion JSON: usa el detector falso (demostración sin modelo)
    GEPP_AVISO_CANAL + GEPP_AVISO_DESTINATARIO: si están, cada hallazgo escribe su aviso

El detector real (RF-DETR u ONNX) llega con PT-08; hasta entonces solo existe el falso.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gepp_worker.cola import ColaTrabajos

VARIABLES_OBLIGATORIAS = ("GEPP_BD_URL", "GEPP_REDIS_URL", "GEPP_CARPETA_VIGILADA")


def _cola() -> ColaTrabajos:
    import redis

    from gepp_worker.cola import ColaTrabajos

    return ColaTrabajos(redis.Redis.from_url(os.environ["GEPP_REDIS_URL"]))


def _detenible() -> mp.synchronize.Event:
    parar = mp.Event()
    signal.signal(signal.SIGTERM, lambda *_: parar.set())
    signal.signal(signal.SIGINT, lambda *_: parar.set())
    return parar


def correr_vigilante() -> None:
    from gepp_worker.vigilante import Vigilante

    parar = _detenible()
    vigilante = Vigilante(
        os.environ["GEPP_CARPETA_VIGILADA"], _cola(), int(os.environ.get("GEPP_FUENTE_ID", "1"))
    )
    print(f"[vigilante] sondeando {vigilante.carpeta}", flush=True)
    vigilante.correr(seguir=lambda: not parar.is_set())


def correr_trabajador() -> None:
    from gepp_bd.sesion import crear_motor
    from gepp_vision.detectores import DetectorFalso, Guion

    from gepp_worker.muestreo import fps_objetivo_configurado
    from gepp_worker.trabajador import Aviso, Configuracion, Trabajador

    guion = os.environ.get("GEPP_GUION_FALSO")
    if not guion:
        sys.exit("Falta GEPP_GUION_FALSO: el detector real llega con PT-08")
    guion_cargado = Guion.desde_json(Path(guion))
    canal, destino = os.environ.get("GEPP_AVISO_CANAL"), os.environ.get("GEPP_AVISO_DESTINATARIO")
    config = Configuracion(
        carpeta_evidencia=Path(os.environ.get("GEPP_CARPETA_EVIDENCIA", "/datos/evidencia")),
        fps_objetivo=fps_objetivo_configurado(),
        aviso=Aviso(canal, destino) if canal and destino else None,
    )
    parar = _detenible()
    trabajador = Trabajador(crear_motor(), _cola(), lambda: DetectorFalso(guion_cargado), config)
    print("[trabajador] esperando videos", flush=True)
    trabajador.correr(seguir=lambda: not parar.is_set())


def main() -> int:
    faltan = [v for v in VARIABLES_OBLIGATORIAS if not os.environ.get(v)]
    if faltan:
        print(f"Faltan variables de entorno: {', '.join(faltan)}", file=sys.stderr)
        return 2
    procesos = [
        mp.Process(target=correr_vigilante, name="vigilante"),
        mp.Process(target=correr_trabajador, name="trabajador"),
    ]
    for p in procesos:
        p.start()

    def reenviar(*_: object) -> None:
        # Cada hijo termina su vuelta actual al recibir SIGTERM: ningún video queda a medias
        # en la base (la transacción del resultado es todo o nada).
        for p in procesos:
            if p.is_alive():
                p.terminate()

    signal.signal(signal.SIGTERM, reenviar)
    signal.signal(signal.SIGINT, reenviar)
    for p in procesos:
        p.join()
    return max((p.exitcode or 0) for p in procesos)


if __name__ == "__main__":
    raise SystemExit(main())
