"""Hallazgos y su outbox: se escriben en la misma transacción o no se escribe ninguno."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from gepp_core import Hallazgo
from sqlalchemy.orm import Session

from gepp_bd.modelos import CANALES_NOTIFICACION, TIPOS_NOTIFICACION
from gepp_bd.modelos import Hallazgo as FilaHallazgo
from gepp_bd.modelos import Notificacion as FilaNotificacion


@dataclass(frozen=True, slots=True)
class Contexto:
    """Dónde ocurrió el hallazgo. El dominio no lo sabe; la persistencia sí."""

    fuente_id: int
    area_id: int
    video_id: int | None = None
    zona_id: int | None = None


@dataclass(frozen=True, slots=True)
class NuevaNotificacion:
    canal: str
    destinatario: str
    tipo: str = "inmediata"
    cuerpo: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.canal not in CANALES_NOTIFICACION:
            raise ValueError(f"canal inválido: {self.canal!r}")
        if self.tipo not in TIPOS_NOTIFICACION:
            raise ValueError(f"tipo de notificación inválido: {self.tipo!r}")


def guardar(
    sesion: Session,
    hallazgo: Hallazgo,
    contexto: Contexto,
    notificaciones: Sequence[NuevaNotificacion] = (),
) -> FilaHallazgo:
    """Persiste un hallazgo del agregador y, en la misma sesión, sus notificaciones.

    No confirma: si quien llama deshace la transacción, no queda ni el hallazgo ni un aviso
    huérfano en la cola del despachador.
    """
    fila = FilaHallazgo(
        video_id=contexto.video_id,
        fuente_id=contexto.fuente_id,
        area_id=contexto.area_id,
        zona_id=contexto.zona_id,
        regla_id=hallazgo.regla_id,
        regla_version=hallazgo.regla_version,
        track_id=hallazgo.track_id,
        epp_faltante=sorted(e.value for e in hallazgo.epp_faltante),
        severidad=int(hallazgo.severidad),
        ts_inicio=hallazgo.ts_inicio,
        ts_fin=hallazgo.ts_fin,
        cuadros_confirmados=hallazgo.cuadros_confirmados,
        confianza_media=hallazgo.confianza_media,
    )
    sesion.add(fila)
    sesion.flush()
    for n in notificaciones:
        sesion.add(
            FilaNotificacion(
                hallazgo_id=fila.id,
                tipo=n.tipo,
                canal=n.canal,
                destinatario=n.destinatario,
                cuerpo=n.cuerpo,
            )
        )
    sesion.flush()
    return fila
