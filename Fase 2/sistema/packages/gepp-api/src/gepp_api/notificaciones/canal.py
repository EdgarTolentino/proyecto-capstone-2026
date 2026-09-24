"""El puerto del canal. Añadir un canal es una clase nueva; nada más cambia (`03-alertas.md`)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

#: Límites del canal más restrictivo (WhatsApp), aplicados desde la v1 aunque no se use:
#: así el día que se encienda no hay que reescribir el formateador.
MAXIMO_TITULO = 60
MAXIMO_CUERPO = 1024

LEYENDA = "Indicio automatizado. Requiere validación humana."


@dataclass(frozen=True, slots=True)
class Aviso:
    titulo: str
    cuerpo: str
    #: Token de un solo uso del botón "Acuso recibo". Una URL filtrada no sirve para acusar.
    token_acuse: str

    def __post_init__(self) -> None:
        if len(self.titulo) > MAXIMO_TITULO:
            raise ValueError(f"título de {len(self.titulo)} caracteres (máximo {MAXIMO_TITULO})")
        if len(self.cuerpo) > MAXIMO_CUERPO:
            raise ValueError(f"cuerpo de {len(self.cuerpo)} caracteres (máximo {MAXIMO_CUERPO})")


class Estado(StrEnum):
    ACEPTADO = "aceptado"
    RECHAZADO_PERMANENTE = "rechazado_permanente"
    FALLO_TRANSITORIO = "fallo_transitorio"


@dataclass(frozen=True, slots=True)
class ResultadoEnvio:
    """Exactamente tres resultados posibles."""

    estado: Estado
    id_externo: str | None = None
    reintentar_en_s: float | None = None
    motivo: str | None = None


@runtime_checkable
class CanalNotificacion(Protocol):
    nombre: str

    def enviar(self, aviso: Aviso, destino: str) -> ResultadoEnvio: ...

    def acuses_recibidos(self) -> list[str]:
        """Tokens de los botones "Acuso recibo" pulsados desde la última consulta.

        Entregado NO es acusado: el acuse es un toque explícito, nunca el "leído" del canal.
        """
        ...
