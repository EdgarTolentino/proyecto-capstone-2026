"""Aplicar y deshacer migraciones sin depender del directorio de trabajo.

`make migrar` llama a `python -m gepp_bd.migrar`. La ubicación de las migraciones se
resuelve desde el paquete, así que funciona igual desde la raíz, desde CI o desde el
trabajador.
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from gepp_bd.sesion import url_desde_entorno

DIRECTORIO_MIGRACIONES = Path(__file__).resolve().parent / "migraciones"


def configuracion(url: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(DIRECTORIO_MIGRACIONES))
    # ConfigParser interpreta '%': se escapa para que una contraseña con '%' no rompa.
    cfg.set_main_option("sqlalchemy.url", (url or url_desde_entorno()).replace("%", "%%"))
    return cfg


def subir(url: str | None = None, revision: str = "head") -> None:
    command.upgrade(configuracion(url), revision)


def bajar(url: str | None = None, revision: str = "base") -> None:
    command.downgrade(configuracion(url), revision)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    accion = args[0] if args else "subir"
    if accion == "subir":
        subir()
    elif accion == "bajar":
        bajar(revision=args[1] if len(args) > 1 else "base")
    else:
        print("uso: python -m gepp_bd.migrar [subir | bajar [revision]]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
