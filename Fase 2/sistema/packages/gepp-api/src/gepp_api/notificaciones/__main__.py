"""`python -m gepp_api.notificaciones`: el despachador en un proceso aparte.

GEPP_BD_URL · GEPP_TELEGRAM_TOKEN · GEPP_DESPACHO_INTERVALO_S (5 por defecto)

`--reintentar-agotados`: no despacha; devuelve a `pendiente` los avisos que agotaron sus intentos,
deja constancia en `auditoria` y termina. No necesita el token.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from types import FrameType

from gepp_bd import transaccion
from gepp_bd.repositorios import auditoria
from gepp_bd.repositorios import notificaciones as repo
from gepp_bd.sesion import crear_motor
from sqlalchemy import Engine

from gepp_api.notificaciones.despachador import Despachador
from gepp_api.notificaciones.telegram import CanalTelegram


def anunciar_cambio(nombre: str, visto: str | None, actual: str | None) -> str | None:
    """Imprime en stderr solo cuando el estado cambia (error nuevo o recuperación): una caída de
    media hora no llena la terminal. Devuelve el estado a recordar."""
    if actual != visto:
        print(f"[despachador] {nombre}: {actual or 'recuperado'}", file=sys.stderr, flush=True)
    return actual


def reintentar_agotados(motor: Engine) -> int:
    """Vuelve a `pendiente` los avisos con los intentos agotados y lo registra. Devuelve cuántos."""
    with transaccion(motor) as s:
        n = repo.reintentar_agotadas(s)
        auditoria.registrar(
            s,
            rol="sistema",
            accion="aviso:reintentar_agotados",
            entidad="notificacion",
            motivo=f"{n} avisos vueltos a pendiente",
        )
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m gepp_api.notificaciones")
    parser.add_argument(
        "--reintentar-agotados",
        action="store_true",
        help="vuelve a pendiente los avisos que agotaron sus intentos y termina",
    )
    args = parser.parse_args(argv)
    if args.reintentar_agotados:
        print(f"[despachador] vueltos a pendiente: {reintentar_agotados(crear_motor())}")
        return 0
    token = os.environ.get("GEPP_TELEGRAM_TOKEN")
    if not token:
        print("Falta GEPP_TELEGRAM_TOKEN (ver docs/operacion/alertas-telegram.md)", file=sys.stderr)
        return 2
    intervalo = float(os.environ.get("GEPP_DESPACHO_INTERVALO_S", "5"))
    canal = CanalTelegram(token)
    despachador = Despachador(crear_motor(), canal)
    seguir = True

    def detener(_: int, __: FrameType | None) -> None:
        nonlocal seguir
        seguir = False

    signal.signal(signal.SIGTERM, detener)
    signal.signal(signal.SIGINT, detener)
    print(f"[despachador] Telegram, cada {intervalo:g} s", flush=True)
    error_visto: str | None = None
    bd_vista: str | None = None
    while seguir:
        r = despachador.ciclo()
        bd_vista = anunciar_cambio("base", bd_vista, r.error_bd)
        error_visto = anunciar_cambio("acuses", error_visto, canal.ultimo_error)
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
