"""Configuración de la API, leída del entorno una vez al arrancar."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from gepp_bd.turnos import TURNOS as _TURNOS

#: Prefijo de todas las rutas (`servers` del contrato). Las URL de evidencia lo llevan
#: completo: el cliente web resuelve `/evidencias/…` desde la raíz del servidor.
PREFIJO = "/api/v1"

AVISO_LEGAL = "Indicio automatizado. Requiere validación humana."


#: Los turnos se comparten con el trabajador: ver `gepp_bd.turnos`.
TURNOS = _TURNOS


def _tokens_desde_entorno() -> dict[str, str]:
    """`GEPP_API_TOKENS="demo=prevencionista@obra.invalid,admin=administrador@obra.invalid"`.

    Autenticación de DEMOSTRACIÓN, igual que el servidor simulado. La real (sesión con
    contraseña o SSO) no es de la v1.
    """
    texto = os.environ.get("GEPP_API_TOKENS", "demo=prevencionista@obra.invalid")
    pares = (p.split("=", 1) for p in texto.split(",") if "=" in p)
    return {token.strip(): email.strip() for token, email in pares}


@dataclass(frozen=True, slots=True)
class Configuracion:
    zona_horaria: ZoneInfo = field(default_factory=lambda: ZoneInfo("America/Santiago"))
    tokens: dict[str, str] = field(default_factory=_tokens_desde_entorno)
    origenes_cors: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
