"""`python -m gepp_api.notificaciones`: el despachador en un proceso aparte.

GEPP_BD_URL · GEPP_TELEGRAM_TOKEN · GEPP_DESPACHO_INTERVALO_S (5 por defecto)
"""

from __future__ import annotations

import os
import signal
import sys
import time
from types import FrameType

from gepp_bd.sesion import crear_motor

from gepp_api.notificaciones.despachador import Despachador
from gepp_api.notificaciones.telegram import CanalTelegram


def main() -> int:
    token = os.environ.get("GEPP_TELEGRAM_TOKEN")
    if not token:
        print("Falta GEPP_TELEGRAM_TOKEN (ver docs/operacion/alertas-telegram.md)", file=sys.stderr)
        return 2
    intervalo = float(os.environ.get("GEPP_DESPACHO_INTERVALO_S", "5"))
    despachador = Despachador(crear_motor(), CanalTelegram(token))
    seguir = True

    def detener(_: int, __: FrameType | None) -> None:
        nonlocal seguir
        seguir = False

    signal.signal(signal.SIGTERM, detener)
    signal.signal(signal.SIGINT, detener)
    print(f"[despachador] Telegram, cada {intervalo:g} s", flush=True)
    while seguir:
        r = despachador.ciclo()
        if not r.vacio:
            print(
                f"[despachador] enviados={r.avisos_enviados} resumenes={r.resumenes} "
                f"al_resumen={r.al_resumen} acusados={r.acusados} fallos={r.fallos}",
                flush=True,
            )
        time.sleep(intervalo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
