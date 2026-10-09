"""Configuración de la API, leída del entorno una vez al arrancar."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from gepp_bd.turnos import TURNOS as _TURNOS

#: Prefijo de todas las rutas (`servers` del contrato). Las URL de evidencia lo llevan
#: completo: el cliente web resuelve `/evidencias/…` desde la raíz del servidor.
PREFIJO = "/api/v1"

AVISO_LEGAL = "Indicio automatizado. Requiere validación humana."


#: Los turnos se comparten con el trabajador: ver `gepp_bd.turnos`.
TURNOS = _TURNOS


#: Tokens cuando `GEPP_API_TOKENS` no está: el prevencionista de demostración más las cuentas
#: del equipo que siembra `perfiles/construccion.yaml`, para entrar al levantar en local sin
#: configurar. Un despliegue fuera del equipo define la variable (ver `.env.example`).
TOKENS_POR_DEFECTO = (
    "demo=prevencionista@obra.invalid,mortega=mortega@duocuc.cl,lgrandon=lgrandon@duocuc.cl"
)


def _tokens_desde_entorno() -> dict[str, str]:
    """`GEPP_API_TOKENS="token=correo,otro=correo"` reemplaza a `TOKENS_POR_DEFECTO`.

    Autenticación de DEMOSTRACIÓN, igual que el servidor simulado. La real (sesión con
    contraseña o SSO) no es de la v1.
    """
    texto = os.environ.get("GEPP_API_TOKENS", TOKENS_POR_DEFECTO)
    pares = (p.split("=", 1) for p in texto.split(",") if "=" in p)
    return {token.strip(): email.strip() for token, email in pares}


class ConfiguracionInvalida(ValueError):
    """La API no arranca con una carpeta de entrada que no sirve."""


def validar_carpeta_entrada(texto: str, vigilada: str | None = None) -> Path:
    """La carpeta de entrada existe, no está bajo `/mnt/` y no se cruza con la vigilada.

    La vigilada la procesa sola, con una sola cámara: si la de entrada fuera la misma o
    estuviera dentro, un archivo se procesaría antes de que alguien eligiera su cámara.
    Las rutas se comparan ya resueltas (enlaces y `..` incluidos).
    """
    carpeta = Path(texto).expanduser().resolve()
    if len(carpeta.parts) > 1 and carpeta.parts[1] == "mnt":
        raise ConfiguracionInvalida(
            "GEPP_CARPETA_ENTRADA está bajo /mnt/: en WSL2 los discos de Windows no son fiables"
        )
    if not carpeta.is_dir():
        raise ConfiguracionInvalida("GEPP_CARPETA_ENTRADA no existe o no es una carpeta")
    if vigilada:
        otra = Path(vigilada).expanduser().resolve()
        # `is_relative_to` incluye el caso de rutas iguales.
        if carpeta.is_relative_to(otra) or otra.is_relative_to(carpeta):
            raise ConfiguracionInvalida(
                "GEPP_CARPETA_ENTRADA no puede ser ni estar dentro de GEPP_CARPETA_VIGILADA "
                "(ni al revés): la vigilada procesa sola, con una sola cámara"
            )
    return carpeta


def _carpeta_entrada_desde_entorno() -> Path | None:
    """`GEPP_CARPETA_ENTRADA` es opcional: sin ella, las rutas de ingesta responden 409."""
    texto = os.environ.get("GEPP_CARPETA_ENTRADA", "").strip()
    if not texto:
        return None
    return validar_carpeta_entrada(texto, os.environ.get("GEPP_CARPETA_VIGILADA"))


@dataclass(frozen=True, slots=True)
class Configuracion:
    zona_horaria: ZoneInfo = field(default_factory=lambda: ZoneInfo("America/Santiago"))
    tokens: dict[str, str] = field(default_factory=_tokens_desde_entorno)
    origenes_cors: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    carpeta_entrada: Path | None = field(default_factory=_carpeta_entrada_desde_entorno)
